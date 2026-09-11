#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import janus_watch_v2 as j2
import janus_watch_v8 as j8

# v9 핵심
# 1) 2026-09-11 시행된 SMR 특별법·시행령 후속 집행을 별도 정책 트랙으로 감시
# 2) 최초 기본계획·시행계획·예산·특구·민관 공동출자 회사·연구조합·핵연료 공급망을 실질 매출 촉매로 추적
# 3) i-SMR 표준설계인가와 부지별 건설허가를 분리해 2035 상용화 목표의 실제 일정 병목을 추적
# 4) '2035 상용화'를 법정 의무기한처럼 오인하지 않도록 정책목표와 법정기한을 분리

SMR_POLICY_KINDS = {
    "smr_special_law",
    "smr_basic_plan",
    "smr_budget",
    "smr_special_zone",
    "smr_public_private_company",
    "smr_fuel_supply",
    "ismr_licensing",
}

RSS_QUERIES = [
    (
        "SMR 특별법·기본계획",
        "SMR 특별법 소형모듈원자로 기본계획 시행계획 예산 특구 핵연료 공급망 민관합작 when:30d",
        "smr_policy_rss",
    ),
    (
        "SMR 특구·민관 공동출자",
        "소형모듈원자로 연구개발 특구 공동출자 회사 연구조합 예산 표준화 when:60d",
        "smr_business_rss",
    ),
    (
        "i-SMR 인허가",
        "i-SMR 혁신형 소형모듈원자로 표준설계인가 건설허가 원안위 기장 2035 when:60d",
        "ismr_license_rss",
    ),
    (
        "과기정통부 SMR 공식",
        "site:msit.go.kr 소형모듈원자로 기본계획 시행계획 특구 공동출자 핵연료 when:90d",
        "smr_policy_rss",
    ),
    (
        "원안위 i-SMR 공식",
        "site:nssc.go.kr i-SMR 표준설계인가 심사 건설허가 when:90d",
        "ismr_license_rss",
    ),
]

for name, query, kind in RSS_QUERIES:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    if not any(s.get("url") == url for s in j2.base.SOURCES):
        j2.base.SOURCES.append({"name": name, "url": url, "kind": kind})

# 법·시행령의 시행 자체도 기준선으로 저장한다. 같은 버전은 재발송하지 않는다.
for source in [
    {
        "name": "국가법령정보센터 SMR 특별법",
        "url": "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=283879&viewCls=lsRvsDocInfoR",
        "kind": "smr_law_static",
    },
    {
        "name": "국가법령정보센터 SMR 특별법 시행령",
        "url": "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=289435&viewCls=lsRvsDocInfoR",
        "kind": "smr_decree_static",
    },
]:
    if not any(s.get("url") == source["url"] for s in j2.base.SOURCES):
        j2.base.SOURCES.append(source)

for term in [
    "i-SMR", "SMR", "과학기술정보통신부", "원자력안전위원회", "한국수력원자력",
]:
    if term not in j2._PROTECTED_TERMS:
        j2._PROTECTED_TERMS.append(term)


def _fresh(pub: str, max_days: int = 90) -> bool:
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
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()


def _policy_kind(title: str, requested_kind: str) -> str:
    low = (title or "").lower()
    if requested_kind == "ismr_license_rss":
        if not any(x in low for x in ["i-smr", "혁신형", "소형모듈원자로", "smr"]):
            return ""
        if any(x in low for x in ["표준설계인가", "심사", "건설허가", "인허가", "원안위", "규제", "검증시험"]):
            return "ismr_licensing"
        return ""

    if not any(x in low for x in ["smr", "소형모듈원자로", "소형모듈원전", "혁신형"]):
        return ""
    if any(x in low for x in ["특별법", "시행령", "법 시행", "본격 시행"]):
        return "smr_special_law"
    if any(x in low for x in ["기본계획", "시행계획", "로드맵"]):
        return "smr_basic_plan"
    if any(x in low for x in ["예산", "지원금", "재원", "보조", "국비", "총사업비"]):
        return "smr_budget"
    if any(x in low for x in ["특구", "연구개발특구", "연구개발 특구"]):
        return "smr_special_zone"
    if any(x in low for x in ["공동출자", "민관합작", "합작회사", "주주", "출자회사", "연구조합"]):
        return "smr_public_private_company"
    if any(x in low for x in ["핵연료", "연료 공급망", "우라늄", "농축", "연료가공"]):
        return "smr_fuel_supply"
    return ""


