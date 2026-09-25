#!/usr/bin/env python3
from __future__ import annotations

import html
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import janus_watch_v2 as j2
import janus_watch_v7 as j7
import janus_watch_v12 as j12

# v13: 한·미·일 SMR 제3국 배치 + BWRX-300 유럽 플릿을 '기사'가 아니라 사업단계로 추적.
# 기준선: 2026-07-07 MOC → 2026-09-22 4사 MOU → 2026-09-23 Implementation Plan.
# 이후 구속력 있는 계약·국가/부지·호기수·투자액·FID·인허가·EPC·장납기 발주가 바뀔 때만 재알림.

GLOBAL_SMR_KINDS = {"smr_trilateral_deployment", "bwrx300_europe_fleet"}

STATE_DEPT_URL = "https://www.state.gov/releases/office-of-the-spokesman/2026/09/the-united-states-announces-civil-nuclear-initiatives-on-the-margins-of-the-united-nations-general-assembly"
GE_MOU_URL = "https://www.gevernova.com/news/press-releases/sge-ge-vernova-hitachi-samsung-ct-sign-mou-advance-bwrx-300-fleet-deployment-europe"

for src in [
    {"name": "미 국무부 한미일 SMR 제3국 배치", "url": STATE_DEPT_URL, "kind": "smr_trilateral_static"},
    {"name": "GE Vernova BWRX-300 유럽 플릿", "url": GE_MOU_URL, "kind": "bwrx300_europe_static"},
]:
    if not any(s.get("url") == src["url"] for s in j2.base.SOURCES):
        j2.base.SOURCES.append(src)

RSS_QUERIES = [
    (
        "한미일 SMR 제3국 배치 이행계획",
        '"small modular reactor" ("United States" Japan Korea) ("implementation plan" OR MOC OR deployment) when:45d',
        "smr_trilateral_rss",
    ),
    (
        "BWRX-300 유럽 플릿·삼성물산",
        '"BWRX-300" ("Samsung C&T" OR SGE OR "GE Vernova" OR Hitachi) (Europe OR Poland OR UK OR Sweden) when:45d',
        "bwrx300_europe_rss",
    ),
]
for name, query, kind in RSS_QUERIES:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
    if not any(s.get("url") == url for s in j2.base.SOURCES):
        j2.base.SOURCES.append({"name": name, "url": url, "kind": kind})

for term in [
    "GE Vernova", "Hitachi", "Samsung C&T", "SGE", "Synthos Green Energy",
    "BWRX-300", "Implementation Plan", "MOC", "UNGA",
]:
    if term not in j2._PROTECTED_TERMS:
        j2._PROTECTED_TERMS.append(term)

_MATERIAL_FOLLOWUP = [
    "final investment decision", " fid ", "definitive agreement",
    "binding development agreement", "binding epc", "epc contract", "epc award",
    "feed contract", "feed award", "purchase order", "equipment order",
    "financial close", "financing closed", "loan approved", "equity committed",
    "site selected", "selected site", "permit granted", "permit approved",
    "license granted", "license approved", "construction start", "construction begins",
    "groundbreaking", "first concrete", "commissioning", "commercial operation",
    "supply agreement", "deployment agreement",
]

_BASELINE_ONLY = [
    "implementation plan", "memorandum of cooperation", "moc",
    "memorandum of understanding", "mou", "advance bwrx-300 fleet deployment",
]


def _fresh(pub: str, max_days: int = 7) -> bool:
    if not pub:
        return True
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() <= max_days * 86400
    except Exception:
        return True


def _clean_title(title: str) -> str:
    title = j2.base.norm(title)
    return re.sub(r"\s+-\s+[^-]{2,100}$", "", title).strip()


def _is_followup(low: str) -> bool:
    padded = f" {low} "
    return any(x in padded for x in _MATERIAL_FOLLOWUP)


