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

# Add PwC recurring-capex structure and Korean power-equipment direct-order
# signals to the SAME generation-buildout watcher. No new workflow/state/route.
t = g.read_text(encoding="utf-8")
t = t.replace("FORMAT_VERSION = 2", "FORMAT_VERSION = 3", 1)

baseline_old = '''    "incremental_gas_bcf_day": 4.0,
}'''
baseline_new = '''    "incremental_gas_bcf_day": 4.0,
    "pwc_total_2026_2050_usd_t": 31.6,
    "pwc_upside_usd_t": 50.0,
    "pwc_annual_2026_usd_b": 800.0,
    "pwc_annual_2030_usd_b": 1100.0,
    "pwc_annual_2050_usd_b": 1800.0,
    "pwc_ict_share_2026_pct": 70.0,
    "pwc_ict_share_2050_pct": 93.0,
    "pwc_refresh_low_years": 4.0,
    "pwc_refresh_high_years": 6.0,
    "pwc_rounds_low": 3.0,
    "pwc_rounds_high": 5.0,
    "hyosung_dc_order_krw_eok": 3865.0,
    "hd_hyundai_dc_framework_krw_eok": 11212.0,
    "hd_hyundai_delivery_year": 2028.0,
    "ls_bloom_dc_order_krw_eok": 3190.0,
    "ls_apr_dc_order_krw_eok": 1703.0,
    "ls_may_dc_order_krw_eok": 1050.0,
}'''
if baseline_old not in t:
    raise SystemExit("generation capex baseline insertion point not found")
t = t.replace(baseline_old, baseline_new, 1)

trusted_old = '''    "bloombergtax.com", "advisorperspectives.com",
)'''
trusted_new = '''    "bloombergtax.com", "advisorperspectives.com", "pwc.com",
    "hyosung.com", "hd-hyundaielectric.com", "hyundai-elec.co.kr", "ls-electric.com",
)'''
if trusted_old not in t:
    raise SystemExit("generation trusted domains insertion point not found")
t = t.replace(trusted_old, trusted_new, 1)

query_old = '''    'data center transformer backlog gas turbine orders power electronics IEA',
)'''
query_new = '''    'data center transformer backlog gas turbine orders power electronics IEA',
    'PwC data centre capex ICT equipment 4 6 years 2050',
    'Hyosung Heavy Industries AI data center transformer order United States',
    'HD Hyundai Electric data center transformer switchgear order North America',
    'LS ELECTRIC data center transformer switchgear order North America',
)'''
if query_old not in t:
    raise SystemExit("generation capex query insertion point not found")
t = t.replace(query_old, query_new, 1)

source_old = '''        ("advisorperspectives", "Bloomberg"),
    ):'''
source_new = '''        ("advisorperspectives", "Bloomberg"), ("pwc", "PwC"),
        ("hyosung", "효성중공업"), ("hyundai", "HD현대일렉트릭"), ("ls-electric", "LS ELECTRIC"),
    ):'''
if source_old not in t:
    raise SystemExit("generation source-label insertion point not found")
t = t.replace(source_old, source_new, 1)

func_anchor = "\ndef stage_of(text: str) -> str:\n"
supplier_func = r'''
SUPPLIER_NEWS_PAGES = (
    ("https://www.hyosung.com/kr/newsroom", "효성중공업"),
    ("https://hyundai-elec.co.kr/elect/ko/PR/newsList.jsp", "HD현대일렉트릭"),
    ("https://nahpdev-web.ls-electric.com/markets/data-center", "LS ELECTRIC"),
)


def collect_supplier_official_updates():
    out = []
    for url, source in SUPPLIER_NEWS_PAGES:
        try:
            soup = BeautifulSoup(fetch(url, 25).text, "html.parser")
        except Exception:
            continue
        for link in soup.find_all("a", href=True):
            title = normalize(link.get_text(" "))
            low = title.lower()
            if not title:
                continue
            if not any(k in low for k in ("data center", "데이터센터", "ai data", "ai 데이터")):
                continue
            if not any(k in low for k in ("order", "contract", "supply", "수주", "계약", "공급", "transformer", "변압기", "switchgear", "배전")):
                continue
            href = urllib.parse.urljoin(url, link.get("href") or "")
            out.append({
                "id": sig(source, title, href),
                "title": title,
                "url": href,
                "source": source,
                "stage": stage_of(title),
                "scale_mw": extract_scale_mw(title),
            })
    return list({x["id"]: x for x in out}.values())

'''
if func_anchor not in t:
    raise SystemExit("generation supplier collector insertion point not found")
