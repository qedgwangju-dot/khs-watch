#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
STATE_PATH = DATA_DIR / "samsung_wallet_stablecoin_watch_state.json"
PENDING_PATH = OUT_DIR / "samsung_wallet_stablecoin_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "samsung_wallet_stablecoin_telegram.txt"
STATUS_PATH = OUT_DIR / "samsung_wallet_stablecoin_status.md"

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

SAMSUNG_INSIGHTS_URL = (
    "https://insights.samsung.com/2026/07/15/"
    "announcing-the-next-galaxy-unpacked-event-watch-the-livestream-on-july-22/"
)
WORKDAY_JOB_URL = (
    "https://sec.wd3.myworkdayjobs.com/en-US/Samsung_Careers/job/"
    "Senior-Manager--Business-Development--Payments---Samsung-Wallet_R118656"
)
DIGITAL_ASSET_URL = "https://www.digitalasset.works/news/articleView.html?idxno=43115"
KBW_FN_URL = "https://www.fnnews.com/news/202610011830546063"
KBW_NEWSWHO_URL = "https://www.newswhoplus.com/news/articleView.html?idxno=70890"
PATENT_US_URL = "https://patents.justia.com/patent/20260212355"
PATENT_US_CROSSCHECK_URL = "https://www.oepm.es/en/informacion-tecnologica/vigilancia-tecnologica/alertas-tecnologicas/inteligencia-artificial-y-blockchain/blockchain/?id=53150&page=5"
PATENT_KR_URL = "https://patents.google.com/patent/KR20250040467A/en"
PATENT_NEWS_URL = "https://www.digitalasset.works/news/articleView.html?idxno=43408"
PATENT_PUBLICATION = "US20260212355A1"
PATENT_PUBLICATION_DATE = "2026-07-23"
PATENT_PRIORITY_DATE = "2023-09-15"
SOLANA_PARTNER_PR = "https://www.prnewswire.com/news-releases/samsung-partners-with-solana-to-natively-deliver-stablecoins-in-samsung-wallet-to-82-million-us-galaxy-devices-302901200.html"
BASTION_PARTNER_PR = "https://www.streetinsider.com/Globe%2BNewswire/Bastion%2BSelected%2Bas%2BOne%2Bof%2BSamsung%2BWallet%E2%80%99s%2BStablecoin%2BPartners%2C%2BProviding%2BRegulated%2BInfrastructure%2C%2BCustody%2C%2Band%2BCross-Border%2BRemittances/27162288.html"
SUI_PARTNER_PR = "https://www.sui.io/blog/samsung-collaborates-with-sui-to-bring-usdc-to-samsung-wallet-on-82-million-u-s-galaxy-devices"

RSS_URLS = [
    "https://news.google.com/rss/search?q="
    + urllib.parse.quote('"Samsung Wallet" stablecoin')
    + "&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q="
    + urllib.parse.quote("삼성월렛 스테이블코인")
    + "&hl=ko&gl=KR&ceid=KR:ko",
]

MAX_AGE_HOURS = 120


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"seen": {}, "updated_at_kst": ""}
    except Exception:
        return {"seen": {}, "updated_at_kst": ""}


def parse_pubdate(value: str) -> dt.datetime | None:
    value = (value or "").strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
    ):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except Exception:
            pass
    return None


