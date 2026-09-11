#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import importlib.util
import json
import pathlib
import re
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "khs_us_investment_alert.html"
STATE = ROOT / "data" / "khs_us_investment_seen.json"
PENDING = ROOT / "out" / "khs_us_investment_pending_seen.json"
CORE_PATH = ROOT / "scripts" / "khs_us_investment_watch_core.py"
KST = ZoneInfo("Asia/Seoul")


def _load_core():
    spec = importlib.util.spec_from_file_location("khs_us_investment_watch_core_finalize", CORE_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def _load_state() -> dict:
    for path in [PENDING, STATE]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _parse_published(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        kst = parsed.astimezone(KST)
        now = dt.datetime.now(KST)
        age_min = max(0, int((now - kst).total_seconds() // 60))
        if age_min < 60:
            age = f"{age_min}분 전"
        elif age_min < 1440:
            age = f"{age_min // 60}시간 전"
        else:
            age = f"{age_min // 1440}일 전"
        return f"{kst.strftime('%m-%d %H:%M KST')} · {age}"
    except Exception:
        return ""


def _source_time(core, title: str, source: str, link: str, lookup_time: str) -> str:
    if core is not None:
        try:
            query_title = _clean(title).replace('"', " ")
            rows = core._rss(f'"{query_title}" when:7d')
            raw_link = html.unescape(link)
            exact = next((r for r in rows if str(r.get("link") or "") == raw_link), None)
            if exact is None:
                exact = next(
                    (
                        r for r in rows
                        if _clean(str(r.get("title") or "")) == _clean(title)
                        and _clean(str(r.get("source") or "")) == _clean(source)
                    ),
                    None,
                )
            if exact is not None:
                parsed = _parse_published(exact.get("published"))
                if parsed:
                    return parsed
        except Exception as exc:
            print(f"publication_time_lookup_failed={type(exc).__name__}")
    return f"{lookup_time} 조회" if lookup_time else "시각 확인 불가"


def _short_judgment(title: str, tags: str) -> str:
    blob = f"{title} {tags}".lower()
    if "두산에너빌리티" in blob or "doosan" in blob:
        return "후보 수혜 기사입니다. Encinal 직접 수주·제조사 확정은 아직 아닙니다."
    if "비에이치아이" in blob or "bhi" in blob:
        return "증권사 추정·후보 수혜입니다. HRSG 실제 공급계약은 아직 미확정입니다."
    if "송금절차" in blob or "45영업일" in blob or "송금" in blob:
        return "협의 진전 신호입니다. 실제 송금일·금액 확정으로는 아직 승격하지 않습니다."
    if "공식정정/정부입장" in blob:
        return "정부 공식상태를 우선합니다. 언론 선행보도와 확정 단계를 분리합니다."
    if "ercot" in blob or "계통연계" in blob:
        return "신청량보다 승인·전원 인가·실제 가동 단계 상승을 우선합니다."
    if "원전" in blob:
        return "부지·노형·기수·발주주체가 공식 확인될 때 수주 단계로 올립니다."
    if "알래스카 lng" in blob:
        return "SPA·FID·금융종결·한국 실제 투자액이 붙을 때만 단계 상승으로 봅니다."
    return "기사 반복이 아니라 사업 상태·금액·당사자·일정의 실제 변화를 확인합니다."


def _aggregate_flags(records: list[dict], text: str) -> dict[str, bool]:
    blob = " ".join(f"{r['title']} {r['tags']}" for r in records).lower() + " " + text.lower()
    return {
        "supply": any(x in blob for x in ["가스터빈·hrsg 공급망", "두산에너빌리티", "비에이치아이", "hrsg"]),
        "funding": any(x in blob for x in ["송금절차", "45영업일", "첫 투자금", "송금 임박", "조기송금"]),
        "energy": any(x in blob for x in ["대미투자 첫사업", "에너지 패키지", "1천억달러", "1000억달러", "원전 최대 8기"]),
        "ercot": any(x in blob for x in ["474gw", "batch zero", "ercot 신청", "계통연계"]),
        "encinal": any(x in blob for x in ["encinal", "엔시날", "6.3gw", "1.4gw", "4.9gw"]),
        "nuclear": "원전" in blob or "ap1000" in blob or "apr1400" in blob,
        "alaska": "알래스카 lng" in blob or "alaska lng" in blob,
    }


def _official_line() -> str:
    status = (_load_state().get("official_status") or {}).get("status")
    if status == "confirmed":
        return "🏛 <b>정부 공식단계 상승</b> · 최신 공식문서를 우선해 확정 상태를 갱신합니다."
    if status == "unconfirmed":
        return "🏛 <b>정부 공식상태: 미확정</b> · 첫 투자금·원전 세부·수익배분은 공식 확정 전입니다."
    return "🏛 <b>정부 공식확정 여부 별도 관리</b>"


def _key_numbers(flags: dict[str, bool], records: list[dict]) -> list[str]:
    lines: list[str] = []
    titles = " ".join(r["title"].lower() for r in records)
    if flags["supply"] or flags["encinal"]:
        lines.append("• Encinal: <b>6.3GW = 1단계 1.4GW → 후속 4.9GW</b> · 가스터빈·HRSG 제조사 미확정")
    if "두산에너빌리티" in titles:
        lines.append("• 두산 기존 미국 계약: <b>380MW급 7기</b>, 2029년 5월부터 순차 공급 · <b>Encinal 계약과 별개</b>")
    if "비에이치아이" in titles:
        lines.append("• 비에이치아이: HRSG <b>8~10기·4,000억~5,000억원</b>은 리딩투자증권 추정 · 확정 수주 아님")
    if flags["funding"]:
        lines.append("• 2025-11-14 MOU: 선정 통지 후 <b>최소 45영업일</b> · 전략투자 연간 납입 최대 <b>200억달러</b>")
    if flags["energy"]:
        lines.append("• WSJ 보도 기준: 에너지 패키지 <b>1,000억달러 초과</b> · 원전 최대 <b>8기</b> · 정부 확정 전")
    if flags["ercot"]:
        lines.append("• ERCOT <b>474GW+</b>는 계통연계 요청량 · 승인·전원 인가·실제 가동과 구분")
    return lines[:4]


def _next_checks(flags: dict[str, bool]) -> list[str]:
    checks: list[str] = []
    if flags["supply"] or flags["encinal"]:
        checks += ["제조사 실명·구매주문(PO)·실제 기수·납기", "AI 고객 실명·전력구매계약(PPA)·4.9GW 후속 승인"]
    if flags["funding"]:
        checks += ["사업 선정일·한국 통보일·자금요청(capital call)·실제 송금일/금액"]
    if flags["nuclear"]:
        checks += ["원전 부지·노형·기수·발주주체·본계약"]
    if flags["ercot"]:
        checks += ["계통연계 승인·전원 인가·실제 가동"]
    if flags["alaska"]:
        checks += ["SPA·FID·금융종결·한국 투자액"]
    out: list[str] = []
    for item in checks:
        if item not in out:
            out.append(item)
    return out[:4]


def _compact_generic(text: str, core, lookup_time: str) -> str | None:
    article_re = re.compile(
        r"(?P<title><b>\d+\.\s+.*?</b>)\n"
        r"(?P<class>• 🟧 <b>구분:\s*(?P<tags>.*?)</b>)\n"
        r"• 의미:\s*(?P<meaning>.*?)\n"
        r"• 출처:\s*<a href=\"(?P<link>[^\"]+)\">(?P<source>.*?)</a>",
        re.S,
    )
    matches = list(article_re.finditer(text))
    if not matches:
        return None

    records: list[dict] = []
    for m in matches[:5]:
        records.append({
            "title_html": m.group("title"),
            "title": _clean(m.group("title")),
            "tags_html": m.group("tags"),
            "tags": _clean(m.group("tags")),
            "link": m.group("link"),
            "source_html": m.group("source"),
            "source": _clean(m.group("source")),
        })

    flags = _aggregate_flags(records, text)
    if flags["supply"] and flags["funding"]:
        title = "🇺🇸 대미투자 | 공급망·송금 변화"
    elif flags["supply"]:
        title = "🇺🇸 대미투자 | 가스터빈·HRSG 공급망"
    elif flags["funding"]:
        title = "🇺🇸 대미투자 | 송금·45영업일"
    elif flags["energy"]:
        title = "🇺🇸 대미투자 | 첫사업·에너지 패키지"
    elif flags["ercot"]:
        title = "🇺🇸 대미투자 | 텍사스 AI 전력"
    else:
        first = text.splitlines()[0] if text.splitlines() else "🇺🇸 대미투자 | 중요 변화"
        title = _clean(first).replace(" | 중요 업데이트", "").replace(" | 최상위 중요 업데이트", "")

    parts = [f"<b>{title}</b>", "", _official_line(), "", "<b>🟧 이번 신규 변화</b>"]
    for idx, r in enumerate(records, 1):
        timestamp = _source_time(core, r["title"], r["source"], r["link"], lookup_time)
        parts += [
            f'<b>{idx}. <a href="{html.escape(r["link"], quote=True)}">{html.escape(re.sub(r"^\d+\.\s*", "", r["title"]))}</a></b>',
            f"• {html.escape(r['tags'])}",
            f"• {_short_judgment(r['title'], r['tags'])}",
            f"• {html.escape(r['source'])} · {timestamp}",
            "",
        ]

    numbers = _key_numbers(flags, records)
    if numbers:
        parts += ["<b>📌 핵심 숫자</b>"] + numbers + [""]

    checks = _next_checks(flags)
    if checks:
        parts += ["<b>다음 확인</b>"] + [f"• {html.escape(x)}" for x in checks] + [""]

    if flags["funding"] or flags["energy"]:
        parts += [
            '<b>공식 기준</b> · <a href="https://www.korea.kr/briefing/actuallyView.do?newsId=148971518&pWise=sub&pWiseMain=F1">첫 투자금·원전 미확정</a> · <a href="https://www.korea.kr/briefing/actuallyView.do?newsId=148971618&pWise=sub&pWiseMain=F1">수익배분 미확정</a>',
            "",
        ]
    if flags["supply"]:
        parts += [
            '<b>공급망 원천</b> · <a href="https://www.doosanenerbility.com/kr/about/news_board_view?id=21000800&page=0&pageSize=9">두산 미국 가스터빈 7기 공식</a>',
            "",
        ]

    if lookup_time:
        parts.append(f"조회 {lookup_time} · 새 변화만 표시 · 기준선은 내부 감시에 유지")

    return "\n".join(parts).strip() + "\n"


def _compact_energy_package(text: str, lookup_time: str) -> str | None:
    if "대미투자 첫사업·에너지 패키지" not in text:
        return None
    parts = [
        "<b>🇺🇸 대미투자 | 첫사업·에너지 패키지</b>",
        "",
        _official_line(),
        "",
        "<b>🟧 이번 변화</b>",
        "• WSJ: 한국의 미국 에너지 투자 패키지가 <b>합의에 근접</b>했다는 보도",
        "• 후보: <b>텍사스 가스발전 + 미국 대형원전 최대 8기</b>",
        "• 동일 WSJ 재전달 기사는 한 사건으로 묶고 정부 공식 확정은 별도 단계로 관리",
        "",
        "<b>📌 핵심 숫자</b>",
        "• 에너지 패키지 <b>1,000억달러 초과</b> · 원전 최대 <b>8기</b>",
        "• 초기 집행 <b>20억달러 초과</b> 가능성 보도 · 실제 송금 규모·시기는 정부 미확정",
        "• Encinal 6.3GW 사업비는 <b>223억달러 보도 ↔ 233억달러 보도</b> 불일치 · 정부 확정액 아님",
        "",
        "<b>다음 확인</b>",
        "• 정부 공식 첫 사업 선정·투자금·지분·수익배분",
        "• 원전 부지·노형·기수·발주주체",
        "• 실제 선정 통지일·자금요청·송금일/금액",
        "",
        '<b>출처</b> · <a href="https://www.wsj.com/world/asia/south-korea-nears-agreement-on-billions-in-u-s-investments-a-win-for-trump-2b58dc4a">WSJ</a> · <a href="https://www.reuters.com/world/asia-pacific/south-korea-nears-agreement-worth-over-100-billion-us-investments-wsj-reports-2026-09-10/">Reuters</a> · <a href="https://www.korea.kr/briefing/actuallyView.do?newsId=148971518&pWise=sub&pWiseMain=F1">산업통상부</a>',
    ]
    if lookup_time:
        parts += ["", f"조회 {lookup_time} · 새 변화만 표시 · 기준선은 내부 감시에 유지"]
    return "\n".join(parts).strip() + "\n"


def _visible_len(text: str) -> int:
    return len(_clean(text.replace("\n", " ")))


def main() -> int:
    if not ALERT.exists():
        print("finalize_alert=none")
        return 0

    text = ALERT.read_text(encoding="utf-8")
    footer = re.search(r"^조회\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+KST)", text, re.M)
    lookup_time = footer.group(1) if footer else dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    core = _load_core()

    compact = _compact_generic(text, core, lookup_time)
    if compact is None:
        compact = _compact_energy_package(text, lookup_time)
    if compact is None:
        # 알림 구조가 새로 생긴 경우에도 장문의 기존 기준선을 그대로 보내지 않도록 상한을 둔다.
        lines = [line for line in text.splitlines() if line.strip()]
        compact = "\n".join(lines[:28]) + "\n"

    if _visible_len(compact) > 3200:
        raise RuntimeError(f"compact alert still too long: {_visible_len(compact)}")

    ALERT.write_text(compact, encoding="utf-8")
    print(f"final_alert_compacted=true visible_chars={_visible_len(compact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
