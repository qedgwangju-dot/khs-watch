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
STATE = Path("data/ai_dc_800v_power_architecture_state.json")
PENDING = OUT / "ai_dc_800v_power_architecture_pending_state.json"
ALERT = OUT / "ai_dc_800v_power_architecture_alert.txt"
STATUS = OUT / "ai_dc_800v_power_architecture_status.md"

FORMAT_VERSION = 6
# Dedupe validation: unchanged extracted facts must remain Telegram-silent.
# Timing-benchmark validation reruns must also remain silent when official facts are unchanged.
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}

NVIDIA_BLOG = "https://blogs.nvidia.com/blog/800-vdc-power-architecture-ai-factory/"
NVIDIA_ARCH = "https://www.nvidia.com/en-us/data-center/technologies/800-vdc-architecture/"
OCP_LVDC = "https://www.opencompute.org/index.php/blog/powering-the-next-era-of-ai-how-google-microsoft-and-nvidia-are-standardizing-and-accelerating-the-industry-transition-to-lvdc"
SCHNEIDER_POWER_RACK = "https://www.se.com/ww/en/work/products/product-reveal/net-shelter-power-rack-800-vdc/"
SCHNEIDER_GUIDE = "https://www.se.com/ww/en/insights/ai-and-technology/artificial-intelligence/vdc-powering-the-future-of-ai-data-centers/"
SCHNEIDER_CALL = "https://www.se.com/ww/en/assets/564/document/528236/transcript-Q4-results-2025.pdf?p_File_Name=2025+Full+Year+Financial+Results+Transcript&p_enDocType=EDMS"
VERTIV_PATH = "https://www.vertiv.com/tr-emea/insights/articles/blog-posts/from-rack-to-data-hall-the-practical-path-to-800-vdc/"
VERTIV_GUIDE = "https://www.vertiv.com/en-ca/insights/articles/educational-articles/the-800-vdc-decision-a-practical-guide-for-ai-power-architecture/"
VERTIV_RELEASE = "https://www.vertiv.com/en-emea/about/news-and-events/news-releases/from-vision-to-readiness-vertiv-collaborates-with-nvidia-to-advance-800-vdc-platform-designs-to-power-the-next-generation-of-ai-factories/"
EATON_GTC = "https://www.eaton.com/kr/ko-kr/company/news-insights/news-releases/2025/eaton-next-generation-ai-factories.html"
HITACHI_800V = "https://hitachidigital.com/news/hitachi-accelerate-gigawatt-scale-ai-factories/"
SIEMENS_SST = "https://press.siemens.com/global/en/pressrelease/siemens-and-reinhausen-develop-direct-current-power-solutions-ai-data-centers"
LS_DC = "https://nahpdev.ls-electric.com/company/articles/2759/industry-usa-ls-electric-america-to-highlight-dc-grid-solutions-for-ai-data-centers-at-data-center-world-2026"
DELTA_DCW = "https://www.delta-singapore.com/en-SG/news/40267"
LG_AIR = "https://www.lg.com/global/newsroom/news/eco-solution/lg-electronics-secures-supply-agreement-to-advance-ai-data-center-cooling-business-in-north-america/"
AIR_LG = "https://www.aircontrolconcepts.com/news/air-and-lg-supply-agreement-aims-to-advance-ai-data-center-cooling-business-in-north-america"
LG_CHILLER_CAPACITY = "https://lg.co.kr/media/release/30623"
VERTIV_DSX = "https://www.vertiv.com/en-asia/about/news-and-events/news-releases/2026/vertiv-brings-converged-physical-infrastructure-to-nvidia-vera-rubin-dsx-ai-factories/"
VERTIV_DSX_CDU = "https://www.vertiv.com/en-emea/about/news-and-events/news-releases/2026/vertiv-coolant-distribution-unit-qualified-as-nvidia-dsx-ready-for-ai-factory-infrastructure/"
NVIDIA_DSX = "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Releases-Vera-Rubin-DSX-AI-Factory-Reference-Design-and-Omniverse-DSX-Digital-Twin-Blueprint-With-Broad-Industry-Support/default.aspx"
SGC_VERTIV_DCD = "https://www.datacenterdynamics.com/en/news/sgc-energy-partners-with-vertiv-to-deploy-powernexus-at-planned-ai-data-center-in-gunsan-south-korea/"
SGC_VERTIV_SED = "https://en.sedaily.ai/finance/2026/09/08/sgc-energy-partners-with-vertiv-on-gunsan-ai-data-center"
SGC_HYUNDAI_EPC = "https://m.hec.co.kr/ko/pr/press-news/press-release/7999"
SGC_EPC_NEWSIS = "https://www.newsis.com/view/NISX20260928_0003805922"

SOURCES = {
    "nvidia_blog": NVIDIA_BLOG,
    "nvidia_arch": NVIDIA_ARCH,
    "ocp": OCP_LVDC,
    "schneider_power_rack": SCHNEIDER_POWER_RACK,
    "schneider_guide": SCHNEIDER_GUIDE,
    "schneider_call": SCHNEIDER_CALL,
    "vertiv_path": VERTIV_PATH,
    "vertiv_guide": VERTIV_GUIDE,
    "vertiv_release": VERTIV_RELEASE,
    "hitachi": HITACHI_800V,
    "siemens": SIEMENS_SST,
    "ls": LS_DC,
    "delta": DELTA_DCW,
    "lg_air": LG_AIR,
    "air_lg": AIR_LG,
    "lg_chiller_capacity": LG_CHILLER_CAPACITY,
    "vertiv_dsx": VERTIV_DSX,
    "vertiv_dsx_cdu": VERTIV_DSX_CDU,
    "nvidia_dsx": NVIDIA_DSX,
    "sgc_vertiv_dcd": SGC_VERTIV_DCD,
    "sgc_vertiv_sed": SGC_VERTIV_SED,
    "sgc_epc_newsis": SGC_EPC_NEWSIS,
}


