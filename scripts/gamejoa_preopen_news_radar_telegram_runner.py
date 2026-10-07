#!/usr/bin/env python3
"""Telegram-first GAMEJOA preopen radar runner.

This keeps source collection in the strict runner, then renders only the
decision-ready Korean core radar for Telegram.
"""

from __future__ import annotations

import importlib.util
import datetime as dt
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

import gamejoa_market_materiality as market_materiality


STRICT_PATH = Path(__file__).with_name("gamejoa_preopen_news_radar_strict_runner.py")
spec = importlib.util.spec_from_file_location("gamejoa_strict_radar", STRICT_PATH)
strict = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(strict)
base = strict.base
SEEN_PATH = base.ROOT / "data" / "gamejoa_preopen_news_radar_seen.json"
VERIFIED_EVENT_ALIAS_PATH = base.ROOT / "data" / "gamejoa_verified_event_aliases.json"
VERIFIED_CORE_RECEIPTS_PATH = base.ROOT / "data" / "gamejoa_verified_core_receipts.json"
DELIVERY_PATH = base.OUT / "gamejoa_preopen_news_radar_delivery.json"


def load_seen_state() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        payload = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "updated_at_kst": ""}
    if not isinstance(payload, dict):
        return {"seen": {}, "updated_at_kst": ""}
    payload.setdefault("seen", {})
    migrate_seen_title_aliases(payload)
    migrate_seen_verified_event_aliases(payload)
    migrate_seen_verified_core_receipts(payload)
    return payload


def save_seen_state(state: dict, now) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_seen_time(value: str | None):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except Exception:
        return None


def digest_seen(value: str) -> str:
    return hashlib.sha256(base.norm(value).encode("utf-8")).hexdigest()[:24]


def canonical_article_url(value: str) -> str:
    """Keep article-identifying parameters; drop only known tracking fields."""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value
    query = [(key, val) for key, val in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_")
             and not (parsed.hostname in {"www.etoday.co.kr", "etoday.co.kr"}
                      and key.lower() == "trc" and val == "main_list_pick")
             and not (key.lower() == "input" and val == "1195m")
             and not (key.lower() in {"ref", "cp"} and val in {"naver", "nv"})]
    return urllib.parse.urlunsplit(("https", parsed.netloc.lower(), parsed.path,
                                  urllib.parse.urlencode(sorted(query)), ""))


def korean_market_move_theme(alert: dict) -> str:
    title = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "")
    if "코스닥" not in title or not any(term in title for term in ("코스피", "천피", "증시")):
        return ""
    move = re.search(r"코스닥\s*([+-]?\d+(?:\.\d+)?)\s*%", title)
    if not move:
        return ""
    catalysts = [term for term in ("마이크론", "반도체 수출", "엔비디아", "관세", "유가", "환율", "금리") if term in title]
    if not catalysts:
        return ""
    published_day = str(alert.get("published") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_day):
        return ""
    return f"korea_market_move:{published_day}:kosdaq:{move.group(1)}:{'+'.join(catalysts)}"


def korean_bond_demand_theme(alert: dict) -> str:
    title = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "")
    if "수요예측" not in title:
        return ""
    issuer = re.match(r"^\s*([가-힣A-Za-z0-9&·]{2,24})\s*,", title)
    multiple = re.search(r"(?:모집(?:예정액)?\s*)?(\d+(?:\.\d+)?)\s*배", title)
    published_day = str(alert.get("published") or "")[:10]
    if not issuer or not multiple or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_day):
        return ""
    return f"korea_bond_demand:{published_day}:{base.norm(issuer.group(1))}:{multiple.group(1)}"


def korean_joint_ceo_theme(alert: dict) -> str:
    title = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "")
    if "공동대표" not in title:
        return ""
    company = re.match(r"^\s*([가-힣A-Za-z0-9&·]{2,24})\s*,", title)
    names = re.search(r"([가-힣]{2,4})\s*[·ㆍ]\s*([가-힣]{2,4})\s*공동대표", title)
    published_day = str(alert.get("published") or "")[:10]
    if not company or not names or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_day):
        return ""
    people = "+".join(sorted((names.group(1), names.group(2))))
    return f"korea_joint_ceo:{published_day}:{base.norm(company.group(1))}:{people}"