t = t.replace(func_anchor, "\n" + supplier_func + func_anchor, 1)

meaning_old = '''    if "ge vernova" in low and any(k in low for k in ("gas turbine", "slot", "data center", "data centre")):
        return True
    if not any(k in low for k in ("data center", "data centre", "hyperscaler", "ai campus", "ai factory")):
'''
meaning_new = '''    if "ge vernova" in low and any(k in low for k in ("gas turbine", "slot", "data center", "data centre")):
        return True
    if "pwc" in low and any(k in low for k in ("data center", "data centre")) and any(k in low for k in ("capex", "ict", "2050", "investment")):
        return True
    if any(k in low for k in ("hyosung", "효성중공업", "hd hyundai", "hd현대일렉트릭", "ls electric")) and any(k in low for k in ("data center", "data centre", "데이터센터")) and any(k in low for k in ("order", "contract", "supply", "수주", "계약", "공급")):
        return True
    if not any(k in low for k in ("data center", "data centre", "hyperscaler", "ai campus", "ai factory")):
'''
if meaning_old not in t:
    raise SystemExit("generation capex meaningful insertion point not found")
t = t.replace(meaning_old, meaning_new, 1)

items_old = "items = collect_news()\n"
items_new = "items = collect_news() + collect_supplier_official_updates()\n"
if items_old not in t:
    raise SystemExit("generation supplier items insertion point not found")
t = t.replace(items_old, items_new, 1)

msg_anchor = '''    if gev_changes:
        msg += ["", "<b>🔄 공급능력 숫자 변경</b>"]
'''
msg_new = '''    msg += ["", "<b>💻 반복 장비투자·한국 전력기기 실수주</b>"]
    msg.append(f"• <b>PwC 누적 자본투자</b> │ 2026~2050 {b['pwc_total_2026_2050_usd_t']:g}조달러 │ AI 가속 상단 약 {b['pwc_upside_usd_t']:g}조달러")
    msg.append(f"• <b>연간 자본투자</b> │ 2026 {b['pwc_annual_2026_usd_b']:,.0f}십억달러 → 2030 {b['pwc_annual_2030_usd_b']:,.0f}십억달러 → 2050 {b['pwc_annual_2050_usd_b']:,.0f}십억달러")
    msg.append(f"• <b>ICT 장비 비중</b> │ 2026 {b['pwc_ict_share_2026_pct']:g}% → 2050 {b['pwc_ict_share_2050_pct']:g}% │ GPU·서버 교체 {b['pwc_refresh_low_years']:g}~{b['pwc_refresh_high_years']:g}년 · 20년 자산에서 {b['pwc_rounds_low']:g}~{b['pwc_rounds_high']:g}회")
    msg.append(f"• <b>효성중공업</b> │ 미국 AI 데이터센터 초고압변압기 <b>{b['hyosung_dc_order_krw_eok']:,.0f}억원</b> 직접 수주")
    msg.append(f"• <b>HD현대일렉트릭</b> │ 북미 데이터센터 장기 기본계약 최대 <b>{b['hd_hyundai_dc_framework_krw_eok']:,.0f}억원</b> │ 실제 개별 발주는 분할 · {int(b['hd_hyundai_delivery_year'])}년까지 순차 납품")
    msg.append(f"• <b>LS ELECTRIC</b> │ 뉴멕시코 {b['ls_bloom_dc_order_krw_eok']:,.0f}억원 · 북미 {b['ls_apr_dc_order_krw_eok']:,.0f}억원 · 미국 빅테크 {b['ls_may_dc_order_krw_eok']:,.0f}억원의 확인된 프로젝트를 각각 추적")
    msg.append("• <b>판정:</b> PwC 전망은 시장 기준선, 기업 수주는 확정 매출 연결 후보로 분리합니다. 기본계약 상단을 실제 발주액과 동일시하지 않습니다.")

    if gev_changes:
        msg += ["", "<b>🔄 공급능력 숫자 변경</b>"]
'''
if msg_anchor not in t:
    raise SystemExit("generation capex message insertion point not found")
