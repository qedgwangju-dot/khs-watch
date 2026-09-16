#!/usr/bin/env python3
from pathlib import Path

PATH = Path("scripts/pjm_data_center_policy_watch.py")

# Keep the existing PJM watcher, but make sure its live run also covers the
# FERC/PJM large-load consumer-protection track and actual capacity-market
# stress signals agreed for this alert family.
POLICY_PATCHES = (
    (
        'FERC_DECISIONS = "https://www.ferc.gov/news-events/news/decisions-notices"\n',
        'FERC_DECISIONS = "https://www.ferc.gov/news-events/news/decisions-notices"\n'
        'PJM_CAPACITY_RESULT = "https://insidelines.pjm.com/pjm-capacity-auction-procures-138318-mw-of-generation-resources-as-work-continues-to-address-growing-electricity-demand/"\n',
    ),
    (
        'DOCKETS = ("ER26-3380", "ER26-3515")',
        'DOCKETS = ("ER26-3380", "ER26-3515", "EL26-67", "RM26-4")',
    ),
    (
        '    "capacity shortfall", "backstop procurement",\n)',
        '    "capacity shortfall", "backstop procurement",\n'
        '    "cost recovery agreement", "transmission security agreement",\n'
        '    "construction service agreement", "readiness requirement",\n'
        '    "site control", "financial security", "speculative load",\n'
        '    "base residual auction", "clearing price", "reliability requirement",\n'
        '    "new generation", "generation uprates", "reserve margin",\n'
        ')',
    ),
    (
        '    \'PJM data center large load FERC\',\n)',
        '    \'PJM data center large load FERC\',\n'
        '    \'PJM "EL26-67" large load\',\n'
        '    \'PJM "Cost Recovery Agreement" data center\',\n'
        '    \'PJM large load readiness "site control"\',\n'
        '    \'PJM 2028 2029 Base Residual Auction capacity price shortfall new generation\',\n'
        '    \'PJM 2029 2030 Base Residual Auction capacity price shortfall new generation\',\n'
        ')',
    ),
    (
        '    (PJM_RBP, "PJM RBP 공식 페이지"),\n):',
        '    (PJM_RBP, "PJM RBP 공식 페이지"),\n'
        '    (PJM_CAPACITY_RESULT, "PJM 용량시장 공식 결과"),\n'
        '    (FERC_DECISIONS, "FERC 결정·명령"),\n'
        '):',
    ),
)

CAPACITY_FUNC_ANCHOR = '\ndef collect_pjm_page(url: str, label: str):\n'
CAPACITY_FUNC = r'''
CAPACITY_DEFAULTS = {
    "capacity_delivery_year": "2028/2029",
    "capacity_cleared_mw": 138318.0,
    "capacity_frr_mw": 10864.0,
    "capacity_total_mw": 149182.0,
    "capacity_price_usd_mw_day": 325.0,
    "capacity_shortfall_mw": 6831.0,
    "capacity_reserve_margin_pct": 14.7,
    "capacity_peak_load_increase_mw": 2000.0,
    "capacity_new_generation_uprates_mw": 525.0,
}


def parse_capacity_stress(previous=None):
    previous = previous or {}
    out = dict(CAPACITY_DEFAULTS)
    for key in CAPACITY_DEFAULTS:
        if previous.get(key) is not None:
            out[key] = previous[key]
    try:
        text = normalize(BeautifulSoup(fetch(PJM_CAPACITY_RESULT).text, "html.parser").get_text(" "))
        m = re.search(r"results of its\s+(\d{4}/\d{4})\s+Base Residual Auction", text, re.I)
        if m:
            out["capacity_delivery_year"] = m.group(1)
        patterns = {
            "capacity_cleared_mw": r"secured\s+([0-9,]+)\s*MW of unforced capacity",
            "capacity_frr_mw": r"FRR acquired an additional\s+([0-9,]+)\s*MW",
            "capacity_total_mw": r"for a total of\s+([0-9,]+)\s*MW in UCAP available",
            "capacity_price_usd_mw_day": r"price came in at.*?\$([0-9,.]+)/MW-day",
            "capacity_shortfall_mw": r"short of PJM.?s reliability requirement by\s+([0-9,]+)\s*MW",
            "capacity_reserve_margin_pct": r"reserve margin of\s+([0-9.]+)%",
            "capacity_peak_load_increase_mw": r"forecasted peak load.*?approximately\s+([0-9,]+)\s*MW higher",
            "capacity_new_generation_uprates_mw": r"cleared\s+([0-9,]+)\s*MW UCAP of new generation and generation uprates",
        }
        for key, pattern in patterns.items():
            m = re.search(pattern, text, re.I)
            if m:
                out[key] = float(m.group(1).replace(",", ""))
    except Exception:
        pass
    return out
'''