def macro_release_theme(alert: dict) -> str:
    """Merge same-period, same-value releases, not forecasts or revised values."""
    title = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "")
    lowered = title.lower()
    indicators = {
        "pce": ("pce", "개인소비지출"),
        "cpi": ("cpi", "소비자물가"),
        "ppi": ("ppi", "생산자물가"),
    }
    indicator = next((name for name, aliases in indicators.items() if any(
        re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lowered) for alias in aliases
    )), "")
    countries = {
        "us": ("미국", "美", "u.s.", "us "),
        "china": ("중국", "中", "china"),
        "japan": ("일본", "日", "japan"),
        "eurozone": ("유로존", "eurozone"),
        "korea": ("한국", "국내", "korea"),
    }
    country = next((name for name, aliases in countries.items() if any(
        alias.lower() in lowered for alias in aliases
    )), "")
    month_match = re.search(r"(?<!\d)(1[0-2]|[1-9])월", title)
    published = parse_seen_time(str(alert.get("published") or ""))
    rates = {float(value) for value in re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", title)}
    if re.search(r"(?:상승|하락|증가|감소)\s*(?:예상|전망)", title):
        return ""
    if not (indicator and country and month_match and published and len(rates) == 1):
        # A headline can omit Korea or quote a counterfactual second rate.
        # Only a verified released-value core may resolve that ambiguity.
        core = str(alert.get("telegram_core_fact") or "")
        if alert.get("body_verified") and core and re.search(
            r"발표|기록|집계|상승했다|하락했다|rose|fell|reported", core, re.I,
        ) and not re.search(r"예상|전망|내외|것으로|forecast|expect", core, re.I):
            context = " ".join(str(alert.get("source_body") or alert.get("source_abstract") or "").split())[:1200]
            core_country = country
            if not core_country and re.search(r"국가데이터처|통계청|한국은행", f"{core} {context}"):
                core_country = "korea"
            source_month = re.search(
                r"(?<!\d)(1[0-2]|[1-9])월\s*(?:소비자\s*물가|개인소비지출|생산자\s*물가|(?:근원\s*)?(?:cpi|pce|ppi))", context, re.I,
            )
            core_has_month = re.search(r"(?<!\d)(1[0-2]|[1-9])월", core)
            if not core_has_month and source_month:
                core = f"{source_month.group(1)}월 {core}"
            if core_country and not re.search(r"부산|대구|인천|광주|대전|울산|세종|충북|충남|전북|전남|경북|경남|제주", title):
                resolved = {"source_title": f"{core_country} {core}", "published": alert.get("published")}
                return macro_release_theme(resolved)
        return ""
    if not any(term in lowered for term in ("상승", "하락", "발표", "기록", "집계", "↑", "↓", "rose", "fell")):
        return ""
    month = int(month_match.group(1))
    year = published.year - (month > published.month)
    basis = "core" if "근원" in title or "core" in lowered else "headline"
    comparison = "mom" if any(term in lowered for term in ("전월", "전달", "mom")) else "headline"
    rate = format(next(iter(rates)), ".12g")
    return f"macro_release:{country}:{indicator}:{year}-{month:02d}:{basis}:{comparison}:{rate}"


def verified_trade_theme(alert: dict) -> str:
    """Same sourced trade fact and quantities, without merging changed purchases."""
    if not alert.get("body_verified"):
        return ""
    core = str(alert.get("telegram_core_fact") or "")
    body = str(alert.get("source_body") or alert.get("source_abstract") or "")
    day = str(alert.get("published") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or not re.search(r"(?:주식|지분).{0,30}(?:매수|매입|매도)", core):
        return ""
    amounts = sorted(set(re.sub(r"[\s,]", "", value) for value in re.findall(
        r"(\d[\d,]*(?:만\s*\d[\d,]*)?)\s*주(?:를|을)?\s*(?:장내(?:에서)?\s*)?(?:매수|매입|매도|사들)", body,
    )))
    if not amounts:
        return ""
    fact = re.sub(r"(?<=\d)\.(?=\d)", "decimal", core.lower())
    fact = re.sub(r"[^a-z0-9가-힣%+\-]", "", fact)
    return f"verified_trade:{day}:{fact}:{'+'.join(amounts)}"


def canonical_alert_for_seen(alert: dict) -> dict:
    """Overridden by the final renderer so cross-source stories share a key."""
    return alert


def canonical_edition_title(title: str) -> str:
    return re.sub(r"\s*[\[(](?:종합(?:\s*\d+보)?|\d+보|상보|속보)[\])]\s*$", "", title).strip()


def normalized_telegram_core(alert: dict) -> str:
    if not alert.get("body_verified"):
        return ""
    core = base.norm(alert.get("telegram_core_fact"))
    return core if len(core) >= 50 and not core.startswith("공개된 제목에 따르면") else ""


def alert_seen_keys(alert: dict) -> list[str]:
    try:
        canonical = canonical_alert_for_seen(alert)
    except Exception:
        canonical = alert
    keys: list[str] = []

    def add(prefix: str, value: str | None) -> None:
        text = base.norm(value or "")
        if not text:
            return
        keys.append(f"{prefix}:{digest_seen(text)}")

    link = str(canonical.get("link") or alert.get("link") or "")
    if "news.google.com/rss/articles" not in link:
        add("link", link)
        add("link", canonical_article_url(link))
    add(
        "event",
        str(canonical.get("supply_chain_theme") or alert.get("supply_chain_theme") or ""),
    )
    add("event", macro_release_theme(canonical))
    add("event", verified_trade_theme(canonical))
    add("event", market_materiality.source_event_identity(canonical))
    add("fact", market_materiality.verified_source_fact_identity(canonical))
    for fact_key in market_materiality.verified_source_fact_keys(canonical):
        add("source_fact", fact_key)
    add("core", normalized_telegram_core(canonical))
    add("title", str(canonical.get("news") or alert.get("news") or ""))
    add("original", str(canonical.get("original_news") or alert.get("original_news") or ""))
    for value in (canonical.get("news"), canonical.get("source_title"), canonical.get("original_news")):
        add("title", canonical_edition_title(str(value or "")))
    return list(dict.fromkeys(keys))


def migrate_seen_title_aliases(state: dict) -> None:
    """Add canonical title aliases for state written before canonical keys existed."""
    seen = state.setdefault("seen", {})
    for entry in list(seen.values()):
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "")
        if not base.norm(title):
            continue
        alias = f"title:{digest_seen(title)}"
        seen.setdefault(alias, dict(entry))
        seen.setdefault(f"title:{digest_seen(canonical_edition_title(title))}", dict(entry))
        link = str(entry.get("link") or "")
        if link and "news.google.com/rss/articles" not in link:
            seen.setdefault(f"link:{digest_seen(canonical_article_url(link))}", dict(entry))
        source_identity = str(entry.get("source_event_identity") or "") or market_materiality.source_event_identity({"source_title": title})
        if source_identity:
            seen.setdefault(f"event:{digest_seen(source_identity)}", dict(entry))
        fact_identity = str(entry.get("source_fact_identity") or "")
        if fact_identity:
            seen.setdefault(f"fact:{digest_seen(fact_identity)}", dict(entry))
        for fact_key in entry.get("source_fact_keys") or []:
            seen.setdefault(f"source_fact:{digest_seen(fact_key)}", dict(entry))
        market_theme = korean_market_move_theme({
            "source_title": title,
            "published": entry.get("first_seen_kst"),
        })
        if market_theme:
            seen.setdefault(f"event:{digest_seen(market_theme)}", dict(entry))
        bond_theme = korean_bond_demand_theme({
            "source_title": title,
            "published": entry.get("first_seen_kst"),
        })
        if bond_theme:
            seen.setdefault(f"event:{digest_seen(bond_theme)}", dict(entry))
        ceo_theme = korean_joint_ceo_theme({
            "source_title": title,
            "published": entry.get("first_seen_kst"),
        })
        if ceo_theme:
            seen.setdefault(f"event:{digest_seen(ceo_theme)}", dict(entry))
        macro_theme = macro_release_theme({
            "source_title": title,
            "published": entry.get("first_seen_kst"),
        })
        if macro_theme:
            seen.setdefault(f"event:{digest_seen(macro_theme)}", dict(entry))


def migrate_seen_verified_event_aliases(state: dict) -> None:
    """Upgrade historical sent receipts only with audited source-event evidence."""
    if not VERIFIED_EVENT_ALIAS_PATH.exists():
        return
    proofs = json.loads(VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))
    seen = state.setdefault("seen", {})
    for proof in proofs.get("entries", []):
        identity = str(proof.get("source_event_identity") or "")
        published = parse_seen_time(proof.get("source_published_kst"))
        if not (
            (identity.startswith("source_event:v1:us:equity_close:")
             or re.fullmatch(r"source_event:v2:(?:license|odd_lot_rule|merger_agreement|broker_earnings|commercial_order|commercial_delivery|scoped_anonymous_order|construction_order|regulatory_package|industrial_product_milestone|legislative_action|capacity_supply_contract|industrial_adoption|industrial_development_mou|site_development_mou|project_safety_assessment|conditional_remittance|listing_suspension_ruling|capital_participation|research_award|analyst_target|industrial_route_study|conditional_index_outlook|intraday_equity|cumulative_foreign_sales|macro_model_report|issuer_quarterly_earnings):[0-9a-f]{64}", identity)) and published
            and re.fullmatch(r"[0-9a-f]{64}", str(proof.get("source_body_sha256") or ""))
            and (not proof.get('source_body_digest') or re.fullmatch(r'[0-9a-f]{64}', str(proof['source_body_digest'])))
            and proof.get("run_id") and proof.get("message_id")
        ):
            raise ValueError("Invalid verified event-alias evidence")
        # A discovery-side equivalence references another article's receipt;
        # it cannot create sent history for the still-unsent source.
        if 'receipt_source' in proof:
            continue
        for entry in list(seen.values()):
            first_seen = parse_seen_time(entry.get("first_seen_kst")) if isinstance(entry, dict) else None
            if not first_seen or first_seen < published:
                continue
            if canonical_article_url(str(entry.get("link") or "")) != canonical_article_url(proof["link"]):
                continue
            if base.norm(canonical_edition_title(str(entry.get("title") or ""))) != base.norm(canonical_edition_title(proof["source_title"])):
                continue
            if proof.get('source_body_digest') and entry.get('source_body_digest') != proof['source_body_digest']:
                continue
            existing_identity = str(entry.get("source_event_identity") or "")
            if existing_identity and existing_identity != identity:
                continue
            entry["source_event_identity"] = identity
            entry.setdefault("source_published_kst", proof["source_published_kst"])
            seen.setdefault(f"event:{digest_seen(identity)}", {
                **entry, "source_event_identity": identity,
                "source_published_kst": proof["source_published_kst"],
                "event_alias_evidence_run_id": proof["run_id"],
                "event_alias_evidence_message_id": proof["message_id"],
            })