t = t.replace(msg_anchor, msg_new, 1)

status_old = '''    f"- 대형 전력변압기 최대 조달기간: **{power_metrics['transformer_lead_max_years']}년**\n"
    f"- 신규 의미자료: **{len(new_items)}건**\n"
'''
status_new = '''    f"- 대형 전력변압기 최대 조달기간: **{power_metrics['transformer_lead_max_years']}년**\n"
    f"- PwC 2026~2050 누적 자본투자 기준: **{BASELINE['pwc_total_2026_2050_usd_t']}조달러**\n"
    f"- PwC ICT 장비 비중: **{BASELINE['pwc_ict_share_2026_pct']}% → {BASELINE['pwc_ict_share_2050_pct']}%**\n"
    f"- 신규 의미자료: **{len(new_items)}건**\n"
'''
if status_old in t:
    t = t.replace(status_old, status_new, 1)

g.write_text(t, encoding="utf-8")
print("US generation watcher recurring-capex + Korean supplier-order guard inserted")

# Extend the existing time-to-power watcher with flexible-load / demand-response
# signals.  This remains part of the same watcher and state file: no new alert
# workflow or Telegram route is created.
s = p.read_text(encoding="utf-8")
s = s.replace("FORMAT_VERSION = 2", "FORMAT_VERSION = 3", 1)

flex_const_anchor = 'ABB_800V = "https://www.abb.com/global/en/company/innovation/hybrid-ac-dc-power"\n'
flex_const_block = flex_const_anchor + '''AEMA_HOME = "https://www.aema.ai/home"\nAEMA_ABOUT = "https://www.aema.ai/about"\nAEMA_SOLUTIONS = "https://www.aema.ai/solutions"\nGOOGLE_DEMAND_RESPONSE = "https://blog.google/innovation-and-ai/infrastructure-and-cloud/global-network/demand-response-data-center-milestone/"\nNVIDIA_EMERALD = "https://www.nvidia.com/en-us/case-studies/emerald-ai/"\nNVIDIA_AEMA = "https://blogs.nvidia.com/blog/ai-energy-management-alliance/"\nGRIDUNITY_AEMA = "https://www.gridunity.com/resources/gridunity-selected-as-founding-board-member-of-new-ai-energy-management-alliance"\n'''
if flex_const_anchor not in s:
    raise SystemExit("time-to-power flexible-load constants insertion point not found")
s = s.replace(flex_const_anchor, flex_const_block, 1)

official_old = '''    "abb.com", "nvidia.com", "eaton.com", "lguplus.com", "ls-electric.com",\n)'''
official_new = '''    "abb.com", "nvidia.com", "eaton.com", "lguplus.com", "ls-electric.com",\n    "aema.ai", "blog.google", "gridunity.com", "epri.com", "pjm.com",\n)'''
if official_old not in s:
    raise SystemExit("time-to-power official domains insertion point not found")
s = s.replace(official_old, official_new, 1)

queries_old = '''    'data center onsite power gas generation BESS 500 MW ERCOT MISO PJM',\n)'''
queries_new = '''    'data center onsite power gas generation BESS 500 MW ERCOT MISO PJM',\n    'AI data center flexible load demand response interconnection utility 100 MW',\n    'AEMA flexible AI data center accelerated interconnection demand response',\n    'NVIDIA DSX Flex Emerald Conductor grid-responsive data center utility',\n    'Google data center demand response utility contract flexible load',\n)'''
if queries_old not in s:
    raise SystemExit("time-to-power flexible-load query insertion point not found")
s = s.replace(queries_old, queries_new, 1)

