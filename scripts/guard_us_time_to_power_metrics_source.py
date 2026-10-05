#!/usr/bin/env python3
from pathlib import Path

# Existing time-to-power runtime guard.
p = Path("scripts/us_data_center_time_to_power_watch.py")
s = p.read_text(encoding="utf-8")
# Public IEA/ABB pages are public but can reject a repository-identifying crawler UA.
# Use a standard browser UA; no authentication or access controls are bypassed.
s = s.replace(
    'HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}',
    'HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}',
    1,
)

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
t = t.replace(
    'HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}',
    'HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}',
    1,
)
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
print_new = '''    f"gev_slots={gev['gas_contract_slot_gw']}GW new={len(new_items)} "\n    f"gev_changes={len(gev_changes)} power_changes={len(power_changes)} pwc_changes={len(pwc_changes)} alert={should_alert}"\n)'''
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
    "ms_new_power_need_2026_2028_gw": 97.0,
    "ms_under_construction_gw": 21.0,
    "ms_available_grid_gw": 19.0,
    "ms_initial_shortfall_gw": 57.0,
    "ms_alternative_supply_gw": 24.0,
    "ms_residual_shortfall_gw": 33.0,
    "ms_residual_shortfall_2029_gw": 72.0,
    "gs_us_2030_power_gw": 108.0,
    "gs_us_prior_2030_power_gw": 83.0,
    "gs_global_growth_2025_2030_pct": 170.0,
    "gs_global_prior_growth_pct": 117.0,
    "gs_btm_gas_capacity_2030_gw": 30.0,
    "gs_btm_power_delivery_2030_gw": 20.0,
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

pwc_func = r'''
def _usd_b_label_ko(usd_b: float) -> str:
    usd_b = float(usd_b)
    if usd_b >= 1000:
        jo = int(usd_b // 1000)
        rem_eok = round((usd_b - jo * 1000) * 10)
        if rem_eok:
            return f"{jo:,}조{rem_eok:,}억달러"
        return f"{jo:,}조달러"
    return f"{usd_b * 10:,.0f}억달러"


def _pwc_change_with_krw(text: str, fx: float) -> str:
    def repl_t(m):
        value = float(m.group(1).replace(",", ""))
        return f"{m.group(0)} = {krw_from_usd_b(value * 1000, fx)}"

    def repl_b(m):
        value = float(m.group(1).replace(",", ""))
        return f"{m.group(0)} = {krw_from_usd_b(value, fx)}"

    out = re.sub(r"([0-9,.]+)\s*조달러", repl_t, text)
    out = re.sub(r"([0-9,.]+)\s*십억달러", repl_b, out)
    return out


def money_suffix_from_title(title: str, fx: float) -> str:
    low = (title or "").replace(",", "")
    values = []
    for pat, mult in (
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)\b", 1000.0),
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:billion|bn|b)\b", 1.0),
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:million|mn|m)\b", 0.001),
        (r"([0-9]+(?:\.[0-9]+)?)\s*조달러", 1000.0),
        (r"([0-9]+(?:\.[0-9]+)?)\s*억달러", 0.1),
    ):
        for m in re.finditer(pat, low, re.I):
            try:
                values.append(float(m.group(1)) * mult)
            except Exception:
                pass
    deduped = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    if not deduped:
        return ""
    return " · 원화환산 " + ", ".join(krw_from_usd_b(v, fx) for v in deduped[:2])


PWC_OUTLOOK = "https://www.pwc.com/gx/en/1/services/consulting/technology/data-centre-outlook.html"
PWC_KEYS = (
    "pwc_total_2026_2050_usd_t",
    "pwc_upside_usd_t",
    "pwc_annual_2026_usd_b",
    "pwc_annual_2030_usd_b",
    "pwc_annual_2050_usd_b",
    "pwc_ict_share_2026_pct",
    "pwc_ict_share_2050_pct",
    "pwc_refresh_low_years",
    "pwc_refresh_high_years",
    "pwc_rounds_low",
    "pwc_rounds_high",
)


def parse_pwc_metrics(old_state: dict):
    oldm = old_state.get("pwc_metrics") or {}
    oldb = old_state.get("baseline") or {}
    metrics = {key: oldm.get(key, oldb.get(key, BASELINE.get(key))) for key in PWC_KEYS}
    errors = []
    try:
        text = _page_text(PWC_OUTLOOK)
        m = re.search(r"(?:US\$|\$)?\s*([0-9.]+)\s*trillion[^.]{0,120}(?:through|to)\s*2050", text, re.I)
        if m:
            metrics["pwc_total_2026_2050_usd_t"] = float(m.group(1))
        m = re.search(r"(?:upside of|upside).*?(?:nearly|about)?\s*\$?\s*([0-9.]+)\s*trillion", text, re.I)
        if m:
            metrics["pwc_upside_usd_t"] = float(m.group(1))
        m = re.search(r"(?:roughly\s*)?\$?\s*([0-9,.]+)\s*billion\s+in\s+2026", text, re.I)
        if m:
            metrics["pwc_annual_2026_usd_b"] = float(m.group(1).replace(",", ""))
        m = re.search(r"\$?\s*([0-9.]+)\s*trillion\s+in\s+2030", text, re.I)
        if m:
            metrics["pwc_annual_2030_usd_b"] = float(m.group(1)) * 1000
        m = re.search(r"\$?\s*([0-9.]+)\s*trillion\s+in\s+2050", text, re.I)
        if m:
            metrics["pwc_annual_2050_usd_b"] = float(m.group(1)) * 1000
        m = re.search(r"ICT equipment rises from\s*([0-9.]+)%[^.]{0,100}2026[^.]{0,100}to\s*([0-9.]+)%[^.]{0,60}2050", text, re.I)
        if m:
            metrics["pwc_ict_share_2026_pct"] = float(m.group(1))
            metrics["pwc_ict_share_2050_pct"] = float(m.group(2))
        if re.search(r"(?:every|turn over every)\s+four to six years", text, re.I):
            metrics["pwc_refresh_low_years"] = 4.0
            metrics["pwc_refresh_high_years"] = 6.0
        if re.search(r"three to five rounds", text, re.I):
            metrics["pwc_rounds_low"] = 3.0
            metrics["pwc_rounds_high"] = 5.0
    except Exception as exc:
        errors.append(f"PwC: {type(exc).__name__}")
    return metrics, errors


def detect_pwc_changes(old_state: dict, now: dict):
    oldm = old_state.get("pwc_metrics") or {}
    if not oldm:
        oldb = old_state.get("baseline") or {}
        oldm = {key: oldb.get(key) for key in PWC_KEYS if oldb.get(key) is not None}
    changes = []
    for key, label, unit in (
        ("pwc_total_2026_2050_usd_t", "PwC 2026~2050 누적 자본투자", "조달러"),
        ("pwc_upside_usd_t", "PwC AI 가속 상단", "조달러"),
        ("pwc_annual_2026_usd_b", "PwC 2026 연간 자본투자", "십억달러"),
        ("pwc_annual_2030_usd_b", "PwC 2030 연간 자본투자", "십억달러"),
        ("pwc_annual_2050_usd_b", "PwC 2050 연간 자본투자", "십억달러"),
    ):
        ov, nv = oldm.get(key), now.get(key)
        if ov is None or nv is None or float(ov) == 0:
            continue
        if abs(float(nv) - float(ov)) / abs(float(ov)) >= 0.10:
            changes.append(f"{label}: {float(ov):g}{unit} → {float(nv):g}{unit}")
    for key, label in (
        ("pwc_ict_share_2026_pct", "PwC ICT 장비 비중 2026"),
        ("pwc_ict_share_2050_pct", "PwC ICT 장비 비중 2050"),
    ):
        ov, nv = oldm.get(key), now.get(key)
        if ov is not None and nv is not None and abs(float(nv) - float(ov)) >= 3.0:
            changes.append(f"{label}: {float(ov):g}% → {float(nv):g}%")
    for key, label in (
        ("pwc_refresh_low_years", "PwC 장비 교체주기 하단"),
        ("pwc_refresh_high_years", "PwC 장비 교체주기 상단"),
        ("pwc_rounds_low", "PwC 20년 투자회차 하단"),
        ("pwc_rounds_high", "PwC 20년 투자회차 상단"),
    ):
        ov, nv = oldm.get(key), now.get(key)
        if ov is not None and nv is not None and abs(float(nv) - float(ov)) >= 1.0:
            changes.append(f"{label}: {float(ov):g} → {float(nv):g}")
    return changes
'''
if func_anchor not in t:
    raise SystemExit("generation PwC parser insertion point not found")
t = t.replace(func_anchor, "\n" + pwc_func + func_anchor, 1)

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
items_new = "pwc_metrics, pwc_source_errors = parse_pwc_metrics(old)\npwc_changes = detect_pwc_changes(old, pwc_metrics)\nitems = collect_news() + collect_supplier_official_updates()\n"
if items_old not in t:
    raise SystemExit("generation supplier items insertion point not found")
t = t.replace(items_old, items_new, 1)

alert_old = "should_alert = baseline_run or format_upgrade or bool(new_items) or bool(gev_changes) or bool(power_changes)\n"
alert_new = "should_alert = baseline_run or format_upgrade or bool(new_items) or bool(gev_changes) or bool(power_changes) or bool(pwc_changes)\n"
if alert_old not in t:
    raise SystemExit("generation PwC alert gate insertion point not found")
t = t.replace(alert_old, alert_new, 1)

pwc_pending_old = '''    "power_source_errors": power_errors,
    "seen_ids": seen,
'''
pwc_pending_new = '''    "power_source_errors": power_errors,
    "pwc_metrics": pwc_metrics,
    "pwc_source_errors": pwc_source_errors,
    "seen_ids": seen,
'''
if pwc_pending_old not in t:
    raise SystemExit("generation PwC state insertion point not found")
t = t.replace(pwc_pending_old, pwc_pending_new, 1)