def migrate_seen_verified_core_receipts(state: dict) -> None:
    """Restore a core key only for an independently audited Telegram receipt."""
    if not VERIFIED_CORE_RECEIPTS_PATH.exists():
        return
    proofs = json.loads(VERIFIED_CORE_RECEIPTS_PATH.read_text(encoding="utf-8"))
    seen = state.setdefault("seen", {})
    for proof in proofs.get("entries", []):
        published = parse_seen_time(proof.get("source_published_kst"))
        core = base.norm(proof.get("telegram_core_fact"))
        if not (published and proof.get("run_id") and proof.get("message_id")
                and len(core) >= 50 and core.endswith(".")
                and re.fullmatch(r"[0-9a-f]{64}", str(proof.get("source_body_sha256") or ""))
                and re.fullmatch(r"[0-9a-f]{64}", str(proof.get("source_body_digest") or ""))):
            raise ValueError("Invalid verified core-receipt evidence")
        for entry in list(seen.values()):
            first_seen = parse_seen_time(entry.get("first_seen_kst")) if isinstance(entry, dict) else None
            if not first_seen or first_seen < published:
                continue
            if canonical_article_url(str(entry.get("link") or "")) != canonical_article_url(proof["link"]):
                continue
            if base.norm(canonical_edition_title(str(entry.get("title") or ""))) != base.norm(
                canonical_edition_title(proof["source_title"])
            ):
                continue
            if entry.get("source_body_digest") != proof["source_body_digest"]:
                continue
            seen.setdefault(f"core:{digest_seen(core)}", {
                **entry,
                "core_alias_evidence_run_id": proof["run_id"],
                "core_alias_evidence_message_id": proof["message_id"],
            })


