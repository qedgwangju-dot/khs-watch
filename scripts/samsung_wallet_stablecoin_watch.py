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


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)

    now_kst = dt.datetime.now(KST)
    now_utc = now_kst.astimezone(UTC)
    old = load_state()
    seen = dict(old.get("seen") or {})

    official = official_context()
    candidates = rss_candidates(now_utc)

    # The missed Samsung US job posting is a high-impact catch-up event. It is sent once,
    # then future alerts are driven by fresh RSS/official changes.
    catchup_key = fingerprint("samsung-wallet-stablecoin-business-development-R118656")
    catchup_new = catchup_key not in seen and (
        official["job_stablecoin_confirmed"] or official["article_confirmed"]
    )

    fresh_news: list[dict] = []
    for item in candidates:
        key = fingerprint((item.get("title") or "") + "|" + (item.get("link") or ""))
        if key in seen:
            continue
        item["fingerprint"] = key
        fresh_news.append(item)

    alert_needed = catchup_new or bool(fresh_news)

    pending_seen = dict(seen)
    if catchup_new:
        pending_seen[catchup_key] = {
            "event": "Samsung Wallet stablecoin payments BD job R118656",
            "first_seen_kst": now_kst.isoformat(timespec="seconds"),
            "source": DIGITAL_ASSET_URL,
        }
    for item in fresh_news[:5]:
        pending_seen[item["fingerprint"]] = {
            "event": item.get("title"),
            "first_seen_kst": now_kst.isoformat(timespec="seconds"),
            "source": item.get("link"),
        }

    pending = {
        "updated_at_kst": now_kst.isoformat(timespec="seconds"),
        "seen": pending_seen,
        "official": official,
        "fresh_candidates": [
            {
                "title": x.get("title"),
                "link": x.get("link"),
                "published_utc": x.get("published_utc"),
            }
            for x in fresh_news[:10]
        ],
    }
    PENDING_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if alert_needed:
        support = "공식 확인" if official["samsung_support_confirmed"] else "공식 페이지 재확인 필요"
        job = (
            "Samsung Careers 원문에서 stablecoin 업무 직접 확인"
            if official["job_stablecoin_confirmed"]
            else "Samsung Careers 원문 동적 페이지 미확인 · Digital Asset 보도로 채용공고 내용 확인"
        )
        lines = [
            "<b>삼성월렛 스테이블코인 사업 실행 신호</b>",
            f"<code>조회 {html.escape(now_kst.isoformat(timespec='seconds'))}</code>",
            "",
            "<b>무엇이 달라졌나</b>",
            "• 삼성전자 미국법인이 Samsung Wallet 결제 사업개발 직무에서 <b>Stablecoin</b>을 issuer·payments·fintech·BNPL과 함께 제휴 분야로 명시",
            "• 해당 역할은 파트너 발굴, 상업조건·데이터 이용·제품 요구사항 협상, 제품팀과 신규 기능 출시까지 담당",
            "",
            "<b>현재 판정</b>",
            "• <b>계획 → 사업개발·파트너십 실행 단계로 한 단계 구체화</b>",
            f"• Samsung Business Insights의 Wallet stablecoin 지원 계획: <b>{support}</b>",
            f"• 채용 원문 검증: {html.escape(job)}",
            "",
            "<b>투자 의미</b>",
            "• Galaxy 단말의 Samsung Wallet이 스테이블코인 결제·송금 유통채널이 될 가능성을 높이는 실행 신호",
            "• 특정 발행사(USDC·USDT 등), 체인, 출시국, 출시일, 수수료·수익배분은 아직 공식 확정되지 않아 수혜주를 단정하지 않음",
            "• 다음 핵심 트리거: 발행사/결제망 실명, 파일럿·출시국, 앱 기능 공개, 상용화 일정, 수수료 구조",
            "",
            "<b>원문</b>",
            f'• Samsung Careers R118656: <a href="{WORKDAY_JOB_URL}">원문</a>',
            f'• Samsung Business Insights: <a href="{SAMSUNG_INSIGHTS_URL}">원문</a>',
            f'• Digital Asset 단독: <a href="{DIGITAL_ASSET_URL}">원문</a>',
        ]
        if fresh_news:
            lines += ["", "<b>추가 최신 보도</b>"]
            for item in fresh_news[:3]:
                title = html.escape(str(item.get("title") or "관련 보도"))
                link = html.escape(str(item.get("link") or ""))
                lines.append(f'• <a href="{link}">{title}</a>')
        ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    status = [
        "# Samsung Wallet stablecoin adoption watch",
        "",
        f"- 조회시각(KST): {now_kst.isoformat(timespec='seconds')}",
        f"- Samsung official support signal: {official['samsung_support_confirmed']}",
        f"- Workday stablecoin direct parse: {official['job_stablecoin_confirmed']}",
        f"- Digital Asset job report confirmed: {official['article_confirmed']}",
        f"- fresh RSS candidates: {len(fresh_news)}",
        f"- alert: {alert_needed}",
        f"- errors: {'; '.join(official['errors']) if official['errors'] else 'none'}",
    ]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")
    print(
        f"samsung_wallet_stablecoin_alert={str(alert_needed).lower()} "
        f"catchup={str(catchup_new).lower()} fresh_news={len(fresh_news)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
