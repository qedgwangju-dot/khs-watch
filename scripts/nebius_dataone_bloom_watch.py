#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT = Path("out")
STATE = Path("data/nebius_dataone_bloom_state.json")
PENDING = OUT / "nebius_dataone_bloom_pending_state.json"
ALERT = OUT / "nebius_dataone_bloom_alert.txt"
STATUS = OUT / "nebius_dataone_bloom_status.md"

FORMAT_VERSION = 7
# Verification reruns must remain silent when extracted facts are unchanged.
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}

FRANKFORT = "https://dataonefrankfort.com/"
NEBIUS_VINELAND = "https://nebius.com/vinelandnj"
NEBIUS_BLOOM = "https://nebius.com/newsroom/nebius-and-bloom-energy-partner-to-power-ai-infrastructure-build-out"
NEBIUS_PARTNER_MODEL = "https://nebius.com/newsroom/nebius-introduces-business-model-to-scale-ai-cloud-globally-through-infrastructure-partnerships"
NEBIUS_NEWSROOM = "https://nebius.com/newsroom"
FRANKFORT_MAYOR = "https://frankfort-in.gov/egov/apps/document/center.egov?id=1579&view=item"
IMPA_ABOUT = "https://www.impa.com/about-impa/"
BLOOM_NEWSROOM = "https://www.bloomenergy.com/newsroom/"
BLOOM_ORACLE = "https://www.bloomenergy.com/news/bloom-energy-and-oracle-expand-strategic-partnership-to-deploy-up-to-2-8-gw-to-accelerate-ai-infrastructure-build-out/"
BLOOM_MITAC = "https://www.bloomenergy.com/news/bloom-energy-continues-to-set-the-standard-for-ai-onsite-power-with-expanded-mitac-partnership/"
BLOOM_800V = "https://investor.bloomenergy.com/press-releases/press-release-details/2026/Bloom-Energys-800V-DC-Native-Power-Can-Cut-Billions-from-AI-Data-Center-Costs-Reduce-Power-Use-and-Eliminate-Need-for-Transformers/default.aspx"
BLOOM_BROOKFIELD_25B = "https://www.bloomenergy.com/news/brookfield-and-bloom-energy-expand-ai-infrastructure-partnership/"
BLOOM_EQUINIX_100MW = "https://www.bloomenergy.com/news/bloom-energy-expands-data-center-power-agreement-with-equinix-surpassing-100mw/"
BLOOM_MIDYEAR_2026 = "https://www.bloomenergy.com/news/ai-data-center-growth-hinges-on-solving-both-power-constraints-and-community-concerns-bloom-energy-report-finds/"
BLOOM_POWER_CONNECT = "https://www.bloomenergy.com/news/bloom-energy-introduces-power-connect/"
BLOOM_ENERGY_SERVER = "https://www.bloomenergy.com/resource/bloom-energy-server/"


def fetch_text(url: str, timeout: int = 25) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return " ".join(BeautifulSoup(r.content, "html.parser").get_text(" ", strip=True).split())


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def number(text: str, pattern: str, cast=float):
    m = re.search(pattern, text, re.I)
    if not m:
        raise RuntimeError(f"pattern missing: {pattern}")
    return cast(m.group(1).replace(",", ""))


def fx(old: dict) -> dict:
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return {"usdkrw": float(q.rate), "basis": q.basis, "source": q.source}
    except Exception:
        prior = old.get("fx") or {}
        if prior.get("usdkrw"):
            return {**prior, "source": str(prior.get("source") or "") + " · 직전 저장값"}
        raise


def krw_from_usd_b(value_b: float, rate: float) -> str:
    eok = int(round(value_b * 1_000_000_000 * rate / 100_000_000))
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def around(text: str, needle: str, width: int = 900) -> str:
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    return text[i:i+width]


