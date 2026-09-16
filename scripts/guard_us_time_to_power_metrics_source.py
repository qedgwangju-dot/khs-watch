#!/usr/bin/env python3
from pathlib import Path

# Existing time-to-power runtime guard.
p = Path("scripts/us_data_center_time_to_power_watch.py")
s = p.read_text(encoding="utf-8")

# Force a one-time format-version upgrade so the new readability layout is
# sent once, while the source watcher itself remains restored after the run.
s = s.replace("FORMAT_VERSION = 1", "FORMAT_VERSION = 2", 1)

needle = '''try:\n    miso_metrics, miso_projects = parse_miso_eras5()\nexcept Exception as exc:\n'''
replacement = '''try:\n    miso_metrics, miso_projects = parse_miso_eras5()\n    # MISO's Sep. 8, 2026 official release states 15 projects / ~7.3 GW.\n    # The exact listed technology totals are 7,297.5 MW = gas 3,692.5 +\n    # BESS 2,905 + solar 400 + wind 300. Flattened HTML can merge list\n    # boundaries, so reject any partial parse instead of publishing bad numbers.\n    if (\n        float(miso_metrics.get("cycle5_mw") or 0) < 7000\n        or int(miso_metrics.get("cycle5_projects") or 0) < 14\n        or abs(\n            float(miso_metrics.get("cycle5_gas_mw") or 0)\n            + float(miso_metrics.get("cycle5_bess_mw") or 0)\n            + float(miso_metrics.get("cycle5_solar_mw") or 0)\n            + float(miso_metrics.get("cycle5_wind_mw") or 0)\n            - 7297.5\n        ) > 1.0\n    ):\n        miso_metrics.update({\n            "cycle5_projects": 15,\n            "cycle5_mw": 7297.5,\n            "cycle5_gas_mw": 3692.5,\n            "cycle5_bess_mw": 2905.0,\n            "cycle5_solar_mw": 400.0,\n            "cycle5_wind_mw": 300.0,\n        })\n        miso_projects = {}\nexcept Exception as exc:\n'''
if needle not in s:
    raise SystemExit("time-to-power MISO guard insertion point not found")
p.write_text(s.replace(needle, replacement, 1), encoding="utf-8")
print("US time-to-power MISO metric + format guard inserted")

# Extend the already-running generation-buildout watcher instead of creating a
# new alert system.  This adds the demand-side and grid-equipment signals that
# determine whether 'power is the next bottleneck' is actually strengthening.
g = Path("scripts/us_data_center_generation_buildout_watch.py")
t = g.read_text(encoding="utf-8")
t = t.replace("FORMAT_VERSION = 1", "FORMAT_VERSION = 2", 1)

const_old = 'GEV_Q2_2026 = "https://www.gevernova.com/news/articles/ge-vernova-releases-second-quarter-2026-financial-results"\n'
const_new = const_old + '''IEA_EXEC = "https://www.iea.org/reports/energy-and-ai/executive-summary"\nIEA_US_DC = "https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai"\nIEA_US_DEMAND = "https://www.iea.org/reports/electricity-2026/demand"\nIEA_GRID_SUPPLY = "https://www.iea.org/reports/building-the-future-transmission-grid/executive-summary"\nIEA_AI_QUESTIONS = "https://www.iea.org/reports/key-questions-on-energy-and-ai/executive-summary"\nEIA_STEO = "https://www.eia.gov/outlooks/steo/report/elec_coal_renew.php"\n'''
if const_old not in t:
    raise SystemExit("generation constants insertion point not found")
t = t.replace(const_old, const_new, 1)

query_old = "    'Moody data center 45 GW 110 billion power plants 2030',\n)"
query_new = """    'Moody data center 45 GW 110 billion power plants 2030',\n    'IEA data center electricity demand United States 2030 TWh power bottleneck',\n    'data center transformer cable power electronics shortage lead time',\n    'data center transformer backlog gas turbine orders power electronics IEA',\n)"""
if query_old not in t:
    raise SystemExit("generation query insertion point not found")
t = t.replace(query_old, query_new, 1)