def relevant(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    samsung = any(x in text for x in ("samsung", "삼성"))
    stable = any(x in text for x in ("stablecoin", "stable coin", "스테이블코인"))
    wallet = any(x in text for x in ("wallet", "월렛", "payment", "결제", "remittance", "송금"))
    return samsung and stable and wallet


def rss_candidates(now_utc: dt.datetime) -> list[dict]:
    out: list[dict] = []
    for rss_url in RSS_URLS:
        try:
            root = ET.fromstring(fetch(rss_url))
        except Exception:
            continue
        for item in root.findall(".//item"):
            title = " ".join((item.findtext("title") or "").split())
            link = (item.findtext("link") or "").strip()
            description = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
            description = re.sub(r"\s+", " ", html.unescape(description)).strip()
            published = parse_pubdate(item.findtext("pubDate") or "")
            if not relevant(title, description):
                continue
            if published and (now_utc - published).total_seconds() > MAX_AGE_HOURS * 3600:
                continue
            out.append({
                "title": title,
                "link": link,
                "summary": description[:500],
                "published_utc": published.isoformat() if published else "",
                "source": "Google News RSS",
            })
    return out


def official_context() -> dict:
    result = {
        "samsung_support_confirmed": False,
        "job_stablecoin_confirmed": False,
        "job_fetch_ok": False,
        "article_confirmed": False,
        "kbw_executive_primary_confirmed": False,
        "kbw_executive_crosscheck_confirmed": False,
        "wallet_patent_us_confirmed": False,
        "wallet_patent_us_crosscheck_confirmed": False,
        "wallet_patent_family_confirmed": False,
        "wallet_patent_news_confirmed": False,
        "explicit_reversal_confirmed": False,
        "solana_partner_primary": False,
        "bastion_partner_primary": False,
        "sui_partner_primary": False,
        "pilot_live_confirmed": False,
        "errors": [],
    }

    try:
        raw = fetch(SAMSUNG_INSIGHTS_URL)
        text = clean_text(raw).lower()
        raw_text = html.unescape(raw.decode("utf-8", errors="replace")).lower()
        combined = f"{text} {raw_text}"
        result["samsung_support_confirmed"] = (
            "samsung wallet" in combined
            and re.search(r"stable[\s\-]?coins?", combined) is not None
            and ("support" in combined or "stablecoins" in combined)
        )
        reversal_terms = (
            "will no longer support stablecoins",
            "will not support stablecoins",
            "stablecoin support has been cancelled",
            "stablecoin support is cancelled",
            "stablecoin support has been withdrawn",
        )
        result["explicit_reversal_confirmed"] = any(term in combined for term in reversal_terms)
    except Exception as exc:
        result["errors"].append(f"samsung_insights: {exc}")

    try:
        raw = fetch(WORKDAY_JOB_URL)
        visible = clean_text(raw).lower()
        raw_text = html.unescape(raw.decode("utf-8", errors="replace")).lower()
        combined = re.sub(r"\\u002d", "-", f"{visible} {raw_text}")
        combined = re.sub(r"\\u0026", "&", combined)
        result["job_fetch_ok"] = True
        stable_match = re.search(r"stable[\s\-]?coin", combined) is not None
        samsung_wallet_match = "samsung wallet" in combined
        bd_match = "business development" in combined
        payment_scope_match = any(
            x in combined
            for x in (
                "payment partnerships",
                "payments",
                "partnership agreements",
                "go-to-market",
            )
        )
        requisition_match = "r118656" in combined
        result["job_stablecoin_confirmed"] = bool(
            stable_match
            and samsung_wallet_match
            and bd_match
            and payment_scope_match
            and requisition_match
        )
    except Exception as exc:
        result["errors"].append(f"workday: {exc}")

    try:
        text = clean_text(fetch(DIGITAL_ASSET_URL)).lower()
        result["article_confirmed"] = (
            "삼성" in text
            and "스테이블코인" in text
            and ("채용" in text or "사업개발" in text)
        )
    except Exception as exc:
        result["errors"].append(f"digitalasset: {exc}")

    # KBW2026 milestone: distinguish a direct public statement by the Samsung Wallet
    # payments/ID/blockchain lead from a mere article headline or hiring inference.
    # Require two separately published reports of the same on-stage statement.
    try:
        text = clean_text(fetch(KBW_FN_URL)).lower()
        result["kbw_executive_primary_confirmed"] = bool(
            "백원석" in text
            and "삼성월렛" in text
            and "스테이블코인" in text
            and "기본 기능" in text
            and "지원" in text
            and ("노력" in text or "속도" in text)
        )
    except Exception as exc:
        result["errors"].append(f"kbw_fn: {exc}")

    try:
        text = clean_text(fetch(KBW_NEWSWHO_URL)).lower()
        result["kbw_executive_crosscheck_confirmed"] = bool(
            "백원석" in text
            and "삼성월렛" in text
            and "스테이블코인" in text
            and (
                "직접 지원" in text
                or "네이티브 지원" in text
                or "지원하는 방향" in text
            )
            and ("송금" in text or "결제" in text or "자금" in text)
        )
    except Exception as exc:
        result["errors"].append(f"kbw_newswho: {exc}")

    # Samsung smart-contract wallet patent milestone. This is a wallet-architecture
    # R&D signal only: the patent itself does not establish Samsung Wallet product
    # deployment, stablecoin support, a named issuer/network, pilot, or launch.
    try:
        text = clean_text(fetch(PATENT_US_URL)).lower()
        result["wallet_patent_us_confirmed"] = bool(
            "20260212355" in text
            and "samsung electronics" in text
            and "smart contract" in text
            and "wallet function" in text
            and ("jul 23, 2026" in text or "july 23, 2026" in text)
            and ("mar 13, 2026" in text or "march 13, 2026" in text)
        )
    except Exception as exc:
        result["errors"].append(f"wallet_patent_us: {exc}")

    try:
        text = clean_text(fetch(PATENT_US_CROSSCHECK_URL)).lower()
        result["wallet_patent_us_crosscheck_confirmed"] = bool(
            "20260212355" in text
            and "samsung electronics" in text
            and "smart contract" in text
            and "wallet function" in text
            and ("23/07/2026" in text or "23.07.2026" in text or "23-07-2026" in text)
        )
    except Exception as exc:
        result["errors"].append(f"wallet_patent_us_crosscheck: {exc}")

    try:
        text = clean_text(fetch(PATENT_KR_URL)).lower()
        result["wallet_patent_family_confirmed"] = bool(
            "kr20250040467a" in text
            and ("삼성전자" in text or "samsung electronics" in text)
            and "pct/kr2024/013967" in text
            and "2023-09-15" in text
            and "smart contract" in text
            and "wallet function" in text
        )
    except Exception as exc:
        result["errors"].append(f"wallet_patent_family: {exc}")

    try:
        text = clean_text(fetch(PATENT_NEWS_URL)).lower()
        result["wallet_patent_news_confirmed"] = bool(
            "삼성전자" in text
            and "스마트" in text
            and ("계약" in text or "컨트랙트" in text)
            and ("지갑" in text or "wallet" in text)
            and ("20260212355" in text or "7월23일" in text or "7월 23일" in text)
        )
    except Exception as exc:
        result["errors"].append(f"wallet_patent_news: {exc}")

    # Partner-source primary announcements, separate from Google News snippets.
    # A single syndicated article is never sufficient for a commercial milestone.
    primary_sources = (
        ("solana_partner_primary", SOLANA_PARTNER_PR,
         ("samsung wallet", "solana foundation", "usdc", "october 2026")),
        ("bastion_partner_primary", BASTION_PARTNER_PR,
         ("samsung wallet", "bastion", "stablecoin", "custody", "82 million")),
        ("sui_partner_primary", SUI_PARTNER_PR,
         ("samsung wallet", "sui", "usdc", "82 million")),
    )
    for key, url, required in primary_sources:
        try:
            text = clean_text(fetch(url, timeout=14)).lower()
            result[key] = all(term in text for term in required)
        except Exception as exc:
            result["errors"].append(f"{key}: {exc}")

    return result


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def topic_state(official: dict, candidates: list[dict], previous: dict | None = None) -> dict:
    """Derive durable subject state.

    News/RSS evidence can establish or corroborate a state, but disappearing/aging
    articles must never erase a previously confirmed business state. Downward changes
    require an explicit official reversal, not absence of evidence.
    """
    previous = previous or {}
    evidence_text = " ".join(
        f"{item.get('title', '')} {item.get('summary', '')}" for item in candidates
    ).lower()

    support_now = bool(official.get("samsung_support_confirmed"))
    support_plan = support_now or bool(previous.get("support_plan"))

    job_exists = bool(official.get("job_fetch_ok"))
    report_bd_scope = (
        ("stablecoin" in evidence_text or "stable coin" in evidence_text or "스테이블코인" in evidence_text)
        and (
            "r118656" in evidence_text
            or "사업개발" in evidence_text
            or "business development" in evidence_text
        )
    )
    stablecoin_bd_now = bool(official.get("job_stablecoin_confirmed")) or report_bd_scope
    stablecoin_bd_scope = stablecoin_bd_now or bool(previous.get("stablecoin_bd_scope"))

    executive_now = bool(
        official.get("kbw_executive_primary_confirmed")
        and official.get("kbw_executive_crosscheck_confirmed")
    )
    executive_default_feature_confirmation = (
        executive_now or bool(previous.get("executive_default_feature_confirmation"))
    )

    patent_now = bool(
        official.get("wallet_patent_family_confirmed")
        and (
            official.get("wallet_patent_us_confirmed")
            or official.get("wallet_patent_us_crosscheck_confirmed")
            or official.get("wallet_patent_news_confirmed")
        )
    )
    smart_contract_wallet_patent_confirmed = (
        patent_now or bool(previous.get("smart_contract_wallet_patent_confirmed"))
    )

    # Do not infer a commercial partner from RSS word co-occurrence. Circle is
    # the USDC issuer; that fact alone is not a Samsung/Circle partnership.
    source_names = [
        name for name, key in (
            ("Solana", "solana_partner_primary"),
            ("Bastion", "bastion_partner_primary"),
            ("Sui", "sui_partner_primary"),
        )
        if official.get(key)
    ]
    primary_partner_confirmed = len(source_names) >= 2
    prior_confirmed = bool(previous.get("partner_primary_confirmed"))
    partner_primary_confirmed = primary_partner_confirmed or prior_confirmed
    stablecoin_partner = (
        ", ".join(source_names)
        if primary_partner_confirmed
        else str(previous.get("stablecoin_partner") or "")
    )
    if not stablecoin_partner and partner_primary_confirmed:
        stablecoin_partner = str(previous.get("stablecoin_partner") or "")

    # Announced service launch dates do not constitute a live pilot or rollout.
    detected_pilot = bool(official.get("pilot_live_confirmed"))
    pilot_or_launch = detected_pilot or bool(previous.get("pilot_or_launch"))
    known_primary_sources = source_names or list(previous.get("partner_primary_sources") or [])
    planned_rollout = (
        "2026년 10월 마지막 주 미국 예정(파트너사 발표·실제 출시 미확인)"
        if partner_primary_confirmed else str(previous.get("planned_rollout") or "")
    )

    reversal = bool(official.get("explicit_reversal_confirmed"))
    if reversal:
        status = "공식 철회·취소 확인"
    else:
        status = "진행 중"

    if pilot_or_launch:
        stage = 4
        stage_name = "파일럿·출시 실행"
    elif stablecoin_partner and partner_primary_confirmed:
        stage = 3
        stage_name = "파트너사 공식 발표 교차확인"
    elif stablecoin_bd_scope:
        stage = 2
        stage_name = "사업개발·파트너십 실행"
    elif support_plan:
        stage = 1
        stage_name = "지원 계획 공식화"
    else:
        stage = 0
        stage_name = "확인 전"

    # No regression from evidence loss. Only an explicit official reversal can
    # supersede the achieved stage, and even then we preserve achieved_stage.
    previous_stage = int(previous.get("stage", 0) or 0)
    if not reversal and stage < previous_stage:
        stage = previous_stage
        stage_name = str(previous.get("stage_name") or stage_name)
        support_plan = bool(previous.get("support_plan")) or support_plan
        stablecoin_bd_scope = bool(previous.get("stablecoin_bd_scope")) or stablecoin_bd_scope
        stablecoin_partner = str(previous.get("stablecoin_partner") or stablecoin_partner)
        pilot_or_launch = bool(previous.get("pilot_or_launch")) or pilot_or_launch

    return {
        "topic": "Samsung Wallet stablecoin adoption",
        "stage": stage,
        "stage_name": stage_name,
        "achieved_stage": max(stage, int(previous.get("achieved_stage", previous_stage) or 0)),
        "support_plan": support_plan,
        "job_exists": job_exists,
        "stablecoin_bd_scope": stablecoin_bd_scope,
        "executive_default_feature_confirmation": executive_default_feature_confirmation,
        "smart_contract_wallet_patent_confirmed": smart_contract_wallet_patent_confirmed,
        "wallet_patent_publication": PATENT_PUBLICATION if smart_contract_wallet_patent_confirmed else "",
        "wallet_patent_publication_date": PATENT_PUBLICATION_DATE if smart_contract_wallet_patent_confirmed else "",
        "wallet_patent_priority_date": PATENT_PRIORITY_DATE if smart_contract_wallet_patent_confirmed else "",
        "wallet_patent_direct_stablecoin_link": False,
        "stablecoin_partner": stablecoin_partner,
        "partner_primary_confirmed": partner_primary_confirmed,
        "partner_primary_sources": known_primary_sources,
        "planned_rollout": planned_rollout,
        "samsung_partner_newsroom_confirmed": False,
        "pilot_or_launch": pilot_or_launch,
        "explicit_reversal_confirmed": reversal,
        "status": status,
        "official_job_scope_now": bool(official.get("job_stablecoin_confirmed")),
    }


def state_changed(old_state: dict, new_state: dict) -> tuple[bool, list[str]]:
    changes: list[str] = []
    if not old_state:
        return True, ["기준 상태 생성"]

    old_stage = int(old_state.get("stage", 0) or 0)
    new_stage = int(new_state.get("stage", 0) or 0)
    if new_stage > old_stage:
        changes.append(
            f"단계 상승: {old_state.get('stage_name', '확인 전')} → {new_state.get('stage_name', '확인 전')}"
        )

    old_partner = str(old_state.get("stablecoin_partner") or "")
    new_partner = str(new_state.get("stablecoin_partner") or "")
    if new_partner and new_partner != old_partner:
        changes.append(
            f"스테이블코인 파트너 확인: {old_partner or '미확정'} → {new_partner}"
        )

    if not bool(old_state.get("pilot_or_launch")) and bool(new_state.get("pilot_or_launch")):
        changes.append("파일럿·출시 실행 신호 확인")

    if not bool(old_state.get("support_plan")) and bool(new_state.get("support_plan")):
        changes.append("Samsung Wallet 스테이블코인 지원 계획 공식 확인")

    if (
        not bool(old_state.get("executive_default_feature_confirmation"))
        and bool(new_state.get("executive_default_feature_confirmation"))
    ):
        changes.append(
            "단계 2 강화: Samsung Wallet 담당 그룹장이 KBW2026에서 스테이블코인을 기본 기능으로 지원하는 방향을 공개 확인"
        )

    if (
        not bool(old_state.get("smart_contract_wallet_patent_confirmed"))
        and bool(new_state.get("smart_contract_wallet_patent_confirmed"))
    ):
        changes.append(
            "R&D 인프라 강화: 삼성전자 스마트계약 지갑 특허 US20260212355A1 공개·패밀리 교차확인 · 단계 2 유지"
        )

    if (
        not bool(old_state.get("explicit_reversal_confirmed"))
        and bool(new_state.get("explicit_reversal_confirmed"))
    ):
        changes.append("공식 철회·취소 신호 확인")

    # Never alert on True→False caused by source aging, parser loss, or article expiry.
    return bool(changes), changes


def evidence_links(candidates: list[dict]) -> list[dict]:
    """Keep corroborating sources for the state transition; do not create one alert per article."""
    out: list[dict] = []
    seen: set[str] = set()
    for item in candidates:
        link = str(item.get("link") or "")
        if not link or link in seen:
            continue
        seen.add(link)
        out.append({
            "title": item.get("title") or "",
            "link": link,
            "published_utc": item.get("published_utc") or "",
            "source": item.get("source") or "",
        })
    return out[:8]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)

    now_kst = dt.datetime.now(KST)
    now_utc = now_kst.astimezone(UTC)
    old = load_state()
    old_topic = old.get("topic_state") or {}

    official = official_context()
    candidates = rss_candidates(now_utc)
    current = topic_state(official, candidates, old_topic)
    changed, changes = state_changed(old_topic, current)

    correction_pending = bool(old.get("correction_pending"))
    if correction_pending:
        changed = True
        changes = [
            "정정: 직전 '사업개발 범위 축소' 알림은 기사 만료에 따른 오판",
            "Samsung Careers R118656의 스테이블코인 결제 제휴 업무가 계속 확인돼 단계 2 유지",
        ]

    evidence = evidence_links(candidates)

    pending = {
        "updated_at_kst": now_kst.isoformat(timespec="seconds"),
        "topic_state": current,
        "evidence": evidence,
        "official": official,
        "correction_pending": False,
    }
    PENDING_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if changed:
        lines = [
            "<b>Samsung Wallet 스테이블코인 상태 변화</b>",
            f"<code>{html.escape(now_kst.isoformat(timespec='seconds'))}</code>",
            "",
            "<b>이번 변화</b>",
            *[f"• {html.escape(change)}" for change in changes[:5]],
            "",
            f"<b>현재 단계 {current['stage']} · {html.escape(str(current['stage_name']))}</b>",
            "• 스테이블코인 지원 계획·사업개발: 기존 확인 유지",
        ]
        if current.get("partner_primary_confirmed"):
            partners = html.escape(str(current.get("stablecoin_partner") or ""))
            lines += [
                f"• 상대방 발표에서 확인된 역할: <b>{partners}</b>",
                "• USDC = Circle 발행 토큰. <b>Samsung–Circle 직접 계약은 미확인</b>",
                f"• 일정: {html.escape(str(current.get('planned_rollout') or '미확정'))}",
                "• 삼성 공식 보도자료·제품 배포·실거래: <b>별도 검증 필요</b>",
                "• <b>출시 예정은 실제 출시가 아니며 단계 4 승격 아님</b>",
            ]
        else:
            lines.append("• 결제 파트너 확정: 아직 교차검증되지 않음")

        if current.get("smart_contract_wallet_patent_confirmed"):
            lines.append("• 지갑 R&D: US20260212355A1 확인 · 실제 Wallet 적용 미확정")

        lines += ["", "<b>검증 근거</b>"]
        if official.get("solana_partner_primary"):
            lines.append(f'• <a href="{SOLANA_PARTNER_PR}">Solana Foundation 발표</a>')
        if official.get("bastion_partner_primary"):
            lines.append(f'• <a href="{BASTION_PARTNER_PR}">Bastion 보도자료</a>')
        if official.get("sui_partner_primary"):
            lines.append(f'• <a href="{SUI_PARTNER_PR}">Sui 공식 발표</a>')
        if not any(official.get(k) for k in ("solana_partner_primary", "bastion_partner_primary", "sui_partner_primary")):
            lines += [
                f'• <a href="{WORKDAY_JOB_URL}">Samsung Careers</a>',
                f'• <a href="{KBW_FN_URL}">KBW 담당자 발언</a>',
            ]
        alert_text = "\n".join(lines).strip() + "\n"
        if len(alert_text) >= 3300:
            raise RuntimeError(f"Samsung alert exceeded compact format: {len(alert_text)}")
        ALERT_PATH.write_text(alert_text, encoding="utf-8")

    status = [
        "# Samsung Wallet stablecoin adoption state watch",
        "",
        f"- 조회시각(KST): {now_kst.isoformat(timespec='seconds')}",
        f"- current stage: {current['stage']} / {current['stage_name']}",
        f"- state changed: {changed}",
        f"- changes: {'; '.join(changes) if changes else 'none'}",
        f"- Samsung official support signal: {official['samsung_support_confirmed']}",
        f"- Workday job exists: {official['job_fetch_ok']}",
        f"- stablecoin BD scope: {'확인 유지' if current['stablecoin_bd_scope'] else '미확인'}",
        f"- KBW executive default-feature confirmation: {current.get('executive_default_feature_confirmation', False)}",
        f"- smart-contract wallet patent confirmed: {current.get('smart_contract_wallet_patent_confirmed', False)}",
        f"- patent publication: {current.get('wallet_patent_publication') or 'unconfirmed'}",
        f"- US patent crosscheck: {official.get('wallet_patent_us_confirmed', False) or official.get('wallet_patent_us_crosscheck_confirmed', False)}",
        f"- patent direct stablecoin/Samsung Wallet link: {current.get('wallet_patent_direct_stablecoin_link', False)}",
        f"- partner: {current['stablecoin_partner'] or 'unconfirmed'}",
        f"- partner primary releases: {', '.join(current.get('partner_primary_sources') or []) or 'not verified'}",
        f"- partner crosschecked: {current.get('partner_primary_confirmed', False)}",
        f"- Samsung newsroom directly verified: {current.get('samsung_partner_newsroom_confirmed', False)}",
        f"- planned rollout: {current.get('planned_rollout') or 'unconfirmed'}",
        f"- pilot/live: {current['pilot_or_launch']}",
        f"- evidence count: {len(evidence)}",
        f"- errors: {'; '.join(official['errors']) if official['errors'] else 'none'}",
    ]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")
    print(
        f"samsung_wallet_stablecoin_state_changed={str(changed).lower()} "
        f"stage={current['stage']} evidence={len(evidence)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