def _scope_key(low: str) -> str:
    if any(x in low for x in ["studsvik", "nyköping", "nykoping", "målma", "malma", "valdemarsvik", "sweden", "swedish"]):
        return "studsvik_sweden"
    if any(x in low for x in ["poland", "polish"]):
        return "poland"
    if any(x in low for x in ["united kingdom", " uk ", "britain", "british"]):
        return "uk"
    if any(x in low for x in ["europe", "european"]):
        return "europe"
    return "global"


def _material_stage(low: str) -> str:
    patterns = [
        ("commercial_operation", ["commercial operation", "commercial service", "enters operation"]),
        ("commissioning", ["commissioning"]),
        ("construction_start", ["construction start", "construction begins", "groundbreaking", "first concrete"]),
        ("equipment_order", ["purchase order", "equipment order", "long-lead order", "long lead order"]),
        ("license_approved", ["license granted", "license approved", "permit granted", "permit approved"]),
        ("fid", ["final investment decision", " fid "]),
        ("financial_close", ["financial close", "financing closed"]),
        ("epc_contract", ["binding epc", "epc contract", "epc award"]),
        ("feed_contract", ["feed contract", "feed award"]),
        ("binding_development", ["definitive agreement", "binding development agreement", "deployment agreement"]),
        ("supply_agreement", ["supply agreement"]),
    ]
    padded = f" {low} "
    for stage, terms in patterns:
        if any(term in padded for term in terms):
            return stage

    # 'selected'만으로는 파트너 선정·공급사 평가·과거 기사까지 모두 잡히므로 금지.
    # 실제 부지 확정 표현만 별도 상태로 인정한다.
    if any(x in padded for x in [" site selected ", " selected site "]):
        return "site_selected"
    if any(site in low for site in ["nyköping", "nykoping", "målma", "malma", "valdemarsvik"]) and any(
        phrase in low for phrase in ["selected as the site", "chosen as the site", "final site"]
    ):
        return "site_selected"
    return ""


def _is_known_bwrx_baseline(low: str) -> bool:
    # 2026-09-03 Studsvik/ReFirm 4기·1.2GW 전략 파트너 선정은 영구 기준선.
    studsvik = any(x in low for x in ["studsvik", "refirm"]) and (
        any(x in low for x in ["1.2-gw", "1.2 gw", "1.2gw", "four-unit", "four unit", "4-unit", "4 unit"])
        or any(x in low for x in ["strategic partner", "strategic collaborator", "selects ge vernova hitachi", "selected ge vernova hitachi"])
    )
    # 2026-09-22 SGE·GE Vernova·Hitachi·Samsung C&T MOU의 14기·4.2GW/유럽 플릿도 영구 기준선.
    sge_mou = (
        any(x in low for x in ["sge", "synthos", "samsung c&t", "samsung"])
        and any(x in low for x in ["4.2gw", "4.2 gw", "14 bwrx-300", "14 reactors", "fleet deployment", "fleet in europe", "target europe", "targets europe"])
    )
    mou_only = any(x in low for x in ["memorandum of understanding", " mou ", "advance bwrx-300 fleet deployment"])
    return studsvik or sge_mou or mou_only


def _global_state_key(title: str, requested: str) -> str:
    low = (title or "").lower()
    stage = _material_stage(low)

    if requested == "smr_trilateral_rss":
        if not any(x in low for x in ["smr", "small modular reactor"]):
            return ""
        if not any(x in low for x in ["korea", "south korea", "republic of korea"]):
            return ""
        if "japan" not in low:
            return ""
        if not any(x in low for x in ["united states", "u.s.", " us "]):
            return ""
        # MOC·Implementation Plan 자체는 이미 9/23 기준선. 이후 실제 계약/부지/FID 등만 통과.
        if not stage:
            return ""
        return f"smr_trilateral|{_scope_key(low)}|{stage}"

    if requested == "bwrx300_europe_rss":
        if "bwrx-300" not in low:
            return ""
        if not any(x in low for x in ["samsung", "sge", "synthos", "ge vernova", "hitachi", "studsvik", "refirm"]):
            return ""
        # 늦게 발견된 9/3 Studsvik 선정기사, 9/22 유럽 MOU·4.2GW 기사 재보도는 신규 상태가 아니다.
        if _is_known_bwrx_baseline(low) and not stage:
            return ""
        if not stage:
            return ""
        return f"bwrx300_europe|{_scope_key(low)}|{stage}"

    return ""