def _rss_items(source, page_text):
    try:
        root = ET.fromstring(page_text)
    except Exception as exc:
        j2._append_error(f"SMR 정책 RSS 파싱 실패 | {source['url']} | {exc}")
        return []
    rows = []
    for item in root.findall(".//item"):
        title = _clean_title(item.findtext("title") or "")
        link = j2.base.norm(item.findtext("link") or "")
        pub = j2.base.norm(item.findtext("pubDate") or "")
        src = item.find("source")
        outlet = j2.base.norm(src.text if src is not None and src.text else "")
        if not title or not link or not _fresh(pub):
            continue
        kind = _policy_kind(title, source.get("kind", ""))
        if not kind:
            continue
        rows.append({
            "source": outlet or source["name"],
            "title": title[:500],
            "url": link,
            "kind": kind,
            "published": pub,
        })
        if len(rows) >= 6:
            break
    return rows


def _static_law_item(source, page_text):
    text = j2.base.norm(re.sub(r"<[^>]+>", " ", page_text))
    if source.get("kind") == "smr_law_static":
        m = re.search(r"법률\s*제\s*([0-9]+)호", text)
        num = m.group(1) if m else "21422"
        title = f"SMR 특별법 시행 2026-09-11 · 법률 제{num}호"
        kind = "smr_special_law"
    else:
        m = re.search(r"대통령령\s*제\s*([0-9]+)호", text)
        num = m.group(1) if m else "36643"
        title = f"SMR 특별법 시행령 시행 2026-09-11 · 대통령령 제{num}호"
        kind = "smr_special_law"
    return [{"source": source["name"], "title": title, "url": source["url"], "kind": kind}]


_PREV_EXTRACT = j2.base.extract_items


def _extract_v9(source, page_text):
    if source.get("kind") in {"smr_policy_rss", "smr_business_rss", "ismr_license_rss"}:
        return _rss_items(source, page_text)
    if source.get("kind") in {"smr_law_static", "smr_decree_static"}:
        return _static_law_item(source, page_text)
    return _PREV_EXTRACT(source, page_text)


j2.base.extract_items = _extract_v9


def _event_title_ko(event: dict) -> str:
    title = j2.base.norm(event.get("title") or "")
    try:
        return j2._translate_ko(title)
    except Exception:
        if re.search(r"[가-힣]", title) and not j2._BAD_TITLE_RE.search(title):
            return title
        return ""


def _stage_label(kind: str) -> str:
    return {
        "smr_special_law": "법·제도",
        "smr_basic_plan": "기본계획·시행계획",
        "smr_budget": "예산·재원",
        "smr_special_zone": "연구개발 특구",
        "smr_public_private_company": "민관 공동출자·연구조합",
        "smr_fuel_supply": "핵연료 공급망",
        "ismr_licensing": "i-SMR 인허가",
    }.get(kind, "SMR 정책")