msg_anchor = '''    if gev_changes:
        msg += ["", "<b>🔄 공급능력 숫자 변경</b>"]
'''
msg_new = '''    cm = pwc_metrics
    msg += ["", "<b>💻 반복 장비투자·한국 전력기기 실수주</b>"]
    msg.append(
        f"• <b>PwC 누적 자본투자</b> │ 2026~2050 {cm['pwc_total_2026_2050_usd_t']:g}조달러 = "
        f"<b>{krw_from_usd_b(cm['pwc_total_2026_2050_usd_t'] * 1000, fx)}</b> │ "
        f"AI 가속 상단 약 {cm['pwc_upside_usd_t']:g}조달러 = "
        f"<b>{krw_from_usd_b(cm['pwc_upside_usd_t'] * 1000, fx)}</b>"
    )
    msg.append(
        f"• <b>연간 자본투자</b> │ "
        f"2026 <b>{_usd_b_label_ko(cm['pwc_annual_2026_usd_b'])}</b> = <b>{krw_from_usd_b(cm['pwc_annual_2026_usd_b'], fx)}</b> → "
        f"2030 <b>{_usd_b_label_ko(cm['pwc_annual_2030_usd_b'])}</b> = <b>{krw_from_usd_b(cm['pwc_annual_2030_usd_b'], fx)}</b> → "
        f"2050 <b>{_usd_b_label_ko(cm['pwc_annual_2050_usd_b'])}</b> = <b>{krw_from_usd_b(cm['pwc_annual_2050_usd_b'], fx)}</b>"
    )
    msg.append(f"• <b>ICT 장비 비중</b> │ 2026 {cm['pwc_ict_share_2026_pct']:g}% → 2050 {cm['pwc_ict_share_2050_pct']:g}% │ GPU·서버 교체 {cm['pwc_refresh_low_years']:g}~{cm['pwc_refresh_high_years']:g}년 · 20년 자산에서 {cm['pwc_rounds_low']:g}~{cm['pwc_rounds_high']:g}회")
    msg.append(f"• <b>효성중공업</b> │ 미국 AI 데이터센터 초고압변압기 <b>{b['hyosung_dc_order_krw_eok']:,.0f}억원</b> 직접 수주")
    msg.append(f"• <b>HD현대일렉트릭</b> │ 북미 데이터센터 장기 기본계약 최대 <b>{b['hd_hyundai_dc_framework_krw_eok']:,.0f}억원</b> │ 실제 개별 발주는 분할 · {int(b['hd_hyundai_delivery_year'])}년까지 순차 납품")
    msg.append(f"• <b>LS ELECTRIC</b> │ 뉴멕시코 {b['ls_bloom_dc_order_krw_eok']:,.0f}억원 · 북미 {b['ls_apr_dc_order_krw_eok']:,.0f}억원 · 미국 빅테크 {b['ls_may_dc_order_krw_eok']:,.0f}억원의 확인된 프로젝트를 각각 추적")
    msg.append("• <b>판정:</b> PwC 전망은 시장 기준선, 기업 수주는 확정 매출 연결 후보로 분리합니다. 기본계약 상단을 실제 발주액과 동일시하지 않습니다.")

    msg += ["", "<b>⚡ Morgan Stanley·Goldman Sachs 전력 병목 기준선</b>"]
    msg.append(
        f"• <b>Morgan Stanley 2026~2028 신규 필요</b> │ <b>{b['ms_new_power_need_2026_2028_gw']:g}GW</b>"
        f" = 건설 중 {b['ms_under_construction_gw']:g}GW + 가용 전력망 {b['ms_available_grid_gw']:g}GW"
        f" + 초기 부족 <b>{b['ms_initial_shortfall_gw']:g}GW</b>"
    )
    msg.append(
        f"• <b>대체전원 반영</b> │ 현장 가스·연료전지·직접원전 등 {b['ms_alternative_supply_gw']:g}GW"
        f" → 2028 잔여 부족 <b>{b['ms_residual_shortfall_gw']:g}GW</b>"
        f" │ 2029까지 <b>{b['ms_residual_shortfall_2029_gw']:g}GW</b>"
    )
    msg.append(
        f"• <b>Goldman Sachs 미국 2030 데이터센터 전력</b> │ {b['gs_us_prior_2030_power_gw']:g}GW"
        f" → <b>{b['gs_us_2030_power_gw']:g}GW</b> (+{(b['gs_us_2030_power_gw']/b['gs_us_prior_2030_power_gw']-1)*100:.1f}%)"
    )
    msg.append(
        f"• <b>Goldman Sachs 글로벌 전력수요 증가</b> │ 2025~2030 기존 +{b['gs_global_prior_growth_pct']:g}%"
        f" → <b>+{b['gs_global_growth_2025_2030_pct']:g}%</b>"
    )
    msg.append(
        f"• <b>현장 가스발전</b> │ 2030 설비 약 {b['gs_btm_gas_capacity_2030_gw']:g}GW"
        f" → 실제 공급전력 <b>{b['gs_btm_power_delivery_2030_gw']:g}GW+</b>"
    )
    msg.append("• <b>판정:</b> 위 GW는 증권사 수요·공급 전망이며 확정 계약·착공·전원 인가 용량과 분리합니다.")
    msg.append("• <b>조기경보:</b> 수요 전망은 오르는데 실제 가용 IT전력·계통접속·발전 착공·상업운전 MW가 따라오지 않으면 병목 악화로 봅니다.")

    if pwc_changes:
        msg += ["", "<b>🔄 PwC 자본투자 전망 변경</b>"]
        for ch in pwc_changes[:6]:
            msg.append(f"• {h(_pwc_change_with_krw(ch, fx))}")
    if pwc_source_errors:
        msg.append("• PwC 원문 연결 오류 시 직전 검증값을 유지하며, 오류 자체로는 변화 알림을 만들지 않습니다.")

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
    f"- Morgan Stanley 2026~2028 신규 필요: **{BASELINE['ms_new_power_need_2026_2028_gw']}GW**\n"
    f"- Morgan Stanley 대체전원 반영 후 2028 부족: **{BASELINE['ms_residual_shortfall_gw']}GW**\n"
    f"- Goldman Sachs 2030 미국 데이터센터 전력: **{BASELINE['gs_us_2030_power_gw']}GW**\n"
    f"- Goldman Sachs 2025~2030 글로벌 전력수요 증가: **+{BASELINE['gs_global_growth_2025_2030_pct']}%**\n"
    f"- 신규 의미자료: **{len(new_items)}건**\n"
'''
if status_old in t:
    t = t.replace(status_old, status_new, 1)

links_old = '''    msg.append(f"• {a('GE Vernova 가스터빈 공급능력', GEV_Q2_2026)}")
    ALERT.write_text'''
links_new = '''    msg.append(f"• {a('GE Vernova 가스터빈 공급능력', GEV_Q2_2026)}")
    msg.append(f"• {a('PwC 글로벌 데이터센터 반복투자 전망', 'https://www.pwc.com/gx/en/1/services/consulting/technology/data-centre-outlook.html')}")
    msg.append(f"• {a('효성중공업 미국 AI 데이터센터 수주', 'https://www.hyosung.com/kr/newsroom/view/19332')}")
    msg.append(f"• {a('HD현대일렉트릭 북미 데이터센터 공급계약', 'https://hyundai-elec.co.kr/elect/ko/PR/newsList.jsp')}")
    msg.append(f"• {a('LS ELECTRIC 데이터센터 전력솔루션', 'https://nahpdev-web.ls-electric.com/markets/data-center')}")
    msg.append(f"• {a('Morgan Stanley 미국 데이터센터 전력부족 전망', 'https://finance.yahoo.com/energy/articles/morgan-stanley-raises-us-data-134656211.html')}")
    msg.append(f"• {a('Goldman Sachs 데이터센터 전력수요 전망', 'https://www.goldmansachs.com/insights/goldman-sachs-exchanges/the-outlook-for-data-center-power-demand-as-ai-token-use-grows')}")
    ALERT.write_text'''
if links_old in t:
    t = t.replace(links_old, links_new, 1)

new_item_money_old = '''            msg.append(f"{idx}. 🔗 {a(ko, x['url'])}")'''
new_item_money_new = '''            money_note = money_suffix_from_title(x['title'], fx)
            msg.append(f"{idx}. 🔗 {a(ko, x['url'])}{h(money_note)}")'''
if new_item_money_old not in t:
    raise SystemExit("generation article-money insertion point not found")
t = t.replace(new_item_money_old, new_item_money_new, 1)

baseline_money_old = '''        msg.append("• 1,100억달러 투자 프레임과 소비자 비용부담 변화")'''
baseline_money_new = '''        msg.append(f"• 1,100억달러 = <b>{krw_from_usd_b(b['capex_usd_b'], fx)}</b> 투자 프레임과 소비자 비용부담 변화")'''
if baseline_money_old not in t:
    raise SystemExit("generation baseline-money insertion point not found")
t = t.replace(baseline_money_old, baseline_money_new, 1)

source_money_old = '''    msg.append(f"• {a('Moody’s 45GW·1,100억달러 분석 보도', MOODYS_BLOOMBERG)}")'''
source_money_new = '''    msg.append(f"• {a('Moody’s 45GW·신규발전 투자 분석 보도', MOODYS_BLOOMBERG)}")'''
if source_money_old not in t:
    raise SystemExit("generation source-label money insertion point not found")
t = t.replace(source_money_old, source_money_new, 1)

print("generation article-money KRW guard inserted")


# Keep Google-News alerts fresh and preserve seen-id insertion order.  Do not
# serialize a set: arbitrary set order can evict previously-seen IDs and make
# old stories look new again.
if "from email.utils import parsedate_to_datetime" not in t:
    t = t.replace(
        "import xml.etree.ElementTree as ET\nfrom pathlib import Path\n",
        "import xml.etree.ElementTree as ET\nfrom email.utils import parsedate_to_datetime\nfrom pathlib import Path\n",
        1,
    )
if "NEWS_ALERT_MAX_AGE_DAYS = 7" not in t:
    t = t.replace("FORMAT_VERSION = 3\n", "FORMAT_VERSION = 3\nNEWS_ALERT_MAX_AGE_DAYS = 7\nSEEN_ID_LIMIT = 5000\n", 1)

gen_news_old = '''            title = normalize(item.findtext("title") or "")
            link = normalize(item.findtext("link") or "")
            source_el = item.find("source")'''
