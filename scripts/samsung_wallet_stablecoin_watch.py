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
        "errors": [],
    }

    try:
        text = clean_text(fetch(SAMSUNG_INSIGHTS_URL)).lower()
        result["samsung_support_confirmed"] = (
            "samsung wallet" in text
            and "stablecoin" in text
            and ("support" in text or "stablecoins" in text)
        )
    except Exception as exc:
        result["errors"].append(f"samsung_insights: {exc}")

    try:
        text = clean_text(fetch(WORKDAY_JOB_URL)).lower()
        result["job_fetch_ok"] = True
        result["job_stablecoin_confirmed"] = (
            "stablecoin" in text
            and "samsung wallet" in text
            and any(x in text for x in ("business development", "payments", "partnership"))
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

    return result


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def topic_state(official: dict, candidates: list[dict]) -> dict:
    """Derive one subject/event state. Articles are evidence, never alert objects."""
    evidence_text = " ".join(
        f"{item.get('title', '')} {item.get('summary', '')}" for item in candidates
    ).lower()

    support_plan = bool(official.get("samsung_support_confirmed"))
    job_exists = bool(official.get("job_fetch_ok"))
    stablecoin_bd_scope = bool(official.get("job_stablecoin_confirmed")) or (
        job_exists
        and (
            ("stablecoin" in evidence_text or "스테이블코인" in evidence_text)
            and ("r118656" in evidence_text or "사업개발" in evidence_text or "business development" in evidence_text)
        )
    )

    # Do not infer a stablecoin partner merely because Galaxy Card uses Barclays/Visa.
    stablecoin_partner = ""
    partner_patterns = [
        ("Circle", ("circle", "usdc")),
        ("Tether", ("tether", "usdt")),
        ("PayPal", ("paypal", "pyusd")),
        ("Stripe", ("stripe",)),
        ("Visa", ("visa",)),
        ("Mastercard", ("mastercard",)),
    ]
    launch_terms = ("launch", "launched", "live", "pilot", "rollout", "출시", "상용화", "파일럿", "도입")
    stable_terms = ("stablecoin", "stable coin", "스테이블코인")
    for name, aliases in partner_patterns:
        if any(alias in evidence_text for alias in aliases) and any(term in evidence_text for term in stable_terms):
            # Partner is only promoted when the same evidence also contains an execution term.
            if any(term in evidence_text for term in launch_terms):
                stablecoin_partner = name
                break

    pilot_or_launch = (
        any(term in evidence_text for term in stable_terms)
        and any(term in evidence_text for term in launch_terms)
        and ("samsung wallet" in evidence_text or "삼성월렛" in evidence_text)
    )

    if pilot_or_launch:
        stage = 4
        stage_name = "파일럿·출시 실행"
    elif stablecoin_partner:
        stage = 3
        stage_name = "스테이블코인 파트너 구체화"
    elif stablecoin_bd_scope:
        stage = 2
        stage_name = "사업개발·파트너십 실행"
    elif support_plan:
        stage = 1
        stage_name = "지원 계획 공식화"
    else:
        stage = 0
        stage_name = "확인 전"

    return {
        "topic": "Samsung Wallet stablecoin adoption",
        "stage": stage,
        "stage_name": stage_name,
        "support_plan": support_plan,
        "job_exists": job_exists,
        "stablecoin_bd_scope": stablecoin_bd_scope,
        "stablecoin_partner": stablecoin_partner,
        "pilot_or_launch": pilot_or_launch,
    }


def state_changed(old_state: dict, new_state: dict) -> tuple[bool, list[str]]:
    changes: list[str] = []
    if not old_state:
        return True, ["기준 상태 생성"]
    if int(new_state.get("stage", 0)) > int(old_state.get("stage", 0)):
        changes.append(
            f"단계 상승: {old_state.get('stage_name', '확인 전')} → {new_state.get('stage_name', '확인 전')}"
        )
    for field, label in (
        ("stablecoin_partner", "스테이블코인 파트너"),
        ("pilot_or_launch", "파일럿·출시 상태"),
        ("support_plan", "지원 계획"),
        ("stablecoin_bd_scope", "사업개발 범위"),
    ):
        if new_state.get(field) != old_state.get(field):
            changes.append(f"{label} 변경: {old_state.get(field)} → {new_state.get(field)}")
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
    current = topic_state(official, candidates)
    changed, changes = state_changed(old_topic, current)
    evidence = evidence_links(candidates)

    pending = {
        "updated_at_kst": now_kst.isoformat(timespec="seconds"),
        "topic_state": current,
        "evidence": evidence,
        "official": official,
    }
    PENDING_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if changed:
        support = "공식 확인" if official["samsung_support_confirmed"] else "공식 페이지 재확인 필요"
        job = (
            "Samsung Careers 원문에서 stablecoin 업무 직접 확인"
            if official["job_stablecoin_confirmed"]
            else "Samsung Careers 직무 존재 확인 + 복수 보도로 stablecoin 업무 범위 교차검증"
        )
        lines = [
            "<b>Samsung Wallet 스테이블코인 상태 변화</b>",
            f"<code>조회 {html.escape(now_kst.isoformat(timespec='seconds'))}</code>",
            "",
            "<b>무엇이 달라졌나</b>",
        ]
        lines += [f"• {html.escape(change)}" for change in changes]
        lines += [
            "",
            "<b>현재 상태</b>",
            f"• <b>{html.escape(str(current['stage_name']))}</b> · 단계 {current['stage']}",
            f"• Samsung Wallet stablecoin 지원 계획: <b>{support}</b>",
            f"• 결제 BD 실행 신호: {html.escape(job)}",
        ]
        if current.get("stablecoin_partner"):
            lines.append(
                f"• 스테이블코인 관련 파트너: <b>{html.escape(str(current['stablecoin_partner']))}</b>"
            )
        else:
            lines.append("• 스테이블코인 발행사·체인·결제 파트너 실명: <b>아직 확정 확인 없음</b>")

        lines += [
            "",
            "<b>투자 의미</b>",
            "• 기사 수가 늘어난 것이 아니라 <b>Samsung Wallet의 스테이블코인 채택 단계가 실제로 변했는지</b>를 기준으로 알림",
            "• 같은 내용을 반복 보도하는 기사만 추가되면 알림하지 않음",
            "• 다음 상태 변화: 발행사/결제망 실명 → 파일럿 → 출시국·출시일 → Wallet 기능 공개 → 상용화·수수료 구조",
            "",
            "<b>근거·교차검증</b>",
            f'• Samsung Business Insights: <a href="{SAMSUNG_INSIGHTS_URL}">원문</a>',
            f'• Samsung Careers R118656: <a href="{WORKDAY_JOB_URL}">원문</a>',
        ]
        if official["article_confirmed"]:
            lines.append(f'• Digital Asset 확인 기사: <a href="{DIGITAL_ASSET_URL}">근거</a>')
        for item in evidence[:3]:
            title = html.escape(str(item.get("title") or "교차검증"))
            link = html.escape(str(item.get("link") or ""))
            lines.append(f'• <a href="{link}">{title}</a>')
        ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    status = [
        "# Samsung Wallet stablecoin adoption state watch",
        "",
        f"- 조회시각(KST): {now_kst.isoformat(timespec='seconds')}",
        f"- current stage: {current['stage']} / {current['stage_name']}",
        f"- state changed: {changed}",
        f"- changes: {'; '.join(changes) if changes else 'none'}",
        f"- Samsung official support signal: {official['samsung_support_confirmed']}",
        f"- Workday job exists: {official['job_fetch_ok']}",
        f"- stablecoin BD scope: {current['stablecoin_bd_scope']}",
        f"- partner: {current['stablecoin_partner'] or 'unconfirmed'}",
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
