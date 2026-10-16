#!/usr/bin/env python3
"""한 번 발송된 10월 16일 환율 경보의 잘못된 전일 종가 기준 정정.

기존 market-stress 워크플로의 출력을 사용한다. 새 Telegram 토큰, 채팅 ID,
전송 경로 및 별도의 예약을 만들지 않는다. 성공적으로 전송된 후에만
기존 workflow가 pending state를 main에 커밋하므로 실패하면 재시도한다.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "korea_market_stress_watch_state.json"
PENDING = ROOT / "out" / "korea_market_stress_pending_state.json"
ALERT = ROOT / "out" / "korea_market_stress_alert.html"
STATUS = ROOT / "out" / "korea_market_stress_status.md"
KST = ZoneInfo("Asia/Seoul")

BAD_EVENT = "fx_daily_down_stage1:2026-10-16"
CORRECTION_EVENT = "fx_close_basis_correction:2026-10-16:v1"
PREVIOUS_OFFICIAL_CLOSE = 1344.6
CURRENT_OFFICIAL_CLOSE = 1331.4
INTRADAY_SNAPSHOT = 1336.4
PREVIOUS_WRONG_BASIS = 1350.0
RATE_YESTERDAY_SOURCE = "https://www.yna.co.kr/amp/view/AKR20261015130900002"
RATE_TODAY_SOURCE = "https://en.yna.co.kr/view/AEN20261016008500320"


def eligible(pending: dict, prior: dict, now: dt.datetime) -> bool:
    keys = set(pending.get("seen_event_keys") or []) | set(prior.get("seen_event_keys") or [])
    if now.date() < dt.date(2026, 10, 16):
        return False
    if BAD_EVENT not in keys or CORRECTION_EVENT in keys:
        return False
    return True


def corrected_change(current: float, previous: float) -> tuple[float, float]:
    return round(current - previous, 1), round((current / previous - 1) * 100, 2)


def message() -> str:
    intraday_change, intraday_pct = corrected_change(INTRADAY_SNAPSHOT, PREVIOUS_OFFICIAL_CLOSE)
    close_change, close_pct = corrected_change(CURRENT_OFFICIAL_CLOSE, PREVIOUS_OFFICIAL_CLOSE)
    return (
        "<b>정정: 10월 16일 원/달러 일간 급락 경보 기준가 오류</b>\n\n"
        "• 이전 경보에서는 10월 15일 15:30 공식 종가를 <b>1,350.0원으로 잘못 파싱</b>하여 "
        "10월 16일 15:18경 1,336.4원 관측에 대해 <b>−13.6원(−1.01%)</b>으로 계산했습니다.\n"
        f"• 실제 10월 15일 서울 15:30 공식 종가는 <b>{PREVIOUS_OFFICIAL_CLOSE:,.1f}원</b>입니다. "
        f"따라서 같은 1,336.4원 관측의 정확한 변화는 <b>{intraday_change:+.1f}원({intraday_pct:+.2f}%)</b>입니다.\n"
        f"• 10월 16일 정규장 15:30 종가는 <b>{CURRENT_OFFICIAL_CLOSE:,.1f}원</b>, "
        f"전일 정규장 대비 <b>{close_change:+.1f}원({close_pct:+.2f}%)</b>입니다.\n"
        "• 기존 환율 1일 경보 기준인 <b>±20원 또는 ±1.00%</b>에는 해당하지 않습니다. "
        "이전 −1.01% 경보는 무효입니다.\n"
        "• 원인은 외환시세 원문에서 미 달러 종가 대신 무관한 원화 금액을 추출한 파싱 오류입니다. "
        "이제 미 달러 15:30 기준가에 연결되는 숫자만 수용하고 불명확하면 판정을 보류하도록 수정했습니다.\n"
        f'• <a href="{RATE_YESTERDAY_SOURCE}">10월 15일 15:30 기준가 근거</a> / '
        f'<a href="{RATE_TODAY_SOURCE}">10월 16일 15:30 종가 근거</a>'
    )


def main() -> int:
    if not PENDING.exists() or not PENDING.stat().st_size:
        print("fx_close_basis_correction=skipped reason=pending_state_missing")
        return 0
    try:
        pending = json.loads(PENDING.read_text(encoding="utf-8"))
        prior = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    except (OSError, ValueError):
        print("fx_close_basis_correction=skipped reason=state_unreadable")
        return 0

    now = dt.datetime.now(KST)
    if not eligible(pending, prior, now):
        print("fx_close_basis_correction=skipped reason=already_sent_or_unrelated")
        return 0

    # 기존 정상 경보를 덮어쓰지 않고, 수정 메시지를 추가한다.
    previous_alert = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    correction = message()
    ALERT.write_text(
        (previous_alert + "\n\n──────────\n\n" + correction if previous_alert else correction) + "\n",
        encoding="utf-8",
    )

    seen = list(pending.get("seen_event_keys") or [])
    if CORRECTION_EVENT not in seen:
        seen.append(CORRECTION_EVENT)
    pending["seen_event_keys"] = seen
    invalidated = list(pending.get("invalidated_event_keys") or [])
    if BAD_EVENT not in invalidated:
        invalidated.append(BAD_EVENT)
    pending["invalidated_event_keys"] = invalidated
    pending["active_keys"] = [key for key in (pending.get("active_keys") or []) if key != BAD_EVENT]
    pending["fx_basis_correction"] = {
        "event_key": CORRECTION_EVENT,
        "wrong_event_key": BAD_EVENT,
        "previous_close_correct": PREVIOUS_OFFICIAL_CLOSE,
        "previous_close_wrong": PREVIOUS_WRONG_BASIS,
        "official_close": CURRENT_OFFICIAL_CLOSE,
        "official_close_date": "2026-10-16",
        "official_source_previous": RATE_YESTERDAY_SOURCE,
        "official_source_current": RATE_TODAY_SOURCE,
        "delivery_state": "pending_workflow_telegram_confirmation",
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if STATUS.exists():
        with STATUS.open("a", encoding="utf-8") as f:
            f.write("\n- 10월 16일 환율 기준가 잘못 적용 경보 정정: Telegram 전송 대기\n")
    print("fx_close_basis_correction=queued; will commit state only after Telegram success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
