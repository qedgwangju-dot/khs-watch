#!/usr/bin/env python3
"""Render domestic nuclear siting alerts after policy guardrails."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")
REPORT_PATH = OUT_DIR / "khs_policy_watch.md"
ALERT_PATH = OUT_DIR / "khs_policy_watch_alert.md"
TITLE_PATH = OUT_DIR / "khs_policy_watch_alert_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"
NUCLEAR_TITLE = "국내 원전 정책: 입지 선정·SMR 표준설계·대형원전 인허가 체크"
NUCLEAR_SECTORS = ["국내 원전/SMR", "원전 기자재/전력기기", "송전망/전선", "두산에너빌리티/KHNP"]
TRANSFORMER_TITLE = "미국, 대형 변압기 관세 25%→15% 인하 보도·공식근거 체크"
TRANSFORMER_SECTORS = ["전력기기/변압기", "관세/수출주", "전력망/데이터센터"]


def is_nuclear_siting(item: dict) -> bool:
    return bool(item.get("korea_nuclear_siting_policy_watch")) or "korea_nuclear_siting_policy" in (item.get("matched") or {})


def is_transformer(item: dict) -> bool:
    return bool(item.get("transformer_tariff_policy_watch")) or "transformer_tariff_policy" in (item.get("matched") or {})


def maybe_line(label: str, value: object) -> list[str]:
    return [f"- {label}: {value}"] if value else []


def render(alerts: list[dict], now: dt.datetime) -> str:
    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    for idx, alert in enumerate(alerts, 1):
        matched_terms = sorted({term for terms in (alert.get("matched") or {}).values() for term in terms})
        matched_keys = ", ".join((alert.get("matched") or {}).keys()) or "정책/규제"
        counter = alert.get("counter") or "원문 세부 조건, 시행일, 예외 조항, 개별 프로젝트 적용 여부 확인이 필요합니다."
        lines.extend([
            f"## {idx}. [{alert.get('importance', '중')}·{alert.get('status', '확정')}] {str(alert.get('title') or '').strip()}",
            f"- 상태 변화: {matched_keys} 신호 확인 ({', '.join(matched_terms[:8])})",
            f"- 원문/출처: [{alert.get('source', 'source')}]({alert.get('link', '')}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
            f"- 한국장 영향: {', '.join(alert.get('impacts') or ['의사결정 영향 제한적'])}",
            f"- 영향 경로: {', '.join(alert.get('paths') or ['정책 타임라인'])}",
            f"- 영향 섹터: {', '.join(alert.get('sectors') or ['정책/규제 일반'])}",
            *maybe_line("국내 원전 입지·인허가 체크", alert.get("domestic_nuclear_siting_check")),
            *maybe_line("체크할 리스크", alert.get("domestic_nuclear_siting_risk_table")),
            *maybe_line("구조 변화", alert.get("domestic_nuclear_siting_structure_note")),
            *maybe_line("변압기 관세 체크", alert.get("transformer_tariff_check")),
            *maybe_line("체크할 리스크", alert.get("transformer_tariff_risk_table")),
            *maybe_line("구조 변화", alert.get("transformer_tariff_structure_note")),
            "- 반영 가능성: 낮음~중간. 공식 원문과 한국장 확산 여부를 장전 레이더에서 재확인해야 합니다.",
            f"- 반대 근거: {counter}",
            "- 즉시 체크: 원문 전문, 시행일/마감일, 인허가·입지·계통·주민수용성, 한국 밸류체인 노출, 관련 종목 수급",
            "",
        ])
    lines.extend([
        "💡 워치 판단: 이번 실행은 국내 원전 입지·인허가 시간표와 전력기기/원전 밸류체인 수급이 바뀌는지를 우선 감지했습니다.",
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
    if not isinstance(alerts, list) or not any(is_nuclear_siting(item) or is_transformer(item) for item in alerts):
        return 0
    for item in alerts:
        if is_nuclear_siting(item):
            item["title"] = NUCLEAR_TITLE
            item["sectors"] = NUCLEAR_SECTORS[:]
        if is_transformer(item):
            item["title"] = TRANSFORMER_TITLE
            item["sectors"] = TRANSFORMER_SECTORS[:]
    now = dt.datetime.now(tz=KST)
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = render(alerts, now)
    REPORT_PATH.write_text(report, encoding="utf-8")
    ALERT_PATH.write_text(report, encoding="utf-8")
    top = alerts[0]
    TITLE_PATH.write_text(f"KHS 정책 워치: [{top.get('importance', '중')}] {str(top.get('title') or '')[:70]}\n", encoding="utf-8")
    print("domestic_nuclear_siting_postprocess=rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
