#!/usr/bin/env python3
from __future__ import annotations

import html
import re

import korea_market_stress_watch_v13 as v13

watch = v13.watch


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
        return (
            f"{company}: 실적 발표 후 주가 급락 · 주당순이익 예상 하회 · "
            "잉여현금흐름 감소 · 설비투자 가이던스 재상향"
            + (f" ({pct_text})" if pct_text else "")
        )
    if any(x in low for x in ("raise", "raised", "raises", "increase", "increased", "boost")) and any(
        x in low for x in ("capex", "capital spending", "capital expenditure")
    ):
        return f"{company}: 인공지능·데이터센터 설비투자 전망 상향" + (f" ({pct_text})" if pct_text else "")
    if any(x in low for x in ("cut", "cuts", "lower", "reduced", "reduce")) and any(
        x in low for x in ("capex", "capital spending", "capital expenditure")
    ):
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
            "• BofA Global Wave 방향 전환 관련 신규 공개자료: ",
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
    # v12 has a legacy direct Telegram sender. Suppress it here so LS/source
    # post-processing and Korean headline translation finish before the workflow
    # sends the final artifact through the configured target bot.
    legacy_module = v13.core.v12
    original_sender = legacy_module._send_market_alert_to_target
    legacy_module._send_market_alert_to_target = lambda: None
    try:
        rc = v13.main()
    finally:
        legacy_module._send_market_alert_to_target = original_sender
    _translate_english_alert_lines()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