def _rss_kind(title: str, requested: str) -> str:
    state_key = _global_state_key(title, requested)
    if not state_key:
        return ""
    if requested == "smr_trilateral_rss":
        return "smr_trilateral_deployment"
    if requested == "bwrx300_europe_rss":
        return "bwrx300_europe_fleet"
    return ""


def _rss_items(source, page_text):
    try:
        root = ET.fromstring(page_text)
    except Exception as exc:
        j2._append_error(f"글로벌 SMR RSS 파싱 실패 | {source['url']} | {exc}")
        return []

    rows = []
    for item in root.findall(".//item"):
        title = _clean_title(item.findtext("title") or "")
        link = j2.base.norm(item.findtext("link") or "")
        pub = j2.base.norm(item.findtext("pubDate") or "")
        src = item.find("source")
        outlet = j2.base.norm(src.text if src is not None and src.text else "")
        requested = source.get("kind", "")
        kind = _rss_kind(title, requested)
        state_key = _global_state_key(title, requested)
        if not title or not link or not kind or not state_key or not _fresh(pub):
            continue
        rows.append({
            "source": outlet or source["name"],
            "title": title[:500],
            "url": link,
            "kind": kind,
            "published": pub,
            "global_state_key": state_key,
        })
        if len(rows) >= 6:
            break
    return rows


def _static_item(source, page_text):
    text = j2.base.norm(re.sub(r"<[^>]+>", " ", page_text))
    low = text.lower()

    if source.get("kind") == "smr_trilateral_static":
        if "implementation plan" not in low or "small modular reactor" not in low:
            return []
        return [{
            "source": source["name"],
            "title": "한미일 SMR 제3국 배치 이행계획 확립 · 2026년 7월 7일 MOC → 2026년 9월 23일 Implementation Plan · 국제 컨소시엄 1,500억달러+ 원자로 투자 목표",
            "url": source["url"],
            "kind": "smr_trilateral_deployment",
        }]

    if source.get("kind") == "bwrx300_europe_static":
        if "bwrx-300" not in low or "samsung c&t" not in low:
            return []
        return [{
            "source": source["name"],
            "title": "GE Vernova·Hitachi·Samsung C&T·SGE BWRX-300 유럽 플릿 MOU · 2026년 9월 22일 · 폴란드 DIP 26기/우선 14기 · 영국 14기 4.2GW",
            "url": source["url"],
            "kind": "bwrx300_europe_fleet",
        }]

    return []


_PREV_EXTRACT = j2.base.extract_items


def _extract_v13(source, page_text):
    if source.get("kind") in {"smr_trilateral_rss", "bwrx300_europe_rss"}:
        return _rss_items(source, page_text)
    if source.get("kind") in {"smr_trilateral_static", "bwrx300_europe_static"}:
        return _static_item(source, page_text)
    return _PREV_EXTRACT(source, page_text)


j2.base.extract_items = _extract_v13


_PREV_FINGERPRINT = j2.base.fingerprint


def _semantic_global_fingerprint_v13(source: str, title: str, url: str) -> str:
    for requested in ("smr_trilateral_rss", "bwrx300_europe_rss"):
        state_key = _global_state_key(title, requested)
        if state_key:
            return hashlib.sha256(f"janus-v13-global|{state_key}".encode("utf-8")).hexdigest()
    return _PREV_FINGERPRINT(source, title, url)


j2.base.fingerprint = _semantic_global_fingerprint_v13