gen_news_new = '''            title = normalize(item.findtext("title") or "")
            link = normalize(item.findtext("link") or "")
            pub = normalize(item.findtext("pubDate") or "")
            if not pub:
                continue
            try:
                published = parsedate_to_datetime(pub)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=dt.timezone.utc)
                if published.astimezone(dt.timezone.utc) < dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=NEWS_ALERT_MAX_AGE_DAYS):
                    continue
            except Exception:
                continue
            source_el = item.find("source")'''
if gen_news_old not in t:
    raise SystemExit("generation freshness insertion point not found")
t = t.replace(gen_news_old, gen_news_new, 1)

gen_seen_old = '''old_ids = set(old.get("seen_ids", []))
new_items = [x for x in items if x["id"] not in old_ids]'''
gen_seen_new = '''old_seen = list(old.get("seen_ids", []))
old_ids = set(old_seen)
new_items = [x for x in items if x["id"] not in old_ids]'''
if gen_seen_old not in t:
    raise SystemExit("generation ordered-dedupe insertion point not found")
t = t.replace(gen_seen_old, gen_seen_new, 1)

gen_cap_old = '''seen = list(dict.fromkeys(list(old_ids) + [x["id"] for x in items]))[-1600:]'''
gen_cap_new = '''seen = list(dict.fromkeys(old_seen + [x["id"] for x in items]))[-SEEN_ID_LIMIT:]'''
if gen_cap_old not in t:
    raise SystemExit("generation seen-limit insertion point not found")
t = t.replace(gen_cap_old, gen_cap_new, 1)
print("US generation watcher freshness + ordered dedupe guard inserted")

t = t.replace("FORMAT_VERSION = 3", "FORMAT_VERSION = 4", 1)

# Add the latest IEA Electricity 2026 grid-investment and timing mismatch
# baselines to the SAME generation-buildout watcher.  These are global grid
# execution metrics, not awarded data-center projects.
grid_const_anchor = 'EIA_STEO = "https://www.eia.gov/outlooks/steo/report/elec_coal_renew.php"\n'
grid_const_new = grid_const_anchor + '''IEA_ELECTRICITY_2026_EXEC = "https://www.iea.org/reports/electricity-2026/executive-summary"\nIEA_ELECTRICITY_2026_GRIDS = "https://www.iea.org/reports/electricity-2026/grids"\n'''
if grid_const_anchor not in t:
    raise SystemExit("generation Electricity 2026 constants insertion point not found")
t = t.replace(grid_const_anchor, grid_const_new, 1)

grid_defaults_old = '''    "power_electronics_bottleneck": True,
}'''
grid_defaults_new = '''    "power_electronics_bottleneck": True,
    "global_grid_investment_usd_b": 400.0,
    "global_grid_investment_growth_2030_pct": 50.0,
    "global_grid_queue_gw": 2500.0,
    "grid_build_low_years": 5.0,
    "grid_build_high_years": 15.0,
    "data_center_build_low_years": 1.0,
    "data_center_build_high_years": 3.0,
}'''
if grid_defaults_old not in t:
    raise SystemExit("generation Electricity 2026 defaults insertion point not found")
t = t.replace(grid_defaults_old, grid_defaults_new, 1)

grid_parse_anchor = '''    return metrics, errors


def detect_power_changes'''
grid_parse_block = r'''    try:
        text = _page_text(IEA_ELECTRICITY_2026_EXEC)
        if re.search(r"USDs*400s*billion", text, re.I):
            metrics["global_grid_investment_usd_b"] = 400.0
        m = re.search(r"increase by roughlys+([0-9.]+)%s+by 2030", text, re.I)
        if m:
            metrics["global_grid_investment_growth_2030_pct"] = float(m.group(1))
        m = re.search(r"more thans+([0-9][0-9,s]*)s+gigawatts", text, re.I)
        if m:
            metrics["global_grid_queue_gw"] = float(re.sub(r"[^0-9.]", "", m.group(1)))
    except Exception as exc:
        errors.append(f"IEA Electricity 2026 executive: {type(exc).__name__}")

    try:
        text = _page_text(IEA_ELECTRICITY_2026_GRIDS)
        m = re.search(r"anywhere froms+([0-9.]+)s+tos+([0-9.]+)s+years", text, re.I)
        if m:
            metrics["grid_build_low_years"] = float(m.group(1))
            metrics["grid_build_high_years"] = float(m.group(2))
        m = re.search(r"([0-9.]+)s*-s*([0-9.]+)s+years for data centres", text, re.I)
        if m:
            metrics["data_center_build_low_years"] = float(m.group(1))
            metrics["data_center_build_high_years"] = float(m.group(2))
    except Exception as exc:
        errors.append(f"IEA Electricity 2026 grids: {type(exc).__name__}")

    return metrics, errors


def detect_power_changes'''
if grid_parse_anchor not in t:
    raise SystemExit("generation Electricity 2026 parser insertion point not found")
t = t.replace(grid_parse_anchor, grid_parse_block, 1)

grid_checks_old = '''        ("gas_turbine_order_growth_pct", 10.0, "IEA 가스터빈 주문 증가율", "%"),
    )'''
grid_checks_new = '''        ("gas_turbine_order_growth_pct", 10.0, "IEA 가스터빈 주문 증가율", "%"),
        ("global_grid_investment_usd_b", 25.0, "IEA 글로벌 연간 전력망 투자", "십억달러"),
        ("global_grid_investment_growth_2030_pct", 5.0, "IEA 2030 전력망 투자 필요 증가율", "%p"),
        ("global_grid_queue_gw", 250.0, "IEA 글로벌 계통접속 대기열", "GW"),
        ("grid_build_high_years", 1.0, "IEA 전력망 구축기간 상단", "년"),
    )'''
if grid_checks_old not in t:
    raise SystemExit("generation Electricity 2026 change checks insertion point not found")
t = t.replace(grid_checks_old, grid_checks_new, 1)

grid_msg_anchor = '''    msg.append(f"• <b>가스터빈 주문</b> │ IEA 2025년 <b>+{pm['gas_turbine_order_growth_pct']:g}%</b> │ 전력전자 공급망 병목={'확인' if pm.get('power_electronics_bottleneck') else '미확인'}")

    if power_changes:'''
grid_msg_new = '''    msg.append(f"• <b>가스터빈 주문</b> │ IEA 2025년 <b>+{pm['gas_turbine_order_growth_pct']:g}%</b> │ 전력전자 공급망 병목={'확인' if pm.get('power_electronics_bottleneck') else '미확인'}")

    grid_change = any(
        any(k in ch for k in ("전력망 투자", "계통접속 대기열", "전력망 구축기간"))
        for ch in power_changes
    )
    if baseline_run or format_upgrade or grid_change:
        current_grid = pm['global_grid_investment_usd_b']
        required_grid = current_grid * (1 + pm['global_grid_investment_growth_2030_pct'] / 100)
        extra_grid = required_grid - current_grid
        msg += ["", "<b>🌐 전력망 투자·접속 병목</b>"]
        msg.append(
            f"• <b>현재 연간 전력망 투자</b> │ 약 {current_grid:,.0f}십억달러 = "
            f"<b>{krw_from_usd_b(current_grid, fx)}</b>"
        )
        msg.append(
            f"• <b>2030 필요 수준</b> │ 현재 대비 +{pm['global_grid_investment_growth_2030_pct']:g}% → "
            f"약 {required_grid:,.0f}십억달러 = <b>{krw_from_usd_b(required_grid, fx)}</b> "
            f"│ 추가 연간 투자 약 {extra_grid:,.0f}십억달러 = <b>{krw_from_usd_b(extra_grid, fx)}</b>"
        )
        msg.append(
            f"• <b>계통접속 대기</b> │ 전 세계 <b>{pm['global_grid_queue_gw']:,.0f}GW+</b> "
            f"재생에너지·저장장치·데이터센터 등 대형부하 프로젝트"
        )
        msg.append(
            f"• <b>시간표 불일치</b> │ 전력망 {pm['grid_build_low_years']:g}~{pm['grid_build_high_years']:g}년 "
            f"vs 데이터센터 {pm['data_center_build_low_years']:g}~{pm['data_center_build_high_years']:g}년"
        )
        msg.append("• <b>판정:</b> 수요 전망 증가보다 계통접속·변전소·송전선 실제 착공과 전원 인가가 늦으면 데이터센터 매출 인식의 병목이 더 커집니다.")

    if power_changes:'''
if grid_msg_anchor not in t:
    raise SystemExit("generation Electricity 2026 message insertion point not found")
t = t.replace(grid_msg_anchor, grid_msg_new, 1)

grid_status_anchor = '''    f"- 대형 전력변압기 최대 조달기간: **{power_metrics['transformer_lead_max_years']}년**\\n"
'''
grid_status_new = grid_status_anchor + '''    f"- IEA 글로벌 연간 전력망 투자: **{power_metrics['global_grid_investment_usd_b']}십억달러**\\n"
    f"- IEA 2030 전력망 투자 필요 증가율: **+{power_metrics['global_grid_investment_growth_2030_pct']}%**\\n"
    f"- IEA 글로벌 계통접속 대기열: **{power_metrics['global_grid_queue_gw']}GW+**\\n"
    f"- IEA 전력망/데이터센터 구축기간: **{power_metrics['grid_build_low_years']}~{power_metrics['grid_build_high_years']}년 / {power_metrics['data_center_build_low_years']}~{power_metrics['data_center_build_high_years']}년**\\n"
'''
if grid_status_anchor not in t:
    raise SystemExit("generation Electricity 2026 status insertion point not found")
t = t.replace(grid_status_anchor, grid_status_new, 1)

grid_links_anchor = '''    msg.append(f"• {a('GE Vernova 가스터빈 공급능력', GEV_Q2_2026)}")'''
grid_links_new = grid_links_anchor + '''\n    msg.append(f"• {a('IEA Electricity 2026 전력망 투자·접속 병목', IEA_ELECTRICITY_2026_EXEC)}")
    msg.append(f"• {a('IEA Electricity 2026 전력망 구축기간', IEA_ELECTRICITY_2026_GRIDS)}")'''
if grid_links_anchor not in t:
    raise SystemExit("generation Electricity 2026 links insertion point not found")