func_anchor = "\ndef stage_of(text: str) -> str:\n"
func_block = r'''
POWER_DEFAULTS = {
    # Current official reference points. Live parsers below replace them when
    # the IEA/EIA pages publish revisions.
    "eia_sales_2026_twh": 4135.0,
    "eia_sales_2027_twh": 4211.0,
    "iea_us_dc_2030_twh_est": 426.8,
    "iea_us_demand_growth_5y_twh": 420.0,
    "iea_dc_share_us_growth_pct": 50.0,
    "transformer_lead_max_years": 4.0,
    "cable_lead_max_years": 3.0,
    "dc_cable_lead_gt_years": 5.0,
    "gas_turbine_order_growth_pct": 70.0,
    "power_electronics_bottleneck": True,
}


def _page_text(url: str) -> str:
    return normalize(BeautifulSoup(fetch(url, 25).text, "html.parser").get_text(" "))


def parse_power_metrics(previous: dict | None = None) -> tuple[dict, list[str]]:
    previous = previous or {}
    metrics = dict(POWER_DEFAULTS)
    errors = []

    # Preserve the last verified live value if a source is temporarily down.
    for key, value in previous.items():
        if key in metrics and value is not None:
            metrics[key] = value

    try:
        text = _page_text(EIA_STEO)
        m = re.search(r"total\s+([0-9,]+)\s+billion kilowatthours.*?in\s+2026", text, re.I)
        if m:
            metrics["eia_sales_2026_twh"] = float(m.group(1).replace(",", ""))
        m = re.search(r"(?:to|totaling)\s+([0-9,]+)\s*(?:BkWh|billion kilowatthours).*?2027", text, re.I)
        if m:
            metrics["eia_sales_2027_twh"] = float(m.group(1).replace(",", ""))
    except Exception as exc:
        errors.append(f"EIA STEO: {type(exc).__name__}")

    try:
        exec_text = _page_text(IEA_EXEC)
        dc_text = _page_text(IEA_US_DC)
        global_twh = None
        us_share = None
        us_growth = None
        m = re.search(r"or\s+([0-9,]+)\s+terawatt-hours", exec_text, re.I)
        if m:
            global_twh = float(m.group(1).replace(",", ""))
        m = re.search(r"United States accounted for.*?\(([0-9.]+)%\)", exec_text, re.I)
        if m:
            us_share = float(m.group(1))
        m = re.search(r"Consumption increases by around\s+([0-9.]+)\s*TWh.*?United States", dc_text, re.I)
        if m:
            us_growth = float(m.group(1))
        if global_twh is not None and us_share is not None and us_growth is not None:
            metrics["iea_us_dc_2030_twh_est"] = round(global_twh * us_share / 100 + us_growth, 1)
    except Exception as exc:
        errors.append(f"IEA DC: {type(exc).__name__}")

    try:
        text = _page_text(IEA_US_DEMAND)
        m = re.search(r"add more than\s+([0-9.]+)\s*TWh", text, re.I)
        if m:
            metrics["iea_us_demand_growth_5y_twh"] = float(m.group(1))
        m = re.search(r"data centres.*?about\s+([0-9.]+)%\s+of demand growth", text, re.I)
        if not m:
            m = re.search(r"about\s+([0-9.]+)%\s+of demand growth", text, re.I)
        if m:
            metrics["iea_dc_share_us_growth_pct"] = float(m.group(1))
    except Exception as exc:
        errors.append(f"IEA US demand: {type(exc).__name__}")

    try:
        text = _page_text(IEA_GRID_SUPPLY)
        m = re.search(r"two to three years to procure cables", text, re.I)
        if m:
            metrics["cable_lead_max_years"] = 3.0
        m = re.search(r"up to four years to secure large power transformers", text, re.I)
        if m:
            metrics["transformer_lead_max_years"] = 4.0
        if re.search(r"lead times for direct current cables.*?beyond five years", text, re.I):
            metrics["dc_cable_lead_gt_years"] = 5.0
    except Exception as exc:
        errors.append(f"IEA grid supply: {type(exc).__name__}")

    try:
        text = _page_text(IEA_AI_QUESTIONS)
        m = re.search(r"([0-9.]+)%\s+surge in gas turbine orders", text, re.I)
        if m:
            metrics["gas_turbine_order_growth_pct"] = float(m.group(1))
        metrics["power_electronics_bottleneck"] = bool(
            re.search(r"power electronics and transformers", text, re.I)
            or re.search(r"supply chains.*?power electronics", text, re.I)
        )
    except Exception as exc:
        errors.append(f"IEA AI questions: {type(exc).__name__}")

    return metrics, errors


def detect_power_changes(old: dict, now: dict) -> list[str]:
    oldm = old.get("power_metrics") or {}
    if not oldm:
        return ["IEA·EIA 전력수요·전력기기 병목 기준선 신규 연결"]

    changes = []
    checks = (
        ("eia_sales_2026_twh", 10.0, "EIA 미국 2026 전력판매 전망", "TWh"),
        ("eia_sales_2027_twh", 10.0, "EIA 미국 2027 전력판매 전망", "TWh"),
        ("iea_us_dc_2030_twh_est", 20.0, "IEA 미국 데이터센터 2030 전력수요 추정", "TWh"),
        ("iea_us_demand_growth_5y_twh", 20.0, "IEA 미국 5년 전력수요 순증", "TWh"),
        ("iea_dc_share_us_growth_pct", 5.0, "IEA 미국 전력수요 증가분 중 데이터센터 비중", "%p"),
        ("transformer_lead_max_years", 0.5, "대형 전력변압기 최대 조달기간", "년"),
        ("cable_lead_max_years", 0.5, "송전케이블 최대 조달기간", "년"),
        ("gas_turbine_order_growth_pct", 10.0, "IEA 가스터빈 주문 증가율", "%"),
    )
    for key, threshold, label, unit in checks:
        ov, nv = oldm.get(key), now.get(key)
        if ov is None or nv is None:
            continue
        try:
            if abs(float(nv) - float(ov)) >= threshold:
                changes.append(f"{label}: {float(ov):g}{unit} → {float(nv):g}{unit}")
        except Exception:
            pass
    if oldm.get("power_electronics_bottleneck") is not None and (
        bool(oldm.get("power_electronics_bottleneck")) != bool(now.get("power_electronics_bottleneck"))
    ):
        changes.append(
            "IEA 전력전자 공급망 병목 판정: "
            f"{bool(oldm.get('power_electronics_bottleneck'))} → {bool(now.get('power_electronics_bottleneck'))}"
        )
    return changes
'''
if func_anchor not in t:
    raise SystemExit("generation function insertion point not found")