fallback_old = '''        "발전·BESS 프로젝트": "데이터센터 연계 발전·BESS 프로젝트 관련 신규 자료",\n    }'''
fallback_new = '''        "발전·BESS 프로젝트": "데이터센터 연계 발전·BESS 프로젝트 관련 신규 자료",\n        "유연부하·수요반응": "AI 데이터센터 유연부하·수요반응·신속 계통접속 관련 신규 자료",\n    }'''
if fallback_old not in s:
    raise SystemExit("time-to-power fallback label insertion point not found")
s = s.replace(fallback_old, fallback_new, 1)

source_old = '''        ("lguplus", "LG유플러스"), ("ls-electric", "LS ELECTRIC"),\n    )'''
source_new = '''        ("lguplus", "LG유플러스"), ("ls-electric", "LS ELECTRIC"),\n        ("aema", "AEMA"), ("blog.google", "Google"), ("gridunity", "GridUnity"),\n    )'''
if source_old not in s:
    raise SystemExit("time-to-power source label insertion point not found")
s = s.replace(source_old, source_new, 1)

classify_old = '''def classify(text: str) -> str:\n    low = (text or "").lower()\n    if "800v" in low and any(k in low for k in ("dc", "direct current", "data center", "data centre", "rack")):\n'''
classify_new = '''def classify(text: str) -> str:\n    low = (text or "").lower()\n    if any(k in low for k in (\n        "ai energy management alliance", "aema", "dsx flex", "emerald conductor",\n        "grid-responsive", "power-flexible", "flexible load", "flexible-load",\n        "demand response", "workload shifting", "computational flexibility",\n        "accelerated interconnection", "expedited interconnection", "flexibility commitment",\n    )):\n        return "유연부하·수요반응"\n    if "800v" in low and any(k in low for k in ("dc", "direct current", "data center", "data centre", "rack")):\n'''
if classify_old not in s:
    raise SystemExit("time-to-power classify insertion point not found")
s = s.replace(classify_old, classify_new, 1)

meaningful_old = '''    if item.get("official") and theme != "기타":\n        return True\n    if theme == "800V DC":\n'''
meaningful_new = '''    if item.get("official") and theme not in {"기타", "유연부하·수요반응"}:\n        return True\n    if theme == "유연부하·수요반응":\n        execution = any(k in text for k in (\n            "contract", "agreement", "signed", "approved", "adopt", "tariff", "program",\n            "pilot", "demonstrat", "commercial", "standard", "rule", "interconnection",\n            "launch", "founding", "board member", "mw", "gw", "계약", "승인", "실증", "상업",\n        ))\n        scale_mw = [float(x.replace(",", "")) for x in re.findall(r"([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*mw", text, re.I)]\n        scale_gw = [float(x.replace(",", "")) * 1000 for x in re.findall(r"([0-9]+(?:\\.[0-9]+)?)\\s*gw", text, re.I)]\n        scale = max(scale_mw + scale_gw + [0])\n        policy_step = any(k in text for k in (\n            "tariff", "rule", "approved", "adopt", "interconnection", "utility", "ferc", "pjm", "miso", "ercot",\n        ))\n        return execution and (item.get("official") or scale >= 100 or policy_step)\n    if theme == "800V DC":\n'''
if meaningful_old not in s:
    raise SystemExit("time-to-power meaningful insertion point not found")
s = s.replace(meaningful_old, meaningful_new, 1)