def _render_smr_policy_cluster(events: list[dict]) -> str:
    uniq = []
    seen = set()
    for e in events:
        key = ((e.get("title") or "").lower(), e.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    lines = [
        "⚛️ <b>[한국 SMR 특별법·i-SMR 웹감시]</b>",
        "",
        "<b>법 시행 이후 '정책 선언 → 예산·특구·출자·발주' 전환을 추적합니다</b>",
        f"<code>법정기한·재원·인허가·매출연결 | 신규 변화 {len(uniq)}건</code>",
        "",
        "<b>법적 기준선</b>",
        "• <b>특별법:</b> 2026년 9월 11일 시행 · 법률 제21422호",
        "• <b>시행령:</b> 2026년 9월 11일 시행 · 대통령령 제36643호",
        "• <b>기본계획:</b> 5년마다 수립 · 최초 계획은 <b>2027년 9월 11일까지</b>",
        "• <b>최초 시행계획:</b> 최초 기본계획 수립 후 <b>3개월 이내</b>",
        "• <b>2035년 상용화:</b> 정부 i-SMR 정책목표이지 특별법의 법정 의무기한은 아님",
        "",
        "<b>돈이 어디로 배분되는지</b>",
        "• 법 자체에 총예산은 없음 → 기본계획에서 <b>소요재원·재원조달 방안</b>이 처음 숫자로 구체화",
        "• 실증 지원 범위: <b>부지 · 안전 기반시설 · 건설 · 운영 · 실증비용 · 연구시설·장비 · 전문인력</b>",
        "• 사업화 지원: <b>부품 표준화 · 시험연구 기자재 공동구매 · 기술이전·사업화 · 국제공동개발</b>",
        "• 기본계획 의무항목: <b>핵연료 공급망 · 국민수용성 · 인력양성 · 국제협력</b>",
        "",
        "<b>실제 매출로 넘어가는 순서</b>",
        "• <b>기본계획/예산 → 특구·민관 공동출자 회사 → 실증 부지·설비 → 표준설계인가 → 건설허가 → 주기기·EPC 발주 → 운영·정비</b>",
        "",
        "<b>이번 신규 기사·공식자료</b>",
    ]
    shown = 0
    for event in uniq[:12]:
        title = _event_title_ko(event)
        if not title:
            continue
        source = j2.base.norm(event.get("source") or "출처 미상")
        url = event.get("url") or ""
        kind = event.get("kind") or ""
        linked = f"<a href=\"{html.escape(url, quote=True)}\">{html.escape(title)}</a>" if url else html.escape(title)
        lines.append(f"• <b>{html.escape(_stage_label(kind))}</b> | {html.escape(source)} — {linked}")
        shown += 1
    if shown == 0:
        lines.append("• 한국어 검증을 통과한 신규 항목이 없어 원문 송출 보류")

    lines.extend([
        "",
        "<b>핵심 병목·실패모드</b>",
        "• <b>예산:</b> 법만 시행되고 기본계획·연도별 예산이 작으면 상장사 매출 연결이 약해짐",
        "• <b>인허가:</b> 특별법의 개발지원과 원안위 안전심사는 별개 — 표준설계인가·건설허가가 지연될 수 있음",
        "• <b>핵연료:</b> 실증용 연료 공급망이 늦으면 설계가 끝나도 실증 일정이 밀릴 수 있음",
        "• <b>특구·출자:</b> 지역·주주·출자금이 미확정이면 '수혜주'를 직접 사업으로 분류하지 않음",
        "• <b>표준화:</b> 초도호기 부품 표준화·제작수율이 낮으면 반복생산 원가절감이 늦어짐",
        "",
        "<b>다음 확인</b>",
        "• <b>제1차 기본계획 총재원·세부사업 금액 → 특구 지역·면적·지원내용 → 민관 공동출자 회사 주주·출자액 → 핵연료 공급계약 → i-SMR 표준설계인가 일정 → 부산 기장 실증·건설 예산 → 주기기·EPC 실제 발주</b>",
    ])
    return "\n".join(lines).strip()


_PREV_RENDER = j2.base.render_alert


def _render_v9(events, fact_changes):
    smr_events = [e for e in events if e.get("kind") in SMR_POLICY_KINDS]
    rest = [e for e in events if e.get("kind") not in SMR_POLICY_KINDS]
    parts = []
    if smr_events:
        parts.append(_render_smr_policy_cluster(smr_events))
    other = _PREV_RENDER(rest, fact_changes)
    if other:
        parts.append(other)
    return "\n\n──────────\n\n".join(parts).strip()


j2.base.render_alert = _render_v9

if __name__ == "__main__":
    sys.exit(j2.base.main())