def _krw_from_usd_billion(usd_b: float) -> tuple[str, str]:
    try:
        rate, provider, stamp = j7._usdkrw()
    except Exception:
        return "", ""
    if not rate:
        return "", ""
    won = usd_b * 1_000_000_000 * rate
    eok = round(won / 100_000_000)
    jo, rem = divmod(eok, 10000)
    amount = f"약 {jo:,}조{rem:,}억원" if jo and rem else (f"약 {jo:,}조원" if jo else f"약 {rem:,}억원")
    return amount, f"1달러={rate:,.2f}원 · {provider} · {stamp}"


def _render_global_smr(events: list[dict]) -> str:
    uniq = []
    seen = set()
    for e in events:
        state_key = e.get("global_state_key") or _global_state_key(
            e.get("title") or "",
            "bwrx300_europe_rss" if e.get("kind") == "bwrx300_europe_fleet" else "smr_trilateral_rss",
        )
        key = (e.get("kind"), state_key or e.get("url"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    baseline = any(
        ("2026년 9월 23일" in (e.get("title") or "")) or ("2026년 9월 22일" in (e.get("title") or ""))
        for e in uniq
    )

    amount_krw, fx = _krw_from_usd_billion(150)
    lines = ["🚨 <b>[한미일 SMR 제3국 배치·BWRX-300 유럽 웹감시]</b>", ""]

    if baseline:
        lines.extend([
            "<b>한미일 SMR 협력이 MOC에서 이행계획·유럽 플릿 개발 단계로 진전</b>",
            "",
            "<b>타임라인</b>",
            "• <b>2026년 7월 7일</b> 미국·일본·한국, Ankara에서 제3국 SMR 배치 MOC 서명",
            "• <b>2026년 9월 22일</b> GE Vernova·Hitachi·Samsung C&T·SGE, 유럽 BWRX-300 플릿 개발 MOU 서명",
            "• <b>2026년 9월 23일</b> 미 국무부, MOC를 실행하기 위한 Implementation Plan 수립 공식 발표",
            "",
            "<b>현재 확정 숫자</b>",
            f"• 국제 컨소시엄 목표: 향후 원자로 투자 <b>1,500억달러 이상{('(' + amount_krw + ')') if amount_krw else ''}</b> — 확정 수주액이 아니라 장기 투자 목표",
            "• BWRX-300: <b>300MW/기</b>",
            "• 폴란드: Decisions in Principle <b>26기</b> · 우선 3개 부지에서 잠재 <b>14기</b> 개발 집중",
            "• 영국: 3개 다호기 부지에 <b>14기 · 4.2GW</b> 제안",
            "• Samsung C&T: 원자로 기술사가 아니라 <b>국제 EPC·사업수행 역량</b>으로 참여",
            "",
            "<b>매출 연결</b>",
            "• 이행계획 세부공개 → 국가·부지 지정 → 개발계약/FEED → 금융·FID → 인허가 → EPC → 주기기·장납기 발주 → 건설·상업운전",
            "",
            "<b>주의</b>",
            "• 현재 4사 합의는 MOU이며, 1,500억달러는 컨소시엄이 촉진하려는 원자로 투자 규모입니다. Samsung C&T 확정 EPC 수주액으로 보면 안 됩니다.",
            "• 미 국무부 Media Note는 Implementation Plan의 세부 실행항목을 공개하지 않았습니다.",
            "",
            "<b>다음 확인</b>",
            "• Implementation Plan 세부문서 · 국가별 호기/부지 · Samsung C&T 계약범위·금액 · GE Vernova Hitachi 주기기 발주 · 금융/FID · 폴란드/영국 인허가 · 첫 착공",
        ])
        if fx:
            lines.append(f"• 환산 기준: {html.escape(fx)}")
    else:
        lines.extend([
            "<b>BWRX-300·한미일 SMR 제3국 배치 후속 단계 변화</b>",
            "",
            "• 기존 기준선: <b>2026년 7월 7일 MOC → 2026년 9월 22일 산업 MOU → 2026년 9월 23일 Implementation Plan</b>",
            "• 계약·부지·호기수·용량·투자액·FID·인허가·EPC·발주 가운데 실제 상태가 달라진 경우만 후속 알림",
            "",
            "<b>이번 신규 자료</b>",
        ])
        for e in uniq[:8]:
            try:
                title = j2._translate_ko(e.get("title") or "")
            except Exception:
                title = e.get("title") or ""
            if not title:
                continue
            url = e.get("url") or ""
            linked = f"<a href=\"{html.escape(url, quote=True)}\">{html.escape(title)}</a>" if url else html.escape(title)
            lines.append(f"• {html.escape(j2.base.norm(e.get('source') or '출처'))} — {linked}")
        lines.extend([
            "",
            "<b>다음 확인</b>",
            "• 구속력 있는 개발계약·FEED/EPC · 부지·호기수 · 자금조달/FID · 인허가 · 장납기 발주 · 상업운전 일정",
        ])

    reps = []
    for e in uniq:
        url = e.get("url") or ""
        if url in {STATE_DEPT_URL, GE_MOU_URL} and url not in reps:
            reps.append(url)
    if reps:
        lines.append("")
        for url in reps:
            label = "미 국무부 원문" if "state.gov" in url else "GE Vernova 공식 원문"
            lines.append(f"<a href=\"{html.escape(url, quote=True)}\"><b>{label}</b></a>")

    return "\n".join(lines).strip()


_PREV_RENDER = j2.base.render_alert


def _render_v13(events, fact_changes):
    cluster = [e for e in events if e.get("kind") in GLOBAL_SMR_KINDS]
    rest = [e for e in events if e.get("kind") not in GLOBAL_SMR_KINDS]
    parts = []
    if cluster:
        parts.append(_render_global_smr(cluster))
    other = _PREV_RENDER(rest, fact_changes)
    if other:
        parts.append(other)
    return "\n\n──────────\n\n".join(parts).strip()


j2.base.render_alert = _render_v13


def _self_test_v13():
    assert _rss_kind(
        "U.S., Japan, South Korea establish Implementation Plan for SMR deployments in other countries",
        "smr_trilateral_rss",
    ) == ""

    # 실제 사용자에게 중복 발송된 기준선 기사들은 모두 신규 상태가 아니어야 한다.
    assert _rss_kind(
        "Studsvik Selects GE Vernova Hitachi, Samsung C&T for 1.2-GW Swedish BWRX-300 Project",
        "bwrx300_europe_rss",
    ) == ""
    assert _rss_kind(
        "SGE, GE Vernova, Hitachi and Samsung C&T target Europe with 4.2GW BWRX-300 SMR fleet",
        "bwrx300_europe_rss",
    ) == ""
    assert _rss_kind(
        "SGE, GE Vernova, Hitachi and Samsung C&T sign MoU to advance BWRX-300 fleet deployment in Europe",
        "bwrx300_europe_rss",
    ) == ""

    # 실제 단계 상승만 통과.
    binding = "Samsung C&T and SGE sign binding EPC development agreement for BWRX-300 project in Poland"
    assert _rss_kind(binding, "bwrx300_europe_rss") == "bwrx300_europe_fleet"
    assert _global_state_key(binding, "bwrx300_europe_rss") == "bwrx300_europe|poland|epc_contract"

    fid_a = "SGE reaches final investment decision for BWRX-300 project in Poland"
    fid_b = "Polish BWRX-300 project reaches FID with SGE and Samsung C&T"
    assert _semantic_global_fingerprint_v13("source-a", fid_a, "https://a.example") == _semantic_global_fingerprint_v13(
        "source-b", fid_b, "https://b.example"
    )

    print("janus_v13_trilateral_bwrx_event_gate=passed semantic_state_dedupe=passed")


if __name__ == "__main__":
    if "--mode" in sys.argv and "self-test" in sys.argv:
        _self_test_v13()
    sys.exit(j2.base.main())
