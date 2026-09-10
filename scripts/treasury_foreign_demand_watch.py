#!/usr/bin/env python3
"""Track foreign demand for U.S. Treasuries from official TIC and Fed H.4.1.

Monthly TIC alerts always fire for a new month. Weekly Fed custody alerts fire only
when the weekly/4-week move is material. The output explicitly separates changes
in holdings from transaction flows and valuation effects so falling market value
is not mislabeled as outright selling.
"""

from __future__ import annotations

import csv
import html as htmllib
import json
import re
import urllib.request
from datetime import datetime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
STATE = DATA / "treasury_foreign_demand_state.json"
NEXT_STATE = DATA / "treasury_foreign_demand_state_next.json"
ALERT = OUT / "treasury_foreign_demand_alert.md"
TITLE = OUT / "treasury_foreign_demand_title.txt"
DETAIL = OUT / "treasury_foreign_demand_detail.json"
STATUS = OUT / "treasury_foreign_demand_status.md"

TABLE5 = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.txt"
TABLE3 = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table3.txt"
H41 = "https://www.federalreserve.gov/releases/h41/current/"

TRACKED = [
    "Japan",
    "United Kingdom",
    "China, Mainland",
    "Belgium",
    "Luxembourg",
    "Cayman Islands",
    "Korea, South",
]
DISPLAY = {
    "Japan": "일본",
    "United Kingdom": "영국",
    "China, Mainland": "중국",
    "Belgium": "벨기에",
    "Luxembourg": "룩셈부르크",
    "Cayman Islands": "케이맨제도",
    "Korea, South": "한국",
}
CORE3 = ["Japan", "United Kingdom", "China, Mainland"]


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-treasury-demand-watch/1.0)",
            "Accept": "text/plain,text/html,application/xhtml+xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def fnum(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if not value or value.lower() in {"n.a.", "na", "nan", "-"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt_bn(v: float | None, *, signed: bool = False) -> str:
    """Format a value expressed in billions of U.S. dollars.

    1 billion dollars = 10 억달러. Values >= $1tn are shown in 조달러.
    """
    if v is None:
        return "확인 불가"
    sign = "+" if signed and v > 0 else ""
    if abs(v) >= 1000:
        return f"{sign}{v/1000:,.3f}조달러"
    return f"{sign}{v*10:,.0f}억달러"


def parse_table5(text: str) -> tuple[list[str], dict[str, list[float | None]]]:
    rows = list(csv.reader(StringIO(text), delimiter="\t"))
    header_i = next(i for i, row in enumerate(rows) if row and row[0].strip() == "Country")
    months = [x.strip() for x in rows[header_i][1:] if x.strip()]
    values: dict[str, list[float | None]] = {}
    for row in rows[header_i + 1 :]:
        if not row or not row[0].strip() or row[0].strip() == "Notes:":
            continue
        name = row[0].strip()
        values[name] = [fnum(x) for x in row[1 : 1 + len(months)]]
    return months, values


def parse_table3(text: str, latest_month: str) -> dict[str, dict[str, float | None]]:
    rows = list(csv.reader(StringIO(text), delimiter="\t"))
    header_i = next(i for i, row in enumerate(rows) if row and row[0].strip() == "country")
    keys = [x.strip() for x in rows[header_i]]
    result: dict[str, dict[str, float | None]] = {}
    for row in rows[header_i + 1 :]:
        if len(row) < len(keys):
            continue
        item = dict(zip(keys, row))
        name = item.get("country", "").strip()
        if name in TRACKED and item.get("date", "").strip() == latest_month:
            result[name] = {
                "net_mn": fnum(item.get("for_treas_net")),
                "lt_net_mn": fnum(item.get("for_lt_treas_net")),
                "lt_val_mn": fnum(item.get("for_lt_treas_valchg")),
                "st_net_mn": fnum(item.get("for_st_treas_net")),
            }
    return result


