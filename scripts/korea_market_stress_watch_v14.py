#!/usr/bin/env python3
from __future__ import annotations

import html
import re

import korea_market_stress_watch_v13 as v13

watch = v13.watch
v12 = v13.v12

FX_TODAY_SOURCE = "https://nwww.newsis.com/view/NISI20260917_0021440924"
SHIP_TODAY_SOURCE = "https://search.newspim.com/news/view/20260917000373"

SHIPBUILDING = [
    ("HD현대중공업", "329180"),
    ("삼성중공업", "010140"),
    ("HD한국조선해양", "009540"),
    ("한화오션", "042660"),
]

DEFENSE = [
    ("한화에어로스페이스", "012450"),
    ("현대로템", "064350"),
    ("LIG넥스원", "079550"),
    ("한국항공우주", "047810"),
]


def _quote_line(name: str, code: str) -> str:
    try:
        q = v12.v11.fetch_stock_quote(code)
        actual = str(q.get("name") or name)
        return f"• {html.escape(actual)}: <b>{q['price']:,.0f}원 ({q['change_pct']:+.2f}%)</b>"
    except Exception:
        return f"• {html.escape(name)}: 당일 시세 확인 실패"


def _append_industrial_fx_rebound() -> None:
    if not watch.ALERT_PATH.exists():
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
    try:
        direction = v12._fx_direction(text)
    except Exception:
        direction = None
    if direction != "up" or "<b>환율 반등 → 수출형 산업재 반응</b>" in text:
        return

    ship_lines = [_quote_line(n, c) for n, c in SHIPBUILDING]
    defense_lines = [_quote_line(n, c) for n, c in DEFENSE]

    additions = [
        "<b>환율 반등 → 수출형 산업재 반응</b>",
        "🔺 <b>원/달러 상승 = 원화 약세 전환 → 조선·방산 등 수출형 산업재 투자심리 보강 가능</b>",
        "• 작동 경로: 달러·유로 등 외화 수주/매출의 원화 환산 부담 완화 → 환율 역풍 완화 → 실적 기대와 밸류에이션 심리 회복",
        "• 오늘 확인: 2026-09-17 오전 9시 원/달러 <b>1,378.5원</b>",
        "",
        "<b>조선 현재 반응</b>",
        *ship_lines,
        "• 오전 10시 5분 확인 사례: HD현대중공업 +5.68% · 삼성중공업 +4.46% · HD한국조선해양 +3.76% · 한화오션 +2.09%",
        "  ↳ 다만 이날 조선주 반등에는 환율뿐 아니라 낙폭 과대, 수주잔고, 실적 개선 기대도 함께 작용",
        "",
        "<b>방산 현재 반응</b>",
        *defense_lines,
        "• 구조: 해외 방산 계약은 외화 노출이 커 원화 약세가 원화 환산 매출·수익성 기대에 우호적으로 작용할 수 있음",
        "  ↳ 실제 효과는 계약 통화, 환헤지 비율, 매출 인식 시점, 현지조달·원가 구조에 따라 달라짐",
        "",
        "• 빠른 시장호흡 확인법: 환율 반등과 조선·방산 동반 상대강세가 같은 시간대에 반복되면 환 민감 심리가 강화된 것으로 판단",
        "• 실패 경로: 원/달러가 다시 1,350원 아래로 빠르게 되밀리거나 조선·방산이 환율 반등에도 약세면 환율 설명력 약화",
        "",
    ]

    lines = text.splitlines()
    insert_at = next((i for i, line in enumerate(lines) if "<b>알림 기준</b>" in line), len(lines))
    lines[insert_at:insert_at] = additions

    if "<b>원문</b>" in lines:
        src = lines.index("<b>원문</b>") + 1
        refs = [
            f'• <a href="{html.escape(FX_TODAY_SOURCE, quote=True)}">원/달러 환율 시황 확인</a>',
            f'• <a href="{html.escape(SHIP_TODAY_SOURCE, quote=True)}">조선주 당일 반등 확인</a>',
        ]
        for item in reversed(refs):
            if item not in lines:
                lines.insert(src, item)

    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _korean_news_title(title: str) -> str:
    raw = html.unescape(title).strip()
    low = raw.lower()
    if not raw or re.search(r"[가-힣]", raw):
        return raw

    company = "해외 하이퍼스케일러"
    if "meta" in low:
        company = "Meta(META)"
    elif "microsoft" in low:
        company = "Microsoft"
    elif "alphabet" in low or "google" in low:
        company = "Alphabet(Google)"
    elif "amazon" in low or "aws" in low:
        company = "Amazon(AWS)"

    pcts = re.findall(r"-?\d+(?:\.\d+)?%", raw)
    pct_text = " · ".join(pcts[:3])

    if "meta" in low and ("crash" in low or "crashing" in low) and "capex" in low:
        return f"{company}: 실적 발표 후 주가 급락 · 주당순이익 예상 하회 · 잉여현금흐름 감소 · 설비투자 가이던스 재상향" + (f" ({pct_text})" if pct_text else "")
    if any(x in low for x in ("raise", "raised", "raises", "increase", "increased", "boost")) and any(x in low for x in ("capex", "capital spending", "capital expenditure")):
        return f"{company}: 인공지능·데이터센터 설비투자 전망 상향" + (f" ({pct_text})" if pct_text else "")
    if any(x in low for x in ("cut", "cuts", "lower", "reduced", "reduce")) and any(x in low for x in ("capex", "capital spending", "capital expenditure")):
        return f"{company}: 인공지능·데이터센터 설비투자 전망 하향" + (f" ({pct_text})" if pct_text else "")
    if "global wave" in low:
        return "BofA Global Wave: 최근 공개자료에서 경기·이익수정 방향 전환 신호 감지"
    if any(x in low for x in ("capex", "capital spending", "capital expenditure", "data center", "ai infrastructure")):
        return f"{company}: 인공지능·데이터센터 설비투자 관련 신규자료" + (f" ({pct_text})" if pct_text else "")
    return "해외 영문 신규자료: 핵심 내용 한국어 검토 필요"


def _translate_english_alert_lines() -> None:
    if not watch.ALERT_PATH.exists():
        return
    lines = watch.ALERT_PATH.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        prefixes = (
            "• 하이퍼스케일러 AI 설비투자 ±10% 이상 수치 포함 신규자료: ",
            "• BofA Global Wave 방향 전환 공개자료: ",
        )
        replaced = False
        for prefix in prefixes:
            if line.startswith(prefix):
                title = line[len(prefix):]
                out.append(prefix + html.escape(_korean_news_title(title)))
                replaced = True
                break
        if not replaced:
            out.append(line)
    watch.ALERT_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    rc = v13.main()
    _append_industrial_fx_rebound()
    _translate_english_alert_lines()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
