#!/usr/bin/env python3
"""인증된 CME FedWatch 종가 API 전용 파서.

CME가 공식적으로 제공하는 목표금리 구간별 확률을 그대로 읽는다.
월평균 선물 가격에서 FedWatch 확률을 2개 구간으로 임의 역산하지 않는다.
OAuth 인증·권한 없이는 수치 반환을 거부한다.
"""
import base64
import datetime as dt
import json
import math
import urllib.parse
import urllib.request
import uuid

AUTH_URL = "https://auth.cmegroup.com/as/token.oauth2"
API_ROOT = "https://markets.api.cmegroup.com/fedwatch/v1"
SOURCE_URL = "https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html"
USER_AGENT = "khs-watch/5.0"


def _request_json(url, headers, body=None, timeout=12):
    req = urllib.request.Request(
        url, data=body, method="POST" if body is not None else "GET",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout) as reply:
        return json.loads(reply.read().decode("utf-8", "replace"))


def oauth_token(api_id, api_password):
    if not api_id or not api_password:
        raise RuntimeError("CME FedWatch 공식 API 인증정보 미설정")
    basic = base64.b64encode((api_id + ":" + api_password).encode()).decode("ascii")
    data = _request_json(
        AUTH_URL, {
            "Authorization": "Basic " + basic,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }, body=b"grant_type=client_credentials",
    )
    token = data.get("access_token") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("CME FedWatch OAuth 인증 토큰 발급 실패")
    return token