def snapshot() -> dict:
    f = fetch_text(FRANKFORT)
    v = fetch_text(NEBIUS_VINELAND)
    nb = fetch_text(NEBIUS_BLOOM)
    pm = fetch_text(NEBIUS_PARTNER_MODEL)
    nr = fetch_text(NEBIUS_NEWSROOM)
    try:
        mayor = fetch_text(FRANKFORT_MAYOR)
    except Exception:
        mayor = ""
    try:
        impa = fetch_text(IMPA_ABOUT)
    except Exception:
        impa = ""
    try:
        bloom_news = fetch_text(BLOOM_NEWSROOM)
    except Exception:
        bloom_news = ""

    bloom_market_errors = []
    try:
        bloom_oracle = fetch_text(BLOOM_ORACLE)
    except Exception as exc:
        bloom_oracle = ""
        bloom_market_errors.append(f"Bloom Oracle: {type(exc).__name__}")
    try:
        bloom_mitac = fetch_text(BLOOM_MITAC)
    except Exception as exc:
        bloom_mitac = ""
        bloom_market_errors.append(f"Bloom MiTAC: {type(exc).__name__}")
    try:
        bloom_800v = fetch_text(BLOOM_800V)
    except Exception as exc:
        bloom_800v = ""
        bloom_market_errors.append(f"Bloom 800V: {type(exc).__name__}")
    try:
        bloom_brookfield = fetch_text(BLOOM_BROOKFIELD_25B)
    except Exception as exc:
        bloom_brookfield = ""
        bloom_market_errors.append(f"Bloom Brookfield: {type(exc).__name__}")
    try:
        bloom_equinix = fetch_text(BLOOM_EQUINIX_100MW)
    except Exception as exc:
        bloom_equinix = ""
        bloom_market_errors.append(f"Bloom Equinix: {type(exc).__name__}")
    try:
        bloom_midyear = fetch_text(BLOOM_MIDYEAR_2026)
    except Exception as exc:
        bloom_midyear = ""
        bloom_market_errors.append(f"Bloom mid-year report: {type(exc).__name__}")
    try:
        bloom_power_connect = fetch_text(BLOOM_POWER_CONNECT)
    except Exception as exc:
        bloom_power_connect = ""
        bloom_market_errors.append(f"Bloom Power Connect: {type(exc).__name__}")
    try:
        bloom_server = fetch_text(BLOOM_ENERGY_SERVER)
    except Exception as exc:
        bloom_server = ""
        bloom_market_errors.append(f"Bloom Energy Server: {type(exc).__name__}")

    required = [
        ("Frankfort", "DataOne would like to build an AI factory", f),
        ("Vineland", "build-to-suit for Nebius by DataOne", v),
        ("Nebius-Bloom", "Nebius and Bloom Energy", nb),
        ("Nebius partner model", "infrastructure partners", pm),
    ]
    for label, needle, body in required:
        if needle.lower() not in body.lower():
            raise RuntimeError(f"{label} identity guard failed")

    investment_b = number(f, r"total capital investment of \$([0-9]+(?:\.[0-9]+)?) billion")
    sqft = number(f, r"Approximately ([0-9,]+) square feet", int)
    acres = number(f, r"parcel of land is approximately ([0-9,]+) acres", int)
    grid_mw = number(f, r"([0-9,]+)MW comes from the grid", int)
    onsite_mw = number(f, r"([0-9,]+)MW will be on-site power generated by fuel cells", int)
    total_mw = grid_mw + onsite_mw
    water_mgal_y = number(f, r"estimated ([0-9,]+) million gallons per year", float)

    tenant_blob = around(f, "Will DataOne tell us who the tenant or customer is?", 900)
    tenant_status = "미공개"
    tenant_name = None
    for candidate in ("Nebius", "Microsoft", "Meta", "Google", "Amazon", "Oracle", "OpenAI", "Anthropic", "xAI"):
        if candidate.lower() in tenant_blob.lower():
            tenant_status = "공식 이름 언급"
            tenant_name = candidate
            break
    if "identity will be disclosed" in tenant_blob.lower() or "official announcement at a later date" in tenant_blob.lower():
        tenant_status = "미공개"
        tenant_name = None

    frankfort_nebius_official = (
        ("frankfort" in nr.lower() and "nebius" in nr.lower()) or tenant_name == "Nebius"
    )

    bloom_named = "bloom fuel cells" in f.lower()
    natural_gas = "fuel cells use natural gas as a feedstock" in f.lower()
    centerpoint = "centerpoint energy" in f.lower()
    low_f = f.lower()
    lng_backup = (
        "storage tank" in low_f
        and "lng" in low_f
        and ("back-up" in low_f or "backup" in low_f)
        and "pipeline gas" in low_f
    )
    substations = 2 if "funding and constructing two substations" in f.lower() else None
    late_2026 = "groundbreaking to occur late 2026 or very early 2027" in f.lower()
    build_months = "18-24개월" if "18-24 months" in f else None

    vineland_confirmed = (
        "build-to-suit for Nebius by DataOne" in v
        and "Nebius will serve as the tenant" in v
        and "Bloom Energy fuel cells" in v
    )
    bloom_long_term = "long-term partnership" in nb.lower() and "328 mw" in nb.lower()
    partner_model = (
        "partners finance and own the infrastructure and hardware" in pm.lower()
        and "takes the resulting capacity to market" in pm.lower()
    )
    bloom_frankfort_official = (
        "frankfort" in bloom_news.lower()
        and ("dataone" in bloom_news.lower() or "data one" in bloom_news.lower())
    )
    mayor_no_commitment = (
        True if "no commitments or agreements have been made" in mayor.lower()
        else None
    )
    impa_members = True if "61 communities" in impa.lower() else None

    bloom_ai_market = {
        # Public company baselines. Oracle figures are contracted/master-agreement
        # quantities; the 800V savings are Bloom's own comparative model, not customer savings realized to date.
        "oracle_master_agreement_gw": (
            number(bloom_oracle, r"up to\s+([0-9.]+)\s+gigawatts", float)
            if bloom_oracle and re.search(r"up to\s+[0-9.]+\s+gigawatts", bloom_oracle, re.I)
            else 2.8
        ),
        "oracle_initial_contracted_gw": (
            number(bloom_oracle, r"initial\s+([0-9.]+)\s+GW", float)
            if bloom_oracle and re.search(r"initial\s+[0-9.]+\s+GW", bloom_oracle, re.I)
            else 1.2
        ),
        "ai_infrastructure_segment_mw_approx": (
            number(bloom_mitac, r"approximately\s+([0-9,]+)\s+MW", float)
            if bloom_mitac and re.search(r"approximately\s+[0-9,]+\s+MW", bloom_mitac, re.I)
            else 250.0
        ),
        "brookfield_financing_framework_usd_b": 25.0,
        "equinix_total_capacity_mw_min": 100.0,
        "equinix_operational_mw": 75.0,
        "equinix_under_construction_mw": 30.0,
        "developer_byop_share_pct": 61.0,
        "power_connect_install_time_reduction_pct": 40.0,
        "natural_gas_sofc_zero_carbon": False,
        "dc_800v_reference_gw": 1.0,
        "dc_800v_noncompute_capex_saving_usd_b": (
            number(bloom_800v, r"non-compute capital expenditures.*?\$([0-9.]+)\s+billion", float)
            if bloom_800v and re.search(r"non-compute capital expenditures.*?\$[0-9.]+\s+billion", bloom_800v, re.I)
            else 3.6
        ),
        "dc_800v_noncompute_capex_saving_pct": (
            number(bloom_800v, r"\$[0-9.]+\s+billion,\s+or\s+([0-9.]+)%", float)
            if bloom_800v and re.search(r"\$[0-9.]+\s+billion,\s+or\s+[0-9.]+%", bloom_800v, re.I)
            else 27.0
        ),
        "dc_800v_tco5_saving_usd_b": (
            number(bloom_800v, r"five-year total cost of ownership by\s+\$([0-9.]+)\s+billion", float)
            if bloom_800v and re.search(r"five-year total cost of ownership by\s+\$[0-9.]+\s+billion", bloom_800v, re.I)
            else 5.5
        ),
        "dc_800v_tco5_saving_pct": (
            number(bloom_800v, r"five-year total cost of ownership by\s+\$[0-9.]+\s+billion,\s+or\s+([0-9.]+)%", float)
            if bloom_800v and re.search(r"five-year total cost of ownership by\s+\$[0-9.]+\s+billion,\s+or\s+[0-9.]+%", bloom_800v, re.I)
            else 9.0
        ),
        "source_errors": bloom_market_errors,
        "vendor_model_note": "800V 비용절감·61% BYOP 수치는 Bloom Energy 자체 모델·설문이며 고객 실현값·시장 전체 확정 비중이 아님",
        "emissions_note": "천연가스 SOFC는 비연소라 NOx·SOx·입자상물질이 매우 낮지만 CO2 배출은 0이 아님",
    }

    relevant = {
        "frankfort": {
            "investment_usd_b": investment_b,
            "building_sqft": sqft,
            "land_acres": acres,
            "grid_mw": grid_mw,
            "onsite_fuel_cell_mw": onsite_mw,
            "total_mw": total_mw,
            "tenant_status": tenant_status,
            "tenant_name": tenant_name,
            "nebius_official_link": frankfort_nebius_official,
            "bloom_named": bloom_named,
            "natural_gas_feedstock": natural_gas,
            "gas_supplier": "CenterPoint Energy" if centerpoint else None,
            "lng_backup_expected": lng_backup,
            "substations": substations,
            "groundbreaking_window": "2026년 말~2027년 초, 승인 조건부" if late_2026 else "확인 필요",
            "construction_duration": build_months,
            "water_million_gal_per_year": water_mgal_y,
            "mayor_no_commitment_statement": mayor_no_commitment,
        },
        "confirmed_partner_chain": {
            "vineland_nebius_dataone_bloom": vineland_confirmed,
            "nebius_bloom_long_term_328mw": bloom_long_term,
            "nebius_partner_owned_capacity_model": partner_model,
            "bloom_frankfort_official_announcement": bloom_frankfort_official,
        },
        "impa": {
            "official_wholesale_provider": True,
            "member_communities_61": impa_members,
            "note": "Frankfort DataOne 공식 FAQ가 IMPA를 계통 공급원으로 명시",
        },
        "bloom_ai_market": bloom_ai_market,
    }
    relevant["digest"] = hashlib.sha256(
        json.dumps(relevant, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return relevant


def changes(old: dict, new: dict) -> list[str]:
    if not old:
        return ["Nebius·DataOne·Bloom 파트너 인프라 기준선 신규 연결"]
    out = []
    of = (old.get("facts") or {}).get("frankfort") or {}
    nf = new["frankfort"]

    fields = [
        ("총 전력", "total_mw", "MW"),
        ("계통 전력", "grid_mw", "MW"),
        ("현장 연료전지", "onsite_fuel_cell_mw", "MW"),
        ("총 투자액", "investment_usd_b", "B달러"),
        ("건물 면적", "building_sqft", "sqft"),
        ("부지", "land_acres", "acres"),
        ("물 사용", "water_million_gal_per_year", "백만갤런/년"),
    ]
    for label, key, unit in fields:
        before, after = of.get(key), nf.get(key)
        if before is not None and after is not None and before != after:
            out.append(f"Frankfort {label} {before}→{after}{unit}")

    if of.get("tenant_name") != nf.get("tenant_name") or of.get("tenant_status") != nf.get("tenant_status"):
        out.append(
            f"Frankfort 고객/임차인 {of.get('tenant_name') or of.get('tenant_status','미공개')}→"
            f"{nf.get('tenant_name') or nf.get('tenant_status','미공개')}"
        )
    if not of.get("nebius_official_link") and nf.get("nebius_official_link"):
        out.append("Frankfort와 Nebius의 공식 직접 연결 확인")
    if of.get("groundbreaking_window") != nf.get("groundbreaking_window"):
        out.append(f"Frankfort 착공 창 {of.get('groundbreaking_window')}→{nf.get('groundbreaking_window')}")
    if of.get("construction_duration") != nf.get("construction_duration"):
        out.append(f"Frankfort 예상 공사기간 {of.get('construction_duration')}→{nf.get('construction_duration')}")
    if of.get("gas_supplier") != nf.get("gas_supplier"):
        out.append(f"Frankfort 가스 공급사 {of.get('gas_supplier')}→{nf.get('gas_supplier')}")

    op = (old.get("facts") or {}).get("confirmed_partner_chain") or {}
    np = new["confirmed_partner_chain"]
    for key, label in (
        ("vineland_nebius_dataone_bloom", "Vineland Nebius·DataOne·Bloom 3자 연결"),
        ("nebius_bloom_long_term_328mw", "Nebius·Bloom 장기 328MW+ 파트너십"),
        ("nebius_partner_owned_capacity_model", "Nebius 파트너 소유 인프라 사업모델"),
        ("bloom_frankfort_official_announcement", "Bloom Energy Frankfort·DataOne 공식 발표"),
    ):
        before = op.get(key)
        after = np.get(key)
        if before is not None and before != after:
            out.append(f"{label} {'확인' if after else '약화/미확인'}")

    if of.get("lng_backup_expected") is not None and of.get("lng_backup_expected") != nf.get("lng_backup_expected"):
        out.append(
            f"Frankfort LNG 백업 계획 {'확인' if nf.get('lng_backup_expected') else '미확인'}"
        )

    ob = (old.get("facts") or {}).get("bloom_ai_market") or {}
    nb = new.get("bloom_ai_market") or {}
    if not ob and nb:
        out.append("Bloom AI 현장전원·800V DC 시장 기준선 신규 연결")
    else:
        for key, label, unit in (
            ("oracle_master_agreement_gw", "Bloom·Oracle 마스터계약 상단", "GW"),
            ("oracle_initial_contracted_gw", "Bloom·Oracle 초기 계약", "GW"),
            ("ai_infrastructure_segment_mw_approx", "Bloom AI 인프라 고객군", "MW"),
            ("brookfield_financing_framework_usd_b", "Bloom·Brookfield AI 전력 금융 프레임", "십억달러"),
            ("equinix_operational_mw", "Bloom·Equinix 운영중 용량", "MW"),
            ("equinix_under_construction_mw", "Bloom·Equinix 건설중 용량", "MW"),
            ("developer_byop_share_pct", "Bloom 설문 BYOP 의향", "%"),
            ("power_connect_install_time_reduction_pct", "Bloom Power Connect 설치시간 단축", "%"),
            ("dc_800v_noncompute_capex_saving_usd_b", "Bloom 1GW 800V 비연산 CAPEX 절감 모델", "십억달러"),
            ("dc_800v_tco5_saving_usd_b", "Bloom 1GW 800V 5년 TCO 절감 모델", "십억달러"),
        ):
            before, after = ob.get(key), nb.get(key)
            if before is not None and after is not None and float(before) != float(after):
                out.append(f"{label} {float(before):g}→{float(after):g}{unit}")
    return out


def render(facts: dict, chg: list[str], fxv: dict, format_upgrade: bool = False) -> str:
    f = facts["frankfort"]
    p = facts["confirmed_partner_chain"]
    bm = facts.get("bloom_ai_market") or {}
    rate = float(fxv["usdkrw"])
    investment_krw = krw_from_usd_b(float(f["investment_usd_b"]), rate)

    title = (
        "✅ Nebius·DataOne·Bloom 알림 가독성 업그레이드"
        if format_upgrade and not chg
        else "⚡ Nebius·DataOne·Bloom 실행 변화"
    )
    lines = [
        f"<b>{title}</b>",
        "",
        "<b>🧭 핵심</b>",
        f"• <b>Frankfort</b> │ 투자 {f['investment_usd_b']:.1f}B달러 ({investment_krw}) │ 계통 {f['grid_mw']}MW + Bloom 연료전지 {f['onsite_fuel_cell_mw']}MW = <b>{f['total_mw']}MW</b>",
        f"• <b>일정</b> │ {html.escape(f['groundbreaking_window'])} · 공사 {html.escape(str(f['construction_duration'] or '확인 필요'))}",
        f"• <b>고객</b> │ {html.escape(f['tenant_name'] or f['tenant_status'])} · Frankfort→Nebius 직접 연결 <b>{'확인' if f['nebius_official_link'] else '미확인'}</b> → <b>525MW를 NBIS 확정용량에 합산하지 않음</b>",
        "",
        "<b>⚡ Bloom 실제 실행</b>",
        f"• <b>Equinix</b> │ 계약 100MW+ · 운영 약 {bm.get('equinix_operational_mw', 0):g}MW · 건설 약 {bm.get('equinix_under_construction_mw', 0):g}MW",
        f"• <b>Oracle</b> │ 초기 계약 {bm.get('oracle_initial_contracted_gw', 0):g}GW · 마스터 상단 {bm.get('oracle_master_agreement_gw', 0):g}GW",
        f"• <b>Nebius·Bloom</b> │ 첫 배치 328MW {'확정' if p['nebius_bloom_long_term_328mw'] else '재확인 필요'} · Vineland 3자 연결 {'확정' if p['vineland_nebius_dataone_bloom'] else '재확인 필요'}",
        f"• <b>Brookfield</b> │ AI 전력 금융 프레임 {bm.get('brookfield_financing_framework_usd_b', 0):g}B달러",
        "",
        "<b>📐 모델·설문은 분리</b>",
        f"• BYOP 의향 {bm.get('developer_byop_share_pct', 0):g}% · Power Connect 설치시간 {bm.get('power_connect_install_time_reduction_pct', 0):g}%+ 단축은 <b>Bloom 설문·목표</b>",
        f"• 1GW 800V 비교모델 │ 비연산 CAPEX {bm.get('dc_800v_noncompute_capex_saving_usd_b', 0):g}B달러·{bm.get('dc_800v_noncompute_capex_saving_pct', 0):g}% / 5년 TCO {bm.get('dc_800v_tco5_saving_usd_b', 0):g}B달러·{bm.get('dc_800v_tco5_saving_pct', 0):g}% 절감 → <b>고객 실현값 아님</b>",
    ]

    if chg:
        lines += ["", "<b>🔄 이번 변화</b>"]
        lines += [f"• {html.escape(x)}" for x in chg[:8]]

    lines += [
        "",
        "<b>📊 투자 의미</b>",
        "• <b>매출 연결</b> │ 연료전지 발주·설치·가동 MW와 전력설비·장기 서비스가 실제 실적 신호",
        "• <b>실패모드</b> │ 고객 미공개·인허가·가스 연결·LNG 안전규정 지연. 천연가스 SOFC는 저대기오염이지만 <b>CO₂ 0이 아님</b>",
        f"• <b>현장 제약</b> │ LNG 백업 {'예' if f['lng_backup_expected'] else '확인 필요'} · 변전소 {f['substations'] if f['substations'] is not None else '확인 필요'}개 · 물 연 {f['water_million_gal_per_year']:.0f}백만 갤런",
        "",
        f"<b>💱 1달러 = {rate:,.2f}원</b> · {html.escape(str(fxv.get('source','')))}",
    ]

    text = "\n".join(lines).strip() + "\n"
    visible = html.unescape(re.sub(r"<[^>]+>", "", text))
    if len(visible) > 2800:
        raise RuntimeError(f"compact Nebius/Bloom alert too long: {len(visible)} chars")
    return text


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (PENDING, ALERT, STATUS):
        p.unlink(missing_ok=True)

    old = load_state()
    facts = snapshot()
    fxv = fx(old)
    baseline = not old.get("initialized")
    format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
    chg = changes(old, facts)
    should_alert = baseline or format_upgrade or bool(chg)

    pending = {
        "initialized": True,
        "format_version": FORMAT_VERSION,
        "facts": facts,
        "fx": fxv,
        "last_changes": chg[:20],
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if should_alert:
        ALERT.write_text(render(facts, chg, fxv, format_upgrade=format_upgrade), encoding="utf-8")

    STATUS.write_text(
        "# Nebius·DataOne·Bloom 파트너 인프라 감시\n\n"
        f"- Frankfort 총 전력: **{facts['frankfort']['total_mw']}MW**\n"
        f"- Frankfort Nebius 직접 연결: **{'확정' if facts['frankfort']['nebius_official_link'] else '미확인'}**\n"
        f"- Vineland 3자 연결: **{'확정' if facts['confirmed_partner_chain']['vineland_nebius_dataone_bloom'] else '재확인 필요'}**\n"
        f"- Bloom·Oracle 마스터계약 상단: **{facts.get('bloom_ai_market', {}).get('oracle_master_agreement_gw')}GW**\n"
        f"- Bloom·Oracle 초기 계약: **{facts.get('bloom_ai_market', {}).get('oracle_initial_contracted_gw')}GW**\n"
        f"- Bloom AI 인프라 고객군: **약 {facts.get('bloom_ai_market', {}).get('ai_infrastructure_segment_mw_approx')}MW**\n"
        f"- Bloom·Equinix 운영/건설: **{facts.get('bloom_ai_market', {}).get('equinix_operational_mw')}MW / {facts.get('bloom_ai_market', {}).get('equinix_under_construction_mw')}MW**\n"
        f"- Bloom·Brookfield 금융 프레임: **${facts.get('bloom_ai_market', {}).get('brookfield_financing_framework_usd_b')}B**\n"
        f"- Bloom 설문 BYOP 의향: **{facts.get('bloom_ai_market', {}).get('developer_byop_share_pct')}%**\n"
        f"- 의미 변화: **{len(chg)}건**\n"
        f"- 알림: **{'예' if should_alert else '아니오'}**\n",
        encoding="utf-8",
    )
    print(
        f"nebius_partner baseline={baseline} changes={len(chg)} "
        f"frankfort_mw={facts['frankfort']['total_mw']} "
        f"nebius_link={facts['frankfort']['nebius_official_link']} alert={should_alert}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