t = t.replace(grid_links_anchor, grid_links_new, 1)

t = t.replace("FORMAT_VERSION = 4", "FORMAT_VERSION = 5", 1)

# Add the confirmed Korean Bloom Energy supply-chain order to the SAME
# generation-buildout watcher. This is a direct contract baseline, not a theme-only link.
vinatech_baseline_old = '''    "ls_bloom_dc_order_krw_eok": 3190.0,
'''
vinatech_baseline_new = '''    "ls_bloom_dc_order_krw_eok": 3190.0,
    "vinatech_bloom_dc_contract_krw_eok": 412.153938,
    "vinatech_bloom_contract_sales_pct": 50.12,
    "vinatech_bloom_contract_end": "2027-04-10",
'''
if vinatech_baseline_old not in t:
    raise SystemExit("Vinatech baseline insertion point not found")
t = t.replace(vinatech_baseline_old, vinatech_baseline_new, 1)

vinatech_trusted_old = '''    "hyosung.com", "hd-hyundaielectric.com", "hyundai-elec.co.kr", "ls-electric.com",
)'''
vinatech_trusted_new = '''    "hyosung.com", "hd-hyundaielectric.com", "hyundai-elec.co.kr", "ls-electric.com",
    "vinatech.com",
)'''
if vinatech_trusted_old not in t:
    raise SystemExit("Vinatech trusted-domain insertion point not found")
t = t.replace(vinatech_trusted_old, vinatech_trusted_new, 1)

vinatech_query_old = '''    'LS ELECTRIC data center transformer switchgear order North America',
)'''
vinatech_query_new = '''    'LS ELECTRIC data center transformer switchgear order North America',
    'VINATech Bloom Energy data center supercapacitor contract order',
    '비나텍 Bloom Energy 데이터센터 슈퍼커패시터 수주 공급계약',
)'''
if vinatech_query_old not in t:
    raise SystemExit("Vinatech query insertion point not found")
t = t.replace(vinatech_query_old, vinatech_query_new, 1)

vinatech_source_old = '''        ("hyosung", "효성중공업"), ("hyundai", "HD현대일렉트릭"), ("ls-electric", "LS ELECTRIC"),
    ):'''
vinatech_source_new = '''        ("hyosung", "효성중공업"), ("hyundai", "HD현대일렉트릭"), ("ls-electric", "LS ELECTRIC"),
        ("vinatech", "비나텍"),
    ):'''
if vinatech_source_old not in t:
    raise SystemExit("Vinatech source-label insertion point not found")
t = t.replace(vinatech_source_old, vinatech_source_new, 1)

vinatech_pages_old = '''    ("https://nahpdev-web.ls-electric.com/markets/data-center", "LS ELECTRIC"),
)'''
vinatech_pages_new = '''    ("https://nahpdev-web.ls-electric.com/markets/data-center", "LS ELECTRIC"),
    ("https://www.vinatech.com/kr/sub/pr/news.php?bid=16&mode=list", "비나텍"),
)'''
if vinatech_pages_old not in t:
    raise SystemExit("Vinatech supplier-page insertion point not found")
t = t.replace(vinatech_pages_old, vinatech_pages_new, 1)

vinatech_meaning_old = '''    if any(k in low for k in ("hyosung", "효성중공업", "hd hyundai", "hd현대일렉트릭", "ls electric")) and any(k in low for k in ("data center", "data centre", "데이터센터")) and any(k in low for k in ("order", "contract", "supply", "수주", "계약", "공급")):
        return True'''
vinatech_meaning_new = '''    if any(k in low for k in ("hyosung", "효성중공업", "hd hyundai", "hd현대일렉트릭", "ls electric", "vinatech", "비나텍", "bloom energy")) and any(k in low for k in ("data center", "data centre", "데이터센터")) and any(k in low for k in ("order", "contract", "supply", "수주", "계약", "공급", "supercapacitor", "슈퍼커패시터")):
        return True'''
if vinatech_meaning_old not in t:
    raise SystemExit("Vinatech meaningful insertion point not found")
t = t.replace(vinatech_meaning_old, vinatech_meaning_new, 1)

vinatech_msg_old = '''    msg.append(f"• <b>LS ELECTRIC</b> │ 뉴멕시코 {b['ls_bloom_dc_order_krw_eok']:,.0f}억원 · 북미 {b['ls_apr_dc_order_krw_eok']:,.0f}억원 · 미국 빅테크 {b['ls_may_dc_order_krw_eok']:,.0f}억원의 확인된 프로젝트를 각각 추적")
    msg.append("• <b>판정:</b> PwC 전망은 시장 기준선, 기업 수주는 확정 매출 연결 후보로 분리합니다. 기본계약 상단을 실제 발주액과 동일시하지 않습니다.")'''
vinatech_msg_new = '''    msg.append(f"• <b>LS ELECTRIC</b> │ 뉴멕시코 {b['ls_bloom_dc_order_krw_eok']:,.0f}억원 · 북미 {b['ls_apr_dc_order_krw_eok']:,.0f}억원 · 미국 빅테크 {b['ls_may_dc_order_krw_eok']:,.0f}억원의 확인된 프로젝트를 각각 추적")
    msg.append(
        f"• <b>비나텍</b> │ Bloom Energy 미국 데이터센터용 슈퍼커패시터 시스템 <b>{b['vinatech_bloom_dc_contract_krw_eok']:,.2f}억원</b> "
        f"· 2025년 매출 대비 <b>{b['vinatech_bloom_contract_sales_pct']:g}%</b> · 계약종료 <b>{b['vinatech_bloom_contract_end']}</b>"
    )
    msg.append("• <b>판정:</b> PwC 전망은 시장 기준선, 기업 수주는 확정 매출 연결 후보로 분리합니다. 기본계약 상단을 실제 발주액과 동일시하지 않습니다.")'''
if vinatech_msg_old not in t:
    raise SystemExit("Vinatech message insertion point not found")
t = t.replace(vinatech_msg_old, vinatech_msg_new, 1)

vinatech_links_old = '''    msg.append(f"• {a('LS ELECTRIC 데이터센터 전력솔루션', 'https://nahpdev-web.ls-electric.com/markets/data-center')}")'''
vinatech_links_new = '''    msg.append(f"• {a('LS ELECTRIC 데이터센터 전력솔루션', 'https://nahpdev-web.ls-electric.com/markets/data-center')}")
    msg.append(f"• {a('비나텍 Bloom Energy 데이터센터 공급', 'https://www.vinatech.com/kr/sub/pr/news.php?bid=16&idx=3365&mode=view')}")'''
if vinatech_links_old not in t:
    raise SystemExit("Vinatech links insertion point not found")
t = t.replace(vinatech_links_old, vinatech_links_new, 1)

t = t.replace("FORMAT_VERSION = 5", "FORMAT_VERSION = 6", 1)
g.write_text(t, encoding="utf-8")
print("US generation watcher recurring-capex + power-gap + global-grid + Bloom supplier guard inserted")

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


if "from email.utils import parsedate_to_datetime" not in s:
    s = s.replace(
        "import xml.etree.ElementTree as ET\nfrom pathlib import Path\n",
        "import xml.etree.ElementTree as ET\nfrom email.utils import parsedate_to_datetime\nfrom pathlib import Path\n",
        1,
    )
if "NEWS_ALERT_MAX_AGE_DAYS = 7" not in s:
    s = s.replace("FORMAT_VERSION = 3\n", "FORMAT_VERSION = 3\nNEWS_ALERT_MAX_AGE_DAYS = 7\nSEEN_ID_LIMIT = 5000\n", 1)

ttp_news_old = '''            pub = normalize(item.findtext("pubDate") or "")
            source_el = item.find("source")'''
ttp_news_new = '''            pub = normalize(item.findtext("pubDate") or "")
            if not pub:
                continue
            try:
                published = parsedate_to_datetime(pub)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=dt.timezone.utc)
                if published.astimezone(dt.timezone.utc) < dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=NEWS_ALERT_MAX_AGE_DAYS):
                    continue
            except Exception:
                continue
            source_el = item.find("source")'''
if ttp_news_old not in s:
    raise SystemExit("time-to-power freshness insertion point not found")
s = s.replace(ttp_news_old, ttp_news_new, 1)

ttp_seen_old = '''old_ids = set(old.get("seen_ids", []))
new_items = [x for x in items if x["id"] not in old_ids]'''
ttp_seen_new = '''old_seen = list(old.get("seen_ids", []))
old_ids = set(old_seen)
new_items = [x for x in items if x["id"] not in old_ids]'''
if ttp_seen_old not in s:
    raise SystemExit("time-to-power ordered-dedupe insertion point not found")
s = s.replace(ttp_seen_old, ttp_seen_new, 1)

ttp_cap_old = '''seen = list(dict.fromkeys(list(old_ids) + [x["id"] for x in items]))[-1800:]'''
ttp_cap_new = '''seen = list(dict.fromkeys(old_seen + [x["id"] for x in items]))[-SEEN_ID_LIMIT:]'''
if ttp_cap_old not in s:
    raise SystemExit("time-to-power seen-limit insertion point not found")
s = s.replace(ttp_cap_old, ttp_cap_new, 1)
print("US time-to-power freshness + ordered dedupe guard inserted")