def strip_html(text: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", htmllib.unescape(text)).strip()


def parse_h41(text: str) -> dict[str, float | str] | None:
    plain = strip_html(text)
    pat = re.compile(
        r"Marketable U\.S\. Treasury securities\s+1\s+([\d,]+)\s+([+-])?\s*([\d,]+)\s+([+-])?\s*([\d,]+)\s+([\d,]+)",
        re.I,
    )
    m = pat.search(plain)
    if not m:
        return None
    value = float(m.group(1).replace(",", "")) / 1000.0
    weekly = float(m.group(3).replace(",", "")) / 1000.0
    if m.group(2) == "-":
        weekly = -weekly
    yoy = float(m.group(5).replace(",", "")) / 1000.0
    if m.group(4) == "-":
        yoy = -yoy
    date_match = re.search(r"Wednesday\s+([A-Z][a-z]{2}\s+\d{1,2},\s+2026)", plain)
    date = date_match.group(1) if date_match else datetime.now(KST).date().isoformat()
    return {"date": date, "value_bn": value, "weekly_bn": weekly, "yoy_bn": yoy}


def classify(holding_change_bn: float, net_flow_bn: float | None, val_bn: float | None) -> str:
    if holding_change_bn < 0 and net_flow_bn is not None and net_flow_bn >= 0:
        return "보유액은 감소했지만 순매도는 아님 → 평가손실·기타 조정 영향 우세"
    if holding_change_bn < 0 and net_flow_bn is not None and net_flow_bn < 0:
        if val_bn is not None and val_bn < 0:
            return "실제 순매도와 평가손실이 동시에 작용"
        return "실제 순매도 확인"
    if holding_change_bn > 0 and net_flow_bn is not None and net_flow_bn > 0:
        return "순매수와 보유액 증가가 함께 확인"
    return "보유액·거래·평가효과 혼합 — 단일 원인 단정 금지"


def build_tic_alert(months: list[str], t5: dict[str, list[float | None]], t3: dict[str, dict[str, float | None]]) -> tuple[str, str, dict]:
    latest = months[0]
    total_now = t5.get("Grand Total", [None])[0]
    total_prev = t5.get("Grand Total", [None, None])[1]
    total_change = total_now - total_prev if total_now is not None and total_prev is not None else None

    core_change = 0.0
    core_net = 0.0
    core_val = 0.0
    core_net_known = True
    core_val_known = True
    country_lines: list[str] = []
    details: dict[str, dict] = {}

    for name in TRACKED:
        vals = t5.get(name, [])
        if len(vals) < 2 or vals[0] is None or vals[1] is None:
            continue
        change = vals[0] - vals[1]
        tx = t3.get(name, {})
        net_mn = tx.get("net_mn")
        val_mn = tx.get("lt_val_mn")
        net_bn = net_mn / 1000.0 if net_mn is not None else None
        val_bn = val_mn / 1000.0 if val_mn is not None else None
        if name in CORE3:
            core_change += change
            if net_bn is None:
                core_net_known = False
            else:
                core_net += net_bn
            if val_bn is None:
                core_val_known = False
            else:
                core_val += val_bn
        line = f"• {DISPLAY[name]}: {fmt_bn(vals[0])} / 전월 {fmt_bn(change, signed=True)}"
        if net_bn is not None:
            line += f" / 순거래 {fmt_bn(net_bn, signed=True)}"
        if val_bn is not None:
            line += f" / 장기채 평가효과 {fmt_bn(val_bn, signed=True)}"
        country_lines.append(line)
        details[name] = {"holding_bn": vals[0], "change_bn": change, "net_bn": net_bn, "lt_val_bn": val_bn}

    core_net_v = core_net if core_net_known else None
    core_val_v = core_val if core_val_known else None
    core_signal = classify(core_change, core_net_v, core_val_v)

    lines = [
        f"🇺🇸 미 국채 해외수요 점검 — TIC {latest}",
        "",
        "핵심 판단",
        f"일본+영국+중국 보유액 변화: {fmt_bn(core_change, signed=True)}.",
        f"판정: {core_signal}.",
        "※ ‘보유액 감소’와 ‘실제 매도’는 같은 말이 아닙니다. TIC 거래·평가변동을 같이 봅니다.",
        "",
        "확정 숫자",
        f"• 전체 외국인 미 국채 보유액: {fmt_bn(total_now)} / 전월 {fmt_bn(total_change, signed=True)}",
        *country_lines,
        "",
        "시장 의미",
        "• 실제 해외 순매도가 확대되면 국채를 받아줄 민간 수요가 더 필요 → 기간 프리미엄·10년/30년 금리 상승 압력.",
        "• 보유액 감소가 주로 평가손실이면 ‘외국이 대규모로 던졌다’는 해석은 과장입니다.",
        "• 장기 실질금리가 같이 오르면 AI·성장주는 할인율 부담이 커집니다.",
        "",
        "주의",
        "• 영국·벨기에·룩셈부르크·케이맨은 보관기관 위치 효과가 커 최종 실소유자로 단정하면 안 됩니다.",
        "• ‘중국이 판 물량을 영국이 그대로 샀다’는 1:1 연결도 TIC만으로는 확인할 수 없습니다.",
        "",
        "다음 확인",
        "• 다음 월간 TIC: 국가별 보유액 + 순거래 + 장기채 평가변동",
        "• 주간 Fed H.4.1 해외 공식계정 국채 보관잔액",
        "• 10년·30년 입찰 응찰률·꼬리·간접낙찰 비중으로 실제 수요 재검증",
        "",
        f"원문: {TABLE5}",
        f"거래·평가 분해: {TABLE3}",
    ]
    detail = {
        "type": "tic",
        "month": latest,
        "total_bn": total_now,
        "total_change_bn": total_change,
        "core3_change_bn": core_change,
        "core3_net_bn": core_net_v,
        "core3_lt_val_bn": core_val_v,
        "countries": details,
    }
    return f"🇺🇸 TIC {latest} 미 국채 해외수요", "\n".join(lines), detail


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, TITLE, DETAIL):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    state = load_state()

    manual_id = "ecb-2026-09-10-deposit-2.50-global-tightening"
    if state.get("manual_global_rates_alert_id") != manual_id:
        now_kst = datetime.now(KST).isoformat(timespec="seconds")
        title = "🔔 글로벌 동시 긴축 경보 — ECB 2.50%"
        body = "\n".join([
            "🔔 [글로벌 동시 긴축] ECB +0.25%p → 예금금리 2.50%",
            "",
            "• ECB: 2026년 두 번째 인상. 6월 2.00→2.25%, 오늘 2.25→2.50%.",
            "• 올해 확정 인상 횟수: 호주 3회 · 한국 2회 · 유럽 2회 · 일본 1회.",
            "• 직접 원인: 중동 에너지 충격으로 유로존 물가가 다시 3%를 웃돌았고, ECB는 2026년 물가 3.0%, 성장 0.9%를 제시.",
            "",
            "시장 해석",
            "• 글로벌 유동성: 공식 공조라기보다 각국이 같은 에너지·물가 충격에 동시에 긴축하는 국면. 장기금리·할인율 상승 압력.",
            "• 금리민감 자산: 고PER 성장주·리츠·고부채 자산은 할인율 부담 확대. 은행은 금리 수혜와 경기·신용비용 악화가 동시에 작용.",
            "",
            "중요 수정",
            "• Fed가 11월까지 동결한다는 것은 확정 사실이 아님. Reuters 조사에서는 동결 전망이 우세하지만, 시장은 9월 인상 가능성을 약 60~65% 반영 중.",
            "• BoJ 위험도 10월보다 먼저 9월 17~18일 회의가 핵심. 1.00→1.25% 인상 기대가 커지면 엔캐리 청산이 위험자산 변동성을 키울 수 있음.",
            "",
            "역풍·반대 시나리오",
            "• 유가가 빠르게 안정되고 근원물가·임금이 둔화하면 추가 인상 기대가 후퇴해 주식 할인율 충격도 완화될 수 있음.",
            "",
            "다음 확인: Fed 9/15~16 → BoJ 9/17~18 → ECB 추가 인상 신호와 유가·장기금리.",
            "출처: ECB 공식 통화정책 결정, Reuters 2026-09-10.",
        ])
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body[:4096] + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps({
            "type": "manual_global_rates",
            "id": manual_id,
            "ecb_deposit_rate": 2.50,
            "ecb_hike_bp": 25,
            "ytd_hikes": {"RBA": 3, "BOK": 2, "ECB": 2, "BOJ": 1},
            "checked_at_kst": now_kst,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        state["manual_global_rates_alert_id"] = manual_id
        state["last_checked_kst"] = now_kst
        NEXT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text(
            "# 글로벌 금리 수동 검증 알림\n\n"
            f"- 조회시각: {now_kst}\n"
            "- ECB 예금금리: 2.50%\n"
            "- 알림 생성: 예\n",
            encoding="utf-8",
        )
        return 0

    t5_text = fetch(TABLE5)
    t3_text = fetch(TABLE3)
    months, t5 = parse_table5(t5_text)
    latest = months[0]
    t3 = parse_table3(t3_text, latest)

    alerts: list[tuple[str, str, dict]] = []
    if state.get("last_tic_month") != latest:
        alerts.append(build_tic_alert(months, t5, t3))

    h41 = None
    try:
        h41 = parse_h41(fetch(H41))
    except Exception:
        h41 = None

    h41_history = list(state.get("h41_history", []))
    if h41 and (not h41_history or h41_history[-1].get("date") != h41.get("date")):
        h41_history.append(h41)
        h41_history = h41_history[-8:]
        four_week = None
        if len(h41_history) >= 5:
            four_week = float(h41_history[-1]["value_bn"]) - float(h41_history[-5]["value_bn"])
        material = abs(float(h41["weekly_bn"])) >= 20 or (four_week is not None and abs(four_week) >= 50)
        if material and not alerts:
            direction = "감소" if float(h41["weekly_bn"]) < 0 else "증가"
            title = "🇺🇸 Fed 해외 공식계정 미 국채 보관잔액 급변"
            body_lines = [
                title,
                "",
                "핵심 판단",
                f"해외 공식·국제계정의 시장성 미 국채 보관잔액이 한 주 {fmt_bn(abs(float(h41['weekly_bn'])))} {direction}했습니다.",
                "TIC보다 좁은 범위의 주간 신호이므로 실제 국가별 매매와 동일시하지 않습니다.",
                "",
                "현재 숫자",
                f"• 보관잔액: {fmt_bn(float(h41['value_bn']))}",
                f"• 주간 변화: {fmt_bn(float(h41['weekly_bn']), signed=True)}",
                f"• 전년 대비: {fmt_bn(float(h41['yoy_bn']), signed=True)}",
            ]
            if four_week is not None:
                body_lines.append(f"• 4주 변화: {fmt_bn(four_week, signed=True)}")
            body_lines += [
                "",
                "시장 의미",
                "• 지속 감소면 해외 공식수요 약화 가능성 → 민간이 더 많은 국채를 흡수해야 해 기간 프리미엄 상승 압력.",
                "• 단 한 주 변화는 결제·보관 이동일 수 있어 월간 TIC와 국채 입찰로 확인합니다.",
                "",
                f"원문: {H41}",
            ]
            alerts.append((title, "\n".join(body_lines), {"type": "h41", **h41, "four_week_bn": four_week}))

    state["last_checked_kst"] = datetime.now(KST).isoformat(timespec="seconds")
    state["h41_history"] = h41_history
    if alerts:
        title, body, detail = alerts[0]
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body[:4096] + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if detail.get("type") == "tic":
            state["pending_tic_month"] = detail.get("month")
    NEXT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# 미 국채 해외수요 점검\n\n"
        f"- 조회시각: {state['last_checked_kst']}\n"
        f"- 최신 TIC 월: {latest}\n"
        f"- 알림 생성: {'예' if alerts else '아니오'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