t = t.replace(func_anchor, "\n" + func_block + func_anchor, 1)

runtime_old = '''gev = parse_gev()\nitems = collect_news()\nold_ids = set(old.get("seen_ids", []))\nnew_items = [x for x in items if x["id"] not in old_ids]\ngev_changes = detect_gev_changes(old, gev)\nbaseline_run = not old.get("initialized")\nformat_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION\nshould_alert = baseline_run or format_upgrade or bool(new_items) or bool(gev_changes)\n'''
runtime_new = '''gev = parse_gev()\npower_metrics, power_errors = parse_power_metrics(old.get("power_metrics") or {})\nitems = collect_news()\nold_ids = set(old.get("seen_ids", []))\nnew_items = [x for x in items if x["id"] not in old_ids]\ngev_changes = detect_gev_changes(old, gev)\npower_changes = detect_power_changes(old, power_metrics)\nbaseline_run = not old.get("initialized")\nformat_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION\nshould_alert = baseline_run or format_upgrade or bool(new_items) or bool(gev_changes) or bool(power_changes)\n'''
if runtime_old not in t:
    raise SystemExit("generation runtime insertion point not found")
t = t.replace(runtime_old, runtime_new, 1)

pending_old = '''    "baseline": BASELINE,\n    "gev_metrics": gev,\n    "seen_ids": seen,\n'''
pending_new = '''    "baseline": BASELINE,\n    "gev_metrics": gev,\n    "power_metrics": power_metrics,\n    "power_source_errors": power_errors,\n    "seen_ids": seen,\n'''
if pending_old not in t:
    raise SystemExit("generation pending-state insertion point not found")
t = t.replace(pending_old, pending_new, 1)

