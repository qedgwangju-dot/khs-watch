import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import hormuz_maritime_watch_v4 as watcher


KNOWN_BASELINE_EVENTS = {
    "news:2026-08-30:strike:hormuz:1": {
        "baseline": True,
        "note": "Known pre-monitor single-projectile tanker incident",
    },
    "news:2026-08-31:strike:hormuz:3": {
        "baseline": True,
        "note": "Known UKMTO 124-26 three-projectile tanker incident",
    },
}

KST = ZoneInfo("Asia/Seoul")
LOCATION_KO = {
    "hormuz": "호르무즈 해협",
    "khasab": "오만 카사브 인근",
    "fujairah": "푸자이라 인근",
    "gulf-of-oman": "오만만",
    "oman": "오만 인근 해역",
    "regional": "호르무즈·인접 해역",
}
EVENT_KO = {
    "strike": "유조선·상선 피격/공격",
    "mine": "기뢰 관련 사건",
    "seizure": "나포·강제 승선",
    "explosion": "폭발·화재",
    "restriction": "강제 정지·통항 제한",
}


def calibrated_source_confidence(items):
    sources = {item.get("source") for item in items if item.get("source")}
    strong = sources & watcher.STRONG_SOURCES
    specialists = sources & watcher.SPECIALIST_SOURCES
    authority_mention = any(item.get("mentions_authority") for item in items)
    if not authority_mention:
        return False
    if len(strong) >= 2:
        return True
    if len(sources) >= 2 and strong and specialists:
        return True
    return len(sources) >= 3 and bool(strong)


_original_load_state = watcher.load_state


def calibrated_load_state():
    state, migrating = _original_load_state()
    events = state.setdefault("confirmed_events", {})
    for key, value in KNOWN_BASELINE_EVENTS.items():
        events.setdefault(key, value)
    return state, migrating


def kst_time(iso_value):
    try:
        value = str(iso_value or "").replace("Z", "+00:00")
        return dt.datetime.fromisoformat(value).astimezone(KST).strftime("%m-%d %H:%M KST")
    except Exception:
        return "시각 미확인"


def safe_link(url, label="원문"):
    clean_url = html.escape(str(url or ""), quote=True)
    return f'<a href="{clean_url}">{html.escape(label)}</a>' if clean_url else "원문 링크 미확인"