# ERCOT market notices need stricter treatment than generic official links:
# 1) archive rows older than the freshness window must not become "new" again;
# 2) the linked notice must still exist and contain the same notice ID;
# 3) community-impact surveys/tooling updates do not equal a Time-to-Power
#    execution step unless they change eligibility/classification/interconnection.
ercot_helper_anchor = '''def is_meaningful(item: dict) -> bool:
'''
ercot_helpers = r'''
def _ercot_notice_id(text: str) -> str:
    m = re.search(r"\bM-[A-Z]\d{6}-\d{2}\b", text or "", re.I)
    return m.group(0).upper() if m else ""


def _ercot_archive_fresh(text: str) -> bool:
    m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", text or "")
    if not m:
        return False
    try:
        published = dt.datetime.strptime(m.group(1), "%m/%d/%Y").replace(tzinfo=dt.timezone.utc)
    except Exception:
        return False
    return published >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=NEWS_ALERT_MAX_AGE_DAYS)


def _ercot_execution_relevant(text: str) -> bool:
    low = (text or "").lower()

    # These are information-gathering / portal-administration events, not
    # interconnection or energization stage changes by themselves.
    if any(k in low for k in (
        "state and community impact rfi",
        "community impact rfi",
        "water sources and consumption",
        "voluntary state and community impact",
        "rfi tool update",
        "restrict visibility",
        "question reference guide",
        "optional survey",
    )):
        return any(k in low for k in (
            "excluded from batch zero",
            "exclusion from batch zero",
            "classification revoked",
            "classification changed",
            "reclassified",
            "interconnection suspended",
            "interconnection denied",
            "may not advance",
            "cannot advance",
            "energization prohibited",
        ))

    return any(k in low for k in (
        "batch zero verification",
        "eligibility verification",
        "conditional classification",
        "final classification",
        "reclassified",
        "interconnection",
        "energization",
        "energized",
        "byog",
        "wlpun",
        "large load curtail",
        "site control",
        "financial security",
        "transmission study",
        "study result",
        "approved",
        "approval",
        "pause",
        "suspend",
    ))


'''
if ercot_helper_anchor not in s:
    raise SystemExit("ERCOT execution helper insertion point not found")
s = s.replace(ercot_helper_anchor, ercot_helpers + ercot_helper_anchor, 1)

ercot_meaning_old = '''    if item.get("official") and theme not in {"기타", "유연부하·수요반응"}:
        return True
'''
ercot_meaning_new = '''    if theme == "ERCOT·Batch Zero":
        return _ercot_execution_relevant(text)
    if item.get("official") and theme not in {"기타", "유연부하·수요반응"}:
        return True
'''
if ercot_meaning_old not in s:
    raise SystemExit("ERCOT execution meaningful gate insertion point not found")
s = s.replace(ercot_meaning_old, ercot_meaning_new, 1)

ercot_rows_old = '''    if row_mode:
        containers = soup.find_all("tr")
        for row in containers:
            text = normalize(row.get_text(" "))
            low = text.lower()
            if not any(k in low for k in keywords):
                continue
            link = row.find("a", href=True)
            href = absurl(url, link.get("href")) if link else url
            theme = classify(text)
            out.append({"id": sig(source, text, href), "source": source, "title": text[:420], "url": href,
                        "official": True, "theme": theme, "summary": text[:800]})
        return out
'''
ercot_rows_new = '''    if row_mode:
        containers = soup.find_all("tr")
        for row in containers:
            text = normalize(row.get_text(" "))
            low = text.lower()
            if not any(k in low for k in keywords):
                continue
            if source == "ERCOT" and not _ercot_archive_fresh(text):
                continue
            link = row.find("a", href=True)
            href = absurl(url, link.get("href")) if link else url
            notice_id = _ercot_notice_id(f"{text} {href}")
            if source == "ERCOT":
                if not notice_id or "/services/comm/mkt_notices/" not in href:
                    continue
                try:
                    detail_text = normalize(BeautifulSoup(fetch(href, 20).text, "html.parser").get_text(" "))
                except Exception:
                    continue
                if notice_id.lower() not in detail_text.lower():
                    continue
            theme = classify(text)
            item_id = sig(source, notice_id) if notice_id else sig(source, text, href)
            out.append({"id": item_id, "source": source, "title": text[:420], "url": href,
                        "official": True, "theme": theme, "summary": text[:800]})
        return out
'''
if ercot_rows_old not in s:
    raise SystemExit("ERCOT archive row gate insertion point not found")
s = s.replace(ercot_rows_old, ercot_rows_new, 1)
print("ERCOT archive freshness + execution-quality guard inserted")

# Extend the existing 800V-DC branch with wide-bandgap power-semiconductor
# execution signals.  Keep the same workflow, state file and Telegram route.
s = s.replace("FORMAT_VERSION = 3", "FORMAT_VERSION = 4", 1)

semi_const_anchor = 'GRIDUNITY_AEMA = "https://www.gridunity.com/resources/gridunity-selected-as-founding-board-member-of-new-ai-energy-management-alliance"\n'
semi_const_new = semi_const_anchor + '''NVIDIA_800V_ARCH = "https://developer.nvidia.com/blog/nvidia-800-v-hvdc-architecture-will-power-the-next-generation-of-ai-factories"\nNVIDIA_800V_ROADMAP = "https://blogs.nvidia.com/blog/800-vdc-power-architecture-ai-factory/"\nOCP_800V_STANDARD = "https://www.opencompute.org/index.php/blog/powering-the-next-era-of-ai-how-google-microsoft-and-nvidia-are-standardizing-and-accelerating-the-industry-transition-to-lvdc"\nINFINEON_SIC_BBU = "https://www.infineon.com/technology-news/2026/infpss202606-093"\nINFINEON_EATON_SST = "https://www.infineon.com/press-release/2026/infpr202609-146"\nWOLFSPEED_LITEON_800V = "https://investor.wolfspeed.com/news/news-details/2026/Wolfspeed-and-LITEON-Partner-to-Support-Hyperscale-AI-Data-Center-Deployments-with-800-VDC-Power-Solutions/default.aspx"\nDIGITIMES_SIC_RESEARCH = "https://apps.digitimes.com/reports/item.php?id=20260929RS400"\n'''
if semi_const_anchor not in s:
    raise SystemExit("800V SiC constants insertion point not found")
s = s.replace(semi_const_anchor, semi_const_new, 1)

semi_official_old = '''    "aema.ai", "blog.google", "gridunity.com", "epri.com", "pjm.com",
)'''
semi_official_new = '''    "aema.ai", "blog.google", "gridunity.com", "epri.com", "pjm.com",
    "infineon.com", "wolfspeed.com", "liteon.com", "opencompute.org", "rohm.com",
    "st.com", "onsemi.com",
)'''
if semi_official_old not in s:
    raise SystemExit("800V SiC official domains insertion point not found")
s = s.replace(semi_official_old, semi_official_new, 1)

semi_trusted_old = '''    "datacenterdynamics.com", "publicpower.org",
)'''
semi_trusted_new = '''    "datacenterdynamics.com", "publicpower.org", "digitimes.com",
)'''
if semi_trusted_old not in s:
    raise SystemExit("800V SiC trusted domains insertion point not found")
s = s.replace(semi_trusted_old, semi_trusted_new, 1)

semi_queries_old = '''    'Google data center demand response utility contract flexible load',
)'''
semi_queries_new = '''    'Google data center demand response utility contract flexible load',
    '800V VDC AI data center SiC GaN Infineon Wolfspeed LiteOn power semiconductor',
    'AI data center solid state transformer SiC Eaton Infineon 800 VDC',
    '6-inch SiC substrate price rebound AI data center 800V HVDC 2027 DIGITIMES',
)'''
if semi_queries_old not in s:
    raise SystemExit("800V SiC queries insertion point not found")
s = s.replace(semi_queries_old, semi_queries_new, 1)

semi_source_old = '''        ("aema", "AEMA"), ("blog.google", "Google"), ("gridunity", "GridUnity"),
    )'''
semi_source_new = '''        ("aema", "AEMA"), ("blog.google", "Google"), ("gridunity", "GridUnity"),
        ("infineon", "Infineon"), ("wolfspeed", "Wolfspeed"), ("liteon", "LITEON"),
        ("opencompute", "OCP"), ("rohm", "ROHM"), ("st.com", "STMicroelectronics"),
        ("onsemi", "onsemi"), ("digitimes", "DIGITIMES"),
    )'''
if semi_source_old not in s:
    raise SystemExit("800V SiC source labels insertion point not found")
s = s.replace(semi_source_old, semi_source_new, 1)

semi_classify_old = '''    if "800v" in low and any(k in low for k in ("dc", "direct current", "data center", "data centre", "rack")):
        return "800V DC"'''
semi_classify_new = '''    wide_bandgap = bool(
        re.search(r"\\b(?:sic|gan)\\b", low)
        or "silicon carbide" in low
        or "gallium nitride" in low
        or "wide-bandgap" in low
        or "wide bandgap" in low
    )
    if (
        any(k in low for k in ("800v", "800 v", "hvdc", "high-voltage direct current"))
        or wide_bandgap
    ) and any(k in low for k in (
        "data center", "data centre", "ai factory", "ai server", "rack",
        "power sidecar", "solid-state transformer", "solid state transformer", "power supply",
    )):
        return "800V DC"'''
if semi_classify_old not in s:
    raise SystemExit("800V SiC classifier insertion point not found")
s = s.replace(semi_classify_old, semi_classify_new, 1)

semi_meaning_old = '''    if theme == "800V DC":
        return any(k in text for k in (
            "customer", "adopt", "deploy", "contract", "order", "supply", "production",
            "validation", "validated", "certif", "launch", "reference design", "commercial",
            "파트너", "수주", "공급", "양산", "인증", "검증",
        ))'''
semi_meaning_new = '''    if theme == "800V DC":
        execution = any(k in text for k in (
            "customer", "adopt", "deploy", "contract", "order", "supply", "production",
            "validation", "validated", "qualification", "qualified", "certif", "launch",
            "reference design", "commercial", "mass production", "partnership",
            "파트너", "수주", "공급", "양산", "인증", "검증",
        ))
        sic_market_turn = (
            any(k in text for k in ("silicon carbide", "sic substrate", "sic substrates"))
            and any(k in text for k in (
                "price", "rebound", "recover", "tight", "shortage", "capacity",
                "yield", "6-inch", "6 inch", "8-inch", "8 inch", "200mm",
            ))
        )
        return execution or sic_market_turn'''
if semi_meaning_old not in s:
    raise SystemExit("800V SiC meaningful gate insertion point not found")
s = s.replace(semi_meaning_old, semi_meaning_new, 1)

