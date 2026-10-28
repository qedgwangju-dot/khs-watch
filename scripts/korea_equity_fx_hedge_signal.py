#!/usr/bin/env python3
"""KOSPI/USDKRW 동행 괴리 경보. NDF 실제 순매수로 오인하지 않는다.

기존 Korea Market Stress 워크플로 안에서만 실행하며 Telegram 계정/주기/상태파일을
새로 만들지 않는다. confirmed delivery 후에만 부모 워크플로가 상태를 커밋한다.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo("Asia/Seoul")
MARKET_PENDING = ROOT / "out/korea_market_stress_pending_state.json"
ROTATION_PENDING = ROOT / "out/fx_sector_rotation_pending_state.json"
ALERT = ROOT / "out/korea_market_stress_alert.html"
STATUS = ROOT / "out/korea_equity_fx_hedge_status.md"
LATEST_BOK_NDF_INFO = (
    "https://www.bok.or.kr/portal/bbs/B0000502/view.do"
    "?menuNo=201265&nttId=11065634"
)
INDEX_SOURCE = "https://m.stock.naver.com/api/index/KOSPI/basic"
MAX_AGE_MINUTES = 30
MAX_FX_DIFFERENCE_KRW = 2.0
MAX_PREVIOUS_CLOSE_DIFFERENCE_KRW = 0.2


def numeric(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def parse_time(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(KST)
    except (TypeError, ValueError):
        return None


def validate(market: dict, sector: dict, now: dt.datetime) -> tuple[dict | None, str]:
    """No alert unless both quotes were observed in same live session with verified FX close."""
    if now.tzinfo is None:
        return None, "현재시각에 시간대가 없습니다"
    now = now.astimezone(KST)
    today = now.date().isoformat()
    snapshot = market.get("snapshot") or {}
    latest = sector.get("latest") or {}
    fx_market = snapshot.get("usdkrw") or {}
    fx_sector = latest.get("fx") or {}
    stamp = parse_time(latest.get("checked_at"))
    if sector.get("date") != today or latest.get("market_phase") != "정규장":
        return None, "오늘 정규장 관측값 아님"
    if not stamp or stamp.date().isoformat() != today:
        return None, "관측시각 또는 오늘자 확인 실패"
    age = (now - stamp).total_seconds() / 60
    if age < -2 or age > MAX_AGE_MINUTES:
        return None, "시장 관측값 지연"
    if fx_sector.get("date") != today or fx_market.get("date") != today:
        return None, "환율 관측 기준일 불일치"
    if fx_market.get("comparison_valid") is not True:
        return None, "전일 서울 15:30 환율 종가 검증 실패"
    if not fx_sector.get("prev_close_source") or fx_sector.get("basis_error"):
        return None, "별도 환율 비교 기준 검증 실패"
    if not str(fx_sector.get("comparison_basis") or "").startswith("서울외환시장 15:30"):
        return None, "정규장 비교 기준 아닌 자료"
    if not str(fx_market.get("prev_date") or "") < today:
        return None, "전일 서울 종가 기준일 미확인"
    kpct = numeric(latest.get("kospi_pct"))
    current = numeric(fx_sector.get("value"))
    prev = numeric(fx_sector.get("prev_close"))
    market_current = numeric(fx_market.get("value"))
    market_prev = numeric(fx_market.get("prev_value"))
    if any(x is None for x in (kpct, current, prev, market_current, market_prev)):
        return None, "지수·환율 숫자 결측"
    if not (800 <= current <= 2500 and 800 <= prev <= 2500):
        return None, "환율 값 범위 초과"
    if abs(current-market_current) > MAX_FX_DIFFERENCE_KRW:
        return None, "서로 다른 환율 조회 시점 차이가 과다"
    if abs(prev-market_prev) > MAX_PREVIOUS_CLOSE_DIFFERENCE_KRW:
        return None, "전일 환율 공식 기준가 불일치"
    if abs(kpct) > 30:
        return None, "주가지수 변동률 비정상"
    fx_delta = current - prev
    fx_pct = (current / prev - 1) * 100
    return {
        "trade_date": today,
        "checked_at": stamp.isoformat(timespec="seconds"),
        "kospi_pct": kpct,
        "usdkrw": current,
        "previous_close": prev,
        "fx_change_krw": fx_delta,
        "fx_change_pct": fx_pct,
        "index_source": INDEX_SOURCE,
        "fx_source": str(fx_sector.get("source") or ""),
        "close_source": str(fx_sector["prev_close_source"]),
        "foreign_flow": (snapshot.get("foreign_flow") or {}),
    }, "검증 완료"


def classify(obs: dict | None) -> tuple[str, int] | None:
    """Positive means both stocks and USD/KRW rise. Reverse is both fall."""
    if obs is None:
        return None
    k, f, w = obs["kospi_pct"], obs["fx_change_pct"], obs["fx_change_krw"]
    if k >= 3 and f >= 0.5 and w >= 5:
        return "동반상승", 2 if k >= 5 and f >= 0.75 and w >= 10 else 1
    if k <= -3 and f <= -0.5 and w <= -5:
        return "동반하락", 2 if k <= -5 and f <= -0.75 and w <= -10 else 1
    return None


def dedupe_key(obs: dict, signal: tuple[str, int]) -> str:
    label, level = signal
    return f"equity_fx_same_direction:{obs['trade_date']}:{label}:level{level}"


def should_alert(old: dict, obs: dict, signal: tuple[str, int]) -> bool:
    key = dedupe_key(obs, signal)
    seen = set(old.get("seen_keys") or [])
    label, level = signal
    stronger = [
        f"equity_fx_same_direction:{obs['trade_date']}:{label}:level{l}"
        for l in range(level, 3)
    ]
    return key not in seen and not any(x in seen for x in stronger)


def render(obs: dict, signal: tuple[str, int]) -> str:
    label, level = signal
    if label == "동반상승":
        heading = "KOSPI 급등 + 원/달러 상승 — 환헤지 가능성 점검"
        interpretation = (
            "주가 상승으로 늘어난 원화 자산에 대한 달러 매수 NDF 헤지, "
            "외환 수급과 달러 강세가 동시에 작용할 가능성. 실제 헤지 여부 미확인"
        )
        alternative = "달러 전반 강세·기업 결제수요·역내 외환 수급도 가능한 원인"
    else:
        heading = "KOSPI 급락 + 원/달러 하락 — 환헤지 청산 가능성 점검"
        interpretation = (
            "외국인의 기존 달러 매수 NDF 헤지가 일부 청산됐을 가능성. "
            "주식 매도에 따른 현물 달러 매수와 방향이 다를 수 있으며 실제 거래 미확인"
        )
        alternative = "달러 전반 약세·수출기업 달러 매도·정책 관련 수급도 가능한 원인"

    flows = obs.get("foreign_flow") or {}
    flow_note = "외국인 현물 수급: 별도 확인 필요"
    value = numeric(flows.get("daily_eok"))
    if flows.get("date") == obs["trade_date"] and value is not None:
        finality = "확정" if flows.get("finality") == "확정" else "장중 잠정"
        direction = "순매수" if value >= 0 else "순매도"
        flow_note = f"외국인 현물 참고: {direction} {abs(value):,.0f}억원 ({finality}, 경보 트리거로 사용하지 않음)"

    return "\n".join([
        f"<b>주가·환율 {html.escape(label)} {level}단계 | {html.escape(heading)}</b>",
        f"• 관측시각: {html.escape(obs['checked_at'])} 한국시간 (장중, 종가 아님)",
        f"• KOSPI: <b>{obs['kospi_pct']:+.2f}%</b> / 원·달러: "
        f"<b>{obs['usdkrw']:,.2f}원</b> (전일 15:30 기준가 "
        f"{obs['previous_close']:,.2f}원 대비 {obs['fx_change_krw']:+,.2f}원, "
        f"{obs['fx_change_pct']:+.2f}%)",
        f"• {html.escape(flow_note)}",
        f"• 가능한 해석: {html.escape(interpretation)}",
        f"• 대안 설명: {html.escape(alternative)}",
        "• <b>중요: NDF 순매수·순매도 금액 및 헤지 비율은 이번 신호로 측정되지 않았습니다.</b> "
        "주가·환율의 동행만으로 역외 기관 헤지 거래를 확정하지 않습니다.",
        "• 조기 확인: 한국은행 비거주자 NDF 순매매, 역내 현물 거래, 달러지수, "
        "은행의 헤지·선물환 포지션, 외국인 현물·선물 수급",
        f'• <a href="{html.escape(obs["index_source"], quote=True)}">KOSPI 시장시세</a> / '
        f'<a href="{html.escape(obs["close_source"], quote=True)}">전일 서울 15:30 종가 근거</a> / '
        f'<a href="{LATEST_BOK_NDF_INFO}">한국은행 외환시장 동향</a>',
    ])


def append_alert(text: str):
    previous = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    ALERT.parent.mkdir(parents=True, exist_ok=True)
    ALERT.write_text((previous + "\n\n──────────\n\n" + text if previous else text) + "\n", encoding="utf-8")


def run(now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(KST)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    if not MARKET_PENDING.exists() or not ROTATION_PENDING.exists():
        STATUS.write_text("- 주가·환율 동행 점검: 선행 감시 파일 없음 — 판정 보류\n", encoding="utf-8")
        return False
    try:
        market = json.loads(MARKET_PENDING.read_text(encoding="utf-8"))
        rotation = json.loads(ROTATION_PENDING.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        STATUS.write_text("- 주가·환율 동행 점검: 입력 오류 — 판정 보류\n", encoding="utf-8")
        return False
    obs, reason = validate(market, rotation, now)
    signal = classify(obs)
    prior = market.get("equity_fx_hedge_signal") or {}
    if not obs or signal is None:
        STATUS.write_text(f"- 주가·환율 동행 점검: {reason if not obs else '동행 경보 임계치 미충족'}\n", encoding="utf-8")
        return False
    if not should_alert(prior, obs, signal):
        STATUS.write_text(f"- 주가·환율 동행 점검: 동일 거래일·동일 단계 재발송 방지 ({obs['trade_date']})\n", encoding="utf-8")
        return False
    key = dedupe_key(obs, signal)
    append_alert(render(obs, signal))
    state = dict(prior)
    state["version"] = 1
    state["seen_keys"] = (list(dict.fromkeys((prior.get("seen_keys") or []) + [key])))[-120:]
    state["last_signal"] = {
        "key": key, "date": obs["trade_date"], "label": signal[0],
        "stage": signal[1], "checked_at": obs["checked_at"],
        "kospi_pct": round(obs["kospi_pct"], 4),
        "fx_change_pct": round(obs["fx_change_pct"], 4),
        "fx_change_krw": round(obs["fx_change_krw"], 4),
        "ndf_signed_flow_verified": False,
    }
    market["equity_fx_hedge_signal"] = state
    MARKET_PENDING.write_text(json.dumps(market, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        f"- 주가·환율 동행 점검: 신규 {signal[0]} {signal[1]}단계, "
        f"일별 고유키 {key}, 텔레그램 전송 대기\n",
        encoding="utf-8",
    )
    return True


if __name__ == "__main__":
    run()