def prune_seen_state(state: dict, now) -> None:
    ttl_days = max(1, int(os.getenv("GAMEJOA_RADAR_SEEN_TTL_DAYS", "14")))
    cutoff = now - dt.timedelta(days=ttl_days)
    seen = state.setdefault("seen", {})
    for key, value in list(seen.items()):
        first_seen = parse_seen_time(value.get("first_seen_kst") if isinstance(value, dict) else None)
        if first_seen and first_seen < cutoff:
            seen.pop(key, None)


def seen_entry_has_lane(entry: object, lane: str) -> bool:
    """Treat pre-lane state as seen everywhere to prevent legacy repeats."""
    if not isinstance(entry, dict):
        return True
    lanes = entry.get("lanes")
    if isinstance(lanes, dict):
        return lane in lanes or "legacy" in lanes
    if isinstance(lanes, list):
        return lane in lanes or "legacy" in lanes
    return True


def recent_seen_event_entries(seen: dict, now, lane: str) -> list[dict]:
    cutoff = now - dt.timedelta(hours=36)
    unique: dict[tuple[str, str, str], dict] = {}
    for entry in seen.values():
        if not isinstance(entry, dict) or (lane != "live" and not seen_entry_has_lane(entry, lane)):
            continue
        if not entry.get("source_body_digest"):
            continue
        last_seen = parse_seen_time(entry.get("last_seen_kst"))
        if not last_seen or last_seen < cutoff or last_seen > now + dt.timedelta(minutes=5):
            continue
        title = str(entry.get("source_title") or "").strip()
        fact = str(entry.get("telegram_core_fact") or "").strip()
        if not title or not fact:
            continue
        key = (base.norm(title), base.norm(fact), str(entry.get("source_published_kst") or ""))
        unique.setdefault(key, entry)
    return sorted(unique.values(), key=lambda row: str(row.get("last_seen_kst") or ""), reverse=True)[:250]


def filter_previously_seen_alerts(
    alerts: list[dict],
    now,
    lane: str = "live",
) -> tuple[list[dict], list[dict]]:
    state = load_seen_state()
    prune_seen_state(state, now)
    seen = state.setdefault("seen", {})
    fresh: list[dict] = []
    skipped: list[dict] = []
    for alert in alerts:
        keys = alert_seen_keys(alert)
        canonical = canonical_alert_for_seen(alert)
        identity = market_materiality.source_event_identity(alert)
        fact_identity = market_materiality.verified_source_fact_identity(canonical)
        body_digest = market_materiality.verified_source_body_digest(canonical)
        verified_fact_keys = market_materiality.verified_source_fact_keys(canonical)
        fact_keys = [f"source_fact:{digest_seen(key)}" for key in verified_fact_keys]
        candidate_core = normalized_telegram_core(canonical)
        # A sourced change of amount/stage may keep the same title or URL.
        # Its structured identity must outrank older coarse title/link keys.
        structured_match_keys = ([f"event:{digest_seen(identity)}"] if identity else
                                 [f"fact:{digest_seen(fact_identity)}"] if fact_identity else [])
        core_match_keys = [key for key in keys if key.startswith("core:")]
        matching_entries = [seen[key] for key in structured_match_keys if key in seen]
        if not structured_match_keys:
            matching_entries = [seen[key] for key in keys if key in seen]
        core_matching_entries = [seen[key] for key in core_match_keys if key in seen]
        coarse_entries = [seen[key] for key in keys if key in seen
                          and key.startswith(("link:", "title:", "original:"))
                          and isinstance(seen[key], dict)]
        if not matching_entries and body_digest:
            # A rule upgrade is not a new event, even when fact kinds change.
            matching_entries = [entry for entry in coarse_entries
                                if entry.get("source_body_digest") == body_digest]
        if not identity and fact_keys and not matching_entries:
            # A shorter syndication may omit a previously sent secondary fact.
            # An added fact must remain fresh; matching just one is insufficient.
            if all(key in seen and (lane == "live" or seen_entry_has_lane(seen[key], lane)) for key in fact_keys):
                matching_entries = [seen[key] for key in fact_keys]
        if (identity or fact_identity) and not matching_entries:
            # Legacy receipts without sufficient event terms still protect
            # their exact URL/title. They cannot prove a material revision.
            matching_entries = [entry for entry in coarse_entries
                                if not entry.get("source_body_digest")
                                and (not entry.get("source_fact_identity")
                                     or canonical_article_url(str(entry.get("link") or ""))
                                     == canonical_article_url(str(canonical.get("link") or "")))
                                and not (entry.get("source_event_identity")
                                         or market_materiality.source_event_identity({"source_title": entry.get("title", "")}))]
        structured_revision = False
        if not matching_entries and coarse_entries:
            candidate_fact_keys = set(verified_fact_keys)
            for entry in coarse_entries:
                entry_event_identity = str(entry.get("source_event_identity") or "")
                entry_fact_identity = str(entry.get("source_fact_identity") or "")
                entry_fact_keys = set(entry.get("source_fact_keys") or [])
                entry_core = base.norm(str(entry.get("telegram_core_fact") or ""))
                core_reflects_revision = bool(candidate_core and entry_core and candidate_core != entry_core)
                if identity and entry_event_identity:
                    if identity != entry_event_identity and core_reflects_revision:
                        structured_revision = True
                        break
                    # A stable event identity is stronger than incidental
                    # extraction differences between two versions.
                    continue
                if (fact_identity and entry_fact_identity and fact_identity != entry_fact_identity
                        and core_reflects_revision):
                    structured_revision = True
                    break
                if (candidate_fact_keys and entry_fact_keys and candidate_fact_keys > entry_fact_keys
                        and core_reflects_revision):
                    structured_revision = True
                    break
        if not matching_entries and not structured_revision:
            # A verified body revision outranks a stale generated summary.
            # Otherwise an identical core remains a useful duplicate receipt
            # for publisher rewrites that lack a common URL or event identity.
            matching_entries = core_matching_entries
        fuzzy_duplicate = False
        if (not matching_entries and not structured_revision
                and body_digest and alert.get("body_verified")):
            candidate_title = str(
                canonical.get("source_title") or canonical.get("original_news") or canonical.get("news") or ""
            )
            candidate_fact = str(canonical.get("telegram_core_fact") or "")
            for entry in recent_seen_event_entries(seen, now, lane):
                if not market_materiality.same_headline_event(
                    candidate_title,
                    str(entry.get("source_title") or ""),
                    candidate_fact,
                    str(entry.get("telegram_core_fact") or ""),
                ):
                    continue
                entry_event_identity = str(entry.get("source_event_identity") or "")
                if identity and entry_event_identity and identity != entry_event_identity:
                    # Similar headlines may describe a later deadline, stage,
                    # counterparty, quantity, or other source-backed revision.
                    if candidate_core != base.norm(str(entry.get("telegram_core_fact") or "")):
                        continue
                fuzzy_duplicate = True
                break
        already_seen = bool(matching_entries) if lane == "live" else any(
            seen_entry_has_lane(entry, lane) for entry in matching_entries
        )
        already_seen = already_seen or fuzzy_duplicate
        if already_seen:
            skipped.append(alert)
            continue
        alert = dict(alert)
        alert["_seen_keys"] = keys
        if lane == "preopen" and matching_entries:
            alert["_preopen_live_seen_bypass"] = True
        fresh.append(alert)
    if skipped:
        print(f"GAMEJOA radar: skipped_seen_alerts={len(skipped)} lane={lane}")
    return fresh, skipped


