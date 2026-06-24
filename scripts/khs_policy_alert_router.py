#!/usr/bin/env python3
"""Route KHS policy-watch alerts into separate delivery lanes."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")

POLICY_REPORT_PATH = OUT_DIR / "khs_policy_watch.md"
POLICY_ALERT_PATH = OUT_DIR / "khs_policy_watch_alert.md"
POLICY_TITLE_PATH = OUT_DIR / "khs_policy_watch_alert_title.txt"
POLICY_ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"

KOREA_PERSONNEL_ALERTS_JSON_PATH = OUT_DIR / "khs_korea_presidential_personnel_alerts.json"


def is_personnel(item: dict) -> bool:
    return "korea_presidential_personnel" in (item.get("matched") or {})


def is_whitehouse(item: dict) -> bool:
    source = str(item.get("source") or "").lower()
    link = str(item.get("link") or "").lower()
    return source.startswith("white house") or "whitehouse.gov" in link


def mostly_ascii(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    ascii_letters = [ch for ch in letters if ord(ch) < 128]
    return len(ascii_letters) / max(len(letters), 1) >= 0.75


def safe_title(alert: dict) -> str:
    title = str(alert.get("title") or "").strip()
    if not title:
        return "미국 정책·규제 문서 공표"
    if mostly_ascii(title):
        source = str(alert.get("source") or "").lower()
        text = " ".join([
            title,
            str(alert.get("summary") or ""),
            " ".join(term for terms in (alert.get("matched") or {}).values() for term in terms),
        ]).lower()
        if "fcc" in source or "federal communications commission" in text:
            return "FCC, 통신 규제 문서 공표"
        if "tariff" in text or "section 301" in text or "customs" in text:
            return "미국, 관세·통상 규정 공표"
        if "export control" in text or "entity list" in text:
            return "미국, 수출통제 규정 공표"
        if "nuclear" in text or "reactor" in text:
            return "미국, 원전 정책 문서 공표"
        if "fda" in text:
            return "FDA, 바이오·의약품 규제 결정 공표"
        return "미국 정책·규제 문서 공표"
    return title


def no_general_report(now: dt.datetime) -> str:
    return "\n".join([
        f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}",
        "",
        "고충격 일반 정책·규제 변경 직접 확인 없음",
        "",
        "💡 워치 판단: 이번 실행에서 일반 정책·규제 라인으로 따로 송출할 고충격 이벤트는 직접 확인되지 않았습니다.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ]) + "\n"


def render_policy_report(alerts: list[dict], now: dt.datetime) -> str:
    if not alerts:
        return no_general_report(now)

    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    for idx, alert in enumerate(alerts, 1):
        matched_terms = sorted({term for terms in (alert.get("matched") or {}).values() for term in terms})
        matched_keys = ", ".join((alert.get("matched") or {}).keys()) or "정책/규제"
        title = safe_title(alert)
        lines.extend([
            f"## {idx}. [{alert.get('importance', '중')}·{alert.get('status', '확정')}] {title}",
            f"- 상태 변화: {matched_keys} 신호 확인 ({', '.join(matched_terms[:8])})",
            f"- 원문/출처: [{alert.get('source', 'source')}]({alert.get('link', '')}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
            f"- 한국장 영향: {', '.join(alert.get('impacts') or ['의사결정 영향 제한적'])}",
            f"- 영향 경로: {', '.join(alert.get('paths') or ['정책 타임라인'])}",
            f"- 영향 섹터: {', '.join(alert.get('sectors') or ['정책/규제 일반'])}",
            "- 반영 가능성: 낮음~중간. 공식 원문/신뢰 소스 확인 후 한국장 확산 여부를 장전 레이더에서 재확인해야 합니다.",
            "- 반대 근거: 원문 세부 조건, 시행일, 예외 조항, 개별 프로젝트 적용 여부 확인이 필요합니다.",
            "- 즉시 체크: 원문 전문, 시행일/마감일, 한국 밸류체인 노출, 관련 해외 티커·ETF 반응",
            "",
        ])
    lines.extend([
        "💡 워치 판단: 이번 실행은 일반 정책·규제 라인으로 송출할 이벤트만 분리했습니다. 전용 감시 대상은 별도 워치에서 따로 송출됩니다.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ])
    return "\n".join(lines) + "\n"


def remove_outputs(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def write_policy_outputs(alerts: list[dict], now: dt.datetime) -> None:
    POLICY_REPORT_PATH.write_text(render_policy_report(alerts, now), encoding="utf-8")
    if not alerts:
        remove_outputs([POLICY_ALERT_PATH, POLICY_TITLE_PATH, POLICY_ALERTS_JSON_PATH])
        return

    POLICY_ALERT_PATH.write_text(render_policy_report(alerts, now), encoding="utf-8")
    POLICY_ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    top = alerts[0]
    POLICY_TITLE_PATH.write_text(
        f"KHS 정책 워치: [{top.get('importance', '중')}] {safe_title(top)[:70]}\n",
        encoding="utf-8",
    )


def main() -> int:
    now = dt.datetime.now(tz=KST)
    if not POLICY_ALERTS_JSON_PATH.exists():
        if KOREA_PERSONNEL_ALERTS_JSON_PATH.exists():
            KOREA_PERSONNEL_ALERTS_JSON_PATH.unlink()
        return 0

    try:
        alerts = json.loads(POLICY_ALERTS_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"policy_router=skip json_error={exc}")
        return 0

    policy_alerts: list[dict] = []
    personnel_alerts: list[dict] = []
    whitehouse_count = 0
    for item in alerts:
        if is_whitehouse(item):
            whitehouse_count += 1
        elif is_personnel(item):
            personnel_alerts.append(item)
        else:
            policy_alerts.append(item)

    write_policy_outputs(policy_alerts, now)
    if personnel_alerts:
        KOREA_PERSONNEL_ALERTS_JSON_PATH.write_text(
            json.dumps(personnel_alerts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        remove_outputs([KOREA_PERSONNEL_ALERTS_JSON_PATH])

    print(
        "policy_router=split "
        f"policy={len(policy_alerts)} korea_personnel={len(personnel_alerts)} "
        f"whitehouse_routed_out={whitehouse_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