flex_func_anchor = '''def detect_metric_changes(old: dict, metrics: dict, projects: dict) -> list[str]:\n'''
flex_func_block = r'''
FLEX_DEFAULTS = {
    # Current official proof points.  100 GW is AEMA's potential estimate,
    # not contracted or energized capacity.
    "google_demand_response_gw": 1.0,
    "commercial_flexible_factory_mw": 100.0,
    "emerald_max_reduction_pct": 40.0,
    "emerald_30s_reduction_pct": 30.0,
    "emerald_max_duration_hours": 10.0,
    "aema_unlock_potential_gw": 100.0,
    "interconnection_backlog_low_years": 5.0,
    "interconnection_backlog_high_years": 10.0,
}


def _flex_page_text(url: str) -> str:
    return normalize(BeautifulSoup(fetch(url, 25).text, "html.parser").get_text(" "))


def parse_flexible_load_metrics(previous: dict | None = None) -> tuple[dict, list[str]]:
    previous = previous or {}
    metrics = dict(FLEX_DEFAULTS)
    errors = []
    for key, value in previous.items():
        if key in metrics and value is not None:
            metrics[key] = value

    try:
        text = _flex_page_text(GOOGLE_DEMAND_RESPONSE)
        m = re.search(r"(?:total of\s+)?([0-9.]+)\s+gigawatt\s*\(GW\).*?demand response", text, re.I)
        if not m:
            m = re.search(r"signed\s+([0-9.]+)\s+GW\s+of data center demand response", text, re.I)
        if m:
            metrics["google_demand_response_gw"] = float(m.group(1))
    except Exception as exc:
        errors.append(f"Google 수요반응: {type(exc).__name__}")

    try:
        text = _flex_page_text(NVIDIA_EMERALD)
        m = re.search(r"up to\s+([0-9.]+)%\s+power reduction", text, re.I)
        if not m:
            m = re.search(r"reduce power demand by up to\s+([0-9.]+)%", text, re.I)
        if m:
            metrics["emerald_max_reduction_pct"] = float(m.group(1))
        m = re.search(r"shed approximately\s+([0-9.]+)%.*?within\s+30 seconds", text, re.I)
        if m:
            metrics["emerald_30s_reduction_pct"] = float(m.group(1))
        m = re.search(r"for up to\s+([0-9.]+)\s+hours", text, re.I)
        if m:
            metrics["emerald_max_duration_hours"] = float(m.group(1))
    except Exception as exc:
        errors.append(f"NVIDIA·Emerald AI: {type(exc).__name__}")

    try:
        text = _flex_page_text(AEMA_SOLUTIONS)
        m = re.search(r"([0-9,]+)\s*-?MW\s+power-flexible AI factory", text, re.I)
        if m:
            metrics["commercial_flexible_factory_mw"] = float(m.group(1).replace(",", ""))
        m = re.search(r"unlock\s+([0-9,]+)\s*GW", text, re.I)
        if m:
            metrics["aema_unlock_potential_gw"] = float(m.group(1).replace(",", ""))
    except Exception as exc:
        errors.append(f"AEMA solutions: {type(exc).__name__}")

    try:
        text = _flex_page_text(AEMA_ABOUT)
        m = re.search(r"([0-9.]+)\s*[–-]\s*([0-9.]+)\s+year interconnection backlog", text, re.I)
        if m:
            metrics["interconnection_backlog_low_years"] = float(m.group(1))
            metrics["interconnection_backlog_high_years"] = float(m.group(2))
    except Exception as exc:
        errors.append(f"AEMA about: {type(exc).__name__}")

    return metrics, errors


def detect_flexible_load_changes(old: dict, now: dict) -> list[str]:
    oldm = old.get("flexible_load_metrics") or {}
    if not oldm:
        return ["유연부하·수요반응 기준선 신규 연결"]
    changes = []
    checks = (
        ("google_demand_response_gw", 0.1, "Google 상업 수요반응 계약", "GW"),
        ("commercial_flexible_factory_mw", 50.0, "상업 규모 유연 AI 팩토리 실증", "MW"),
        ("emerald_max_reduction_pct", 5.0, "Emerald AI 최대 부하감축", "%"),
        ("emerald_30s_reduction_pct", 5.0, "Emerald AI 30초 감축", "%"),
        ("emerald_max_duration_hours", 1.0, "Emerald AI 최대 감축 지속시간", "시간"),
        ("aema_unlock_potential_gw", 10.0, "AEMA 기존 전력망 활용 잠재치", "GW"),
        ("interconnection_backlog_high_years", 1.0, "AEMA 주요시장 계통접속 적체 상단", "년"),
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
    return changes


'''
if flex_func_anchor not in s:
    raise SystemExit("time-to-power flexible metrics function insertion point not found")