def filter_alerts_for_run_mode(classified: list[dict], now, live_mode: bool) -> tuple[list[dict], list[dict]]:
    """Apply lane-aware seen-state suppression.

    The 06:30 radar is an overnight digest. It must retain qualifying items
    when an earlier real-time run announced them, but it must not repeat an
    item already sent in an earlier preopen digest. A successful preopen send
    also prevents the next live poll from repeating the same stories.
    """
    if live_mode:
        return filter_previously_seen_alerts(classified, now, "live")
    digest_alerts, skipped = filter_previously_seen_alerts(classified, now, "preopen")
    bypassed = sum(bool(alert.get("_preopen_live_seen_bypass")) for alert in digest_alerts)
    print(f"GAMEJOA radar: preopen_digest_seen_bypass={bypassed}")
    return digest_alerts, skipped


def record_seen_alerts(alerts: list[dict], now) -> None:
    if not alerts:
        return
    state = load_seen_state()
    prune_seen_state(state, now)
    seen = state.setdefault("seen", {})
    lane = "live" if os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live" else "preopen"
    seen_at = now.isoformat(timespec="seconds")
    for alert in alerts:
        keys = list(dict.fromkeys([*(alert.get("_seen_keys") or []), *alert_seen_keys(alert)]))
        for key in keys:
            existing = seen.get(key) if isinstance(seen.get(key), dict) else {}
            raw_lanes = existing.get("lanes")
            if isinstance(raw_lanes, dict):
                lanes = dict(raw_lanes)
            elif isinstance(raw_lanes, list):
                lanes = {name: existing.get("first_seen_kst") or seen_at for name in raw_lanes}
            else:
                lanes = {"legacy": existing.get("first_seen_kst") or seen_at} if existing else {}
            lanes[lane] = seen_at
            seen[key] = {
                **existing,
                "first_seen_kst": existing.get("first_seen_kst") or seen_at,
                "last_seen_kst": seen_at,
                "lanes": lanes,
                "title": alert.get("news") or alert.get("original_news") or "",
                "source_title": alert.get("source_title") or alert.get("original_news") or alert.get("news") or "",
                "telegram_core_fact": alert.get("telegram_core_fact") or "",
                "source": alert.get("publisher") or alert.get("source") or "",
                "link": alert.get("link") or "",
                "source_event_identity": market_materiality.source_event_identity(alert),
                "source_fact_identity": market_materiality.verified_source_fact_identity(canonical_alert_for_seen(alert)),
                "source_fact_keys": market_materiality.verified_source_fact_keys(canonical_alert_for_seen(alert)),
                "source_body_digest": market_materiality.verified_source_body_digest(canonical_alert_for_seen(alert)),
                "source_published_kst": str(alert.get("published") or ""),
            }
    save_seen_state(state, now)


def reset_delivery_status() -> None:
    try:
        DELIVERY_PATH.unlink()
    except FileNotFoundError:
        pass


def delivery_confirmed_sent() -> bool:
    if not DELIVERY_PATH.exists():
        print("GAMEJOA radar: seen_state_not_recorded delivery_status_missing")
        return False
    try:
        payload = json.loads(DELIVERY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"GAMEJOA radar: seen_state_not_recorded delivery_status_unreadable={type(exc).__name__}")
        return False
    status = str(payload.get("status") or "").strip().lower()
    if status != "sent":
        print(f"GAMEJOA radar: seen_state_not_recorded delivery_status={status or 'missing'}")
        return False
    return True


def parse_hhmm(value: str, fallback: tuple[int, int]) -> int:
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", value or "")
    if not match:
        return fallback[0] * 60 + fallback[1]
    hour, minute = int(match.group(1)), int(match.group(2))
    return max(0, min(23, hour)) * 60 + max(0, min(59, minute))


