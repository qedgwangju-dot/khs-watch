#!/usr/bin/env python3
"""Render transformer tariff alerts after the generic policy guardrails."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from khs_policy_alert_explainer import ensure_explained, explanation_lines


KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")
REPORT_PATH = OUT_DIR / "khs_policy_watch.md"
ALERT_PATH = OUT_DIR / "khs_policy_watch_alert.md"
TITLE_PATH = OUT_DIR / "khs_policy_watch_alert_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"

TITLE = "미국, 대형 변압기 관세 25%→15% 인하 보도·공식근거 체크"
SECTORS = ["전력기기/변압기", "관세/수출주", "전력망/데이터센터"]


def is_transformer_alert(item: dict) -> bool:
    return bool(item.get("transformer_tariff_policy_watch")) or "transformer_tariff_policy" in (item.get("matched") or {})


def render(alerts: list[dict], now: dt.datetime) -> str:
    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    for idx, alert in enumerate(alerts, 1):
        matched_terms = sorted({term for terms in (alert.get("matched") or {}).values() for term in terms})
        matched_keys = ", ".join((alert.get("matched") or {}).keys()) or "정책/규제"
        lines.extend([
            f"## {idx}. [{alert.get('importance', '중')}·{alert.get('status', '확정')}] {str(alert.get('title') or '').strip()}",
            f"- 상태 변화: {matched_keys} 신호 확인 ({', '.join(matched_terms[:8])})",
            f"- 원문/출처: [{alert.get('source', 'source')}]({alert.get('link', '')}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
            *explanation_lines(alert),
            *([f"- 변압기 관세 체크: {alert.get('transformer_tariff_check')}"] if alert.get("transformer_tariff_check") else []),
            *([f"- 체크할 리스크: {alert.get('transformer_tariff_risk_table')}"] if alert.get("transformer_tariff_risk_table") else []),
            *([f"- 구조 변화: {alert.get('transformer_tariff_structure_note')}"] if alert.get("transformer_tariff_structure_note") else []),
            "- 즉시 체크: 품목코드, 시행일, 원산지 요건, 한국 전력기기 밸류체인 노출, 관련 해외 티커·ETF 반응",
            "",
        ])
    lines.extend([
        "💡 워치 판단: 이번 실행은 변압기 관세율과 미국 전력망 투자 수혜 기대가 돈 버는 능력·수급·시간표를 바꿀 수 있는지 우선 감지했습니다.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    if not ALERTS_JSON_PATH.exists():
        return 0
    try:
        alerts = json.loads(ALERTS_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(alerts, list) or not any(is_transformer_alert(item) for item in alerts):
        return 0

    for item in alerts:
        if is_transformer_alert(item):
            item["title"] = TITLE
            item["sectors"] = SECTORS[:]
            ensure_explained(item)

    now = dt.datetime.now(tz=KST)
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = render(alerts, now)
    REPORT_PATH.write_text(report, encoding="utf-8")
    ALERT_PATH.write_text(report, encoding="utf-8")
    TITLE_PATH.write_text(f"KHS 정책 워치: [상] {TITLE}\n", encoding="utf-8")
    print("transformer_tariff_postprocess=rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
