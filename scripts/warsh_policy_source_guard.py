#!/usr/bin/env python3
"""Warsh 금리선물 원천의 최신성·기준일 확인(알림 공통 가드).

저장된 과거 금리·확률은 최신 선물시장 값으로 승격하지 않는다.
공식 CME 결제값의 최신 수집 성공 및 관측일을 모두 확인할 때만 읽는다.
"""
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SUCCESS_STATUS = "시장원천 최신성·연준 공식범위 교차검증 통과"


def market_state_is_fresh(state, now=None):
    if not isinstance(state, dict):
        return False
    if state.get("source_status") != SUCCESS_STATUS or state.get("source_error"):
        return False
    trade_date = state.get("official_settlement_date")
    validated_at = state.get("last_validated_at_utc")
    if not trade_date or not validated_at:
        return False
    utc_now = now or datetime.now(timezone.utc)
    if utc_now.tzinfo is None:
        return False
    try:
        validation = datetime.fromisoformat(str(validated_at).replace("Z", "+00:00"))
        ny_today = utc_now.astimezone(ZoneInfo("America/New_York")).date()
        days = (ny_today - datetime.strptime(str(trade_date), "%Y-%m-%d").date()).days
        age_seconds = (utc_now - validation.astimezone(timezone.utc)).total_seconds()
        if not 0 <= days <= 4 or not 0 <= age_seconds <= 36 * 3600:
            return False
        meetings = state.get("meetings") or []
        valid = [
            row for row in meetings
            if isinstance(row, dict)
            and str(row.get("date") or "") >= ny_today.isoformat()
            and math.isfinite(float(row.get("post_rate")))
            and 0 <= float(row.get("post_rate")) <= 20
        ]
        return bool(valid)
    except (TypeError, ValueError, OverflowError, AttributeError):
        return False


def probability_weighted_bp(probability_percent, hike_bp=25):
    """명확하게 식별된 두 결과의 확률 계산에만 사용(예: 80%=20bp)."""
    p = float(probability_percent)
    move = float(hike_bp)
    if not (math.isfinite(p) and 0 <= p <= 100 and math.isfinite(move)):
        raise ValueError("확률·금리변화 입력이 올바르지 않음")
    return p * move / 100.0