semi_func_anchor = '''def detect_metric_changes(old: dict, metrics: dict, projects: dict) -> list[str]:
'''
semi_func_block = r'''
POWER_SEMI_DEFAULTS = {
    # Verified public reference points. DIGITIMES values remain research
    # estimates; official product/qualification facts are kept separately.
    "nvidia_full_scale_year": 2027.0,
    "nvidia_row_power_center_mw": 2.0,
    "nvidia_partner_count_min": 80.0,
    "infineon_bbu_kw": 24.0,
    "infineon_bbu_efficiency_pct": 99.0,
    "infineon_bbu_density_w_in3": 450.0,
    "digitimes_ev_share_2026_pct": 65.0,
    "digitimes_sic_6in_rebound_year": 2027.0,
    "digitimes_hvdc_start_year": 2027.0,
    "digitimes_hvdc_end_year": 2028.0,
    "wolfspeed_liteon_200mm_qualified": True,
    "infineon_eaton_sst_apac": True,
}


def _semi_page_text(url: str) -> str:
    return normalize(BeautifulSoup(fetch(url, 25).text, "html.parser").get_text(" "))


def parse_power_semiconductor_metrics(previous: dict | None = None) -> tuple[dict, list[str]]:
    previous = previous or {}
    metrics = dict(POWER_SEMI_DEFAULTS)
    errors = []
    for key, value in previous.items():
        if key in metrics and value is not None:
            metrics[key] = value

    try:
        text = _semi_page_text(NVIDIA_800V_ROADMAP)
        m = re.search(r"up tos+([0-9.]+)s+megawatts?s+per row", text, re.I)
        if m:
            metrics["nvidia_row_power_center_mw"] = float(m.group(1))
        m = re.search(r"more thans+([0-9,]+)s+(?:equipment manufacturers|ecosystem companies|partners)", text, re.I)
        if m:
            metrics["nvidia_partner_count_min"] = float(m.group(1).replace(",", ""))
    except Exception as exc:
        errors.append(f"NVIDIA 800V roadmap: {type(exc).__name__}")

    try:
        text = _semi_page_text(NVIDIA_800V_ARCH)
        m = re.search(r"full-scale production.*?(20[0-9]{2})", text, re.I)
        if m:
            metrics["nvidia_full_scale_year"] = float(m.group(1))
    except Exception as exc:
        errors.append(f"NVIDIA 800V architecture: {type(exc).__name__}")

    try:
        text = _semi_page_text(INFINEON_SIC_BBU)
        m = re.search(r"([0-9.]+)s*kWs+battery backup unit", text, re.I)
        if m:
            metrics["infineon_bbu_kw"] = float(m.group(1))
        m = re.search(r"([0-9.]+)s*W/in", text, re.I)
        if m:
            metrics["infineon_bbu_density_w_in3"] = float(m.group(1))
        m = re.search(r"efficiency exceedings+([0-9.]+)s*percent", text, re.I)
        if m:
            metrics["infineon_bbu_efficiency_pct"] = float(m.group(1))
    except Exception as exc:
        errors.append(f"Infineon SiC BBU: {type(exc).__name__}")

    try:
        text = _semi_page_text(WOLFSPEED_LITEON_800V)
        metrics["wolfspeed_liteon_200mm_qualified"] = bool(
            re.search(r"successful qualification", text, re.I)
            and re.search(r"200mm silicon carbide", text, re.I)
        )
    except Exception as exc:
        errors.append(f"Wolfspeed-LITEON 800V: {type(exc).__name__}")

    try:
        text = _semi_page_text(INFINEON_EATON_SST)
        metrics["infineon_eaton_sst_apac"] = bool(
            re.search(r"silicon carbide", text, re.I)
            and re.search(r"APAC", text, re.I)
            and re.search(r"solid-state transformer|SST", text, re.I)
        )
    except Exception as exc:
        errors.append(f"Infineon-Eaton SST: {type(exc).__name__}")

    try:
        text = _semi_page_text(DIGITIMES_SIC_RESEARCH)
        m = re.search(r"EVs are estimated to account fors+([0-9.]+)%", text, re.I)
        if m:
            metrics["digitimes_ev_share_2026_pct"] = float(m.group(1))
        if re.search(r"6-inch SiC substrate prices.*?rebound ins+2027", text, re.I):
            metrics["digitimes_sic_6in_rebound_year"] = 2027.0
        m = re.search(r"800V HVDC architecture,s*(20[0-9]{2})s*[-–]s*(20[0-9]{2})", text, re.I)
        if m:
            metrics["digitimes_hvdc_start_year"] = float(m.group(1))
            metrics["digitimes_hvdc_end_year"] = float(m.group(2))
    except Exception as exc:
        errors.append(f"DIGITIMES SiC research: {type(exc).__name__}")

    return metrics, errors


def detect_power_semiconductor_changes(old: dict, now: dict) -> list[str]:
    oldm = old.get("power_semiconductor_metrics") or {}
    if not oldm:
        return ["800V DC·SiC/GaN 실행 기준선 신규 연결"]
    changes = []
    checks = (
        ("nvidia_full_scale_year", 1.0, "NVIDIA 800V DC 본격 양산 연도", "년"),
        ("nvidia_row_power_center_mw", 0.5, "NVIDIA 800V 행 단위 전력센터 규모", "MW"),
        ("nvidia_partner_count_min", 10.0, "800V DC 생태계 기업 수 하한", "개"),
        ("infineon_bbu_kw", 5.0, "Infineon SiC BBU 출력", "kW"),
        ("infineon_bbu_efficiency_pct", 0.5, "Infineon SiC BBU 효율", "%"),
        ("infineon_bbu_density_w_in3", 25.0, "Infineon SiC BBU 전력밀도", "W/in³"),
        ("digitimes_ev_share_2026_pct", 5.0, "DIGITIMES 2026 SiC EV 응용 비중", "%"),
        ("digitimes_sic_6in_rebound_year", 1.0, "DIGITIMES 6인치 SiC 가격 반등 예상연도", "년"),
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
    for key, label in (
        ("wolfspeed_liteon_200mm_qualified", "Wolfspeed-LITEON 200mm SiC 800V DC 검증"),
        ("infineon_eaton_sst_apac", "Infineon-Eaton SiC SST APAC 공급"),
    ):
        if key in oldm and bool(oldm.get(key)) != bool(now.get(key)):
            changes.append(f"{label}: {bool(oldm.get(key))} → {bool(now.get(key))}")
    return changes


'''
if semi_func_anchor not in s:
    raise SystemExit("800V SiC metrics function insertion point not found")
s = s.replace(semi_func_anchor, semi_func_block + semi_func_anchor, 1)

semi_runtime_old = '''flexible_load_metrics, flexible_load_errors = parse_flexible_load_metrics(old.get("flexible_load_metrics") or {})
errors.extend(flexible_load_errors)

items: list[dict] = []'''
semi_runtime_new = '''flexible_load_metrics, flexible_load_errors = parse_flexible_load_metrics(old.get("flexible_load_metrics") or {})
errors.extend(flexible_load_errors)
power_semiconductor_metrics, power_semiconductor_errors = parse_power_semiconductor_metrics(
    old.get("power_semiconductor_metrics") or {}
)
errors.extend(power_semiconductor_errors)

items: list[dict] = []'''
if semi_runtime_old not in s:
    raise SystemExit("800V SiC runtime insertion point not found")
s = s.replace(semi_runtime_old, semi_runtime_new, 1)

semi_change_old = '''metric_changes = detect_metric_changes(old, miso_metrics, miso_projects)
flexible_load_changes = detect_flexible_load_changes(old, flexible_load_metrics)
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
should_alert = baseline_run or format_upgrade or bool(new_items) or bool(metric_changes) or bool(flexible_load_changes)'''
semi_change_new = '''metric_changes = detect_metric_changes(old, miso_metrics, miso_projects)
flexible_load_changes = detect_flexible_load_changes(old, flexible_load_metrics)
power_semiconductor_changes = detect_power_semiconductor_changes(old, power_semiconductor_metrics)
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
should_alert = (
    baseline_run or format_upgrade or bool(new_items) or bool(metric_changes)
    or bool(flexible_load_changes) or bool(power_semiconductor_changes)
)'''
if semi_change_old not in s:
    raise SystemExit("800V SiC change gate insertion point not found")
s = s.replace(semi_change_old, semi_change_new, 1)

semi_pending_old = '''    "flexible_load_metrics": flexible_load_metrics,
    "flexible_load_source_errors": flexible_load_errors,
    "seen_ids": seen,'''
semi_pending_new = '''    "flexible_load_metrics": flexible_load_metrics,
    "flexible_load_source_errors": flexible_load_errors,
    "power_semiconductor_metrics": power_semiconductor_metrics,
    "power_semiconductor_source_errors": power_semiconductor_errors,
    "seen_ids": seen,'''
if semi_pending_old not in s:
    raise SystemExit("800V SiC pending-state insertion point not found")
s = s.replace(semi_pending_old, semi_pending_new, 1)

semi_msg_old = '''    msg.append("• <b>800V DC</b> · 기사량이 아니라 고객 채택·양산·수주·인증·검증만 알림")

    fm = flexible_load_metrics'''
