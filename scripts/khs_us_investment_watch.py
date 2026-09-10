#!/usr/bin/env python3
from __future__ import annotations

import html
import importlib.util
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

    # WSJ 재전달 제목은 숫자를 생략하고 '1호 대미투자 합의 근접·원전 발표'만 남기는 경우가 있다.
    wsj_relay_signal = (
        "wsj" in low
        and ("원전" in norm or "nuclear" in low)
        and any(token in norm for token in ["합의근접", "합의임박", "1호대미투자", "대미투자1호", "내주", "발표"])
    )

    korea_signal = any(
        token in norm
        for token in ["대미투자", "한국", "한미전략투자"]
    ) or "korea" in low or "south korea" in low
    return (package_signal or wsj_relay_signal) and korea_signal


def _semantic_key(row: dict) -> str:
    if _is_energy_package_row(row):
        return "energy_package_official" if core._is_official(row) else "energy_package_media"
    return _ORIG_SEMANTIC_KEY(row)


def _run_event_key(row: dict) -> str:
    if _is_energy_package_row(row):
        return "energy_package_official" if core._is_official(row) else "energy_package_media"
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


def _is_official_record(record: dict) -> bool:
    return core._is_official({"title": record["title_plain"], "source": record["source_plain"]})


def _official_progress_lines(records: list[dict]) -> list[str]:
    official = [r for r in records if _is_official_record(r)]
    if not official:
        return [
            "• 언론의 <b>합의 근접</b>과 정부의 <b>공식 확정</b>을 분리합니다.",
            "• 공식 선정·투자금·노형·송금이 확인되기 전에는 확정 단계로 올리지 않습니다.",
        ]

    blob = " ".join(r["title_plain"] for r in official).lower()
    if any(x in blob for x in ["확정된 바 없습니다", "미확정", "협의 중", "사실이 아닙니다"]):
        return [
            "• 🏛 <b>정부 공식자료 동시 확인:</b> 구체 투자처·발표시점·첫 송금 규모·시기·원전 협력 사항은 공식 확정 전입니다.",
            "• 수익배분 구조 역시 정부가 <b>한미 협의 중·미확정</b>이라고 밝힌 상태를 우선합니다.",
        ]
    if any(x in blob for x in ["확정", "선정", "의결", "승인", "발표"]):
        return [
            "• 🏛 <b>정부 공식 단계 상승 감지:</b> 언론 보도보다 공식 발표 내용을 우선해 사업·금액·노형·송금 상태를 갱신합니다."
        ]
    return ["• 🏛 <b>정부 공식자료 동시 감지:</b> 공식 원문을 우선해 확정·미확정 상태를 판정합니다."]


def _compact_related(records: list[dict]) -> list[str]:
    related = []
    for r in records:
        if _is_official_record(r):
            continue
        if "대미투자 첫사업/에너지패키지" in r["tags_plain"]:
            continue
        if _is_energy_package_row({"title": r["title_plain"], "source": r["source_plain"]}):
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
        '<a href="https://www.korea.kr/briefing/actuallyView.do?newsId=148971518">산업통상부 9월 9일 공식 설명자료</a>',
        '<a href="https://admin.korea.kr/briefing/actuallyView.do?newsId=148971618">산업통상부 9월 10일 수익배분 공식 설명자료</a>',
    ]

    relay_names = []
    for r in records:
        if _is_official_record(r):
            continue
        if not _is_energy_package_row({"title": r["title_plain"], "source": r["source_plain"]}):
            continue
        name = r["source_plain"].strip()
        if name and name not in relay_names and name.lower() not in {"wsj", "wall street journal", "reuters"}:
            relay_names.append(name)
    if relay_names:
        lines.append("국내 재전달: " + " · ".join(html.escape(x) for x in relay_names[:3]) + " <b>(동일 WSJ 사건으로 묶음·중계링크 생략)</b>")
    return lines