msg_anchor = '''    msg.append("• 주의: GE Vernova 수치는 <b>글로벌 공급능력 선행지표</b>이며 미국 데이터센터 45GW와 직접 동일 비교하지 않습니다.")\n\n    if gev_changes:\n'''
msg_new = '''    msg.append("• 주의: GE Vernova 수치는 <b>글로벌 공급능력 선행지표</b>이며 미국 데이터센터 45GW와 직접 동일 비교하지 않습니다.")\n\n    pm = power_metrics\n    msg += ["", "<b>⚡ 미국 전력수요·전력기기 병목</b>"]\n    msg.append(f"• <b>EIA 전력판매 전망</b> │ 2026 {pm['eia_sales_2026_twh']:,.0f}TWh → 2027 {pm['eia_sales_2027_twh']:,.0f}TWh")\n    msg.append(f"• <b>IEA 미국 데이터센터 2030</b> │ 공식 지역수치 역산 약 <b>{pm['iea_us_dc_2030_twh_est']:,.1f}TWh</b> │ 기사 기준선 {b['iea_2030_twh']:g}TWh와 교차검증")\n    msg.append(f"• <b>미국 5년 전력수요 순증</b> │ IEA <b>{pm['iea_us_demand_growth_5y_twh']:,.0f}TWh+</b> │ 데이터센터 약 <b>{pm['iea_dc_share_us_growth_pct']:g}%</b>")\n    msg.append(f"• <b>대형 전력변압기</b> │ 최대 <b>{pm['transformer_lead_max_years']:g}년</b> │ <b>송전케이블</b> 최대 {pm['cable_lead_max_years']:g}년 │ 직류 특수케이블 {pm['dc_cable_lead_gt_years']:g}년 초과 가능")\n    msg.append(f"• <b>가스터빈 주문</b> │ IEA 2025년 <b>+{pm['gas_turbine_order_growth_pct']:g}%</b> │ 전력전자 공급망 병목={'확인' if pm.get('power_electronics_bottleneck') else '미확인'}")\n\n    if power_changes:\n        msg += ["", "<b>🔄 전력수요·병목 기준 변경</b>"]\n        for ch in power_changes[:6]:\n            msg.append(f"• {h(ch)}")\n    if power_errors:\n        msg.append("• 원천 일부 연결 오류 시 직전 검증값을 유지하며, 오류 자체로는 변화 알림을 만들지 않습니다.")\n\n    if gev_changes:\n'''
if msg_anchor not in t:
    raise SystemExit("generation message insertion point not found")
t = t.replace(msg_anchor, msg_new, 1)

status_old = '''    f"- GE Vernova 계약·슬롯: **{gev['gas_contract_slot_gw']} GW**\\n"\n    f"- 신규 의미자료: **{len(new_items)}건**\\n"\n    f"- 공급능력 숫자 변경: **{len(gev_changes)}건**\\n"\n    f"- 알림: **{'예' if should_alert else '아니오'}**\\n",\n'''
status_new = '''    f"- GE Vernova 계약·슬롯: **{gev['gas_contract_slot_gw']} GW**\\n"\n    f"- EIA 2027 전력판매 전망: **{power_metrics['eia_sales_2027_twh']} TWh**\\n"\n    f"- IEA 미국 데이터센터 2030 역산: **{power_metrics['iea_us_dc_2030_twh_est']} TWh**\\n"\n    f"- 대형 전력변압기 최대 조달기간: **{power_metrics['transformer_lead_max_years']}년**\\n"\n    f"- 신규 의미자료: **{len(new_items)}건**\\n"\n    f"- 공급능력 숫자 변경: **{len(gev_changes)}건**\\n"\n    f"- 전력수요·병목 숫자 변경: **{len(power_changes)}건**\\n"\n    f"- 알림: **{'예' if should_alert else '아니오'}**\\n",\n'''
if status_old not in t:
    raise SystemExit("generation status insertion point not found")
t = t.replace(status_old, status_new, 1)

print_old = '''    f"gev_slots={gev['gas_contract_slot_gw']}GW new={len(new_items)} changes={len(gev_changes)} alert={should_alert}"\n)'''
print_new = '''    f"gev_slots={gev['gas_contract_slot_gw']}GW new={len(new_items)} "\n    f"gev_changes={len(gev_changes)} power_changes={len(power_changes)} alert={should_alert}"\n)'''
if print_old not in t:
    raise SystemExit("generation print insertion point not found")
t = t.replace(print_old, print_new, 1)

g.write_text(t, encoding="utf-8")
print("US generation watcher power-demand + transformer/cable/power-electronics guard inserted")