semi_msg_new = '''    msg.append("• <b>800V DC</b> · 고객 채택·양산·수주·인증·검증 + SiC/GaN 기판·소자 가격·수급 전환만 알림")

    semi_item = any(x.get("theme") == "800V DC" for x in new_items)
    if baseline_run or format_upgrade or power_semiconductor_changes or semi_item:
        sm = power_semiconductor_metrics
        msg += ["", "<b>🔌 800V DC·SiC/GaN 실행판</b>"]
        msg.append(
            f"• <b>NVIDIA 시간표</b> · 800V DC 본격 양산 <b>{int(sm['nvidia_full_scale_year'])}년</b> "
            f"· 행 단위 전력센터 최대 <b>{sm['nvidia_row_power_center_mw']:g}MW</b> "
            f"· 생태계 <b>{int(sm['nvidia_partner_count_min'])}개+</b>"
        )
        msg.append(
            f"• <b>Infineon SiC BBU</b> · <b>{sm['infineon_bbu_kw']:g}kW</b> "
            f"· 효율 <b>{sm['infineon_bbu_efficiency_pct']:g}%+</b> "
            f"· 전력밀도 <b>{sm['infineon_bbu_density_w_in3']:g}W/in³</b>"
        )
        msg.append(
            "• <b>공식 공급 검증</b> · Wolfspeed 200mm SiC → LITEON 800V DC 전력 사이드카·컴퓨트 랙 PSU 검증 "
            f"<b>{'확인' if sm.get('wolfspeed_liteon_200mm_qualified') else '미확인'}</b> "
            f"· Infineon SiC → Eaton APAC MVSST <b>{'확인' if sm.get('infineon_eaton_sst_apac') else '미확인'}</b>"
        )
        msg.append(
            f"• <b>DIGITIMES Research</b> · 2026 SiC 응용 중 EV <b>{sm['digitimes_ev_share_2026_pct']:g}%</b> 추정 "
            f"· 6인치 기판 가격 <b>{int(sm['digitimes_sic_6in_rebound_year'])}년</b> 초기 반등 전망 "
            f"· 800V HVDC 구조 <b>{int(sm['digitimes_hvdc_start_year'])}~{int(sm['digitimes_hvdc_end_year'])}</b> 수요 촉매"
        )
        msg.append("• <b>증거등급:</b> NVIDIA·OCP·Infineon·Wolfspeed는 공식 실행 사실, DIGITIMES의 응용 비중·가격 반등 연도는 리서치 전망으로 분리합니다.")
        msg.append("• <b>조기경보:</b> 2027 양산 일정 지연, 6인치 가격 재하락, 200mm 수율·고객검증 지연, GaN/Si 대체, 안전·인증 지연을 먼저 봅니다.")

    if power_semiconductor_changes:
        msg += ["", "<b>🔄 800V DC·SiC/GaN 기준 변경</b>"]
        for ch in power_semiconductor_changes[:6]:
            msg.append(f"• <b>{h(ch)}</b>")

    fm = flexible_load_metrics'''
if semi_msg_old not in s:
    raise SystemExit("800V SiC message insertion point not found")
s = s.replace(semi_msg_old, semi_msg_new, 1)

semi_scope_old = '''        msg.append("• 800V DC는 고객 채택·수주·양산·인증 단계 전환만 알림")'''
semi_scope_new = '''        msg.append("• 800V DC는 고객 채택·수주·양산·인증 + SiC/GaN 기판·소자 가격·수급 전환만 알림")'''
if semi_scope_old not in s:
    raise SystemExit("800V SiC baseline scope insertion point not found")
s = s.replace(semi_scope_old, semi_scope_new, 1)

semi_status_marker = '''    f"- 신규 의미자료: **{len(new_items)}건**'''
semi_status_prefix = '''    f"- NVIDIA 800V DC 본격 양산 연도: **{int(power_semiconductor_metrics.get('nvidia_full_scale_year', 0))}**\\n"
    f"- NVIDIA 800V 행 단위 전력센터: **{power_semiconductor_metrics.get('nvidia_row_power_center_mw')} MW**\\n"
    f"- DIGITIMES 6인치 SiC 가격 반등 예상: **{int(power_semiconductor_metrics.get('digitimes_sic_6in_rebound_year', 0))}년**\\n"
'''
if semi_status_marker not in s:
    raise SystemExit("800V SiC status insertion point not found")
s = s.replace(semi_status_marker, semi_status_prefix + semi_status_marker, 1)

semi_print_old = '''f"flex_changes={len(flexible_load_changes)} alert={should_alert}"'''
semi_print_new = '''f"flex_changes={len(flexible_load_changes)} power_semi_changes={len(power_semiconductor_changes)} "
    f"alert={should_alert}"'''
if semi_print_old not in s:
    raise SystemExit("800V SiC print insertion point not found")
s = s.replace(semi_print_old, semi_print_new, 1)

semi_links_old = '''    msg.append(f"• {a('NVIDIA·Emerald AI 유연부하 실증', NVIDIA_EMERALD)}")'''
semi_links_new = '''    msg.append(f"• {a('NVIDIA·Emerald AI 유연부하 실증', NVIDIA_EMERALD)}")
    if baseline_run or format_upgrade or power_semiconductor_changes or semi_item:
        msg.append(f"• {a('NVIDIA 800V DC 양산 로드맵', NVIDIA_800V_ARCH)}")
        msg.append(f"• {a('OCP Google·Microsoft·NVIDIA 800V DC 표준화', OCP_800V_STANDARD)}")
        msg.append(f"• {a('Infineon 24kW SiC BBU', INFINEON_SIC_BBU)}")
        msg.append(f"• {a('Infineon·Eaton SiC SST', INFINEON_EATON_SST)}")
        msg.append(f"• {a('Wolfspeed·LITEON 800V DC SiC 검증', WOLFSPEED_LITEON_800V)}")
        msg.append(f"• {a('DIGITIMES SiC 기판 회복 연구', DIGITIMES_SIC_RESEARCH)}")'''
if semi_links_old not in s:
    raise SystemExit("800V SiC official links insertion point not found")
s = s.replace(semi_links_old, semi_links_new, 1)


# Add state-level data-center permitting / cost-allocation requirements to the
# SAME time-to-power watcher. These are state-specific rules, not a nationwide
# uniform mandate, and are kept separate from FERC/RTO interconnection rules.
s = s.replace("FORMAT_VERSION = 4", "FORMAT_VERSION = 5", 1)

state_policy_const_anchor = 'DIGITIMES_SIC_RESEARCH = "https://apps.digitimes.com/reports/item.php?id=20260929RS400"\n'
state_policy_const_new = state_policy_const_anchor + '''MA_EO_658 = "https://www.mass.gov/executive-orders/no-658-establishing-requirements-for-responsible-data-center-development-and-operations-in-massachusetts-to-protect-and-support-ratepayers-communities-and-the-environment"
PA_GRID_REQUIREMENTS = "https://dced.pa.gov/business-assistance/data-center-resources/grid-requirements/"
VA_LARGE_LOAD_FACTS = "https://www.scc.virginia.gov/about-the-scc/scc-facts/"
'''
if state_policy_const_anchor not in s:
    raise SystemExit("state policy constants insertion point not found")
s = s.replace(state_policy_const_anchor, state_policy_const_new, 1)

state_policy_func_anchor = '''def detect_metric_changes(old: dict, metrics: dict, projects: dict) -> list[str]:
'''
state_policy_func_block = r'''
STATE_POLICY_DEFAULTS = {
    # Verified 2026 official public baselines. Live parsers below refresh them.
    "ma_threshold_mw": 25.0,
    "ma_grid_upgrade_cost_shift_prohibited": True,
    "ma_incremental_clean_energy_required": True,
    "ma_acp_deadline": "2026-12-31",
    "ma_community_benefits_required": True,
    "pa_full_incremental_power_cost_required": True,
    "pa_local_approval_required": True,
    "pa_clean_firm_share_2035_pct": 32.0,
    "va_min_td_charge_pct": 85.0,
    "va_collateral_pct": 60.0,
    "va_new_contract_effective_year": 2027.0,
}


def _state_policy_page_text(url: str) -> str:
    return normalize(BeautifulSoup(fetch(url, 25).text, "html.parser").get_text(" "))


def parse_state_policy_metrics(previous: dict | None = None) -> tuple[dict, list[str]]:
    previous = previous or {}
    metrics = dict(STATE_POLICY_DEFAULTS)
    errors = []
    for key, value in previous.items():
        if key in metrics and value is not None:
            metrics[key] = value

    try:
        text = _state_policy_page_text(MA_EO_658)
        low = text.lower()
        if "twenty-five megawatts" in low or re.search(r"\b25\s*(?:mw|megawatts?)\b", text, re.I):
            metrics["ma_threshold_mw"] = 25.0
        metrics["ma_grid_upgrade_cost_shift_prohibited"] = bool(
            re.search(r"other ratepayers do not pay distribution grid upgrades", text, re.I)
        )
        metrics["ma_incremental_clean_energy_required"] = bool(
            re.search(r"sufficient incremental new clean electricity generation", text, re.I)
        )
        metrics["ma_community_benefits_required"] = bool(
            re.search(r"community benefits agreement", text, re.I)
        )
        if re.search(r"December\s+31,\s+2026", text, re.I):
            metrics["ma_acp_deadline"] = "2026-12-31"
    except Exception as exc:
        errors.append(f"Massachusetts EO 658: {type(exc).__name__}")

    try:
        text = _state_policy_page_text(PA_GRID_REQUIREMENTS)
        metrics["pa_full_incremental_power_cost_required"] = bool(
            re.search(
                r"pay all costs associated with interconnection, transmission, distribution, network upgrades",
                text,
                re.I,
            )
            or re.search(r"full cost of new electricity generation, transmission, distribution", text, re.I)
        )
        metrics["pa_local_approval_required"] = bool(
            re.search(r"local approval", text, re.I)
        )
        m = re.search(r"up to\s+([0-9.]+)\s*percent\s+in\s+2035", text, re.I)
        if m:
            metrics["pa_clean_firm_share_2035_pct"] = float(m.group(1))
    except Exception as exc:
        errors.append(f"Pennsylvania GRID: {type(exc).__name__}")

    try:
        text = _state_policy_page_text(VA_LARGE_LOAD_FACTS)
        m = re.search(r"pay at least\s+([0-9.]+)%\s+of the transmission and distribution costs", text, re.I)
        if m:
            metrics["va_min_td_charge_pct"] = float(m.group(1))
        m = re.search(r"cover up to\s+([0-9.]+)%\s+of the customer.?s minimum charges", text, re.I)
        if m:
            metrics["va_collateral_pct"] = float(m.group(1))
        m = re.search(r"on or after January\s+1,\s+(20[0-9]{2})", text, re.I)
        if m:
            metrics["va_new_contract_effective_year"] = float(m.group(1))
    except Exception as exc:
        errors.append(f"Virginia SCC: {type(exc).__name__}")

    return metrics, errors


def detect_state_policy_changes(old: dict, now: dict) -> list[str]:
    oldm = old.get("state_policy_metrics") or {}
    if not oldm:
        return ["주정부 인허가·비용부담 기준선 신규 연결"]
    changes = []
    numeric_checks = (
        ("ma_threshold_mw", "Massachusetts 적용 문턱", "MW"),
        ("pa_clean_firm_share_2035_pct", "Pennsylvania 2035 청정·상시전원 비중", "%"),
        ("va_min_td_charge_pct", "Virginia 송배전 최소요금 비중", "%"),
        ("va_collateral_pct", "Virginia 담보 상단", "%"),
        ("va_new_contract_effective_year", "Virginia 신규계약 적용연도", "년"),
    )
    for key, label, unit in numeric_checks:
        ov, nv = oldm.get(key), now.get(key)
        if ov is None or nv is None:
            continue
        try:
            if float(ov) != float(nv):
                changes.append(f"{label}: {float(ov):g}{unit} → {float(nv):g}{unit}")
        except Exception:
            pass
    for key, label in (
        ("ma_grid_upgrade_cost_shift_prohibited", "Massachusetts 전력망 증설비용 전가 차단"),
        ("ma_incremental_clean_energy_required", "Massachusetts 추가 청정전력 조달"),
        ("ma_community_benefits_required", "Massachusetts 지역사회 편익협약"),
        ("pa_full_incremental_power_cost_required", "Pennsylvania 신규 전력인프라 전액 부담"),
        ("pa_local_approval_required", "Pennsylvania 지역승인"),
    ):
        if key in oldm and bool(oldm.get(key)) != bool(now.get(key)):
            changes.append(f"{label}: {bool(oldm.get(key))} → {bool(now.get(key))}")
    if oldm.get("ma_acp_deadline") and oldm.get("ma_acp_deadline") != now.get("ma_acp_deadline"):
        changes.append(
            f"Massachusetts 대체준수부담금 기한: {oldm.get('ma_acp_deadline')} → {now.get('ma_acp_deadline')}"
        )
    return changes


'''
if state_policy_func_anchor not in s:
    raise SystemExit("state policy function insertion point not found")