def translate_title_to_korean(title, fallback):
    title = re.sub(r"\s+-\s+[^-]{2,80}$", "", str(title or "")).strip()
    if not title:
        return fallback
    if len(re.findall(r"[가-힣]", title)) >= 4:
        return title
    try:
        query = urllib.parse.urlencode({
            "client": "gtx",
            "sl": "auto",
            "tl": "ko",
            "dt": "t",
            "q": title,
        })
        request = urllib.request.Request(
            "https://translate.googleapis.com/translate_a/single?" + query,
            headers={"User-Agent": "Mozilla/5.0 KHS-Hormuz-Translator/1.0"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        translated = "".join(part[0] for part in payload[0] if part and part[0]).strip()
        if translated and len(re.findall(r"[가-힣]", translated)) >= 2:
            return translated
    except Exception:
        pass
    return fallback


def official_summary(item):
    text = watcher.clean(item.get("text", ""))
    low = text.lower()
    rows = []
    location = "호르무즈·인접 해역"
    if "khasab" in low:
        location = "오만 카사브 인근"
    elif "strait of hormuz" in low or "hormuz" in low:
        location = "호르무즈 해협"
    elif "fujairah" in low:
        location = "푸자이라 인근"
    rows.append(f"<b>위치</b> · {location}")

    count_match = re.search(r"\b(\d+)\s+(?:unknown\s+|unidentified\s+)?projectiles?\b", low)
    if count_match:
        rows.append(f"<b>사건</b> · 선박이 미상 발사체 {count_match.group(1)}발에 피격")
    elif "projectile" in low or "struck" in low or "attack" in low:
        rows.append("<b>사건</b> · 선박 피격/공격 사건 확인")
    elif "mine" in low:
        rows.append("<b>사건</b> · 기뢰 관련 보안사건 확인")
    else:
        rows.append("<b>사건</b> · 선박 보안사건 확인")

    if "crew are reported safe" in low or "crew are safe" in low or "all crew are reported safe" in low:
        rows.append("<b>인명</b> · 승무원 안전 보고")
    if "no environmental impact" in low or "no reported environmental impact" in low:
        rows.append("<b>환경</b> · 보고된 해양오염 없음")
    return rows


def readable_official_alert(item, news, update):
    lines = [
        "<b>호르무즈 해상보안 공식 업데이트</b>" if update else "<b>호르무즈 해상보안 공식 신규 경보</b>",
        f"<b>UKMTO</b> · {html.escape(str(item.get('warning') or '번호 미확인'))}",
        f"<b>확인</b> · {watcher.now_kst().strftime('%Y-%m-%d %H:%M KST')}",
        "",
    ]
    lines.extend(official_summary(item))
    lines.extend([
        "<b>무기·공격주체</b> · 공식 확인 전 추정하지 않음",
        f"<b>UKMTO 원문</b> · {safe_link(item.get('url'))}",
    ])
    related = [row for row in news if row.get("warning") == item.get("warning")][:3]
    if related:
        lines.extend(["", f"<b>교차검증</b> · 독립 출처 {len(related)}곳"])
        for row in related:
            fallback = "호르무즈 해상보안 사건 관련 보도"
            ko_title = translate_title_to_korean(row.get("title"), fallback)
            lines.append(
                f"• {html.escape(str(row.get('source') or '출처 미확인'))} · "
                f"{html.escape(ko_title)} · {safe_link(row.get('url'))}"
            )
    lines.extend([
        "",
        "<b>주의</b> · 원문에서 무기 종류가 특정되지 않은 경우 <b>미상 발사체</b>로 표기하며, 미사일·포탄·드론으로 임의 단정하지 않습니다.",
    ])
    return "\n".join(lines) + "\n"


def readable_cluster_alert(cluster):
    sources = cluster.get("sources", [])
    event_name = EVENT_KO.get(cluster.get("event_kind"), "해상보안 사건")
    location = LOCATION_KO.get(cluster.get("location"), "호르무즈·인접 해역")
    lines = [
        "<b>호르무즈 해상보안 교차검증 경보</b>",
        f"<b>사건</b> · {event_name}",
        f"<b>위치</b> · {location}",
        f"<b>확인</b> · {watcher.now_kst().strftime('%Y-%m-%d %H:%M KST')}",
    ]
    if cluster.get("warning"):
        lines.append(f"<b>UKMTO 경보</b> · {html.escape(str(cluster.get('warning')))}")
    if cluster.get("projectile_count") is not None:
        lines.append(f"<b>발사체</b> · {cluster.get('projectile_count')}발")
    lines.extend([
        f"<b>검증</b> · 독립 신뢰출처 {len(sources)}곳 교차 일치",
        "",
        "<b>확인 출처</b>",
    ])
    for row in sources[:4]:
        fallback = f"{location} {event_name} 관련 보도"
        ko_title = translate_title_to_korean(row.get("title"), fallback)
        lines.append(
            f"• {html.escape(str(row.get('source') or '출처 미확인'))} · "
            f"{kst_time(row.get('published_utc'))}\n"
            f"  {html.escape(ko_title)} · {safe_link(row.get('url'))}"
        )
    lines.extend([
        "",
        "<b>판정 기준</b> · UKMTO 직접 원문을 읽지 못한 경우에만 복수 독립 출처가 같은 사건을 확인했을 때 보조 경보로 송출",
        "<b>주의</b> · 원문에서 무기 종류가 특정되지 않은 경우 <b>미상 발사체</b>로 유지하며 공격주체·미사일·포탄·드론은 공식 확인 전 단정하지 않습니다.",
    ])
    return "\n".join(lines) + "\n"



# v5: 공식 UKMTO 직접탐지와 '같은 사건' 교차검증을 보강한다.
watcher.STATE_VERSION = 5
UKMTO_DIRECT_PAGES = (
    "https://www.ukmto.org/",
    "https://www.ukmto.org/recent-incidents",
    "https://www.ukmto.org/ukmto-products/warnings",
)
_original_official_scan = watcher.official_scan
_original_news_scan = watcher.news_scan

SOURCE_DOMAINS = {
    "Reuters": "reuters.com",
    "Associated Press": "apnews.com",
    "AP News": "apnews.com",
    "Anadolu Ajansı": "aa.com.tr",
    "Anadolu Agency": "aa.com.tr",
    "Arab News": "arabnews.com",
    "Gulf News": "gulfnews.com",
    "The Maritime Executive": "maritime-executive.com",
    "Lloyd’s List": "lloydslist.com",
    "Lloyd's List": "lloydslist.com",
    "TradeWinds": "tradewindsnews.com",
    "RFE/RL": "rferl.org",
    "Radio Free Europe/Radio Liberty": "rferl.org",
    "Oman News Agency": "omannews.gov.om",
    "U.S. Central Command": "centcom.mil",
    "CENTCOM": "centcom.mil",
}


def _bing_rss(query, news=False):
    base = "https://www.bing.com/news/search" if news else "https://www.bing.com/search"
    url = base + "?" + urllib.parse.urlencode({"q": query, "format": "rss"})
    body, _, _ = watcher.fetch(url, "application/rss+xml,application/xml,text/xml,*/*")
    root = __import__("xml.etree.ElementTree", fromlist=["ElementTree"]).fromstring(body)
    rows = []
    for item in root.findall(".//item"):
        rows.append({
            "title": watcher.clean(item.findtext("title") or ""),
            "url": (item.findtext("link") or "").strip(),
            "description": watcher.clean(item.findtext("description") or ""),
        })
    return rows


def _strip_source_suffix(title, source):
    value = str(title or "").strip()
    suffix = " - " + str(source or "").strip()
    if suffix.strip() != "-" and value.lower().endswith(suffix.lower()):
        value = value[:-len(suffix)].rstrip()
    return value


def _resolve_direct_publisher_url(item):
    current = str(item.get("url") or "")
    source = str(item.get("source") or "")
    domain = SOURCE_DOMAINS.get(source)
    if not domain:
        return current
    if domain in urllib.parse.urlparse(current).netloc.lower():
        return current

    if "news.google.com/" in current:
        try:
            from googlenewsdecoder import gnewsdecoder
            decoded = gnewsdecoder(current, timeout=12.0)
            if isinstance(decoded, dict) and decoded.get("success"):
                link = str(decoded.get("decoded_url") or "")
                if domain in urllib.parse.urlparse(link).netloc.lower():
                    return link
        except Exception:
            pass

    title = _strip_source_suffix(item.get("title"), source)
    queries = [
        f'site:{domain} "{title}"',
        f'site:{domain} {title[:140]}',
    ]
    for query in queries:
        try:
            for hit in _bing_rss(query, news=False):
                link = hit.get("url") or ""
                if domain in urllib.parse.urlparse(link).netloc.lower():
                    return link
        except Exception:
            continue
    return current


def _official_index_max_warning():
    """공식 UKMTO 도메인의 검색 색인에서 최신 경보번호 힌트만 얻는다.

    이 값은 직접원문으로 승격하지 않고, 다음 공식 PDF 후보 번호를 찾는 데만 사용한다.
    """
    max_no = 0
    hints = []
    for query in (
        'site:ukmto.org "UKMTO #" "Strait of Hormuz"',
        'site:ukmto.org "UKMTO #" tanker projectile',
        'site:ukmto.org "UKMTO WARNING" Hormuz',
    ):
        try:
            hits = _bing_rss(query, news=False)
        except Exception:
            continue
        for hit in hits:
            text = " ".join([hit.get("title") or "", hit.get("description") or "", hit.get("url") or ""])
            for m in re.finditer(r"UKMTO\s+#?(\d{2,3})|WARNING[_\s-]+(\d{2,3})[-_]26", text, flags=re.I):
                number = int(m.group(1) or m.group(2))
                max_no = max(max_no, number)
                date_match = re.search(
                    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+2026\b",
                    text,
                    flags=re.I,
                )
                hints.append((number, date_match.group(0) if date_match else None))
    return max_no, hints


def _decode_html(body):
    return body.decode("utf-8", errors="replace")


def _official_page_rows(url):
    rows = {}
    errors = []
    links = []
    try:
        body, _, final_url = watcher.fetch(url, "text/html,application/xhtml+xml,*/*")
        raw = _decode_html(body)
        text = watcher.clean(raw)
        matches = list(re.finditer(
            r"(Attack|Advisory|Hijack|Suspicious Activity)\s+UKMTO\s+#?(\d{2,3})",
            text,
            flags=re.I,
        ))
        for idx, match in enumerate(matches):
            number = int(match.group(2))
            end = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(text), match.start() + 2200)
            snippet = watcher.clean(text[match.start():end])[:2200]
            no = f"{number:03d}-26"
            key = f"ukmto-page:{no}:{watcher.digest(snippet)}"
            rows[key] = {
                "key": key,
                "warning": no,
                "url": final_url,
                "text": snippet,
                "relevant": watcher.relevant(snippet),
                "lane": "official-direct-page",
            }

        for href in re.findall(r'href=["\']([^"\']+)["\']', raw, flags=re.I):
            href = html.unescape(href)
            absolute = urllib.parse.urljoin(final_url, href)
            low = absolute.lower()
            if "ukmto" in low and ("warning" in low or "/products/" in low) and (".pdf" in low or "ukmto_warning" in low):
                links.append(absolute)
    except Exception as exc:
        errors.append(f"{url}: {type(exc).__name__}: {exc}")
    return list(rows.values()), list(dict.fromkeys(links)), errors


def robust_official_scan(highest):
    rows = {}
    errors = []
    max_seen = highest
    page_ok = False
    pdf_links = []

    for page in UKMTO_DIRECT_PAGES:
        page_rows, links, page_errors = _official_page_rows(page)
        if page_rows or not page_errors:
            page_ok = True
        errors.extend(page_errors)
        pdf_links.extend(links)
        for item in page_rows:
            no_int = watcher.warning_int(item.get("warning"))
            if no_int:
                max_seen = max(max_seen, no_int)
            rows[item["key"]] = item

    # 공식 페이지에 노출된 PDF 링크를 직접 읽는다. 최신 링크를 우선하며 과거 전체를 무차별 조회하지 않는다.
    def link_no(url):
        no = watcher.warning_no(url.replace("_", "-"))
        return watcher.warning_int(no)

    pdf_links = sorted(set(pdf_links), key=link_no, reverse=True)
    for url in pdf_links[:40]:
        try:
            text, final_url = watcher.fetch_source(url)
        except Exception:
            continue
        no = watcher.warning_no(text) or watcher.warning_no(final_url.replace("_", "-"))
        if not no or "ukmto" not in watcher.lowered(text):
            continue
        no_int = watcher.warning_int(no)
        max_seen = max(max_seen, no_int)
        key = f"ukmto:{no}:{watcher.digest(text)}"
        rows[key] = {
            "key": key,
            "warning": no,
            "url": final_url,
            "text": text,
            "relevant": watcher.relevant(text),
            "lane": "official-direct-pdf",
        }

    # UKMTO 공식 도메인의 검색색인은 직접원문으로 사용하지 않고,
    # 최신 경보번호를 찾아 다음 직접 PDF 후보를 좁히는 용도로만 사용한다.
    index_max, _ = _official_index_max_warning()
    max_seen = max(max_seen, index_max)

    # 기존 guessed-PDF 경로는 마지막 보조수단으로 유지한다.
    # index_max가 147이면 148번부터 당일/전일 공식 PDF를 직접 시도한다.
    legacy, legacy_max, legacy_errors, legacy_ok = _original_official_scan(max_seen)
    page_ok = page_ok or legacy_ok
    errors.extend(legacy_errors)
    max_seen = max(max_seen, legacy_max)
    for item in legacy:
        rows[item["key"]] = item
    return list(rows.values()), max_seen, errors, page_ok


def _extract_incident_details(text):
    low = watcher.lowered(text)
    details = set()

    time_match = re.search(r"\b([0-2]?\d[:.]?\d{2})\s*(?:gmt|utc)\b", low)
    if time_match:
        details.add("time:" + re.sub(r"\D", "", time_match.group(1)).zfill(4))

    nm_match = re.search(
        r"\b(\d{1,3})\s*(?:nautical\s+miles?|nm)\s*(east|west|north|south|northeast|northwest|southeast|southwest)?",
        low,
    )
    if nm_match:
        direction = (nm_match.group(2) or "").strip()
        details.add(f"distance:{nm_match.group(1)}:{direction}")

    for token, terms in {
        "outbound": ("outbound", "outbound transit"),
        "inbound": ("inbound", "inbound transit"),
        "fire": ("small fire", "caught fire", "fire onboard", "fire on board", "resulting in a fire"),
        "blackout": ("blackout", "loss of power", "power loss"),
        "crew_safe": ("crew were safe", "crew are safe", "all crew", "no casualties", "no casualty"),
        "no_env": ("no environmental impact", "no environmental effects", "no pollution"),
    }.items():
        if any(term in low for term in terms):
            details.add(token)
    return details


def _enrich_news_item(item):
    row = dict(item)
    row["origin_source"] = row.get("source")
    row["article_text"] = ""
    row["resolved_url"] = row.get("url")
    try:
        direct_url = _resolve_direct_publisher_url(row)
        text, final_url = watcher.fetch_source(direct_url)
        text = watcher.clean(text)[:80_000]
        if text:
            row["article_text"] = text
            row["resolved_url"] = final_url
            top = text[:5000].lower()
            if row.get("source") == "Arab News" and (
                "associated press" in top or re.search(r"\bap\b", top)
            ):
                row["origin_source"] = "Associated Press"
    except Exception:
        pass

    combined = " ".join([
        str(row.get("title") or ""),
        str(row.get("description") or ""),
        str(row.get("article_text") or ""),
    ])
    row["event_kind"] = watcher.classify_event(combined) or row.get("event_kind")
    row["projectile_count"] = watcher.projectile_count(combined)
    row["location"] = watcher.location_bucket(combined)
    row["mentions_authority"] = any(
        term in watcher.lowered(combined)
        for term in ("ukmto", "uk maritime agency", "uk maritime", "united kingdom maritime trade operations", "centcom", "u.s. central command")
    )
    row["incident_details"] = sorted(_extract_incident_details(combined))
    return row


def robust_news_scan():
    news, errors, samples = _original_news_scan()
    enriched = [_enrich_news_item(item) for item in news]
    return enriched, errors, samples


def _identity(item):
    return item.get("origin_source") or item.get("source") or ""


def strict_source_confidence(items):
    identities = {_identity(item) for item in items if _identity(item)}
    if len(identities) < 2:
        return False
    if not any(item.get("mentions_authority") for item in items):
        return False

    primary = identities & watcher.PRIMARY_SOURCES
    strong = identities & watcher.STRONG_SOURCES
    specialists = identities & watcher.SPECIALIST_SOURCES
    shared = set.intersection(*[set(item.get("incident_details") or []) for item in items]) if items else set()
    strong_shared = {x for x in shared if x.startswith("time:") or x.startswith("distance:") or x in {"outbound", "inbound", "fire", "blackout", "crew_safe", "no_env"}}

    # 1차 통신사+독립 강한 출처, 또는 강한 출처 2곳이면 세부사건 앵커 1개 이상 필요.
    if primary and len(strong) >= 2 and strong_shared:
        return True
    if len(strong) >= 2 and strong_shared:
        return True

    # 전문매체 조합은 오보/재전재 위험 때문에 같은 사건의 세부 앵커 2개 이상을 요구한다.
    if strong and specialists and len(strong_shared) >= 2:
        return True
    return False


def strict_compatible(a, b):
    if a.get("event_kind") != b.get("event_kind"):
        return False
    loc_a, loc_b = a.get("location"), b.get("location")
    if loc_a != loc_b and {loc_a, loc_b} not in ({"khasab", "hormuz"}, {"oman", "hormuz"}):
        return False

    warning_a, warning_b = a.get("warning"), b.get("warning")
    if warning_a and warning_b:
        return warning_a == warning_b

    details_a = set(a.get("incident_details") or [])
    details_b = set(b.get("incident_details") or [])
    for prefix in ("time:", "distance:"):
        va = {x for x in details_a if x.startswith(prefix)}
        vb = {x for x in details_b if x.startswith(prefix)}
        if va and vb and va.isdisjoint(vb):
            return False

    count_a, count_b = a.get("projectile_count"), b.get("projectile_count")
    if count_a is not None and count_b is not None and count_a != count_b:
        return False

    shared = details_a & details_b
    hard_shared = {
        x for x in shared
        if x.startswith("time:") or x.startswith("distance:") or x in {"outbound", "inbound", "fire", "blackout", "crew_safe", "no_env"}
    }
    return bool(hard_shared)


def strict_clusters(news):
    ordered = sorted(news, key=lambda row: row.get("published_epoch", 0))
    clusters = {}
    window = watcher.CLUSTER_WINDOW_HOURS * 3600
    for anchor in ordered:
        rows = [
            row for row in ordered
            if 0 <= row.get("published_epoch", 0) - anchor.get("published_epoch", 0) <= window
            and strict_compatible(anchor, row)
        ]
        unique = {}
        for row in rows:
            unique.setdefault(_identity(row), row)
        rows = list(unique.values())
        if not strict_source_confidence(rows):
            continue

        warnings = [row.get("warning") for row in rows if row.get("warning")]
        warning = max(warnings, key=watcher.warning_int) if warnings else None

        # 발사체 수는 최소 2개 독립 원천이 같은 수량을 직접 뒷받침할 때만 확정 표시한다.
        count_support = {}
        for row in rows:
            count = row.get("projectile_count")
            if count is not None:
                count_support.setdefault(count, set()).add(_identity(row))
        count = None
        count_sources = 0
        for candidate, identities in count_support.items():
            if len(identities) >= 2 and len(identities) > count_sources:
                count = candidate
                count_sources = len(identities)

        location = "khasab" if any(row.get("location") == "khasab" for row in rows) else anchor.get("location")
        day = dt.datetime.fromtimestamp(anchor["published_epoch"], dt.timezone.utc).strftime("%Y-%m-%d")
        event_key = f"warning:{warning}" if warning else f"news:{day}:{anchor.get('event_kind')}:{location}:{count if count is not None else 'x'}"

        shared_details = set.intersection(*[set(row.get("incident_details") or []) for row in rows]) if rows else set()
        candidate = {
            "event_key": event_key,
            "warning": warning,
            "event_kind": anchor.get("event_kind"),
            "location": location,
            "projectile_count": count,
            "projectile_count_sources": count_sources,
            "confirmed_details": sorted(shared_details),
            "first_epoch": min(row["published_epoch"] for row in rows),
            "last_epoch": max(row["published_epoch"] for row in rows),
            "sources": sorted(rows, key=lambda row: (0 if _identity(row) in watcher.PRIMARY_SOURCES else 1, -row.get("published_epoch", 0))),
        }
        old = clusters.get(event_key)
        if old is None or len(candidate["sources"]) > len(old["sources"]):
            clusters[event_key] = candidate
    return list(clusters.values())


def readable_cluster_alert_v5(cluster):
    sources = cluster.get("sources", [])
    event_name = EVENT_KO.get(cluster.get("event_kind"), "해상보안 사건")
    location = LOCATION_KO.get(cluster.get("location"), "호르무즈·인접 해역")
    identities = {_identity(row) for row in sources if _identity(row)}
    lines = [
        "<b>호르무즈 해상보안 교차검증 경보</b>",
        f"<b>사건</b> · {event_name}",
        f"<b>위치</b> · {location}",
        f"<b>확인</b> · {watcher.now_kst().strftime('%Y-%m-%d %H:%M KST')}",
    ]
    if cluster.get("warning"):
        lines.append(f"<b>UKMTO 경보</b> · {html.escape(str(cluster.get('warning')))}")
    if cluster.get("projectile_count") is not None:
        lines.append(
            f"<b>발사체</b> · {cluster.get('projectile_count')}발 "
            f"(독립 원천 {cluster.get('projectile_count_sources', 0)}곳 수량 일치)"
        )

    confirmed_details = set(cluster.get("confirmed_details") or [])
    detail_labels = []
    if "outbound" in confirmed_details:
        detail_labels.append("출항 방향 통항 중")
    if "inbound" in confirmed_details:
        detail_labels.append("입항 방향 통항 중")
    if "fire" in confirmed_details:
        detail_labels.append("화재")
    if "blackout" in confirmed_details:
        detail_labels.append("정전")
    if "crew_safe" in confirmed_details:
        detail_labels.append("승무원 안전/사상자 없음")
    if "no_env" in confirmed_details:
        detail_labels.append("환경 피해 보고 없음")
    if detail_labels:
        lines.append("<b>세부 일치</b> · " + " · ".join(detail_labels))

    lines.extend([
        f"<b>검증</b> · 독립 원천 {len(identities)}곳 교차 일치",
        "",
        "<b>확인 출처</b>",
    ])
    for row in sources[:4]:
        fallback = f"{location} {event_name} 관련 보도"
        ko_title = translate_title_to_korean(row.get("title"), fallback)
        source = str(row.get("source") or "출처 미확인")
        origin = str(row.get("origin_source") or source)
        label = source if origin == source else f"{origin} / {source} 재게시"
        lines.append(
            f"• {html.escape(label)} · {kst_time(row.get('published_utc'))}\n"
            f"  {html.escape(ko_title)} · {safe_link(row.get('resolved_url') or row.get('url'))}"
        )
    lines.extend([
        "",
        "<b>판정 기준</b> · UKMTO 직접 원문이 탐지되지 않은 경우에만, 서로 독립된 원천이 사건 세부정보까지 일치할 때 보조 경보로 송출",
        "<b>주의</b> · 원문에서 무기 종류가 특정되지 않은 경우 <b>미상 발사체</b>로 유지하며 공격주체·미사일·포탄·드론은 공식 확인 전 단정하지 않습니다.",
    ])
    return "\n".join(lines) + "\n"


watcher.official_scan = robust_official_scan
watcher.news_scan = robust_news_scan
watcher.source_confidence = strict_source_confidence
watcher.compatible = strict_compatible
watcher.build_confirmed_clusters = strict_clusters
watcher.load_state = calibrated_load_state
watcher.build_official_alert = readable_official_alert
watcher.build_cluster_alert = readable_cluster_alert_v5


if __name__ == "__main__":
    raise SystemExit(watcher.main())