def _reorder_energy_package_alert(text: str) -> str:
    records = _article_records(text)
    energy_records = [
        r for r in records
        if "대미투자 첫사업/에너지패키지" in r["tags_plain"]
        or _is_energy_package_row({"title": r["title_plain"], "source": r["source_plain"]})
    ]
    if not energy_records:
        return text

    last_line = next((line for line in reversed(text.splitlines()) if line.startswith("조회 ")), "")
    related_block = _compact_related(records)

    parts = [
        "<b>🇺🇸 대미투자 첫사업·에너지 패키지 | WSJ 합의 근접·정부 미확정</b>",
        "",
        "<b>① 무엇이 바뀌었나</b>",
        "• WSJ가 한국의 미국 에너지 투자 패키지가 <b>합의에 근접</b>했다고 보도했습니다.",
        "• 후보 범위는 <b>텍사스 가스발전 + 대형원전 최대 8기</b>이며, 동일 WSJ 원보도를 재전달한 국내 기사는 <b>한 사건으로 묶어</b> 표시합니다.",
        "",
        "<b>② 현재 공식상태</b>",
    ]
    parts += _official_progress_lines(records)
    parts += [
        "",
        "<b>③ 핵심 숫자</b>",
        "• WSJ 에너지 패키지 보도: <b>1,000억달러 초과 ≈ 134조2,040억원 초과</b>",
        "• 원전: <b>최대 8기</b> · 노형·기수·발주주체는 공식 확정 전",
        "• WSJ 이달 초기 집행 가능성 보도: <b>20억달러 초과 ≈ 2조6,841억원 초과</b>",
        "• MOU상 전략투자 납입 한도: <b>총 2,000억달러 / 연 200억달러</b>",
        "",
        "<b>④ 사업별 기준선</b>",
        "🔥 엔시날 가스복합발전 · 6.3GW",
        "• Reuters·주요 보도 기준 <b>223억달러 ≈ 29조9,275억원</b>",
        "• 산업통상부 9월 9일 설명자료가 인용한 한겨레 보도에는 <b>233억달러 ≈ 31조2,695억원</b>으로 표기 → <b>10억달러 차이</b> 별도 확인",
        "• 정부는 구체 투자처·금액 자체를 아직 공식 확정하지 않았습니다.",
        "⚛️ 미국 대형원전 · 최대 8기 · 기존 보도상 <b>1,200억달러 ≈ 161조448억원</b>",
        "🧊 알래스카 LNG · 한국 협상 보도 기준 <b>670억달러 ≈ 89조9,167억원</b>",
        "📦 223억달러 기준 세 후보사업 단순합 · <b>2,093억달러 ≈ 280조8,890억원</b>",
        "",
        "<b>⑤ 꼭 구분할 숫자</b>",
        "• <b>총사업비 ≠ 한국 정부 실제 송금액 ≠ 한국 기업 수주액</b>",
        "• 1,000억달러 초과는 WSJ의 패키지 하한 표현이며 원전 8기+엔시날의 확정 합계가 아닙니다.",
        "• 첫 자금 전액이 엔시날로 들어간다는 의미도 아닙니다.",
        "• 한국 투자지분·미국 측 자금·민간자금·프로젝트파이낸싱·보증을 분리 확인합니다.",
        "",
    ]

    if "🛡️ 대미투자 안전판·원금회수 기준선" in text:
        parts += [
            "<b>🛡️ 2025-11-14 MOU 원금회수 기준선</b>",
            "• 원 MOU는 상위 투자 SPV가 프로젝트 수익을 모아 한국 원금+이자를 상환하는 <b>리스크 풀링</b> 구조입니다.",
            "• 원리금 상환 전 수익배분 <b>한·미 5:5</b> → 상환 후 <b>한국 1 : 미국 9</b>",
            "• <b>20년 내 전체 원리금 상환이 어렵다고 예상되면 수익배분 비율 조정 가능</b>",
            "• 상환이자: 미국 국채 20년물 고정금리 + 가산금리",
            "• 단, <b>2026-09-10 현재 수익배분 구조의 실제 적용 방식은 한미 협의 중·미확정</b>이라는 정부 설명을 우선합니다.",
            "",
        ]
    if "⏱️ 45영업일·조기송금 적용 검증 기준선" in text:
        parts += core._funding_guard_block() + [""]
    if "⚡ 텍사스 AI 현장발전·계통연계 기준선" in text:
        parts += core._texas_ai_power_block() + [""]
    if "🧊 알래스카 LNG 실질 진전 기준선" in text:
        parts += core._alaska_lng_block() + [""]

    parts += related_block
    parts += [
        "<b>⑥ 다음 확인</b>" if not related_block else "<b>⑦ 다음 확인</b>",
        "1) 정부 공식 첫 사업 선정  2) 투자금·지분·수익배분  3) 원전 부지·노형·기수  4) 실제 첫 자금요청·송금",
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
    if core.ALERT.exists():
        original = core.ALERT.read_text(encoding="utf-8")
        reordered = _reorder_energy_package_alert(original)
        if reordered != original:
            core.ALERT.write_text(reordered, encoding="utf-8")
            print("alert_reordered=true")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
