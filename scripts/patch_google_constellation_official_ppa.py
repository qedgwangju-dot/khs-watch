#!/usr/bin/env python3
from pathlib import Path

p = Path("scripts/us_data_center_generation_buildout_watch.py")
s = p.read_text(encoding="utf-8")

# This patch runs after guard_us_time_to_power_metrics_source.py.  It promotes
# Google–Constellation from the earlier Reuters/Bloomberg negotiation baseline
# to the Oct. 6, 2026 first-party signed agreement while keeping the reported
# "$1B+" negotiation value distinct from the official transaction economics.
s = s.replace("HYPERSCALER_NUCLEAR_PPA_EXTENSION_V5", "HYPERSCALER_NUCLEAR_PPA_EXTENSION_V6", 1)
s = s.replace("PPA_STATE_VERSION = 5", "PPA_STATE_VERSION = 6", 1)

anchor = 'PPA_REUTERS_GOOGLE_CONSTELLATION_SIGNED = "https://www.reuters.com/business/energy/google-enters-massive-36-gw-power-deal-with-constellation-energy-2026-10-06/"\n'
if anchor not in s:
    raise SystemExit("Google-Constellation signed Reuters anchor missing")
s = s.replace(
    anchor,
    anchor + 'PPA_GOOGLE_CONSTELLATION_OFFICIAL = "https://www.googlecloudpresscorner.com/2026-10-06-Google-and-Constellation-Announce-Landmark-Agreement-to-Bring-890-MW-of-New-Nuclear-Capacity-to-PJM-Grid-as-Part-of-Long-Term-Power-Deal"\n',
    1,
)

old = '''    "google_constellation": {
        "buyer": "Google",
        "seller": "Constellation",
        "stage": "reported_near_deal",
        "official": False,
        "amount_floor_usd_b": 1.0,
        "provenance": {
            "stage": "media",
            "amount_floor_usd_b": "media",
        },
        "ppa_mw": None,
        "uprate_mw": None,
        "plant_capacity_mw": None,
        "years": None,
        "plant": None,
        "asset_mode": "unknown",
        "source": "Bloomberg 보도·Reuters 재확인",
        "url": PPA_REUTERS_GOOGLE_CONSTELLATION,
        "published": "2026-10-06",
        "note": "다년 계약 협상 임박 보도 · 아직 양사 공식 체결 발표 없음",
    },'''
new = '''    "google_constellation": {
        "buyer": "Google",
        "seller": "Constellation",
        "stage": "signed_official",
        "official": True,
        "amount_floor_usd_b": 1.0,
        "nuclear_upgrade_investment_floor_usd_b": 4.3,
        "ppa_mw": 890.0,
        "total_supply_mw": 3590.0,
        "nuclear_supply_mw": 890.0,
        "other_pjm_supply_mw": 2700.0,
        "uprate_mw": 890.0,
        "nuclear_unit_count": 11,
        "years": 20,
        "other_pjm_years": 15,
        "first_uprate_year": 2028,
        "plant": "Constellation PJM nuclear fleet · 11 units in Illinois, Pennsylvania, New Jersey",
        "asset_mode": "existing_uprate",
        "provenance": {
            "stage": "official",
            "amount_floor_usd_b": "prior_media",
            "nuclear_upgrade_investment_floor_usd_b": "official",
            "ppa_mw": "official",
            "total_supply_mw": "official",
            "nuclear_supply_mw": "official",
            "other_pjm_supply_mw": "official",
            "uprate_mw": "official",
            "nuclear_unit_count": "official",
            "years": "official",
            "other_pjm_years": "official",
            "first_uprate_year": "official",
            "plant": "official",
            "asset_mode": "official",
        },
        "source": "Google·Constellation 공식",
        "url": PPA_GOOGLE_CONSTELLATION_OFFICIAL,
        "published": "2026-10-06",
        "note": "20년 원전 PPA 890MW · 11개 기존 원전 호기 출력증강 · Constellation 신규투자 43억달러 초과 · 별도 PJM 2,700MW 15년 공급계약 · 첫 출력증강 2028년 예상",
    },'''
if old not in s:
    raise SystemExit("Google-Constellation baseline block missing")
s = s.replace(old, new, 1)