def forecasts(token, meeting_dates):
    if not token or not meeting_dates:
        raise RuntimeError("CME 공식 API 토큰 또는 회의일 누락")
    params = urllib.parse.urlencode({"meetingDt": ",".join(meeting_dates)})
    headers = {
        "Authorization": "Bearer " + token,
        "CME-Application-Name": "khs-watch",
        "CME-Application-Vendor": "khs-watch",
        "CME-Application-Version": "5.0",
        "CME-Request-ID": str(uuid.uuid4()),
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    data = _request_json(API_ROOT + "/forecasts?" + params, headers)
    payload = data.get("payload") if isinstance(data, dict) else None
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("CME 공식 FedWatch 예측확률 응답 내용 없음")
    return payload


def _float(value):
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except (TypeError, ValueError, OverflowError):
        pass
    raise ValueError("CME 확률·금리 비정상 입력")


def _range_bps(value):
    v = _float(value)
    if v < 0 or v > 2000 or int(v) != v or int(v) % 25:
        raise ValueError("CME 정책금리 목표구간 단위 오류")
    return int(v)


def parse_forecast(rec, base_low, base_high, today):
    """0~1 비율의 공식 rateRange 확률을 0~100%로 변환한다.

    미래 회의의 목표금리 분포는 현재 정책금리 대비 누적 경로이며
    '그 회의에서 정확히 25bp 인상할 확률'과 동일하지 않다.
    """
    if not isinstance(rec, dict):
        raise ValueError("CME 예측정보 형식 오류")
    meeting = str(rec.get("meetingDt") or "")
    report = str(rec.get("reportingDt") or "")
    try:
        md = dt.date.fromisoformat(meeting)
        rd = dt.date.fromisoformat(report)
    except ValueError:
        raise ValueError("CME 회의일·자료일 날짜 파싱 실패")
    if md < today or rd > today or rd > md:
        raise ValueError("CME 회의일 또는 공식 확률 발표일이 미래/과거 불일치")
    if (today - rd).days > 4:
        raise ValueError("CME FedWatch 확률 발표일 오래됨")
    ranges = rec.get("rateRange")
    if not isinstance(ranges, list) or not ranges:
        raise ValueError("CME FedWatch 구간별 확률 누락")

    seen, total, levels = set(), 0.0, []
    for entry in ranges:
        if not isinstance(entry, dict):
            raise ValueError("CME 목표금리 구간 레코드 오류")
        lo, hi = _range_bps(entry.get("lowerRt")), _range_bps(entry.get("upperRt"))
        if hi - lo != 25 or (lo, hi) in seen:
            raise ValueError("CME 중복 목표금리 구간 또는 25bp 이외 구간")
        seen.add((lo, hi))
        if entry.get("probability") is None:
            continue
        p = _float(entry["probability"])
        if p < 0 or p > 1:
            raise ValueError("CME 확률 단위가 0~1 범위를 벗어남")
        total += p
        levels.append((lo, hi, p))
    if not levels or abs(total - 1.0) > 0.005:
        raise ValueError(f"CME 확률 합계 100% 검산 실패: {total}")
    if any(lo < 0 or hi > 2000 for lo, hi, _ in levels):
        raise ValueError("CME 비현실적 목표금리")

    base_lo, base_hi = _range_bps(base_low * 100), _range_bps(base_high * 100)
    if base_hi - base_lo != 25:
        raise ValueError("연준 공식 목표금리 범위 검증 실패")
    post_mid = sum(((lo + hi) / 200.0) * p for lo, hi, p in levels)
    base_mid = (base_lo + base_hi) / 200.0
    after_25_exact = sum(p for lo, hi, p in levels if lo == base_lo + 25 and hi == base_hi + 25) * 100
    after_25_plus = sum(p for lo, hi, p in levels if lo >= base_lo + 25) * 100
    hold = sum(p for lo, hi, p in levels if lo == base_lo and hi == base_hi) * 100
    cut = sum(p for lo, hi, p in levels if lo < base_lo) * 100
    outcomes = {f"{lo / 100:.2f}~{hi / 100:.2f}%": round(p * 100, 5)
                for lo, hi, p in levels if p > 0}
    return {
        "date": meeting,
        "reporting_date": report,
        "post_rate": post_mid,
        "pre_rate": base_mid,
        "change_bp": (post_mid - base_mid) * 100,
        "implied_avg": post_mid,
        "hike25_prob": after_25_exact,
        "hike25_or_more_prob": after_25_plus,
        "hold_prob": hold,
        "cut_prob": cut,
        "outcomes": outcomes,
        "prob_cell": " / ".join(f"{k} {v:.1f}%" for k, v in outcomes.items()),
        "contract": "CME FedWatch EOD",
    }


def build_snapshot(payload, meeting_dates, baseline, today):
    """공식 발표일·회의일·목표구간·확률합계·연말 회의를 모두 확인."""
    if not isinstance(payload, list):
        raise ValueError("CME FedWatch 응답이 목록이 아님")
    allowed = set(meeting_dates)
    latest_by_meeting = {}
    for rec in payload:
        if not isinstance(rec, dict):
            continue
        date = str(rec.get("meetingDt") or "")
        if date not in allowed:
            continue
        # 같은 회의에 과거 reportingDt 여러 개가 있으면 최신 것만 선택
        report = str(rec.get("reportingDt") or "")
        if date not in latest_by_meeting or report > str(latest_by_meeting[date].get("reportingDt") or ""):
            latest_by_meeting[date] = rec

    if any(d not in latest_by_meeting for d in meeting_dates):
        raise RuntimeError("CME 공식 확률에 향후 FOMC 회의가 누락됨")

    parsed = [parse_forecast(latest_by_meeting[d], baseline["low"], baseline["high"], today)
              for d in meeting_dates]
    report_dates = {m["reporting_date"] for m in parsed}
    if len(report_dates) != 1:
        raise RuntimeError("CME 회의별 확률 기준일 불일치")
    if not any(m["date"][:4] == str(today.year) for m in parsed):
        raise RuntimeError("CME 연말 시장경로 자료 누락")

    return {
        "meetings": parsed,
        "forecast_reporting_date": next(iter(report_dates)),
        "official_settlement_date": None,
        "market_data_basis": "CME FedWatch 공식 인증 API 종가 확률",
        "source_kind": "CME FedWatch 공식 인증 API",
        "url": SOURCE_URL,
        "source_api_url": API_ROOT + "/forecasts",
    }
