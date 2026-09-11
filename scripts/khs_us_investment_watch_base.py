#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE_PATH = HERE / "khs_us_investment_watch_core.py"

spec = importlib.util.spec_from_file_location("khs_us_investment_watch_core", CORE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"core module load failed: {CORE_PATH}")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

_ORIG_SEMANTIC_KEY = core._semantic_key
_ORIG_RUN_EVENT_KEY = core._run_event_key


def _normalized_title(value: str) -> str:
    low = html.unescape(value or "").lower()
    low = low.replace("韓", "한국")
    return re.sub(r"[\s'\"“”‘’·,:;()\[\]{}<>_\-/]+", "", low)


def _is_korean_gov_row(row: dict) -> bool:
    blob = f"{row.get('title', '')} {row.get('source', '')}".lower()
    return any(
        token in blob
        for token in ["정책브리핑", "대한민국 정책브리핑", "산업통상부", "산업통상", "재정경제부", "기획재정부"]
    )


def _is_energy_package_row(row: dict) -> bool:
    raw = f"{row.get('title', '')} {row.get('source', '')}"
    low = raw.lower()
    norm = _normalized_title(raw)

    package_signal = any(
        token in low
        for token in [
            "100 billion",
            "eight nuclear",
            "first project",
            "agreement near",
            "nears agreement",
        ]
    ) or any(
        token in norm
        for token in [
            "1천억달러",
            "1000억달러",
            "원전8기",
            "8기원전",
            "첫사업",
            "1호대미투자",
            "대미투자1호",
            "합의임박",
            "합의근접",
            "내주원전",
            "원전등발표",
        ]
    )

    wsj_relay_signal = (
        "wsj" in low
        and ("원전" in norm or "nuclear" in low)
        and any(
            token in norm
            for token in ["합의근접", "합의임박", "1호대미투자", "대미투자1호", "내주", "발표"]
        )
    )

    official_package_signal = (
        _is_korean_gov_row(row)
        and "대미투자" in norm
        and any(
            token in norm
            for token in [
                "첫투자금",
                "첫송금",
                "원전투자",
                "원전협력",
                "투자프로젝트",
                "투자처",
            ]
        )
    )

    korea_signal = any(
        token in norm
        for token in ["대미투자", "한국", "한미전략투자"]
    ) or "korea" in low or "south korea" in low

    return (package_signal or wsj_relay_signal or official_package_signal) and korea_signal


def _semantic_key(row: dict) -> str:
    if _is_energy_package_row(row):
        return "energy_package_official" if _is_korean_gov_row(row) else "energy_package_media"
    return _ORIG_SEMANTIC_KEY(row)


def _run_event_key(row: dict) -> str:
    if _is_energy_package_row(row):
        return "energy_package_official" if _is_korean_gov_row(row) else "energy_package_media"
    return _ORIG_RUN_EVENT_KEY(row)


core._semantic_key = _semantic_key
core._run_event_key = _run_event_key


_ARTICLE_RE = re.compile(
    r'<b>\d+\. (?P<title>.*?)</b>\n'
    r'• 🟧 <b>구분: (?P<tags>.*?)</b>\n'
    r'• 의미: (?P<meaning>.*?)\n'
    r'• 출처: <a href="(?P<link>[^"]+)">(?P<source>.*?)</a>',
    re.S,
)


def _article_records(text: str) -> list[dict]:
    records = []
    for match in _ARTICLE_RE.finditer(text):
        item = match.groupdict()
        item["title_plain"] = html.unescape(re.sub(r"<[^>]+>", "", item["title"]))
        item["tags_plain"] = html.unescape(re.sub(r"<[^>]+>", "", item["tags"]))
        item["source_plain"] = html.unescape(re.sub(r"<[^>]+>", "", item["source"]))
        records.append(item)
    return records


def _is_korean_gov_record(record: dict) -> bool:
    return _is_korean_gov_row(
        {"title": record["title_plain"], "source": record["source_plain"]}
    )


