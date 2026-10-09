#!/usr/bin/env python3
"""Warsh 금리선물 원천의 최신성·기준일 확인(알림 공통 가드).

저장된 과거 금리·확률은 최신 선물시장 값으로 승격하지 않는다.
공식 CME 결제값의 최신 수집 성공 및 관측일을 모두 확인할 때만 읽는다.
"""
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

SUCCESS_STATUS = "시장원천 최신성·연준 공식범위 교차검증 통과"


def market_state_is_fresh(state, now=None):
    if not isinstance(state, dict):
        return False
    if state.get("source_status") != SUCCESS_STATUS or state.get("source_error"):
        return False
    validated_at = state.get("last_validated_at_utc")
    source = str(state.get("source") or "")
    host = (urlparse(source).hostname or "").lower()
    basis = str(state.get("market_data_basis") or "")
    api_mode = basis == "CME FedWatch 공식 인증 API 종가 확률"
    # 홈페이지 URL만으로 공식 API 인증을 증명할 수 없다.
    # 실제 데이터 조회에 사용된 허용된 CME API endpoint도 확인한다.
    if api_mode:
        api_url = str(state.get("source_api_url") or "")
        if (host not in {"www.cmegroup.com", "cmegroup.com"}
                or api_url != "https://markets.api.cmegroup.com/fedwatch/v1/forecasts"):
            return False
        trade_date = state.get("forecast_reporting_date")
    else:
        if host not in {"cmegroup.com", "www.cmegroup.com"}:
            return False
        trade_date = state.get("official_settlement_date")
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
        if not valid:
            return False
        # 인증된 공식 FedWatch 확률은 모든 FOMC 회의에 누적 목표금리분포를 제공한다.
        # 소수점/100배 단위, 부분합, 보고일 누락, 이전회의 재사용 모두 거절.
        if api_mode:
            if len(valid) != len(meetings):
                return False
            for row in valid:
                if row.get("reporting_date") != trade_date:
                    return False
                odds = row.get("outcomes")
                if not isinstance(odds, dict) or not odds:
                    return False
                values = [float(p) for p in odds.values()]
                if not all(math.isfinite(p) and 0 <= p <= 100 for p in values):
                    return False
                if abs(sum(values) - 100.0) > .06:
                    return False
                for field in ("hike25_prob", "hike25_or_more_prob", "hold_prob", "cut_prob"):
                    val = float(row[field])
                    if not math.isfinite(val) or val < 0 or val > 100:
                        return False
                if float(row["hike25_prob"]) > float(row["hike25_or_more_prob"]) + .001:
                    return False
        elif "결제값" in basis and any(row.get("hike25_prob") is not None for row in valid):
            return False
        return True
    except (TypeError, ValueError, OverflowError, AttributeError):
        return False


def probability_weighted_bp(probability_percent, hike_bp=25):
    """명확하게 식별된 두 결과의 확률 계산에만 사용(예: 80%=20bp)."""
    p = float(probability_percent)
    move = float(hike_bp)
    if not (math.isfinite(p) and 0 <= p <= 100 and math.isfinite(move)):
        raise ValueError("확률·금리변화 입력이 올바르지 않음")
    return p * move / 100.0