def preopen_send_window_open(now) -> bool:
    if os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live":
        return True
    if os.getenv("ALLOW_OFF_WINDOW_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        return True
    current = now.hour * 60 + now.minute
    start = parse_hhmm(os.getenv("PREOPEN_SEND_WINDOW_START_KST", "05:30"), (5, 30))
    end = parse_hhmm(os.getenv("PREOPEN_SEND_WINDOW_END_KST", "07:30"), (7, 30))
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def strip_news_suffix(title: str) -> str:
    return re.split(r"\s+-\s+", title or "", maxsplit=1)[0].strip()


def ko_place(value: str) -> str:
    return value.strip().replace(", ", "·").replace(" and ", "·")


def ko_local_dc_title(raw_title: str) -> str:
    title = strip_news_suffix(raw_title)
    patterns = [
        (r"^(?P<place>.+?) residents seek (?:a )?fall vote to block big data centers", "{place} 주민, 대형 데이터센터 차단 위한 가을 주민투표 추진"),
        (r"^(?P<place>.+?) City Council working to ban data centers", "{place} 시의회, 데이터센터 금지 추진"),
        (r"^(?P<place>.+?) City Council votes to pass data center moratorium.*", "{place} 시의회, 데이터센터 모라토리엄 통과"),
        (r"^(?P<place>.+?) to vote on (?P<months>\d+)-month pause for data center development", "{place}, 데이터센터 개발 {months}개월 중단안 표결 예정"),
        (r"^(?P<place>.+?) data center development pause approved by city council", "{place}, 시의회가 데이터센터 개발 일시중단 승인"),
        (r"^Metro Planning Commission backs two bills on data centers", "메트로 계획위원회, 데이터센터 관련 법안 2건 지지"),
        (r"^What.?s in Sen\. Brown.?s proposed .Residents First. data center legislation", "브라운 상원의 '주민 우선' 데이터센터 법안 내용 부각"),
    ]
    for pattern, template in patterns:
        match = re.search(pattern, title, re.I)
        if match:
            return template.format(**{k: ko_place(v) for k, v in match.groupdict().items()})
    if re.search(r"moratorium|pause", title, re.I):
        return "미국 지역 데이터센터 모라토리엄·개발 일시중단 움직임 확인"
    if re.search(r"ban|block", title, re.I):
        return "미국 지역 데이터센터 금지·차단 움직임 확인"
    if re.search(r"planning commission|public hearing|ordinance|permit|zoning", title, re.I):
        return "미국 지역 데이터센터 인허가·조례 일정 확인"
    return "미국 지역 데이터센터 규제 뉴스 확인"


def korean_title(alert: dict) -> str:
    original = alert.get("original_news") or alert.get("news") or ""
    sectors = alert.get("sectors") or []
    if alert.get("local_dc_policy"):
        return ko_local_dc_title(original)
    if "데이터센터/전력망/전력기기" in sectors:
        return "데이터센터·전력망 정책/수급 뉴스 확인"
    if "반도체/AI" in sectors:
        return "반도체·AI 밸류체인 고충격 뉴스 확인"
    if "관세/수출통제" in sectors:
        return "미국 관세·수출통제 정책 뉴스 확인"
    if "방산/정유/해운/지정학" in sectors:
        return "지정학·에너지 공급망 뉴스 확인"
    if "바이오/FDA" in sectors:
        return "바이오·FDA 이벤트 뉴스 확인"
    if "한국 직접 영향" in sectors:
        return "한국 기업 직접 영향 뉴스 확인"
    return strip_news_suffix(original)


def normalize_alert(alert: dict) -> dict:
    alert = dict(alert)
    alert["original_news"] = alert.get("original_news") or alert.get("news") or ""
    alert["news"] = korean_title(alert)
    return alert


def source_summary(items: list[dict]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        publisher = item.get("publisher") or "출처 확인 불가"
        counts[publisher] = counts.get(publisher, 0) + 1
    return " / ".join(f"{name} {count}건" if count > 1 else name for name, count in counts.items())


def compact_real_yield(fred: dict, te: dict) -> str:
    if fred.get("value") is None or te.get("value") is None:
        return "FRED/TE 중 일부 확인 불가"
    mismatch = abs(float(fred["value"]) - float(te["value"])) >= 0.03 or str(fred.get("reference")) != str(te.get("reference"))
    state = "지연/불일치" if mismatch else "교차확인"
    return f"{state}: DFII10 {fred['value']:.2f}%({fred.get('reference')}), TE TIPS {te['value']:.2f}%({te.get('reference')})"


def local_dc_cluster(alerts: list[dict]) -> dict | None:
    local_items = [a for a in alerts if a.get("local_dc_policy")]
    if len(local_items) < 2:
        return None
    cluster_seen_keys = list(dict.fromkeys(
        key
        for item in local_items
        for key in (item.get("_seen_keys") or alert_seen_keys(item))
    ))
    examples = [
        {"title": item["news"], "publisher": item.get("publisher") or item.get("source") or "출처 확인 불가", "link": item.get("link") or ""}
        for item in local_items[:4]
    ]
    return {
        "score": max(int(a.get("score", 0)) for a in local_items),
        "importance": "상",
        "news": "미국 지역 데이터센터 금지·모라토리엄 확산",
        "impacts": ["시간표", "할인율"],
        "sectors": ["데이터센터/전력망/전력기기"],
        "interpretation": "지역 조례·주민투표·인허가 보류가 AI 데이터센터 CAPEX의 승인 시간표와 전력망 접속 프리미엄을 건드리는 신호입니다.",
        "counter": "개별 지역 이슈일 수 있어 공식 의사록·조례·투표일 확인 전에는 전국 CAPEX 둔화로 과대해석하지 않습니다.",
        "examples": examples,
        "cluster_count": len(local_items),
        "_seen_keys": cluster_seen_keys,
    }


def display_alerts(alerts: list[dict], limit: int) -> list[dict]:
    cluster = local_dc_cluster(alerts)
    if not cluster:
        return alerts[:limit]
    non_local = [a for a in alerts if not a.get("local_dc_policy")]
    return ([cluster] + non_local[: max(0, limit - 1)])[:limit]


def final_alerts_for_output(alerts: list[dict], limit: int) -> list[dict]:
    """Return the single final list shared by report, JSON, send, and seen state."""
    return display_alerts(alerts, limit)


def unique_alert_candidates(alerts: list[dict]) -> list[dict]:
    """Keep every unseen candidate until the final source and impact gates run."""
    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for alert in alerts:
        key = (
            base.norm(str(alert.get("original_news") or alert.get("news") or "")),
            base.norm(str(alert.get("publisher") or alert.get("source") or "")),
            str(alert.get("published") or "")[:10],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)
    return deduped


def partition_realtime_policy_alerts(alerts: list[dict], live_mode: bool) -> tuple[list[dict], list[dict]]:
    """Keep market-moving policy news in the radar's verified delivery path.

    A topic marker is not evidence that another workflow delivered the event.
    The normal source, impact and seen-state gates still apply to every item.
    """
    return alerts, []


def alert_identity(alert: dict) -> tuple[str, str, str]:
    return (
        base.norm(str(alert.get("original_news") or alert.get("news") or "")),
        base.norm(str(alert.get("publisher") or alert.get("source") or "")),
        str(alert.get("published") or "")[:10],
    )


def selection_diagnostics(
    rows: list[dict],
    notes: list[str],
    classified: list[dict],
    skipped_seen: list[dict],
    candidates: list[dict],
    selected: list[dict],
    live_mode: bool,
) -> dict:
    source_failures = [
        note for note in notes
        if "확인 불가" in note or "HTTPError" in note or "TimeoutError" in note or "URLError" in note
    ]
    detail_coverage = {}
    detail_queue_stats = {}
    for note in notes:
        if note.startswith("Korean business detail queue:"):
            detail_queue_stats = {
                name: int(value) for name, value in re.findall(r"(\w+)=(\d+)", note)
            }
    for note in notes:
        match = re.search(
            r"(?:Korean business detail:|korean_business_detail) attempted=(\d+) verified=(\d+) failed=(\d+) deferred=(\d+)",
            note,
        )
        if match:
            detail_coverage = dict(zip(
                ("attempted", "verified", "failed", "deferred"),
                (int(value) for value in match.groups()),
            ))
            if detail_coverage["failed"]:
                source_failures.append(
                    f"Korean business article body verification failed={detail_coverage['failed']}"
                )
            break
    selected_keys = {alert_identity(alert) for alert in selected}
    market_channels: dict[str, int] = {}
    for alert in selected:
        for channel in alert.get("stock_market_channels") or []:
            market_channels[channel] = market_channels.get(channel, 0) + 1
    excluded = []
    for alert in candidates:
        if alert_identity(alert) in selected_keys:
            continue
        excluded.append({
            "title": alert.get("original_news") or alert.get("news") or "",
            "source": alert.get("publisher") or alert.get("source") or "",
            "reason": alert.get("_exclusion_reason") or alert.get("guardrail_note") or "final_quality_filter",
            "guardrail_note": alert.get("guardrail_note") or "",
            "decision_debug": alert.get("_decision_debug") or {},
            "market_materiality": alert.get("market_materiality") or {},
        })
    return {
        "collected_rows": len(rows),
        "classified_alerts": len(classified),
        "seen_filter_applied": True,
        "seen_filter_scope": "all_lanes" if live_mode else "preopen_lane",
        "preopen_digest_seen_bypass": 0 if live_mode else sum(
            bool(alert.get("_preopen_live_seen_bypass")) for alert in candidates
        ),
        "seen_filtered_alerts": len(skipped_seen),
        "deduped_candidates": len(candidates),
        "selected_alerts": len(selected),
        "stock_market_channels": market_channels,
        "excluded_alerts": excluded,
        "source_failures": source_failures,
        "detail_coverage": detail_coverage,
        "detail_queue": detail_queue_stats,
        "coverage_incomplete": bool(detail_coverage.get("failed") or detail_coverage.get("deferred")),
    }


def compact_alert(alert: dict, idx: int, now) -> str:
    examples = alert.get("examples") or []
    count_suffix = f" ({alert['cluster_count']}건 묶음)" if alert.get("cluster_count") else ""
    lines = [f"{idx}) [{alert['importance']}] {alert['news']}{count_suffix}"]
    if examples:
        lines.append("- 확인: " + " / ".join(item["title"] for item in examples[:4]))
        source_text = source_summary(examples[:4])
    else:
        source_text = alert.get("publisher") or alert.get("source") or "출처 확인 불가"
    lines += [
        f"- 영향: {'·'.join(alert['impacts'])} | 섹터: {', '.join(alert['sectors'])}",
        f"- 해석: {alert['interpretation']}",
        f"- 체크: {alert['counter']}",
        f"- 출처: {source_text} · 조회 {now:%H:%M KST}",
        "",
    ]
    return "\n".join(lines)


def compact_report(alerts: list[dict], fred: dict, te: dict, now) -> str:
    limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "7"))))
    visible = display_alerts(alerts, limit)
    live_mode = os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live"
    if live_mode:
        title = f"📰 실시간 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · {now:%H:%M}"
        empty_line = "실시간 고충격 뉴스 직접 확인 없음"
    else:
        title = f"장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
        comment_title = "💡 06:30 장전 뉴스 코멘트"
        followup_line = "06:50 투자기상도에서 수치·수급·테마와 재확인 필요."
        empty_line = "장전 고충격 뉴스 직접 확인 없음"
    lines = [title, f"선별: 핵심 {len(visible)}건", ""]
    if visible:
        for idx, alert in enumerate(visible, 1):
            lines.append(compact_alert(alert, idx, now))
        changed = "·".join(visible[0]["impacts"])
    else:
        lines += [empty_line, ""]
        changed = "명확한 변화 없음"
    if live_mode:
        lines += ["투자 조언이 아닌 참고용 뉴스 브리핑입니다."]
    else:
        lines += [
            comment_title,
            f"오늘 핵심 변화는 `{changed}`입니다. 한국장에서는 관련 해외 티커 반응과 국내 수급 확산 여부를 먼저 확인합니다.",
            f"할인율: {compact_real_yield(fred, te)}",
            followup_line,
            "",
            "투자 조언이 아닌 참고용 뉴스 브리핑입니다.",
        ]
    return "\n".join(lines).strip() + "\n"


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:base.TELEGRAM_LIMIT], "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        resp.read()
    print("Telegram: sent")