def _parse_official_status_from_records(records: list[dict]) -> dict | None:
    gov_records = [r for r in records if _is_korean_gov_record(r)]
    if not gov_records:
        return None

    for r in gov_records:
        title = r["title_plain"]
        low = title.lower()
        if any(
            token in low
            for token in ["확정된 바 없습니다", "미확정", "협의 중", "사실이 아닙니다", "결정된 바 없습니다"]
        ):
            return {
                "status": "unconfirmed",
                "title": title,
                "source": r["source_plain"],
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }

    for r in gov_records:
        title = r["title_plain"]
        low = title.lower()
        if any(token in low for token in ["공식 확정", "최종 확정", "선정", "의결", "승인", "체결"]):
            return {
                "status": "confirmed",
                "title": title,
                "source": r["source_plain"],
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }

    return {
        "status": "official_seen",
        "title": gov_records[0]["title_plain"],
        "source": gov_records[0]["source_plain"],
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def _read_state_dict(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _persist_official_status(records: list[dict]) -> dict:
    fresh = _parse_official_status_from_records(records)
    state_path = core.PENDING if core.PENDING.exists() else core.STATE
    state = _read_state_dict(state_path)

    if fresh:
        state["official_status"] = fresh
        if core.PENDING.exists():
            core.PENDING.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return fresh

    stored = state.get("official_status") or {}
    if stored:
        return stored

    return {
        "status": "unconfirmed",
        "title": "대미투자 수익배분 구조 및 첫 투자금·원전 관련 구체사항은 미확정",
        "source": "산업통상부·재정경제부",
        "updated_at": "2026-09-10T00:00:00+09:00",
    }


def _official_progress_lines(status: dict) -> list[str]:
    state = status.get("status")
    if state == "unconfirmed":
        return [
            "• 🏛 <b>최신 정부 공식상태: 미확정</b>",
            "• 산업통상부·재정경제부는 첫 투자금 규모·시기, 원전 협력의 구체사항, 수익배분 구조가 <b>한미 협의 중이며 아직 확정되지 않았다</b>고 밝혔습니다.",
            "• 따라서 언론의 <b>합의 근접·합의 임박</b>과 정부의 <b>공식 확정</b>을 별도 단계로 관리합니다.",
        ]
    if state == "confirmed":
        return [
            "• 🏛 <b>정부 공식 단계 상승 감지</b>",
            f"• 최신 공식 제목: {html.escape(str(status.get('title') or '공식 확정'))}",
            "• 이후에는 언론 선행보도보다 해당 정부 공식문서를 우선해 사업·금액·노형·송금 상태를 갱신합니다.",
        ]
    if state == "official_seen":
        return [
            "• 🏛 <b>정부 공식자료 신규 감지</b>",
            f"• 최신 공식 제목: {html.escape(str(status.get('title') or '공식자료'))}",
            "• 확정·미확정 문구를 원문 기준으로 판정하고 언론 보도와 분리합니다.",
        ]
    return [
        "• 언론의 합의 진전과 정부 공식 확정을 분리합니다.",
        "• 정부 공식문서가 확인되기 전에는 확정 단계로 올리지 않습니다.",
    ]


def _official_status_label(status: dict) -> str:
    if status.get("status") == "unconfirmed":
        return "정부 미확정"
    if status.get("status") == "confirmed":
        return "정부 공식단계 상승"
    return "공식확정 분리"


def _compact_related(records: list[dict]) -> list[str]:
    related = []
    for r in records:
        if _is_korean_gov_record(r):
            continue
        if "대미투자 첫사업/에너지패키지" in r["tags_plain"]:
            continue
        if _is_energy_package_row(
            {"title": r["title_plain"], "source": r["source_plain"]}
        ):
            continue
        related.append(r)

    if not related:
        return []

    out = ["<b>⑥ 관련 신규 변화</b>"]
    for r in related[:3]:
        out += [
            f"• <b>{html.escape(r['title_plain'])}</b>",
            f"  └ {html.escape(r['tags_plain'])} · <a href=\"{html.escape(r['link'], quote=True)}\">{html.escape(r['source_plain'])}</a>",
        ]
    out.append("")
    return out


def _source_lines(records: list[dict]) -> list[str]:
    lines = [
        "<b>⑦ 출처</b>",
        '<a href="https://www.wsj.com/world/asia/south-korea-nears-agreement-on-billions-in-u-s-investments-a-win-for-trump-2b58dc4a">WSJ 원문</a>',
        '<a href="https://www.reuters.com/world/asia-pacific/south-korea-nears-agreement-worth-over-100-billion-us-investments-wsj-reports-2026-09-10/">Reuters 교차검증</a>',
        '<a href="https://www.korea.kr/briefing/actuallyView.do?newsId=148971518&pWise=sub&pWiseMain=F1">산업통상부 9월 9일 공식 설명자료</a>',
        '<a href="https://www.korea.kr/briefing/actuallyView.do?newsId=148971618&pWise=sub&pWiseMain=F1">산업통상부 9월 10일 수익배분 공식 설명자료</a>',
        '<a href="https://www.korea.kr/news/policyNewsView.do?newsId=148954760&pWise=main&pWiseMain=L4">2025-11-14 한미 전략적 투자 MOU 공식 설명</a>',
    ]

    relay_names = []
    for r in records:
        if _is_korean_gov_record(r):
            continue
        if not _is_energy_package_row(
            {"title": r["title_plain"], "source": r["source_plain"]}
        ):
            continue
        name = r["source_plain"].strip()
        if (
            name
            and name not in relay_names
            and name.lower() not in {"wsj", "wall street journal", "reuters"}
        ):
            relay_names.append(name)

    if relay_names:
        lines.append(
            "국내 재전달: "
            + " · ".join(html.escape(x) for x in relay_names[:3])
            + " <b>(동일 WSJ 사건으로 묶음·중계링크 생략)</b>"
        )
    return lines


def _normalize_common_accuracy(text: str) -> str:
    text = text.replace(
        "• 6.3GW · 보도 범위 <b>220억~223억달러 ≈ 29조5,249억~29조9,275억원</b>\n"
        "└ 223억달러 기준 GW당 <b>35.40억달러 ≈ 4조7,509억원</b>",
        "• 6.3GW · Reuters·이데일리 등 보도 기준 <b>223억달러 ≈ 29조9,275억원</b>\n"
        "• 산업통상부 9월 9일 설명자료가 인용한 한겨레 보도에는 <b>233억달러 ≈ 31조2,695억원</b>으로 기재\n"
        "• <b>223억달러 ↔ 233억달러는 언론 보도 간 불일치이며 정부 확정액이 아님</b>\n"
        "└ GW당 단순환산: 223억달러 기준 <b>35.40억달러 ≈ 4조7,504억원</b> / 233억달러 기준 <b>36.98억달러 ≈ 4조9,634억원</b>"
    )
    text = text.replace(
        "<b>📦 3개 프로젝트 보도상 총사업비 단순합</b>\n"
        "• 223억달러+1,200억달러+670억달러 = <b>2,093억달러 ≈ 280조8,890억원</b>",
        "<b>📦 3개 프로젝트 보도상 총사업비 단순합</b>\n"
        "• 엔시날 223억달러 기준: <b>2,093억달러 ≈ 280조8,890억원</b>\n"
        "• 엔시날 233억달러 기준: <b>2,103억달러 ≈ 282조2,310억원</b>\n"
        "• 두 값 모두 <b>언론 보도 단순합이며 한국 실제 투자액이 아님</b>"
    )
    text = text.replace(
        "• 2,093억달러는 후보사업 총사업비 단순합이며 <b>한국 실제 투자액·한도 초과를 뜻하지 않음</b>",
        "• 2,093억~2,103억달러는 엔시날 보도값 차이를 반영한 후보사업 단순합이며 <b>한국 실제 투자액·한도 초과를 뜻하지 않음</b>"
    )
    text = text.replace(
        "6.3GW·220억~223억달러 검토안의 정부 확정 여부와 한국 실제 투자부담이 핵심입니다.",
        "6.3GW 엔시날은 223억달러 보도와 233억달러 보도가 엇갈리며 정부 확정액은 아직 없습니다. 실제 한국 투자부담과 본계약 금액을 분리 확인해야 합니다."
    )
    text = text.replace(
        "<b>🛡️ 대미투자 안전판·원금회수 기준선</b>",
        "<b>🛡️ 2025-11-14 MOU 원금회수 기준선</b>"
    )
    text = text.replace(
        "<b>한국 원금+이자를 상환하는 risk-pooling 구조</b>",
        "<b>한국 원금+이자를 상환하는 리스크 풀링(risk-pooling) 구조</b>"
    )
    return text


def _reorder_energy_package_alert(text: str, official_status: dict) -> str:
    records = _article_records(text)
    energy_records = [
        r
        for r in records
        if "대미투자 첫사업/에너지패키지" in r["tags_plain"]
        or _is_energy_package_row(
            {"title": r["title_plain"], "source": r["source_plain"]}
        )
    ]
    if not energy_records:
        return _normalize_common_accuracy(text)

    last_line = next(
        (line for line in reversed(text.splitlines()) if line.startswith("조회 ")),
        "",
    )
    related_block = _compact_related(records)

    parts = [
        f"<b>🇺🇸 대미투자 첫사업·에너지 패키지 | WSJ 합의 근접·{_official_status_label(official_status)}</b>",
        "",
        "<b>① 무엇이 바뀌었나</b>",
        "• WSJ는 한국의 미국 에너지 투자 패키지가 <b>합의에 근접</b>했다고 보도했습니다.",
        "• 후보 범위는 <b>텍사스 가스발전 + 대형원전 최대 8기</b>입니다.",
        "• 동일 WSJ 원보도를 재전달한 국내 기사는 <b>새 사건으로 중복 집계하지 않고 한 사건으로 묶습니다.</b>",
        "",
        "<b>② 현재 공식상태</b>",
    ]
    parts += _official_progress_lines(official_status)
    parts += [
        "",
        "<b>③ 핵심 숫자</b>",
        "• WSJ 에너지 패키지 보도: <b>1,000억달러 초과 ≈ 134조2,040억원 초과</b>",
        "• 원전: <b>최대 8기</b> · 노형·기수·발주주체는 공식 확정 전",
        "• WSJ 이달 초기 집행 가능성 보도: <b>20억달러 초과 ≈ 2조6,841억원 초과</b>",
        "• 2025-11-14 MOU상 전략투자: <b>총 2,000억달러 / 연간 납입 최대 200억달러</b>",
        "",
        "<b>④ 사업별 기준선</b>",
        "🔥 엔시날 가스복합발전 · 6.3GW",
        "• Reuters·이데일리 등 보도 기준 <b>223억달러 ≈ 29조9,275억원</b>",
        "• 산업통상부 9월 9일 설명자료가 인용한 한겨레 보도에는 <b>233억달러 ≈ 31조2,695억원</b>",
        "• <b>10억달러 차이는 언론 보도 간 불일치이며 정부는 구체 투자금액을 공식 확정하지 않았습니다.</b>",
        "• GW당 단순환산: 223억달러 기준 <b>35.40억달러 ≈ 4조7,504억원</b> / 233억달러 기준 <b>36.98억달러 ≈ 4조9,634억원</b>",
        "⚛️ 미국 대형원전 · 최대 8기 · 기존 보도상 <b>1,200억달러 ≈ 161조448억원</b>",
        "🧊 알래스카 LNG · 한국 협상 보도 기준 <b>670억달러 ≈ 89조9,167억원</b>",
        "📦 세 후보사업 단순합 · 엔시날 223억달러 기준 <b>2,093억달러 ≈ 280조8,890억원</b> / 233억달러 기준 <b>2,103억달러 ≈ 282조2,310억원</b>",
        "",
        "<b>⑤ 꼭 구분할 숫자</b>",
        "• <b>총사업비 ≠ 한국 정부 실제 송금액 ≠ 한국 기업 수주액</b>",
        "• 1,000억달러 초과는 WSJ의 패키지 하한 표현이며 원전 8기+엔시날의 확정 합계가 아닙니다.",
        "• 첫 자금 전액이 엔시날로 들어간다는 의미도 아닙니다.",
        "• 한국 투자지분·미국 측 자금·민간자금·프로젝트파이낸싱·보증을 분리 확인합니다.",
        "",
    ]

    if "🛡️ 대미투자 안전판·원금회수 기준선" in text or "🛡️ 2025-11-14 MOU 원금회수 기준선" in text:
        parts += [
            "<b>🛡️ 2025-11-14 MOU 원금회수 기준선</b>",
            "• 공식 MOU 설명 기준, 투자 SPV는 개별 프로젝트 SPV의 수익을 모아 한국의 원금과 이자를 상환하는 <b>리스크 풀링</b> 구조입니다.",
            "• 원리금 상환 전 수익배분 <b>한·미 5:5</b> → 상환 후 <b>한국 1 : 미국 9</b>",
            "• <b>20년 내 전체 원리금 상환이 어렵다고 예상되면 수익배분 비율 조정 가능</b>",
            "• 상환이자: 미국 국채 20년물 고정금리 + 가산금리",
            "• 단, <b>2026-09-10 현재 실제 수익배분 구조는 한미 협의 중·미확정</b>이라는 산업통상부·재정경제부 설명을 우선합니다.",
            "",
        ]

    if "⏱️ 45영업일·조기송금 적용 검증 기준선" in text:
        parts += [
            "<b>⏱️ 45영업일·조기송금 적용 검증 기준선</b>",
            "• 2025-11-14 공식 MOU 설명: 사업자금은 미국의 투자처 선정 통지를 받은 날로부터 <b>최소 45영업일이 경과한 날</b> 납입합니다.",
            "• 전략투자 2,000억달러는 <b>연간 최대 200억달러</b>, 사업 진척도에 따른 <b>자금요청(capital call)</b> 방식입니다.",
            "• 외환시장 불안 우려 시 한국은 납입 시기·규모 조정을 요구할 수 있습니다.",
            "• WSJ의 이달 20억달러 초과 초기 집행 보도는 <b>실제 선정 통지일·별도 합의·운영해석</b>을 확인하기 전 확정 송금으로 저장하지 않습니다.",
            "",
        ]

    if "⚡ 텍사스 AI 현장발전·계통연계 기준선" in text:
        parts += core._texas_ai_power_block() + [""]
    if "🧊 알래스카 LNG 실질 진전 기준선" in text:
        parts += core._alaska_lng_block() + [""]

    parts += related_block
    parts += [
        "<b>⑥ 다음 확인</b>" if not related_block else "<b>⑦ 다음 확인</b>",
        "1) 정부 공식 첫 사업 선정  2) 투자금·지분·수익배분  3) 원전 부지·노형·기수  4) 실제 선정 통지일  5) 첫 자금요청·송금",
        "",
    ]

    source_heading = "⑦" if not related_block else "⑧"
    source_lines = _source_lines(records)
    source_lines[0] = f"<b>{source_heading} 출처</b>"
    parts += source_lines
    parts += [
        "",
        "원화 환산 검산 기준: 1달러=1,342.04원 · 2026-09-10 17:26 KST 기준값",
    ]
    if last_line:
        parts.append(last_line)

    return "\n".join(parts) + "\n"


def main() -> int:
    result = core.main()
    if not core.ALERT.exists():
        return result

    original = core.ALERT.read_text(encoding="utf-8")
    records = _article_records(original)
    official_status = _persist_official_status(records)
    corrected = _reorder_energy_package_alert(original, official_status)
    corrected = _normalize_common_accuracy(corrected)

    if corrected != original:
        core.ALERT.write_text(corrected, encoding="utf-8")
        print("alert_reordered_and_accuracy_normalized=true")

    return result


if __name__ == "__main__":
    raise SystemExit(main())
