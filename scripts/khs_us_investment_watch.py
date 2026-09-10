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
        ]
    ) or any(
        token in norm
        for token in [
            "1천억달러",
            "1000억달러",
            "원전8기",
            "8기원전",
            "첫사업",
            "합의임박",
        ]
    )
    korea_signal = any(
        token in norm
        for token in ["대미투자", "한국", "한미전략투자"]
    ) or "korea" in low or "south korea" in low
    return package_signal and korea_signal


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


def _source_rank(source: str) -> int:
    low = (source or "").lower()
    if "wall street journal" in low or low.strip() == "wsj":
        return 0
    if "reuters" in low:
        return 1
    if any(x in low for x in ["정책브리핑", "산업통상", "재정경제부", "기획재정부"]):
        return 2
    if "연합뉴스" in low:
        return 3
    return 4


def _official_progress_line(records: list[dict]) -> str:
    official = [r for r in records if core._is_official({"title": r["title_plain"], "source": r["source_plain"]})]
    if not official:
        return "• 언론의 <b>합의 임박</b>과 정부의 <b>공식 확정</b>을 분리합니다. 공식 선정·투자금·노형·송금이 확인되기 전에는 확정 단계로 올리지 않습니다."
    blob = " ".join(r["title_plain"] for r in official).lower()
    if any(x in blob for x in ["확정된 바 없습니다", "미확정", "협의 중", "사실이 아닙니다"]):
        return "• 🏛 <b>정부 공식자료 동시 확인:</b> 구체 투자내용은 아직 확정되지 않은 상태로 유지합니다."
    if any(x in blob for x in ["확정", "선정", "의결", "승인", "발표"]):
        return "• 🏛 <b>정부 공식 단계 상승 감지:</b> 언론 보도보다 공식 발표 내용을 우선해 사업·금액·노형·송금 상태를 갱신합니다."
    return "• 🏛 <b>정부 공식자료 동시 감지:</b> 공식 원문을 우선해 확정·미확정 상태를 판정합니다."


def _compact_related(records: list[dict]) -> list[str]:
    related = [r for r in records if "대미투자 첫사업/에너지패키지" not in r["tags_plain"]]
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
    domestic = []
    seen = set()
    for r in sorted(records, key=lambda x: _source_rank(x["source_plain"])):
        name = r["source_plain"].strip()
        if not name or name.lower() in {"wsj", "wall street journal", "reuters"}:
            continue
        key = (name, r["link"])
        if key in seen:
            continue
        seen.add(key)
        domestic.append(
            f'<a href="{html.escape(r["link"], quote=True)}">{html.escape(name)}</a>'
        )
        if len(domestic) >= 3:
            break

    lines = [
        "<b>⑦ 출처</b>",
        '<a href="https://www.wsj.com/world/asia/south-korea-nears-agreement-on-billions-in-u-s-investments-a-win-for-trump-2b58dc4a">WSJ 원문</a>',
        '<a href="https://www.reuters.com/world/asia-pacific/south-korea-nears-agreement-worth-over-100-billion-us-investments-wsj-reports-2026-09-10/">Reuters 교차검증</a>',
    ]
    if domestic:
        lines.append("국내 재전달: " + " · ".join(domestic) + " <b>(동일 사건으로 묶음)</b>")
    return lines


def _reorder_energy_package_alert(text: str) -> str:
    if "대미투자 첫사업·에너지 패키지" not in text:
        return text

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
        "<b>🇺🇸 대미투자 첫사업·에너지 패키지 | 중요 업데이트</b>",
        "",
        "<b>① 무엇이 바뀌었나</b>",
        "• WSJ가 한국의 미국 에너지 투자 패키지가 <b>합의에 근접</b>했다고 보도했습니다.",
        "• 후보 범위는 <b>텍사스 가스발전 + 대형원전 최대 8기</b>이며, 동일 WSJ 원보도를 재전달한 국내 기사는 <b>한 사건으로 묶어</b> 표시합니다.",
        "",
        "<b>② 현재 공식상태</b>",
        _official_progress_line(records),
        "",
        "<b>③ 핵심 숫자</b>",
        "• 에너지 패키지: <b>1,000억달러 초과 ≈ 134조2,040억원 초과</b>",
        "• 원전: <b>최대 8기</b> · 노형·기수·발주주체는 공식 확정 전",
        "• 이달 초기 집행 가능성 보도: <b>20억달러 초과 ≈ 2조6,841억원 초과</b>",
        "• 전략투자 실제 납입 한도: <b>총 2,000억달러 / 연 200억달러</b>",
        "",
        "<b>④ 사업별 기준선</b>",
        "🔥 엔시날 가스복합발전 · 6.3GW · <b>220억~223억달러 ≈ 29조5,249억~29조9,275억원</b>",
        "⚛️ 미국 대형원전 · 최대 8기 · 기존 보도상 <b>1,200억달러 ≈ 161조448억원</b>",
        "🧊 알래스카 LNG · 한국 협상 보도 기준 <b>670억달러 ≈ 89조9,167억원</b>",
        "📦 세 후보사업 단순합 · <b>2,093억달러 ≈ 280조8,890억원</b>",
        "",
        "<b>⑤ 꼭 구분할 숫자</b>",
        "• <b>총사업비 ≠ 한국 정부 실제 송금액 ≠ 한국 기업 수주액</b>",
        "• 1,000억달러 초과는 패키지 하한 표현이며 원전 8기+엔시날의 확정 합계가 아닙니다.",
        "• 첫 자금 전액이 엔시날로 들어간다는 의미도 아닙니다.",
        "• 한국 투자지분·미국 측 자금·민간자금·프로젝트파이낸싱·보증을 분리 확인합니다.",
        "",
    ]

    if "🛡️ 대미투자 안전판·원금회수 기준선" in text:
        parts += core._safeguard_block() + [""]
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
        "원화 환산 기준: 1달러=1,342.04원 · 2026-09-10 17:26 KST 기준값",
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