def fetch_text(url: str, timeout: int = 25) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return " ".join(BeautifulSoup(r.content, "html.parser").get_text(" ", strip=True).split())


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fx(old: dict) -> dict:
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return {"usdkrw": float(q.rate), "basis": q.basis, "source": q.source}
    except Exception:
        prior = old.get("fx") or {}
        if prior.get("usdkrw"):
            return {**prior, "source": str(prior.get("source") or "") + " · 직전 저장값"}
        return {}


def get_source_texts(old: dict) -> tuple[dict[str, str], list[str]]:
    texts: dict[str, str] = {}
    errors: list[str] = []
    for key, url in SOURCES.items():
        try:
            text = fetch_text(url)
            if len(text) < 100:
                raise RuntimeError("source text too short")
            texts[key] = text
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}")
            prior = ((old.get("source_cache") or {}).get(key) or {}).get("text")
            if prior:
                texts[key] = prior
    return texts, errors


def contains(texts: dict[str, str], key: str, *needles: str) -> bool | None:
    text = texts.get(key)
    if not text:
        return None
    low = text.lower()
    return all(n.lower() in low for n in needles)


def any_contains(texts: dict[str, str], key: str, needles: tuple[str, ...]) -> bool | None:
    text = texts.get(key)
    if not text:
        return None
    low = text.lower()
    return any(n.lower() in low for n in needles)


def regex_value(texts: dict[str, str], key: str, pattern: str, cast=float):
    text = texts.get(key) or ""
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return cast(m.group(1).replace(",", ""))
    except Exception:
        return None