def main() -> int:
    now = base.kst_now()
    rows, notes = strict.collect_items(now)
    classified = [normalize_alert(a) for a in (strict.classify(r, now) for r in rows if base.fresh(r, now)) if a]
    live_mode = os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live"
    classified, routed_policy = partition_realtime_policy_alerts(classified, live_mode)
    if routed_policy:
        print(f"GAMEJOA radar: routed_to_realtime_policy={len(routed_policy)}")
    alerts, skipped_seen = filter_alerts_for_run_mode(classified, now, live_mode)
    # Preserve body-verified direct-watch articles before the score cutoff.
    # These rows are explicitly curated because broad search ranking can bury
    # market-moving follow-up analysis below generic high-score policy items.
    alerts.sort(key=lambda a: (
        0 if a.get("_pinned_direct_article") else 1,
        -a["score"],
        a["published"],
    ))

    pinned_count = sum(bool(a.get("_pinned_direct_article")) for a in classified)
    pinned_fresh_count = sum(bool(a.get("_pinned_direct_article")) for a in alerts)
    print(
        "GAMEJOA radar direct-watch: "
        f"classified={pinned_count} fresh_after_seen={pinned_fresh_count}"
    )

    output_limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "7"))))
    deduped = unique_alert_candidates(alerts)
    deduped.sort(key=lambda a: (-a["score"], a["published"]))
    final_alerts = final_alerts_for_output(deduped, output_limit)
    diagnostics = selection_diagnostics(rows, notes, classified, skipped_seen, deduped, final_alerts, live_mode)
    print(
        "GAMEJOA radar selection: "
        f"rows={diagnostics['collected_rows']} "
        f"classified={diagnostics['classified_alerts']} "
        f"seen_filtered={diagnostics['seen_filtered_alerts']} "
        f"candidates={diagnostics['deduped_candidates']} "
        f"selected={diagnostics['selected_alerts']} "
        f"source_failures={len(diagnostics['source_failures'])}"
    )
    print("GAMEJOA radar market scope: " + json.dumps(
        diagnostics["stock_market_channels"], ensure_ascii=False, sort_keys=True
    ))
    for excluded in diagnostics["excluded_alerts"][:10]:
        print(
            "GAMEJOA radar excluded: "
            f"reason={excluded['reason']} "
            f"guardrail={excluded.get('guardrail_note') or '-'} "
            f"debug={json.dumps(excluded.get('decision_debug') or {}, ensure_ascii=False, default=str)} "
            f"source={excluded['source']} title={excluded['title']}"
        )
    fred, te = base.collect_dfii10(), base.collect_te()
    report = compact_report(final_alerts, fred, te, now)
    if not final_alerts and (diagnostics["source_failures"] or diagnostics["coverage_incomplete"]):
        report = report.replace(
            "실시간 고충격 뉴스 직접 확인 없음",
            "실시간 고충격 뉴스 최종 선별 0건 · 일부 기사 본문 미확인",
        ).replace(
            "장전 고충격 뉴스 직접 확인 없음",
            "장전 고충격 뉴스 최종 선별 0건 · 일부 기사 본문 미확인",
        )

    base.OUT.mkdir(parents=True, exist_ok=True)
    (base.OUT / "gamejoa_preopen_news_radar.md").write_text(report, encoding="utf-8")
    (base.OUT / "gamejoa_preopen_news_radar_title.txt").write_text(report.splitlines()[0] + "\n", encoding="utf-8")
    (base.OUT / "gamejoa_preopen_news_radar.json").write_text(
        json.dumps({"query_time_kst": now.isoformat(timespec="seconds"), "run_mode": "live" if live_mode else "preopen", "alerts": final_alerts, "selection_diagnostics": diagnostics, "skipped_seen_alerts": len(skipped_seen), "source_notes": notes, "fred_dfii10": fred, "tradingeconomics_tips": te}, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    base.print_utf8(report)
    if os.getenv("TELEGRAM_DRY_RUN", "").lower() in {"1", "true", "yes", "y"}:
        print("Telegram: dry run")
        return 0
    if os.getenv("SEND_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        reset_delivery_status()
        send_telegram(report)
        if final_alerts and preopen_send_window_open(now) and delivery_confirmed_sent():
            record_seen_alerts(final_alerts, now)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