s = s.replace(flex_func_anchor, flex_func_block + flex_func_anchor, 1)

runtime_anchor = '''items: list[dict] = []\n'''
runtime_insert = '''flexible_load_metrics, flexible_load_errors = parse_flexible_load_metrics(old.get("flexible_load_metrics") or {})\nerrors.extend(flexible_load_errors)\n\nitems: list[dict] = []\n'''
if runtime_anchor not in s:
    raise SystemExit("time-to-power flexible runtime insertion point not found")
s = s.replace(runtime_anchor, runtime_insert, 1)

change_old = '''metric_changes = detect_metric_changes(old, miso_metrics, miso_projects)\nbaseline_run = not old.get("initialized")\nformat_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION\nshould_alert = baseline_run or format_upgrade or bool(new_items) or bool(metric_changes)\n'''
change_new = '''metric_changes = detect_metric_changes(old, miso_metrics, miso_projects)\nflexible_load_changes = detect_flexible_load_changes(old, flexible_load_metrics)\nbaseline_run = not old.get("initialized")\nformat_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION\nshould_alert = baseline_run or format_upgrade or bool(new_items) or bool(metric_changes) or bool(flexible_load_changes)\n'''
if change_old not in s:
    raise SystemExit("time-to-power flexible change insertion point not found")
s = s.replace(change_old, change_new, 1)

pending_old2 = '''    "miso_metrics": miso_metrics,\n    "miso_eras_projects": miso_projects,\n    "seen_ids": seen,\n'''
pending_new2 = '''    "miso_metrics": miso_metrics,\n    "miso_eras_projects": miso_projects,\n    "flexible_load_metrics": flexible_load_metrics,\n    "flexible_load_source_errors": flexible_load_errors,\n    "seen_ids": seen,\n'''
if pending_old2 not in s:
    raise SystemExit("time-to-power flexible pending-state insertion point not found")
s = s.replace(pending_old2, pending_new2, 1)

msg_anchor2 = '''    msg.append("• <b>800V DC</b> · 기사량이 아니라 고객 채택·양산·수주·인증·검증만 알림")\n\n    if metric_changes:\n'''
msg_new2 = '''    msg.append("• <b>800V DC</b> · 기사량이 아니라 고객 채택·양산·수주·인증·검증만 알림")\n\n    fm = flexible_load_metrics\n    msg += ["", "<b>🧠 유연부하·수요반응 실행판</b>"]\n    msg.append(f"• <b>Google 상업 계약</b> · 미국 유틸리티 수요반응 누적 <b>{fm['google_demand_response_gw']:g}GW</b>")\n    msg.append(f"• <b>상업 규모 실증</b> · 유연 AI 팩토리 <b>{fm['commercial_flexible_factory_mw']:,.0f}MW</b>")\n    msg.append(f"• <b>부하감축 성능</b> · 최대 <b>{fm['emerald_max_reduction_pct']:g}%</b> 1분 이내 · 약 {fm['emerald_30s_reduction_pct']:g}% 30초 · 최대 {fm['emerald_max_duration_hours']:g}시간")\n    msg.append(f"• <b>AEMA 잠재치</b> · 기존 전력망 추가 활용 <b>{fm['aema_unlock_potential_gw']:g}GW</b> 주장 · 확보·전원 인가 용량과 구분")\n    msg.append(f"• <b>계통접속 적체</b> · 주요시장 현재 약 <b>{fm['interconnection_backlog_low_years']:g}~{fm['interconnection_backlog_high_years']:g}년</b> · 실제 단축 개월 수 확인 시 우선 알림")\n\n    if flexible_load_changes:\n        msg += ["", "<b>🔄 유연부하 숫자 변경</b>"]\n        for ch in flexible_load_changes[:6]:\n            msg.append(f"• <b>{h(ch)}</b>")\n\n    if metric_changes:\n'''
if msg_anchor2 not in s:
    raise SystemExit("time-to-power flexible message insertion point not found")
s = s.replace(msg_anchor2, msg_new2, 1)

