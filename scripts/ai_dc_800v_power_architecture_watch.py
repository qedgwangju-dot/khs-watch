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

FORMAT_VERSION = 2
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}

NVIDIA_BLOG = "https://blogs.nvidia.com/blog/800-vdc-power-architecture-ai-factory/"
NVIDIA_ARCH = "https://www.nvidia.com/en-us/data-center/technologies/800-vdc-architecture/"
OCP_LVDC = "https://www.opencompute.org/index.php/blog/powering-the-next-era-of-ai-how-google-microsoft-and-nvidia-are-standardizing-and-accelerating-the-industry-transition-to-lvdc"
SCHNEIDER_POWER_RACK = "https://www.se.com/ww/en/work/products/product-reveal/net-shelter-power-rack-800-vdc/"
SCHNEIDER_GUIDE = "https://www.se.com/ww/en/insights/ai-and-technology/artificial-intelligence/vdc-powering-the-future-of-ai-data-centers/"
VERTIV_GUIDE = "https://www.vertiv.com/en-ca/insights/articles/educational-articles/the-800-vdc-decision-a-practical-guide-for-ai-power-architecture/"
VERTIV_RELEASE = "https://www.vertiv.com/en-emea/about/news-and-events/news-releases/from-vision-to-readiness-vertiv-collaborates-with-nvidia-to-advance-800-vdc-platform-designs-to-power-the-next-generation-of-ai-factories/"
EATON_GTC = "https://www.eaton.com/kr/ko-kr/company/news-insights/news-releases/2025/eaton-next-generation-ai-factories.html"
HITACHI_800V = "https://hitachidigital.com/news/hitachi-accelerate-gigawatt-scale-ai-factories/"
SIEMENS_SST = "https://press.siemens.com/global/en/pressrelease/siemens-and-reinhausen-develop-direct-current-power-solutions-ai-data-centers"
LS_DC = "https://nahpdev.ls-electric.com/company/articles/2759/industry-usa-ls-electric-america-to-highlight-dc-grid-solutions-for-ai-data-centers-at-data-center-world-2026"
DELTA_DCW = "https://www.delta-singapore.com/en-SG/news/40267"

SOURCES = {
    "nvidia_blog": NVIDIA_BLOG,
    "nvidia_arch": NVIDIA_ARCH,
    "ocp": OCP_LVDC,
    "schneider_power_rack": SCHNEIDER_POWER_RACK,
    "schneider_guide": SCHNEIDER_GUIDE,
    "vertiv_guide": VERTIV_GUIDE,
    "vertiv_release": VERTIV_RELEASE,
    "hitachi": HITACHI_800V,
    "siemens": SIEMENS_SST,
    "ls": LS_DC,
    "delta": DELTA_DCW,
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
    vert = texts.get("vertiv_guide", "")
    vrel = texts.get("vertiv_release", "")
    n_arch = texts.get("nvidia_arch", "")
    hitachi = texts.get("hitachi", "")
    siemens = texts.get("siemens", "")
    ls = texts.get("ls", "")
    delta = texts.get("delta", "")

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
                "stage": (
                    "800 VDC 공식 참조 아키텍처·NVIDIA 생태계 참여"
                    if "Eaton" in n_arch else "공식 Eaton 기준선·NVIDIA 재확인 필요"
                ),
                "standards_signal": None,
                "legacy_ac_bridge": None,
                "source_mode": "Eaton 공식 2025 참조 아키텍처 기준값 + NVIDIA 공식 파트너 목록 실시간 교차확인",
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

    live_vendor_800v = 0
    for name, row in facts["vendors"].items():
        if row.get("stage") not in ("확인 불가", "DC grid 개념·전시"):
            live_vendor_800v += 1

    facts["market"] = {
        "official_multi_vendor_800v_count": live_vendor_800v,
        "hybrid_bridge_confirmed": bool(
            facts["architecture"].get("nvidia_existing_ac_retrofit")
            and facts["vendors"]["Schneider Electric"].get("sidecar")
        ),
        "native_facility_800v_mass_adoption_confirmed": False,
        "technology_only_moat": "낮음/미확정" if live_vendor_800v >= 5 and sst_version else "판정 보류",
        "moat_check_basis": "OCP 공개 표준 + 다수 공식 공급사. 실제 해자는 양산·안전인증·통합 EPC·제어/운영SW·서비스에서 재검증",
        "jpm_user_note_status": "사용자 제공 리서치 요약은 독립 공식 원문 미확보라 알림 트리거 기준으로 사용하지 않음",
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

    pm, nm = prev.get("market") or {}, new.get("market") or {}
    for key, label in (
        ("official_multi_vendor_800v_count", "공식 800 VDC 직접 참여 공급사 수"),
        ("hybrid_bridge_confirmed", "하이브리드 AC/DC 브리지"),
        ("native_facility_800v_mass_adoption_confirmed", "시설 전체 Native 800 VDC 대량도입"),
        ("technology_only_moat", "사이드카·SST 기술 단독 해자"),
    ):
        before, after = pm.get(key), nm.get(key)
        if before is not None and after is not None and before != after:
            out.append(f"{label} {before}→{after}")
    return out


def render(facts: dict, chg: list[str], errors: list[str], fxv: dict) -> str:
    a = facts["architecture"]
    v = facts["vendors"]
    m = facts["market"]

    lines = [
        "<b>⚡ AI 데이터센터 800 VDC 전환·하이브리드 AC/DC 감시</b>",
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
        f"• 사이드카·SST 기술 단독 해자 │ <b>{html.escape(m['technology_only_moat'])}</b>",
        f"  └ {html.escape(m['moat_check_basis'])}",
        "• JPM의 '도입 지연·2030년대까지 하이브리드 주류' 문구는 공개 원문을 독립 확보하지 못해 공식 기준선으로 사용하지 않음",
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
        f'• <a href="{VERTIV_GUIDE}">Vertiv 800 VDC 의사결정 가이드</a>',
        f'• <a href="{EATON_GTC}">Eaton 800 VDC 공식 참조 아키텍처</a>',
        f'• <a href="{HITACHI_800V}">Hitachi 800 VDC</a>',
        f'• <a href="{SIEMENS_SST}">Siemens SST</a>',
        f'• <a href="{LS_DC}">LS ELECTRIC DC Grid</a>',
        f'• <a href="{DELTA_DCW}">Delta 800 VDC In-Row</a>',
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
        "# AI 데이터센터 800 VDC 전환 감시\n\n"
        f"- 하이브리드 AC/DC 브리지: **{'확인' if facts['market']['hybrid_bridge_confirmed'] else '판정 보류'}**\n"
        f"- 시설 전체 Native 800 VDC 대량도입: **{'확정' if facts['market']['native_facility_800v_mass_adoption_confirmed'] else '미확정'}**\n"
        f"- OCP SST 사양: **v{facts['architecture'].get('ocp_sst_spec_version') or '확인 불가'}**\n"
        f"- 공식 800 VDC 직접 참여 공급사: **{facts['market']['official_multi_vendor_800v_count']}개**\n"
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