s = s.replace(
    '"blog.google", "sustainability.google", "aboutamazon.com",',
    '"blog.google", "sustainability.google", "googlecloudpresscorner.com", "aboutamazon.com",',
    1,
)

# Preserve the separate 15-year PJM supply term and first-uprate year through
# scoring, state merge, provenance, and material-change detection.
s = s.replace(
    '"nuclear_unit_count", "years", "plant", "asset_mode")',
    '"nuclear_unit_count", "years", "other_pjm_years", "first_uprate_year", "plant", "asset_mode")',
    1,
)
s = s.replace(
    '"nuclear_unit_count", "years", "plant", "asset_mode", "source",',
    '"nuclear_unit_count", "years", "other_pjm_years", "first_uprate_year", "plant", "asset_mode", "source",',
    1,
)
s = s.replace(
    '"nuclear_unit_count", "years", "plant", "asset_mode", "site_investment_floor_usd_b"',
    '"nuclear_unit_count", "years", "other_pjm_years", "first_uprate_year", "plant", "asset_mode", "site_investment_floor_usd_b"',
    1,
)
s = s.replace(
    '("nuclear_unit_count", "업그레이드 원전 호기 수"),\n        ("years", "계약기간"),',
    '("nuclear_unit_count", "업그레이드 원전 호기 수"),\n        ("years", "원전 PPA 계약기간"),\n        ("other_pjm_years", "PJM 기타 공급 계약기간"),\n        ("first_uprate_year", "첫 출력증강 예정연도"),',
    1,
)

render_anchor = '''        if _now.get("nuclear_unit_count") is not None:
            unit_scope = "공식" if provenance.get("nuclear_unit_count") == "official" else "보도"
            lines.append(f"• <b>대상</b> │ {unit_scope} 원전 {int(_now['nuclear_unit_count'])}개 호기 업그레이드")
'''
if render_anchor not in s:
    raise SystemExit("Google-Constellation render anchor missing")
s = s.replace(
    render_anchor,
    render_anchor + '''        if _now.get("other_pjm_years") is not None:
            other_year_scope = "공식" if provenance.get("other_pjm_years") == "official" else "보도"
            lines.append(f"• <b>PJM 기타 공급기간</b> │ {other_year_scope} {int(_now['other_pjm_years'])}년")
        if _now.get("first_uprate_year") is not None:
            uprate_year_scope = "공식" if provenance.get("first_uprate_year") == "official" else "보도"
            lines.append(f"• <b>첫 출력증강</b> │ {uprate_year_scope} {int(_now['first_uprate_year'])}년 예상")
''',
    1,
)

s = s.replace(
    "• Google–Constellation 현재 기준선 │ 최소 10억달러 다년계약 협상 임박 보도 · 양사 공식 체결 발표 전",
    "• Google–Constellation │ 공식 체결 · 원전 890MW 20년 · 11개 호기 출력증강 · Constellation 43억달러 초과 투자 · 별도 PJM 2,700MW 15년 · 첫 증설 2028년 예상 · 10억달러는 체결 전 보도치로 최종 계약가 미공개",
    1,
)

# Regression: official signed terms must remain distinct from the earlier media
# value and from Amazon's Calvert Cliffs terms.
test_anchor = '    print("hyperscaler_nuclear_ppa_parser_self_test=passed")\n'
if test_anchor not in s:
    raise SystemExit("PPA self-test end anchor missing")
s = s.replace(
    test_anchor,
    '''    official_google = PPA_BASELINES["google_constellation"]
    if (
        official_google.get("stage") != "signed_official"
        or not official_google.get("official")
        or float(official_google.get("ppa_mw") or 0) != 890.0
        or int(official_google.get("years") or 0) != 20
        or float(official_google.get("other_pjm_supply_mw") or 0) != 2700.0
        or int(official_google.get("other_pjm_years") or 0) != 15
        or int(official_google.get("nuclear_unit_count") or 0) != 11
        or float(official_google.get("nuclear_upgrade_investment_floor_usd_b") or 0) != 4.3
        or int(official_google.get("first_uprate_year") or 0) != 2028
        or (official_google.get("provenance") or {}).get("amount_floor_usd_b") != "prior_media"
    ):
        raise RuntimeError(f"Google official signed baseline regression: {official_google}")

''' + test_anchor,
    1,
)

p.write_text(s, encoding="utf-8")
print("Google-Constellation official signed PPA patch applied")