BASELINE_OLD = "baseline = parse_baseline()\nitems = []"
BASELINE_NEW = '''_saved_baseline = old.get("baseline", {})
_required_baseline_keys = (
    "target_mw",
    "max_price_usd_mw_day",
    "max_years",
    "planned_start",
)
try:
    baseline = parse_baseline()
except requests.RequestException as _exc:
    if not all(_saved_baseline.get(_k) is not None for _k in _required_baseline_keys):
        raise
    baseline = dict(_saved_baseline)
    print(
        "PJM baseline source temporarily unavailable; "
        f"keeping last verified official baseline ({type(_exc).__name__})"
    )
for _k in _required_baseline_keys:
    if baseline.get(_k) is None and _saved_baseline.get(_k) is not None:
        baseline[_k] = _saved_baseline[_k]
baseline.update(parse_capacity_stress(_saved_baseline))
items = []'''

text = PATH.read_text(encoding="utf-8")
for old, new in POLICY_PATCHES:
    if old not in text:
        raise SystemExit(f"PJM policy guard insertion point not found: {old[:80]}")
    text = text.replace(old, new, 1)

if CAPACITY_FUNC_ANCHOR not in text:
    raise SystemExit("PJM capacity function insertion point not found")
text = text.replace(CAPACITY_FUNC_ANCHOR, "\n" + CAPACITY_FUNC + CAPACITY_FUNC_ANCHOR, 1)

if BASELINE_OLD not in text:
    raise SystemExit("PJM baseline guard insertion point not found")
text = text.replace(BASELINE_OLD, BASELINE_NEW, 1)

# Workflow first upgrades the legacy source from v2 to v5. Bump one more time
# so this new numeric market-stress block is delivered once and becomes state.
text = text.replace("FORMAT_VERSION = 5", "FORMAT_VERSION = 6", 1)

changes_old = '''    ("planned_start", "RBP 개시 목표일"),\n):'''
changes_new = '''    ("planned_start", "RBP 개시 목표일"),\n    ("capacity_delivery_year", "용량시장 대상연도"),\n    ("capacity_price_usd_mw_day", "용량시장 낙찰가격"),\n    ("capacity_shortfall_mw", "용량시장 신뢰도 부족분"),\n    ("capacity_new_generation_uprates_mw", "신규발전·증설 낙찰량"),\n    ("capacity_reserve_margin_pct", "용량시장 예비율"),\n    ("capacity_peak_load_increase_mw", "용량시장 피크부하 전망 증가"),\n):'''
if changes_old not in text:
    raise SystemExit("PJM changes-loop insertion point not found")
text = text.replace(changes_old, changes_new, 1)