baseline_scope_old = '''        msg.append("• 800V DC는 고객 채택·수주·양산·인증 단계 전환만 알림")\n'''
baseline_scope_new = '''        msg.append("• 800V DC는 고객 채택·수주·양산·인증 단계 전환만 알림")\n        msg.append("• 유연부하·수요반응은 계약 MW·감축률·응답시간·지속시간·계통접속 단축을 추적")\n'''
if baseline_scope_old not in s:
    raise SystemExit("time-to-power flexible baseline scope insertion point not found")
s = s.replace(baseline_scope_old, baseline_scope_new, 1)

interpret_old = '''    msg.append("• 발전·BESS와 부하 위치가 다르면 변전소·송전선 비용이 다음 병목인지 함께 봅니다.")\n'''
interpret_new = '''    msg.append("• 발전·BESS와 부하 위치가 다르면 변전소·송전선 비용이 다음 병목인지 함께 봅니다.")\n    msg.append("• 유연부하는 기술 실증보다 <b>유틸리티가 실제 접속용량·접속기간 산정에 인정하는지</b>를 최종 실행 신호로 봅니다.")\n'''
if interpret_old not in s:
    raise SystemExit("time-to-power flexible interpretation insertion point not found")
s = s.replace(interpret_old, interpret_new, 1)

links_old = '''    msg.append(f"• {a('ERCOT 대형부하 Batch Zero', ERCOT_LARGE_LOAD)}")\n'''
links_new = '''    msg.append(f"• {a('ERCOT 대형부하 Batch Zero', ERCOT_LARGE_LOAD)}")\n    msg.append(f"• {a('AEMA 유연 AI 데이터센터', AEMA_SOLUTIONS)}")\n    msg.append(f"• {a('Google 1GW 수요반응 계약', GOOGLE_DEMAND_RESPONSE)}")\n    msg.append(f"• {a('NVIDIA·Emerald AI 유연부하 실증', NVIDIA_EMERALD)}")\n'''
if links_old not in s:
    raise SystemExit("time-to-power flexible official links insertion point not found")
s = s.replace(links_old, links_new, 1)

status_old2 = '''    f"- MISO 제5차: **{miso_metrics.get('cycle5_mw')} MW / {miso_metrics.get('cycle5_projects')}개**\\n"\n    f"- 신규 의미자료: **{len(new_items)}건**\\n"\n    f"- 숫자 변경: **{len(metric_changes)}건**\\n"\n'''
status_new2 = '''    f"- MISO 제5차: **{miso_metrics.get('cycle5_mw')} MW / {miso_metrics.get('cycle5_projects')}개**\\n"\n    f"- Google 수요반응 계약: **{flexible_load_metrics.get('google_demand_response_gw')} GW**\\n"\n    f"- 유연 AI 팩토리 상업 규모 실증: **{flexible_load_metrics.get('commercial_flexible_factory_mw')} MW**\\n"\n    f"- 최대 부하감축: **{flexible_load_metrics.get('emerald_max_reduction_pct')}%**\\n"\n    f"- 신규 의미자료: **{len(new_items)}건**\\n"\n    f"- 기존 실행 숫자 변경: **{len(metric_changes)}건**\\n"\n    f"- 유연부하 숫자 변경: **{len(flexible_load_changes)}건**\\n"\n'''
if status_old2 not in s:
    raise SystemExit("time-to-power flexible status insertion point not found")
s = s.replace(status_old2, status_new2, 1)

print_old2 = '''    f"gia={miso_metrics.get('gia_gw')}GW new={len(new_items)} changes={len(metric_changes)} alert={should_alert}"\n)'''
print_new2 = '''    f"gia={miso_metrics.get('gia_gw')}GW new={len(new_items)} changes={len(metric_changes)} "\n    f"flex_changes={len(flexible_load_changes)} alert={should_alert}"\n)'''
if print_old2 not in s:
    raise SystemExit("time-to-power flexible print insertion point not found")
s = s.replace(print_old2, print_new2, 1)

p.write_text(s, encoding="utf-8")
print("US time-to-power flexible-load + demand-response guard inserted")