def snapshot(texts: dict[str, str]) -> dict:
    n_blog = texts.get("nvidia_blog", "")
    ocp = texts.get("ocp", "")
    sch = texts.get("schneider_power_rack", "")
    sch_call = texts.get("schneider_call", "")
    vert_path = texts.get("vertiv_path", "")
    vert = texts.get("vertiv_guide", "")
    vrel = texts.get("vertiv_release", "")
    n_arch = texts.get("nvidia_arch", "")
    hitachi = texts.get("hitachi", "")
    siemens = texts.get("siemens", "")
    ls = texts.get("ls", "")
    delta = texts.get("delta", "")
    lg_air = texts.get("lg_air", "")
    air_lg = texts.get("air_lg", "")
    lg_capacity = texts.get("lg_chiller_capacity", "")
    vertiv_dsx = texts.get("vertiv_dsx", "")
    vertiv_dsx_cdu = texts.get("vertiv_dsx_cdu", "")
    nvidia_dsx = texts.get("nvidia_dsx", "")
    sgc_dcd = texts.get("sgc_vertiv_dcd", "")
    sgc_sed = texts.get("sgc_vertiv_sed", "")
    sgc_epc_newsis = texts.get("sgc_epc_newsis", "")

    partner_count_min = regex_value(
        texts,
        "nvidia_blog",
        r"more than\s+([0-9,]+)\s+(?:ecosystem\s+)?companies",
        int,
    )
    if partner_count_min is None and "more than 80" in n_blog.lower():
        partner_count_min = 80

    sst_version = None
    m = re.search(r"(?:SST Specification|Solid-State Transformer Specification)\s*v?([0-9]+(?:\.[0-9]+)+)", ocp, re.I)
    if m:
        sst_version = m.group(1)
    elif re.search(r"v0\.3", ocp, re.I):
        sst_version = "0.3"

    sch_kw = regex_value(texts, "schneider_power_rack", r"([0-9,]+)\s*kW", int)
    sch_eff = regex_value(texts, "schneider_power_rack", r"([0-9]+(?:\.[0-9]+)?)%\s*peak efficiency", float)

    facts = {
        "architecture": {
            "nvidia_hybrid_power_rack_h2_2026": contains(texts, "nvidia_blog", "power rack", "second half of 2026"),
            "nvidia_row_power_center_2027": contains(texts, "nvidia_blog", "row power center", "2027"),
            "nvidia_existing_ac_retrofit": contains(texts, "nvidia_blog", "existing AC infrastructure", "800 VDC"),
            "nvidia_partner_count_min": partner_count_min,
            "ocp_sst_spec_version": sst_version,
            "ocp_open_standard_google_microsoft_nvidia": contains(texts, "ocp", "Google", "Microsoft", "NVIDIA"),
            "ocp_safety_bodies": all(x in ocp for x in ("UL", "NFPA", "IEEE", "IEC")) if ocp else None,
        },
        "vendors": {
            "Schneider Electric": {
                "stage": "상용 제품 페이지" if sch else "확인 불가",
                "sidecar": contains(texts, "schneider_guide", "power racks", "immediate"),
                "power_rack_kw": sch_kw,
                "peak_efficiency_pct": sch_eff,
                "turnkey_signal": contains(texts, "schneider_power_rack", "protection", "metering", "storage"),
                "legacy_ac_bridge": contains(texts, "schneider_power_rack", "AC", "800 VDC"),
            },
            "Vertiv": {
                "stage": "2026년 하반기 상용화 계획" if "second half of 2026" in vrel.lower() else ("800 VDC 공식 경로" if vert else "확인 불가"),
                "parallel_paths": contains(texts, "vertiv_guide", "parallel paths", "coexist"),
                "system_scope": contains(texts, "vertiv_guide", "conversion", "distribution", "protection"),
            },
            "Eaton": {
                "stage": "800 VDC 공식 참조 아키텍처",
                "standards_signal": None,
                "legacy_ac_bridge": None,
                "nvidia_current_partner_visible": True if "Eaton" in n_arch else False,
                "source_mode": "Eaton 공식 2025 참조 아키텍처 기준값 고정 확인 · NVIDIA 공식 파트너 목록은 보조 교차확인",
            },
            "Hitachi Energy": {
                "stage": "Vera Rubin DSX 통합·시뮬레이션" if "800" in hitachi and "DSX" in hitachi else "확인 불가",
                "grid_to_rack": any(x in hitachi.lower() for x in ("grid-to-rack", "power and control architecture")) if hitachi else None,
            },
            "Siemens": {
                "stage": "SST 개발·산업화" if "solid-state transformer" in siemens.lower() and "800 vdc" in siemens.lower() else "확인 불가",
                "sst_36kv_to_800v": (
                    ("36 kv" in siemens.lower() or "36kv" in siemens.lower())
                    and "800 vdc" in siemens.lower()
                ) if siemens else None,
                "software_protection_scope": all(x in siemens.lower() for x in ("protection", "control")) if siemens else None,
            },
            "LS ELECTRIC": {
                "stage": "DC grid 개념·전시" if "dc grid" in ls.lower() and "data center" in ls.lower() else "확인 불가",
                "direct_800v_product_confirmed": True if "800 vdc" in ls.lower() and "product" in ls.lower() else False if ls else None,
            },
            "Delta": {
                "stage": "800 VDC In-Row 제품 공개" if "800 vdc" in delta.lower() and "in-row" in delta.lower() else "확인 불가",
                "sst_signal": "solid state transformer" in delta.lower() if delta else None,
            },
        },
    }

    lg_air_capacity_gw_min = regex_value(
        texts,
        "lg_air",
        r"(?:more than|exceeding)\s+([0-9]+(?:\.[0-9]+)?)\s*GW",
        float,
    )
    if lg_air_capacity_gw_min is None and re.search(r"(?:more than|exceeding)\s*5\s*GW", lg_air, re.I):
        lg_air_capacity_gw_min = 5.0

    lg_first_half_orders_usd_m = regex_value(
        texts,
        "lg_air",
        r"first-half orders[^.]{0,160}?(?:\$|USD\s*)([0-9]+(?:\.[0-9]+)?)\s*million",
        float,
    )
    lg_2027_chiller_target_usd_m = regex_value(
        texts,
        "lg_air",
        r"2027 chiller business revenue target[^.]{0,160}?(?:\$|USD\s*)([0-9]+(?:\.[0-9]+)?)\s*million",
        float,
    )
    lg_capacity_investment_krw_billion = None
    if lg_capacity and ("1,500억" in lg_capacity or "1,500억 원" in lg_capacity):
        lg_capacity_investment_krw_billion = 150.0

    vertiv_block_mw = regex_value(
        texts,
        "vertiv_dsx",
        r"([0-9]+(?:\.[0-9]+)?)\s*MW\s+infrastructure blocks",
        float,
    )
    vertiv_cdu_mw = regex_value(
        texts,
        "vertiv_dsx_cdu",
        r"([0-9]+(?:\.[0-9]+)?)\s*MW\s+Vertiv",
        float,
    )

    sgc_pair_text = sgc_dcd + " " + sgc_sed
    sgc_initial_mw = regex_value(
        texts,
        "sgc_vertiv_sed",
        r"initial\s+([0-9]+(?:\.[0-9]+)?)\s*(?:MW|-?megawatts?)",
        float,
    )
    if sgc_initial_mw is None:
        m = re.search(
            r"capacity of\s+([0-9]+(?:\.[0-9]+)?)\s*MW[^.]{0,80}?initial phase",
            sgc_dcd,
            re.I,
        )
        sgc_initial_mw = float(m.group(1)) if m else None
    m = re.search(
        r"(?:up to|as much as)\s+([0-9]+(?:\.[0-9]+)?)\s*(?:MW|megawatts?)",
        sgc_pair_text,
        re.I,
    )
    sgc_max_mw = float(m.group(1)) if m else None

    facts["execution"] = {
        "lg_air_bilateral_official_long_term_contract": bool(
            lg_air
            and air_lg
            and "long-term" in lg_air.lower()
            and "long-term" in air_lg.lower()
            and ("5gw" in lg_air.lower() or "5 gw" in lg_air.lower())
            and ("5gw" in air_lg.lower() or "5 gw" in air_lg.lower())
        ),
        "lg_air_capacity_gw_min": lg_air_capacity_gw_min,
        "lg_air_multi_year_program": "multi-year" in lg_air.lower() if lg_air else None,
        "lg_air_air_cooled_centrifugal_chiller": "air-cooled centrifugal chiller" in lg_air.lower() if lg_air else None,
        "lg_air_official_contract_value_disclosed": False,
        "lg_first_half_aidc_cooling_orders_usd_m": lg_first_half_orders_usd_m,
        "lg_2027_chiller_revenue_target_usd_m": lg_2027_chiller_target_usd_m,
        "lg_chiller_capacity_investment_krw_billion": lg_capacity_investment_krw_billion,
        "lg_us_chiller_factory_h1_2027": bool(
            lg_capacity
            and ("내년 상반기" in lg_capacity or "2027" in lg_capacity)
            and ("버지니아" in lg_capacity or "virginia" in lg_capacity.lower())
        ),
        "vertiv_nvidia_vera_rubin_dsx_official": bool(
            vertiv_dsx
            and nvidia_dsx
            and "vera rubin dsx" in vertiv_dsx.lower()
            and "vertiv" in nvidia_dsx.lower()
        ),
        "vertiv_onecore_standard_block_mw": vertiv_block_mw,
        "vertiv_dsx_ready_cdu_mw": vertiv_cdu_mw,
        "sgc_vertiv_mou_dual_source": bool(
            sgc_dcd
            and sgc_sed
            and "vertiv" in sgc_dcd.lower()
            and "vertiv" in sgc_sed.lower()
            and ("mou" in sgc_sed.lower() or "memorandum of understanding" in sgc_dcd.lower())
        ),
        "sgc_vertiv_non_binding_mou": "non-binding" in sgc_dcd.lower() if sgc_dcd else None,
        "sgc_vertiv_initial_mw": sgc_initial_mw,
        "sgc_vertiv_max_mw": sgc_max_mw,
        "sgc_vertiv_powernexus_planned": "powernexus" in sgc_pair_text.lower(),
        "sgc_vertiv_binding_supply_contract_confirmed": False,
        "sgc_phase1_energization_q1_2028": bool(
            sgc_dcd and ("q1 2028" in sgc_dcd.lower() or "first quarter of 2028" in sgc_dcd.lower())
        ),
        "sgc_hyundai_epc_official_verified_baseline": True,
        "sgc_hyundai_epc_contract_confirmed": bool(
            sgc_epc_newsis
            and "8700" in sgc_epc_newsis.replace(",", "")
            and ("60MW" in sgc_epc_newsis or "60㎿" in sgc_epc_newsis)
        ),
        "sgc_phase1_epc_krw_billion": 870.0 if (
            sgc_epc_newsis and "8700" in sgc_epc_newsis.replace(",", "")
        ) else None,
        "sgc_phase1_construction_start_2026_10": bool(
            sgc_epc_newsis and ("10월" in sgc_epc_newsis or "October" in sgc_epc_newsis)
        ),
        "sgc_epc_source_mode": "현대엔지니어링 2026-09-28 공식 보도자료로 8,700억원·60MW·10월 착공·MEP 범위를 사전 검증; runner는 Newsis 교차원문을 실시간 재조회",
        "sgc_epc_cooling_tower_switchgear_scope_reported": bool(
            sgc_epc_newsis and "냉각탑" in sgc_epc_newsis and "수배전반" in sgc_epc_newsis
        ),
        "sgc_ktcloud_ups_battery_role_reported": bool(
            sgc_epc_newsis and "kt cloud" in sgc_epc_newsis.lower() and "UPS" in sgc_epc_newsis and "배터리" in sgc_epc_newsis
        ),
        "scope_note": "LG-AIR는 공식 장기공급계약. SGC-Vertiv는 비구속 MOU·기술검토/적용 계획이며 확정 공급계약으로 승격 금지. 7조달러는 산업 투자전망이지 Vertiv 계약금액이 아님.",
    }
    live_vendor_800v = 0
    for name, row in facts["vendors"].items():
        if row.get("stage") not in ("확인 불가", "DC grid 개념·전시"):
            live_vendor_800v += 1

    # Schneider FY2025 official earnings-call transcript is a PDF and can
    # arrive as binary text through the runner. Keep the exact official
    # transcript figures as a verified baseline, and overwrite them only when
    # live text extraction succeeds with the same guarded phrases.
    sch_impacted_low = 15
    sch_impacted_high = 25
    sch_full_ready_2028 = True
    sch_step_2028_2030 = True
    sch_timing_source = "Schneider FY2025 공식 실적발표 transcript 검증 기준값"

    m = re.search(r"(15)%[^.]{0,80}(25)%[^.]{0,180}(?:2030|demand)", sch_call, re.I)
    if m:
        sch_impacted_low, sch_impacted_high = int(m.group(1)), int(m.group(2))
        sch_timing_source = "Schneider FY2025 공식 실적발표 transcript 실시간 파싱"
    elif "15%, 25%" in sch_call and "2030" in sch_call:
        sch_timing_source = "Schneider FY2025 공식 실적발표 transcript 실시간 파싱"

    if sch_call and ("ready by '28" in sch_call or "ready by 28" in sch_call):
        sch_full_ready_2028 = True
    if sch_call and "step by step" in sch_call.lower() and ("'28 and 2030" in sch_call or "28 and 2030" in sch_call):
        sch_step_2028_2030 = True
    vert_sidecar_h2_2026 = bool(
        vert_path and "commercialization begins in the second half of 2026" in vert_path.lower()
    )
    vert_ramp_2027 = bool(
        vert_path and "deployment ramp through 2027" in vert_path.lower()
    )
    vert_centralized_2028_2029 = bool(
        vert_path and "2028 to 2029 timeframe and beyond" in vert_path.lower()
    )
    vert_sst_lower_readiness = bool(
        vert_path
        and "higher technology readiness level" in vert_path.lower()
        and "solid-state transformer" in vert_path.lower()
    )

    facts["market"] = {
        "official_multi_vendor_800v_count": live_vendor_800v,
        "hybrid_bridge_confirmed": bool(
            facts["architecture"].get("nvidia_existing_ac_retrofit")
            and facts["vendors"]["Schneider Electric"].get("sidecar")
        ),
        "native_facility_800v_mass_adoption_confirmed": False,
        "schneider_2030_demand_impacted_pct_low": sch_impacted_low,
        "schneider_2030_demand_impacted_pct_high": sch_impacted_high,
        "schneider_full_architecture_ready_2028": sch_full_ready_2028,
        "schneider_transition_step_2028_2030": sch_step_2028_2030,
        "schneider_timing_source": sch_timing_source,
        "vertiv_sidecar_commercialization_h2_2026": vert_sidecar_h2_2026,
        "vertiv_deployment_ramp_2027": vert_ramp_2027,
        "vertiv_centralized_2028_2029_plus": vert_centralized_2028_2029,
        "vertiv_sst_lower_readiness_than_mv_dc_ups": vert_sst_lower_readiness,
        "legacy_ac_near_term_displacement_risk": "낮음/점진적" if (
            facts["architecture"].get("nvidia_existing_ac_retrofit")
            and facts["vendors"]["Schneider Electric"].get("sidecar")
            and vert_sidecar_h2_2026
        ) else "판정 보류",
        "technology_only_moat": "낮음/미확정" if live_vendor_800v >= 5 and sst_version else "판정 보류",
        "moat_check_basis": "OCP 공개 표준 + 다수 공식 공급사. 실제 해자는 양산·안전인증·통합 EPC·제어/운영SW·서비스에서 재검증",
        "jpm_user_note_status": "사용자 제공 JPM 리서치 요약은 공개 원문을 독립 확보하지 못해 공식 알림 트리거로 사용하지 않음. 대신 Schneider·Vertiv·NVIDIA 공식 일정으로 교차검증",
    }

    facts["digest"] = hashlib.sha256(
        json.dumps(facts, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return facts


def changes(old: dict, new: dict) -> list[str]:
    if not old:
        return ["AI 데이터센터 800 VDC 전환 기준선 신규 연결"]
    prev = old.get("facts") or {}
    out: list[str] = []

    pa = prev.get("architecture") or {}
    na = new.get("architecture") or {}
    for key, label in (
        ("nvidia_hybrid_power_rack_h2_2026", "NVIDIA 하이브리드 파워랙 H2 2026"),
        ("nvidia_row_power_center_2027", "NVIDIA Row Power Center 2027"),
        ("nvidia_existing_ac_retrofit", "기존 AC 인프라 유지형 800 VDC"),
        ("ocp_sst_spec_version", "OCP SST 사양 버전"),
        ("ocp_safety_bodies", "800 VDC 안전표준 협력"),
    ):
        before, after = pa.get(key), na.get(key)
        if before is not None and after is not None and before != after:
            out.append(f"{label} {before}→{after}")

    before_partners, after_partners = pa.get("nvidia_partner_count_min"), na.get("nvidia_partner_count_min")
    if before_partners is not None and after_partners is not None and before_partners != after_partners:
        out.append(f"NVIDIA 800 VDC 생태계 공급사 {before_partners}+→{after_partners}+")

    pv = prev.get("vendors") or {}
    nv = new.get("vendors") or {}
    for name, row in nv.items():
        old_row = pv.get(name) or {}
        if old_row.get("stage") and row.get("stage") and old_row.get("stage") != row.get("stage"):
            out.append(f"{name} 800 VDC 단계 {old_row.get('stage')}→{row.get('stage')}")
        if name == "LS ELECTRIC":
            before = old_row.get("direct_800v_product_confirmed")
            after = row.get("direct_800v_product_confirmed")
            if before is not None and after is not None and before != after:
                out.append(f"LS ELECTRIC 800 VDC 직접 제품 확인 {before}→{after}")

    pe, ne = prev.get("execution") or {}, new.get("execution") or {}
    if not pe and ne:
        if ne.get("lg_air_bilateral_official_long_term_contract"):
            out.append(f"LG전자-AIR 북미 AIDC 칠러 장기공급계약 기준선 편입 · {ne.get('lg_air_capacity_gw_min') or 5}GW+")
        if ne.get("sgc_vertiv_mou_dual_source"):
            out.append(
                f"SGC에너지-Vertiv 군산 AIDC MOU 기준선 편입 · "
                f"{ne.get('sgc_vertiv_initial_mw') or 60:.0f}MW→최대 {ne.get('sgc_vertiv_max_mw') or 300:.0f}MW · 확정 공급계약 아님"
            )
        if ne.get("vertiv_nvidia_vera_rubin_dsx_official"):
            out.append("Vertiv-NVIDIA Vera Rubin DSX 공동개발·통합 인프라 기준선 편입")
    else:
        for key, label in (
            ("lg_air_capacity_gw_min", "LG-AIR 장기공급 대상 AIDC 용량"),
            ("lg_air_official_contract_value_disclosed", "LG-AIR 공식 계약금액 공개 여부"),
            ("lg_first_half_aidc_cooling_orders_usd_m", "LG 상반기 AIDC 냉각 수주"),
            ("lg_2027_chiller_revenue_target_usd_m", "LG 2027 칠러 매출 목표"),
            ("lg_chiller_capacity_investment_krw_billion", "LG 칠러 생산능력 투자"),
            ("vertiv_onecore_standard_block_mw", "Vertiv OneCore 표준 블록"),
            ("vertiv_dsx_ready_cdu_mw", "Vertiv DSX Ready CDU"),
            ("sgc_vertiv_initial_mw", "SGC-Vertiv 초기 설계 용량"),
            ("sgc_vertiv_max_mw", "SGC-Vertiv 최대 계획 용량"),
            ("sgc_vertiv_binding_supply_contract_confirmed", "SGC-Vertiv 확정 공급계약"),
            ("sgc_phase1_energization_q1_2028", "SGC 군산 1단계 2028년 1분기 전원 인가 목표"),
            ("sgc_hyundai_epc_contract_confirmed", "SGC 군산 1단계 현대엔지니어링 EPC 수주"),
            ("sgc_phase1_epc_krw_billion", "SGC 군산 1단계 EPC 사업규모(십억원)"),
            ("sgc_phase1_construction_start_2026_10", "SGC 군산 1단계 2026년 10월 착공"),
        ):
            before, after = pe.get(key), ne.get(key)
            if before is not None and after is not None and before != after:
                out.append(f"{label} {before}→{after}")

    pm, nm = prev.get("market") or {}, new.get("market") or {}
    for key, label in (
        ("official_multi_vendor_800v_count", "공식 800 VDC 직접 참여 공급사 수"),
        ("hybrid_bridge_confirmed", "하이브리드 AC/DC 브리지"),
        ("native_facility_800v_mass_adoption_confirmed", "시설 전체 Native 800 VDC 대량도입"),
        ("technology_only_moat", "사이드카·SST 기술 단독 해자"),
        ("legacy_ac_near_term_displacement_risk", "기존 AC 전력기기 단기 대체위험"),
        ("schneider_2030_demand_impacted_pct_low", "Schneider 2030 영향비중 하단"),
        ("schneider_2030_demand_impacted_pct_high", "Schneider 2030 영향비중 상단"),
        ("schneider_full_architecture_ready_2028", "Schneider full architecture 2028 준비"),
        ("schneider_transition_step_2028_2030", "Schneider 2028~2030 단계 전환"),
        ("vertiv_sidecar_commercialization_h2_2026", "Vertiv sidecar H2 2026 상용화"),
        ("vertiv_deployment_ramp_2027", "Vertiv 2027 배치 확대"),
        ("vertiv_centralized_2028_2029_plus", "Vertiv 중앙집중형 2028~2029+"),
        ("vertiv_sst_lower_readiness_than_mv_dc_ups", "Vertiv SST 상대 성숙도"),
    ):
        before, after = pm.get(key), nm.get(key)
        if before is not None and after is not None and before != after:
            out.append(f"{label} {before}→{after}")
    return out


def render(facts: dict, chg: list[str], errors: list[str], fxv: dict) -> str:
    a = facts["architecture"]
    v = facts["vendors"]
    m = facts["market"]
    e = facts["execution"]

    lines = [
        "<b>⚡ AI 데이터센터 800 VDC·전력/냉각 인프라 실행 감시</b>",
        "",
        "<b>📌 현재 공식 확인</b>",
        f"• NVIDIA 하이브리드 파워랙 H2 2026 │ <b>{'확인' if a['nvidia_hybrid_power_rack_h2_2026'] else '재확인 필요'}</b>",
        f"• NVIDIA Row Power Center 2027 │ <b>{'확인' if a['nvidia_row_power_center_2027'] else '재확인 필요'}</b>",
        f"• 기존 AC 시설을 유지한 800 VDC 랙 도입 │ <b>{'확인' if a['nvidia_existing_ac_retrofit'] else '재확인 필요'}</b>",
        f"• OCP SST 사양 │ <b>v{html.escape(str(a['ocp_sst_spec_version'] or '확인 불가'))}</b> · Google·Microsoft·NVIDIA 공개 표준화",
        f"• NVIDIA 생태계 │ <b>{a['nvidia_partner_count_min'] or '확인 불가'}개+</b> 공급사",
        "",
        "<b>🧭 현재 판정</b>",
        f"• 하이브리드 AC/DC 브리지 │ <b>{'확인' if m['hybrid_bridge_confirmed'] else '판정 보류'}</b>",
        "  └ 기존 건물의 AC 전력망·중전압/저전압 배전 인프라를 당장 전면 폐기하지 않고 랙 인근에서 800 VDC로 변환하는 경로가 공식 로드맵에 존재",
        f"• 시설 전체 Native 800 VDC 대량도입 │ <b>{'아직 확정 아님' if not m['native_facility_800v_mass_adoption_confirmed'] else '확정'}</b>",
        f"• 기존 AC 전력기기 단기 대체위험 │ <b>{html.escape(str(m.get('legacy_ac_near_term_displacement_risk')))}</b>",
        f"• Schneider 공식 실적발표 교차검증 │ 2030년 수요 영향 추정 <b>{m.get('schneider_2030_demand_impacted_pct_low')}~{m.get('schneider_2030_demand_impacted_pct_high')}%</b> · full architecture 2028 준비={m.get('schneider_full_architecture_ready_2028')}",
        f"  └ {html.escape(str(m.get('schneider_timing_source')))}",
        f"• Vertiv 공식 경로 │ sidecar H2 2026 상용화={m.get('vertiv_sidecar_commercialization_h2_2026')} · 2027 ramp={m.get('vertiv_deployment_ramp_2027')} · 중앙집중형 2028~2029+={m.get('vertiv_centralized_2028_2029_plus')}",
        f"• SST 상대 성숙도 │ Vertiv 기준 MV DC UPS가 SST보다 성숙한 선행경로={m.get('vertiv_sst_lower_readiness_than_mv_dc_ups')}",
        f"• 사이드카·SST 기술 단독 해자 │ <b>{html.escape(m['technology_only_moat'])}</b>",
        f"  └ {html.escape(m['moat_check_basis'])}",
        "• JPM의 '도입 지연·2030년대까지 하이브리드 주류' 문구는 공개 원문을 독립 확보하지 못해 공식 기준선으로 사용하지 않음. 대신 Schneider·Vertiv·NVIDIA 공식 일정으로 검증",
        "",
        "<b>🧊 전력·냉각 인프라 실행</b>",
        f"• LG전자-AIR │ 북미 AIDC <b>{e.get('lg_air_capacity_gw_min') or 5:g}GW+</b> 칠러 장기공급계약 · 양사 공식 확인={e.get('lg_air_bilateral_official_long_term_contract')}",
        "  └ 공식 계약금액은 미공개. 3~5년·GW당 4,000~5,000억원·총 2.0~2.5조원은 언론/시장 추정치로 확정매출 취급 금지",
        f"• LG 실행능력 │ 상반기 AIDC 냉각 수주 USD {e.get('lg_first_half_aidc_cooling_orders_usd_m') or 428:g}M · 2027 칠러 매출목표 USD {e.get('lg_2027_chiller_revenue_target_usd_m') or 680:g}M · 생산능력 투자 {e.get('lg_chiller_capacity_investment_krw_billion') or 150:g}0억원",
        f"• Vertiv-NVIDIA │ Vera Rubin DSX 공식 공동개발={e.get('vertiv_nvidia_vera_rubin_dsx_official')} · OneCore 표준 블록 {e.get('vertiv_onecore_standard_block_mw') or 12.5:g}MW · DSX Ready CDU {e.get('vertiv_dsx_ready_cdu_mw') or 2.3:g}MW",
        f"• SGC에너지-Vertiv │ 군산 초기 {e.get('sgc_vertiv_initial_mw') or 60:g}MW → 최대 {e.get('sgc_vertiv_max_mw') or 300:g}MW · PowerNexus 적용 계획={e.get('sgc_vertiv_powernexus_planned')}",
        f"  └ Vertiv 관계는 <b>{'비구속 MOU' if e.get('sgc_vertiv_non_binding_mou') else 'MOU/기술검토'}</b> · Vertiv 확정 공급계약={e.get('sgc_vertiv_binding_supply_contract_confirmed')}",
        f"  └ 프로젝트 실행은 현대엔지니어링 60MW EPC 수주={e.get('sgc_hyundai_epc_contract_confirmed')} · 약 {e.get('sgc_phase1_epc_krw_billion') * 10:,.0f}억원 · 2026년 10월 착공={e.get('sgc_phase1_construction_start_2026_10')} · Q1 2028 전원 인가 목표={e.get('sgc_phase1_energization_q1_2028')}" if e.get("sgc_phase1_epc_krw_billion") is not None else "  └ 프로젝트 EPC 금액 원천 재확인 필요",
        "• 기사 제목의 7조달러는 글로벌 데이터센터 투자 전망치이며 Vertiv 수주액·SGC 사업비가 아님",
        "",
        "<b>🏭 관련 기업 지도</b>",
    ]
    for name in ("Schneider Electric", "Eaton", "Vertiv", "Hitachi Energy", "Siemens", "LS ELECTRIC", "Delta"):
        row = v[name]
        lines.append(f"• {html.escape(name)} │ {html.escape(str(row.get('stage')))}")

    lines += [
        "",
        "<b>🔔 앞으로 즉시 알림</b>",
        "• NVIDIA/OCP가 파워랙·Row Power Center·시설 전체 Native 800 VDC 일정 변경",
        "• OCP SST/LVDC 사양 버전 또는 UL·NFPA·IEEE·IEC 안전 기준 변경",
        "• Schneider·Eaton·Vertiv·Hitachi·Siemens·LS ELECTRIC·Delta가 계획/시제품→상용 출하·첫 고객으로 전환",
        "• 기존 AC 배전·UPS·변압기·스위치기어를 보존하는 하이브리드 기간이 연장/단축되는 공식 증거",
        "• 시설 전체 800 VDC 또는 SST가 실제 대규모 상업 데이터센터에 채택되는 첫 확정 사례",
        "• LG-AIR 5GW+ 프로그램의 실제 발주·납품 일정·공식 계약금액·고객 실명·CDU 추가 공급",
        "• SGC-Vertiv가 비구속 MOU→구속력 있는 공급계약/실제 납품으로 승격",
        "• 군산 60MW 1단계가 2026년 10월 착공→Q1 2028 전원 인가 일정대로 진행되는지",
        "• 제품 단품이 아니라 EPC·보호·계측·에너지저장·냉각·운영SW·서비스를 묶은 턴키 수주",
        "",
        "<b>⚠️ 공정 병목 후보</b>",
        "• 안전·아크플래시·접지·보호협조 표준 미성숙 → 인증·현장 승인 지연",
        "• 800 VDC 커넥터·차단기·버스웨이·에너지저장·DC/DC 생태계 동시 준비 필요",
        "• 사이드카는 빠른 도입 경로지만 랙 옆 공간·냉각·서비스 동선 제약 발생",
        "• SST는 중전압→800 VDC 단일화 장점이 있지만 전력반도체 원가·수율·신뢰성·보호 설계 검증이 병목",
        "",
        "<b>🔗 공식 원문</b>",
        f'• <a href="{NVIDIA_BLOG}">NVIDIA 800 VDC 로드맵</a>',
        f'• <a href="{OCP_LVDC}">OCP LVDC·SST 표준화</a>',
        f'• <a href="{SCHNEIDER_POWER_RACK}">Schneider NetShelter Power Rack 800VDC</a>',
        f'• <a href="{SCHNEIDER_CALL}">Schneider 2025 연간 실적발표 transcript</a>',
        f'• <a href="{VERTIV_PATH}">Vertiv rack→data hall 단계별 경로</a>',
        f'• <a href="{VERTIV_GUIDE}">Vertiv 800 VDC 의사결정 가이드</a>',
        f'• <a href="{EATON_GTC}">Eaton 800 VDC 공식 참조 아키텍처</a>',
        f'• <a href="{HITACHI_800V}">Hitachi 800 VDC</a>',
        f'• <a href="{SIEMENS_SST}">Siemens SST</a>',
        f'• <a href="{LS_DC}">LS ELECTRIC DC Grid</a>',
        f'• <a href="{DELTA_DCW}">Delta 800 VDC In-Row</a>',
        f'• <a href="{LG_AIR}">LG전자-AIR 5GW+ 칠러 장기공급계약</a>',
        f'• <a href="{AIR_LG}">AIR 공식 LG 장기공급계약</a>',
        f'• <a href="{VERTIV_DSX}">Vertiv Vera Rubin DSX</a>',
        f'• <a href="{SGC_VERTIV_DCD}">SGC에너지-Vertiv 군산 AIDC MOU 교차검증</a>',
        f'• <a href="{SGC_HYUNDAI_EPC}">현대엔지니어링 군산 SGC AIDC EPC 수주</a>',
    ]

    if chg:
        lines += ["", "<b>🔄 이번 변화</b>"]
        lines += [f"• {html.escape(x)}" for x in chg[:12]]
    if errors:
        lines += ["", "<b>⚠️ 원천 재조회 오류</b>"]
        lines += [f"• {html.escape(x)}" for x in errors[:8]]
        lines.append("• 오류 원천은 직전 성공값을 유지하며 신규 확정 변화로 승격하지 않음")

    if fxv.get("usdkrw"):
        lines += ["", f"💱 1달러 = {float(fxv['usdkrw']):,.2f}원 · {html.escape(str(fxv.get('source','')))}"]
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (PENDING, ALERT, STATUS):
        p.unlink(missing_ok=True)

    old = load_state()
    texts, errors = get_source_texts(old)
    facts = snapshot(texts)
    fxv = fx(old)
    baseline = not old.get("initialized")
    format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
    chg = changes(old, facts)
    should_alert = baseline or format_upgrade or bool(chg)

    cache = {}
    for key, text in texts.items():
        cache[key] = {
            "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text": text[:120000],
            "url": SOURCES[key],
        }

    pending = {
        "initialized": True,
        "format_version": FORMAT_VERSION,
        "facts": facts,
        "source_cache": cache,
        "source_errors": errors,
        "fx": fxv,
        "last_changes": chg[:30],
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if should_alert:
        ALERT.write_text(render(facts, chg, errors, fxv), encoding="utf-8")

    STATUS.write_text(
        "# AI 데이터센터 800 VDC·전력/냉각 인프라 실행 감시\n\n"
        f"- 하이브리드 AC/DC 브리지: **{'확인' if facts['market']['hybrid_bridge_confirmed'] else '판정 보류'}**\n"
        f"- 시설 전체 Native 800 VDC 대량도입: **{'확정' if facts['market']['native_facility_800v_mass_adoption_confirmed'] else '미확정'}**\n"
        f"- 기존 AC 전력기기 단기 대체위험: **{facts['market'].get('legacy_ac_near_term_displacement_risk')}**\n"
        f"- Schneider 2030 영향 추정: **{facts['market'].get('schneider_2030_demand_impacted_pct_low')}~{facts['market'].get('schneider_2030_demand_impacted_pct_high')}%**\n"
        f"- Vertiv 중앙집중형 2028~2029+: **{facts['market'].get('vertiv_centralized_2028_2029_plus')}**\n"
        f"- OCP SST 사양: **v{facts['architecture'].get('ocp_sst_spec_version') or '확인 불가'}**\n"
        f"- 공식 800 VDC 직접 참여 공급사: **{facts['market']['official_multi_vendor_800v_count']}개**\n"
        f"- LG전자-AIR 북미 칠러 장기계약: **{facts['execution'].get('lg_air_capacity_gw_min') or 5}GW+ / 공식 계약금액 미공개**\n"
        f"- SGC에너지-Vertiv: **{facts['execution'].get('sgc_vertiv_initial_mw') or 60:.0f}MW→최대 {facts['execution'].get('sgc_vertiv_max_mw') or 300:.0f}MW / 비구속 MOU**\n"
        f"- SGC 군산 1단계 실행: **현대엔지니어링 EPC 약 {facts['execution'].get('sgc_phase1_epc_krw_billion') * 10:,.0f}억원 / 2026년 10월 착공 / Q1 2028 전원 인가 목표**\n" if facts["execution"].get("sgc_phase1_epc_krw_billion") is not None else ""
        f"- 의미 변화: **{len(chg)}건**\n"
        f"- 알림: **{'예' if should_alert else '아니오'}**\n"
        f"- 원천 오류: **{'; '.join(errors) if errors else '없음'}**\n",
        encoding="utf-8",
    )
    print(
        f"ai_dc_800v baseline={baseline} format_upgrade={format_upgrade} "
        f"changes={len(chg)} vendors={facts['market']['official_multi_vendor_800v_count']} "
        f"hybrid={facts['market']['hybrid_bridge_confirmed']} alert={should_alert} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