msg_anchor = '''    if baseline.get("planned_start"):\n        msg.append(f"• 개시 목표  <b>{h(baseline['planned_start'])}</b> · FERC 승인 전제")\n\n    if annual_usd or total_usd:\n'''
msg_new = '''    if baseline.get("planned_start"):\n        msg.append(f"• 개시 목표  <b>{h(baseline['planned_start'])}</b> · FERC 승인 전제")\n\n    msg += ["", "<b>⚡ 용량시장 실제 스트레스</b>"]\n    msg.append(\n        f"• <b>{h(baseline.get('capacity_delivery_year'))} BRA</b> │ 낙찰 <b>${baseline.get('capacity_price_usd_mw_day'):,.2f}/MW-day</b> │ 신뢰도 부족 <b>{baseline.get('capacity_shortfall_mw'):,.0f}MW</b>"\n    )\n    msg.append(\n        f"• <b>확보용량</b> │ 경매 {baseline.get('capacity_cleared_mw'):,.0f}MW + FRR {baseline.get('capacity_frr_mw'):,.0f}MW = 총 {baseline.get('capacity_total_mw'):,.0f}MW"\n    )\n    msg.append(\n        f"• <b>신규발전·증설</b> │ <b>{baseline.get('capacity_new_generation_uprates_mw'):,.0f}MW</b> │ 피크부하 전망은 전년 경매 대비 약 +{baseline.get('capacity_peak_load_increase_mw'):,.0f}MW"\n    )\n    msg.append(\n        f"• <b>예비율</b> │ {baseline.get('capacity_reserve_margin_pct'):g}% │ 가격이 상한에 걸려도 신규 공급이 수요 증가를 못 따라가는지 판정"\n    )\n\n    if annual_usd or total_usd:\n'''
if msg_anchor not in text:
    raise SystemExit("PJM message capacity insertion point not found")
text = text.replace(msg_anchor, msg_new, 1)

scope_old = '''            "• 실제 목표MW → 낙찰MW → 낙찰가격 → 계약기간",\n            "• BESS·가스·원전·청정에너지 낙찰 기술과 사업자",\n'''
scope_new = '''            "• 실제 목표MW → 낙찰MW → 낙찰가격 → 계약기간",\n            "• 용량시장 부족MW → 낙찰가격 → 신규발전·증설MW → 예비율",\n            "• BESS·가스·원전·청정에너지 낙찰 기술과 사업자",\n'''
if scope_old not in text:
    raise SystemExit("PJM scope insertion point not found")
text = text.replace(scope_old, scope_new, 1)

official_old = '''        f"• {a('PJM RBP 원문', PJM_RBP)}",\n        f"• {a('PJM 기준 설명', PJM_BASELINE)}",\n        f"• {a('FERC Decisions', FERC_DECISIONS)}",\n'''
official_new = '''        f"• {a('PJM RBP 원문', PJM_RBP)}",\n        f"• {a('PJM 용량시장 결과', PJM_CAPACITY_RESULT)}",\n        f"• {a('PJM 기준 설명', PJM_BASELINE)}",\n        f"• {a('FERC Decisions', FERC_DECISIONS)}",\n'''
if official_old not in text:
    raise SystemExit("PJM official-links insertion point not found")
text = text.replace(official_old, official_new, 1)

status_old = '''    f"- 개시 목표: **{baseline.get('planned_start')}**\\n"\n    f"- 현재 신규 자료: **{len(new_items)}건**\\n"\n'''
status_new = '''    f"- 개시 목표: **{baseline.get('planned_start')}**\\n"\n    f"- 용량시장 대상연도: **{baseline.get('capacity_delivery_year')}**\\n"\n    f"- 용량시장 낙찰가격: **${baseline.get('capacity_price_usd_mw_day')}/MW-day**\\n"\n    f"- 용량시장 신뢰도 부족분: **{baseline.get('capacity_shortfall_mw')} MW**\\n"\n    f"- 신규발전·증설 낙찰량: **{baseline.get('capacity_new_generation_uprates_mw')} MW**\\n"\n    f"- 예비율: **{baseline.get('capacity_reserve_margin_pct')}%**\\n"\n    f"- 현재 신규 자료: **{len(new_items)}건**\\n"\n'''
if status_old not in text:
    raise SystemExit("PJM status capacity insertion point not found")
text = text.replace(status_old, status_new, 1)

PATH.write_text(text, encoding="utf-8")
print("PJM baseline + FERC large-load + capacity-market stress guard inserted")