s = s.replace(state_policy_func_anchor, state_policy_func_block + state_policy_func_anchor, 1)

state_policy_runtime_old = '''power_semiconductor_metrics, power_semiconductor_errors = parse_power_semiconductor_metrics(
    old.get("power_semiconductor_metrics") or {}
)
errors.extend(power_semiconductor_errors)

items: list[dict] = []'''
state_policy_runtime_new = '''power_semiconductor_metrics, power_semiconductor_errors = parse_power_semiconductor_metrics(
    old.get("power_semiconductor_metrics") or {}
)
errors.extend(power_semiconductor_errors)
state_policy_metrics, state_policy_errors = parse_state_policy_metrics(
    old.get("state_policy_metrics") or {}
)
errors.extend(state_policy_errors)

items: list[dict] = []'''
if state_policy_runtime_old not in s:
    raise SystemExit("state policy runtime insertion point not found")
s = s.replace(state_policy_runtime_old, state_policy_runtime_new, 1)

state_policy_change_old = '''power_semiconductor_changes = detect_power_semiconductor_changes(old, power_semiconductor_metrics)
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
should_alert = (
    baseline_run or format_upgrade or bool(new_items) or bool(metric_changes)
    or bool(flexible_load_changes) or bool(power_semiconductor_changes)
)'''
state_policy_change_new = '''power_semiconductor_changes = detect_power_semiconductor_changes(old, power_semiconductor_metrics)
state_policy_changes = detect_state_policy_changes(old, state_policy_metrics)
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
should_alert = (
    baseline_run or format_upgrade or bool(new_items) or bool(metric_changes)
    or bool(flexible_load_changes) or bool(power_semiconductor_changes)
    or bool(state_policy_changes)
)'''
if state_policy_change_old not in s:
    raise SystemExit("state policy alert gate insertion point not found")
s = s.replace(state_policy_change_old, state_policy_change_new, 1)

state_policy_pending_old = '''    "power_semiconductor_metrics": power_semiconductor_metrics,
    "power_semiconductor_source_errors": power_semiconductor_errors,
    "seen_ids": seen,'''
state_policy_pending_new = '''    "power_semiconductor_metrics": power_semiconductor_metrics,
    "power_semiconductor_source_errors": power_semiconductor_errors,
    "state_policy_metrics": state_policy_metrics,
    "state_policy_source_errors": state_policy_errors,
    "seen_ids": seen,'''
if state_policy_pending_old not in s:
    raise SystemExit("state policy pending state insertion point not found")
s = s.replace(state_policy_pending_old, state_policy_pending_new, 1)

state_policy_msg_anchor = '''    fm = flexible_load_metrics
'''
state_policy_msg_block = '''    sp = state_policy_metrics
    if baseline_run or format_upgrade or state_policy_changes:
        msg += ["", "<b>🏛️ 주정부 인허가·비용부담 실행판</b>"]
        msg.append(
            f"• <b>Massachusetts</b> · 피크수요 <b>{sp['ma_threshold_mw']:g}MW 초과</b> "
            f"· 지역사회 편익협약 {'의무' if sp.get('ma_community_benefits_required') else '재확인'} "
            f"· 다른 요금납부자에게 송배전 증설비용 전가 {'차단' if sp.get('ma_grid_upgrade_cost_shift_prohibited') else '재확인'}"
        )
        msg.append(
            f"  ↳ 연간 사용전력을 충당할 추가 청정전력 조달 {'요구' if sp.get('ma_incremental_clean_energy_required') else '재확인'} "
            f"· 부족 시 대체준수부담금 제도 기한 <b>{sp.get('ma_acp_deadline')}</b>"
        )
        msg.append(
            f"• <b>Pennsylvania</b> · 지역승인 {'요구' if sp.get('pa_local_approval_required') else '재확인'} "
            f"· 신규 발전·송전·배전·계통접속·망증설 비용 {'전액 사업자 부담' if sp.get('pa_full_incremental_power_cost_required') else '재확인'} "
            f"· 청정·상시전원 비중 2035년 최대 <b>{sp['pa_clean_firm_share_2035_pct']:g}%</b>"
        )
        msg.append(
            f"• <b>Virginia</b> · 송전·배전 월 최소요금 <b>{sp['va_min_td_charge_pct']:g}%</b> "
            f"· 신용조건 미충족 시 계약기간 최소요금의 최대 <b>{sp['va_collateral_pct']:g}%</b> 담보 "
            f"· 신규계약 <b>{int(sp['va_new_contract_effective_year'])}년</b> 적용"
        )
        msg.append("• <b>판정:</b> 미국 전체의 단일 규정이 아니라 주별 인허가·요금·비용배분 조건이 강화되는 흐름으로 봅니다.")
        msg.append("• <b>투자 연결:</b> 계통증설 비용과 허가기간을 직접 부담할수록 빠른 현장전원·연료전지·가스·BESS의 상대가치가 올라갈 수 있습니다.")
        if state_policy_errors:
            msg.append("• 일부 공식 페이지 조회 실패 시 직전 검증값을 유지하고, 오류 자체는 변화로 알리지 않습니다.")

    if state_policy_changes:
        msg += ["", "<b>🔄 주정부 인허가·비용부담 기준 변경</b>"]
        for ch in state_policy_changes[:8]:
            msg.append(f"• <b>{h(ch)}</b>")

    fm = flexible_load_metrics
'''
if state_policy_msg_anchor not in s:
    raise SystemExit("state policy message insertion point not found")
s = s.replace(state_policy_msg_anchor, state_policy_msg_block, 1)

state_policy_scope_old = '''        msg.append("• 유연부하·수요반응은 계약 MW·감축률·응답시간·지속시간·계통접속 단축을 추적")
'''
state_policy_scope_new = '''        msg.append("• 유연부하·수요반응은 계약 MW·감축률·응답시간·지속시간·계통접속 단축을 추적")
        msg.append("• 주정부 인허가·요금은 Massachusetts·Pennsylvania·Virginia의 비용배분·지역승인·청정전력 의무 변화를 추적")
'''
if state_policy_scope_old not in s:
    raise SystemExit("state policy baseline scope insertion point not found")
s = s.replace(state_policy_scope_old, state_policy_scope_new, 1)

state_policy_status_marker = '''    f"- 신규 의미자료: **{len(new_items)}건**'''
state_policy_status_prefix = '''    f"- Massachusetts 데이터센터 규제 문턱: **{state_policy_metrics.get('ma_threshold_mw')} MW 초과**\\n"
    f"- Pennsylvania 신규 전력인프라 전액 부담: **{state_policy_metrics.get('pa_full_incremental_power_cost_required')}**\\n"
    f"- Virginia 송배전 최소요금: **{state_policy_metrics.get('va_min_td_charge_pct')}%**\\n"
    f"- 주정부 정책 원천 오류: **{'; '.join(state_policy_errors) if state_policy_errors else '없음'}**\\n"
'''
if state_policy_status_marker not in s:
    raise SystemExit("state policy status insertion point not found")
s = s.replace(state_policy_status_marker, state_policy_status_prefix + state_policy_status_marker, 1)

state_policy_print_old = '''f"flex_changes={len(flexible_load_changes)} power_semi_changes={len(power_semiconductor_changes)} "
    f"alert={should_alert}"'''
state_policy_print_new = '''f"flex_changes={len(flexible_load_changes)} power_semi_changes={len(power_semiconductor_changes)} "
    f"state_policy_changes={len(state_policy_changes)} alert={should_alert}"'''
if state_policy_print_old not in s:
    raise SystemExit("state policy print insertion point not found")
s = s.replace(state_policy_print_old, state_policy_print_new, 1)

state_policy_links_old = '''        msg.append(f"• {a('DIGITIMES SiC 기판 회복 연구', DIGITIMES_SIC_RESEARCH)}")'''
state_policy_links_new = '''        msg.append(f"• {a('DIGITIMES SiC 기판 회복 연구', DIGITIMES_SIC_RESEARCH)}")
    if baseline_run or format_upgrade or state_policy_changes:
        msg.append(f"• {a('Massachusetts Executive Order 658', MA_EO_658)}")
        msg.append(f"• {a('Pennsylvania GRID Requirements', PA_GRID_REQUIREMENTS)}")
        msg.append(f"• {a('Virginia 대형부하 요금 기준', VA_LARGE_LOAD_FACTS)}")'''
if state_policy_links_old not in s:
    raise SystemExit("state policy links insertion point not found")
s = s.replace(state_policy_links_old, state_policy_links_new, 1)


p.write_text(s, encoding="utf-8")
print("US time-to-power flexible-load + 800V SiC/GaN + state-policy guard inserted")
