"""Verify the BIS remote-access rule without confusing inspection and publication.

This collector has no delivery or state-writing capability.  The existing policy
lane owns selection, Telegram receipts and acknowledgement.  Historical press
terms never become the facts of the newly published rule.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import unicodedata
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
EASTERN = ZoneInfo("America/New_York")
DOCUMENT = "2026-23529"
RIN = "0694-AK50"
PUBLISHED_API = f"https://www.federalregister.gov/api/v1/documents/{DOCUMENT}.json"
INSPECTION_API = f"https://www.federalregister.gov/api/v1/public-inspection-documents/{DOCUMENT}.json"
INSPECTION_URL = f"https://www.federalregister.gov/public-inspection/{DOCUMENT}/addressing-remote-access-to-advanced-semiconductors"
# Summary and operative §§742.6, 743.10, 744.24 from the verified 2026-11-16
# public-inspection text. Dates are canonicalized relative to publication;
# whitespace/typography are excluded, but scope, thresholds and duties are not.
VERIFIED_MATERIAL_SIGNATURE = 'ac88bc8650019031d482bc7ebf0ed97ba9b5fe9720e9850b93b7efd59f589aa4'
_FAILURES: list[dict] = []


def get_source_failures() -> list[dict]:
    return list(_FAILURES)


def plain(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def official_url(value: str) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme == "https" and parsed.hostname in {
        "www.federalregister.gov", "www.govinfo.gov", "public-inspection.federalregister.gov"
    } and not parsed.username and not parsed.password


def metadata_verified(meta: dict, *, inspection: bool) -> bool:
    agency = " ".join(str(x.get("name", "")) for x in meta.get("agencies", []) if isinstance(x, dict)).lower()
    link = str(meta.get("html_url", ""))
    return bool(
        str(meta.get("document_number")) == DOCUMENT
        and str(meta.get("type", "")).lower() == "rule"
        and "industry and security" in agency
        and plain(str(meta.get("title", ""))).lower() == "addressing remote access to advanced semiconductors"
        and official_url(link) and DOCUMENT in link
        and (("/public-inspection/" in link) == inspection)
    )


def body_verified(raw: str) -> bool:
    body = plain(raw).lower()
    return all(term in body for term in (
        "addressing remote access to advanced semiconductors", "0694-ak50", "261116-0005",
        "bureau of industry and security", "interim final rule", "country group d:5", "macau",
    ))


def material_signature(raw: str, publication: dt.date | None = None) -> str:
    """Fingerprint controlling passages, not isolated words anywhere in the text."""
    body = unicodedata.normalize("NFKC", plain(raw))
    scopes = (
        (r"SUMMARY:", r"DATES:"),
        (r"(?:§|Section)\s*742\.6\s+Regional stability\.", r"PART\s+743\b"),
        (r"(?:§|Section)\s*743\.10\s+Reporting requirements", r"PART\s+744\b"),
        (r"(?:§|Section)\s*744\.24\s+Restrictions on exports", r"PART\s+748\b"),
    )
    sections = []
    for start_pattern, end_pattern in scopes:
        # References in the preamble may repeat a section title. The actual
        # amendment is the last matching title preceding the next CFR part.
        starts = list(re.finditer(start_pattern, body, re.I))
        section = ""
        for start in reversed(starts):
            end = re.search(end_pattern, body[start.end():], re.I)
            if end:
                section = body[start.start():start.end() + end.start()]
                break
        sections.append(section or "MISSING_OPERATIVE_SECTION")

    month = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    calendar_date = rf"(?:{month}\s+\d{{1,2}},\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})"
    def relative_date(match):
        value = match.group(2)
        try:
            actual = dt.date.fromisoformat(value) if re.match(r"\d{4}-", value) else dt.datetime.strptime(value, "%B %d, %Y").date()
        except ValueError:
            return match.group(0)
        if publication:
            delta = (actual - publication).days
            suffix = str(delta) if delta >= 0 else "MINUS" + str(abs(delta))
        else:
            suffix = "UNRESOLVED" + actual.isoformat()
        return match.group(1) + " PUBLICATIONDATEOFFSET" + suffix

    normalized = []
    for section in sections:
        section = re.sub(r"\[INSERT DATE OF PUBLICATION IN (?:THE )?FEDERAL REGISTER\]",
                         "PUBLICATIONDATEOFFSET0", section, flags=re.I)
        section = re.sub(rf"(\bon(?:\s+or\s+after)?\s+)({calendar_date})",
                         relative_date, section, flags=re.I)
        normalized.append(re.sub(r"[^a-z0-9]", "", section.lower()))
    # Catch a later corrective clause retaining old numbers in the preamble,
    # including an added replacement outside the original section boundaries.
    aggregate_values = sorted({str(int(value.replace(",", ""))) for value in re.findall(
        r"(\d[\d,]*)\s+[\"'“”‘’]?aggregate\s+TPP", body, re.I)})
    grace_periods = sorted(set(re.findall(
        r"(?:must|shall)\s+obtain\s+a\s+licen[cs]e\b.{0,80}?\bwith(?:in)?\s+(\d+)\s+days", body, re.I)))
    payload = json.dumps([normalized, aggregate_values, grace_periods], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verified_conditions(raw: str, publication: dt.date | None = None) -> bool:
    """Exact facts require the validated controlling text, not a word checklist."""
    return body_verified(raw) and material_signature(raw, publication) == VERIFIED_MATERIAL_SIGNATURE


def effective_date(raw: str, meta: dict) -> dt.date | None:
    """Resolve DATES only; a proposed publication date or placeholder is insufficient."""
    body = plain(raw)
    match = re.search(r"DATES:\s*(.{0,900}?)(?:ADDRESSES:|Comment due date:|Comments due date:|$)", body, re.I)
    dates = match.group(1) if match else ""
    if not dates or "INSERT DATE" in dates.upper():
        return None
    match = re.search(r"(?:effective(?:\s+date)?[\s:]*|effective\s+on\s+)([A-Z][a-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})", dates, re.I)
    if not match:
        return None
    value = match.group(1)
    try:
        result = dt.date.fromisoformat(value) if re.match(r"\d{4}-", value) else dt.datetime.strptime(value, "%B %d, %Y").date()
    except ValueError:
        return None
    metadata_date = str(meta.get("effective_on") or meta.get("effective_date") or "")[:10]
    if metadata_date and metadata_date != result.isoformat():
        return None
    return result


def make_item(meta: dict, body: str, now: dt.datetime, *, inspection: bool) -> dict | None:
    if not metadata_verified(meta, inspection=inspection) or not body_verified(body):
        return None
    try:
        publication = dt.date.fromisoformat(str(meta.get("publication_date", "")))
        if inspection:
            filed = dt.datetime.fromisoformat(str(meta.get("filed_at", "")).replace("Z", "+00:00"))
            if filed.tzinfo is None or filed > now:
                return None
            observed = filed.astimezone(KST)
        else:
            # U.S. legal dates must not advance simply because it is already
            # tomorrow in Korea.  Metadata must actually be published too.
            if publication > now.astimezone(EASTERN).date():
                return None
            observed = dt.datetime.combine(publication, dt.time(), tzinfo=EASTERN).astimezone(KST)
    except (TypeError, ValueError):
        return None
    effective = None if inspection else effective_date(body, meta)
    active = effective is not None and effective <= now.astimezone(EASTERN).date()
    stage = "public-inspection" if inspection else "effective" if active else "final"
    legal_label = (
        "잠정 최종규칙 공개열람·관보 미게재·효력 발생 확인 전" if inspection else
        "관보 게재·명시된 효력일 도달 확인" if active else
        "관보 게재 확인·효력일 별도 확인"
    )
    signature = material_signature(body, publication)
    detail_ok = signature == VERIFIED_MATERIAL_SIGNATURE
    revision_suffix = "" if detail_ok else "-revision-" + signature[:16]
    bullets = [
        f"문서 {DOCUMENT}·규제 식별번호 {RIN}: {legal_label}.",
        (f"관보 게재 예정일은 {publication.isoformat()}이며, 예정일 도래만으로 게재·발효 처리하지 않습니다."
         if inspection else f"실제 관보 게재일은 {publication.isoformat()}이며, " +
         (f"원문 효력일은 {effective.isoformat()}입니다." if effective else "효력일은 원문 DATES에서 추가 확인해야 합니다.")),
    ]
    if detail_ok:
        bullets += [
            "추가 목적지 수출허가 대상은 인도네시아·말레이시아·싱가포르·태국·브라질 5개국으로, 앞선 보도의 7개국과 다릅니다.",
            "D:5 국가·마카오에 본사나 최종모회사를 둔 기업에 제공되는 총처리성능(TPP) 12,000,000 초과 원격 연산을 대상으로 하며 연결 데이터센터를 합산합니다.",
            "미국 본사·최종모회사 대상의 5개국 목적지 허가 예외에는 제743.10조 보고 조건이 붙고, 상업적 추천시스템 예외에도 용도 확인·정보 제출 조건이 있습니다.",
            "기존 원격 서비스를 계속 제공하려는 대상 데이터센터에는 규칙 효력 발생 후 90일 내 허가 요건이 있으며, 지금 임의의 확정 기한을 만들지 않습니다.",
            "기존 AI Diffusion 규칙의 정식 철회 조항을 포함하며, 2025년 불집행·철회 예고와 구분합니다.",
        ]
    else:
        bullets.append("요약·적용 조항이 검증한 공개열람본과 달라 국가·성능·예외·이행기한의 세부 숫자 재사용을 보류하며 문안 재검증이 필요합니다.")
    event_day = observed.date().isoformat()
    profile = {
        "title": "미 BIS, GPU 원격접근 잠정 최종규칙 공개열람" if inspection else
                 "미 BIS, GPU 원격접근 규칙 관보 게재·효력일 확인" if active else
                 "미 BIS, GPU 원격접근 규칙 관보 게재",
        "core": "RASA 법안과 별도의 BIS 행정규칙으로, 원격 연산·해외 반도체 공급의 허가 조건을 변경하는 문서가 확인됐습니다.",
        "stage": legal_label, "event_date": event_day,
        "event_date_label": "공개열람 등록일(한국시간)" if inspection else "관보 게재일(미국 기준)",
        "actual_bullets": bullets,
        "timeline": "11월 11일 보도 → 11월 16일 BIS 공개 → 공개열람 → 실제 관보 게재·효력일 → 허가·이행기한",
        "scope_note": "행정규칙 공개와 RASA 제정은 별개이며 미국 GPU·중국 연구자 전체의 일괄 사용 금지로 해석하지 않습니다.",
        "next": "관보 정식판·효력일·90일 이행기한, 허가 예외·최종사용자 및 GPU 주문·납기 변화를 확인합니다.",
        "investment": "허가 심사와 고객 확인은 GPU·HBM·데이터센터 장비 주문 및 현금 회수 시점을 바꿀 수 있습니다.",
        "korea": "삼성전자·SK하이닉스 및 서버 부품의 해당 고객 주문 변화는 별도 확인하며 확정 매출로 계산하지 않습니다.",
        "priced_in": "공개열람과 실제 발효·고객 발주 감소를 분리합니다.",
        "counter": "최종 문안 변경·예외·허가 승인 및 중국의 대체 가속기 채택에 따라 영향이 달라집니다.",
        "failure": "허가 지연·고객 우회·범위 변경·중국 대체 가속기 전환이 위험입니다.",
        "impacts": ("돈 버는 능력", "수급", "시간표"),
        "paths": ("공개열람", "관보 게재", "효력·허가", "고객 주문"),
        "sectors": "AI 가속기·HBM·해외 데이터센터·클라우드",
    }
    if not detail_ok:
        profile["title"] = "미 BIS, GPU 원격접근 규칙 문안 변화·세부 조건 확인 보류"
        profile["next"] = "변경된 규칙 원문·정정 여부·적용 조건과 효력일을 다시 확인합니다."
    return {
        "title": str(meta["title"]).strip(), "description": plain(body)[:50000],
        "link": str(meta["html_url"]), "source": "미 연방관보·BIS 원문",
        "published_kst": observed.isoformat(timespec="seconds"), "published_precision": "date" if not inspection else "second",
        "priority": 0, "official_api_verified": True,
        "bis_gpu_remote_stage": f"official-{stage}-{DOCUMENT}{revision_suffix}",
        "bis_rule_document": DOCUMENT, "bis_rule_profile": profile,
        "bis_rule_conditions_verified": detail_ok,
        "bis_rule_material_signature": signature,
        "bis_rule_publication_date": publication.isoformat(),
        "bis_rule_effective_date": effective.isoformat() if effective else None,
    }


def collect_current_bis_items(now: dt.datetime, fetch_text) -> list[dict]:
    _FAILURES.clear()
    errors = []
    for api, inspection in ((PUBLISHED_API, False), (INSPECTION_API, True)):
        try:
            meta = json.loads(fetch_text(api, timeout=8))
            if not isinstance(meta, dict) or not metadata_verified(meta, inspection=inspection):
                raise ValueError("document metadata identity mismatch")
            text_url = str(meta.get("raw_text_url") or "")
            if not official_url(text_url):
                raise ValueError("official full-text URL missing or invalid")
            body = fetch_text(text_url, timeout=9)
            item = make_item(meta, body, now, inspection=inspection)
            if not item:
                raise ValueError("full text, publication date or identity did not verify")
            if inspection:
                publication = dt.date.fromisoformat(item["bis_rule_publication_date"])
                due = dt.datetime.combine(publication, dt.time(9), tzinfo=EASTERN)
                if now.astimezone(EASTERN) >= due:
                    _FAILURES.append({"source": "BIS remote rule official publication", "url": PUBLISHED_API,
                                      "error": "Scheduled publication day 09:00 Eastern has passed, but the published document was not verified. Public-inspection fallback is not publication or effectiveness evidence. " + ", ".join(errors)})
                    item["bis_rule_profile"]["stage"] = "공식 공개열람본 확인·정식 게재 및 효력 확인 보류"
                    item["bis_rule_profile"]["actual_bullets"][0] = f"문서 {DOCUMENT}·규제 식별번호 {RIN}: 공개열람본은 확인했으나 예정일 경과 후 정식 관보 조회는 확인되지 않았습니다."
            if not item["bis_rule_conditions_verified"]:
                _FAILURES.append({"source": "BIS remote rule material conditions", "url": text_url,
                                  "error": "Material conditions differ from validated snapshot; detailed facts withheld."})
            print(f"trusted_policy_news=bis_remote_document_verified document={DOCUMENT} stage={item['bis_gpu_remote_stage']} full_text=true")
            return [item]
        except Exception as exc:
            errors.append(f"{'inspection' if inspection else 'published'}:{type(exc).__name__}")
    _FAILURES.append({"source": "BIS remote-access current rule", "url": INSPECTION_API,
                      "error": "Official document could not be verified; acknowledgement remains pending. " + ", ".join(errors)})
    print("trusted_policy_news=bis_remote_document_unverified acknowledgement_unchanged=true")
    return []
