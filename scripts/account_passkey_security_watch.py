#!/usr/bin/env python3
"""Low-noise account security / passkey watcher.

Alerts only on concrete structural changes:
- major platform/bank passkey default rollouts or adoption milestones
- passkey/private-key/session-token bypasses with verified impact
- credential-stuffing breaches/fines with named organizations or measured scope
- FIDO/passkey interoperability or regulatory changes
- annual password-cracking economics when the underlying benchmark changes

The first run establishes a silent baseline. Search-source failure is fail-closed.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "account_passkey_security_watch_state.json"
PENDING_PATH = OUT / "account_passkey_security_watch_pending_state.json"
ALERT_TITLE = OUT / "account_passkey_security_watch_alert_title.txt"
ALERT_BODY = OUT / "account_passkey_security_watch_alert.html"
STATUS_PATH = OUT / "account_passkey_security_watch_status.md"
CONFIRMED_PATH = OUT / "account_passkey_security_watch_telegram_confirmed.json"

GOOGLE_NEWS = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 khs-account-passkey-security-watch/1.0"
MAX_AGE_HOURS = 168
SEEN_RETENTION_DAYS = 90
MAX_ALERT_EVENTS = 5
BACKFILL_GRACE_HOURS = 12

NEWS_QUERIES = [
    '(passkey OR FIDO) (Google OR Apple OR Microsoft OR Amazon OR Kakao OR bank) (launch OR default OR rollout OR adoption OR accounts OR customers)',
    '(passkey OR FIDO) (vulnerability OR bypass OR malware OR "private key" OR "session token" OR recovery OR theft)',
    '"credential stuffing" (breach OR fine OR regulator OR bank OR retail OR accounts)',
    '(passkey OR passwordless OR FIDO) (regulation OR regulator OR standard OR interoperability OR transfer OR banking OR finance)',
]

TRUSTED_SOURCE_HINTS = (
    "fido alliance", "fidoalliance", "google", "apple", "microsoft", "amazon",
    "kakao", "samsung", "reuters", "bloomberg", "financial times", "cnbc",
    "the verge", "ars technica", "techcrunch", "wired", "unit 42",
    "palo alto", "crowdstrike", "securityweek", "bleepingcomputer",
    "hive systems", "hivesystems", "금융위원회", "fsc", "금융보안원",
    "fsec", "개인정보보호위원회", "privacy", "연합뉴스", "yonhap",
)

CATEGORY_PATTERNS = [
    ("패스키 대규모 도입·기본전환", (
        "passkey", "passkeys", "passwordless", "default", "rollout",
        "rolled out", "enabled", "adoption", "accounts", "customers",
        "기본", "도입", "전환", "계정",
    )),
    ("패스키 우회·개인키·세션 탈취", (
        "passkey", "private key", "session token", "bypass", "malware",
        "steal", "stolen", "theft", "compromise", "recovery",
        "개인키", "세션", "탈취", "우회", "악성코드",
    )),
    ("크리덴셜 스터핑 대형사고·제재", (
        "credential stuffing", "breach", "fine", "penalty", "regulator",
        "affected", "leak", "크리덴셜 스터핑", "과징금", "유출",
    )),
    ("FIDO 표준·상호운용성", (
        "fido", "standard", "specification", "interoperability", "transfer",
        "export", "import", "credential exchange", "표준", "상호운용", "이전",
    )),
    ("비밀번호 해독 경제성 변화", (
        "password table", "brute force", "brute-force", "crack",
        "rtx 5090", "bcrypt", "gpu rent", "해독", "무차별 대입",
    )),
    ("금융·규제의 패스워드리스 전환", (
        "bank", "banking", "financial", "regulation", "regulator",
        "authentication requirement", "금융", "감독규정", "인증",
    )),
]

HANGUL_RE = re.compile(r"[가-힣]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
TRANSLATE_GOOGLE = "https://translate.googleapis.com/translate_a/single"
IDENTIFIERS = ("FIDO", "Google", "Apple", "Microsoft", "Amazon", "Kakao", "Samsung", "Passkey", "RTX 5090")


def fetch_bytes(url: str, timeout: int = 25, attempts: int = 3) -> bytes:
    last = None
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml,application/xml,text/html,application/json,*/*",
                "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= attempts:
                raise
        except Exception as exc:
            last = exc
            if attempt >= attempts:
                raise
        time.sleep(min(8, attempt * 2))
    raise RuntimeError(f"fetch failed: {last}")


def strip_html(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).replace("\xa0", " ").split())


def parse_pubdate(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        return None


def google_news_url(query: str, locale: str = "en") -> str:
    if locale == "ko":
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return GOOGLE_NEWS + "?" + urllib.parse.urlencode(params)


def parse_google_news(query: str, now: dt.datetime) -> list[dict]:
    root = None
    last = None
    for locale in ("en", "ko"):
        try:
            root = ET.fromstring(fetch_bytes(google_news_url(query, locale)))
            break
        except Exception as exc:
            last = exc
    if root is None:
        raise RuntimeError(f"Google News primary+fallback failed: {last}")

    out = []
    for node in root.findall(".//item"):
        title = strip_html(node.findtext("title") or "")
        desc = strip_html(node.findtext("description") or "")
        link = (node.findtext("link") or "").strip()
        source_node = node.find("source")
        source = strip_html(source_node.text if source_node is not None and source_node.text else "")
        published = parse_pubdate(node.findtext("pubDate"))
        if not title or not link:
            continue
        if published and now - published > dt.timedelta(hours=MAX_AGE_HOURS):
            continue
        out.append({
            "title": title,
            "description": desc,
            "source": source or "Google News",
            "url": link,
            "published_at": published.isoformat() if published else None,
        })
    return out


def trusted(source: str) -> bool:
    low = (source or "").lower()
    return any(x in low for x in TRUSTED_SOURCE_HINTS)


def category(text: str) -> str:
    low = text.lower()
    scores = []
    for label, patterns in CATEGORY_PATTERNS:
        score = sum(1 for p in patterns if p in low)
        if score:
            scores.append((score, label))
    if not scores:
        return "계정 보안 변화"
    scores.sort(reverse=True)
    return scores[0][1]


def entity(text: str) -> str:
    low = text.lower()
    mapping = (
        ("FIDO Alliance", ("fido alliance", "fidoalliance")),
        ("Google", ("google",)),
        ("Apple", ("apple",)),
        ("Microsoft", ("microsoft",)),
        ("Amazon", ("amazon",)),
        ("카카오", ("kakao", "카카오")),
        ("삼성전자", ("samsung", "삼성")),
        ("금융권", ("bank", "banking", "금융", "은행")),
        ("Hive Systems", ("hive systems", "hivesystems")),
    )
    for label, pats in mapping:
        if any(p in low for p in pats):
            return label
    return "계정·인증 생태계"


def material(item: dict) -> bool:
    text = f" {item.get('title','')} {item.get('description','')} "
    low = text.lower()
    if not trusted(item.get("source", "")):
        return False
    if not any(x in low for x in ("passkey", "passkeys", "passwordless", "fido", "credential stuffing", "크리덴셜 스터핑", "password table", "비밀번호")):
        return False

    # Generic tips/how-to articles are not alerts.
    if any(x in low for x in ("how to", "tips", "guide", "설정법", "사용법")) and not any(
        x in low for x in ("breach", "vulnerability", "fine", "default", "rollout", "launched", "released", "standard", "regulation", "과징금", "유출", "취약점", "기본 전환")
    ):
        return False

    concrete = (
        "launched", "released", "rollout", "rolled out", "default", "enabled",
        "million", "billion", "accounts", "customers", "vulnerability", "bypass",
        "malware", "private key", "session token", "breach", "fine", "penalty",
        "credential stuffing", "standard", "specification", "regulation",
        "rtx 5090", "bcrypt", "gpu rent",
        "도입", "출시", "기본", "계정", "취약점", "우회", "탈취", "유출",
        "과징금", "크리덴셜 스터핑", "표준", "규정", "해독",
    )
    return any(x in low for x in concrete)


def fingerprint(item: dict) -> str:
    raw = "|".join([item.get("url",""), item.get("title",""), item.get("source","")])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(UTC)
    except Exception:
        return None


def stale_backfill(item: dict, watermark: dt.datetime | None) -> bool:
    if watermark is None:
        return False
    published = _parse_iso(item.get("published_at"))
    return bool(published and published < watermark - dt.timedelta(hours=BACKFILL_GRACE_HOURS))


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen": {}, "news_watermark_utc": None}
    try:
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        obj.setdefault("initialized", False)
        obj.setdefault("seen", {})
        obj.setdefault("news_watermark_utc", None)
        return obj
    except Exception:
        return {"initialized": False, "seen": {}, "news_watermark_utc": None}


def save_json(path: pathlib.Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _translate_google(text: str) -> str:
    params = urllib.parse.urlencode({"client":"gtx","sl":"auto","tl":"ko","dt":"t","q":text})
    req = urllib.request.Request(
        TRANSLATE_GOOGLE + "?" + params,
        headers={"User-Agent":USER_AGENT,"Accept":"application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    chunks = payload[0] if isinstance(payload, list) and payload else []
    return "".join(str(x[0]) for x in chunks if isinstance(x,list) and x and x[0]).strip()


def translate_title(text: str) -> str:
    value = strip_html(text)
    if HANGUL_RE.search(value) or len(LATIN_WORD_RE.findall(value)) < 3:
        return value
    try:
        out = strip_html(_translate_google(value))
        if HANGUL_RE.search(out):
            found = [x for x in IDENTIFIERS if x.lower() in value.lower() and x.lower() not in out.lower()]
            return (" · ".join(found) + " · " if found else "") + out
    except Exception:
        pass
    return "계정·인증 보안 관련 중요 변화"


def impact(cat: str) -> str:
    mapping = {
        "패스키 대규모 도입·기본전환": "대형 플랫폼·은행의 기본 인증이 비밀번호에서 패스키로 이동하는 실제 사용자 규모와 전환율을 확인합니다.",
        "패스키 우회·개인키·세션 탈취": "패스키 자체보다 단말·동기화·복구·세션 토큰이 새로운 공격면이 되는지 확인합니다.",
        "크리덴셜 스터핑 대형사고·제재": "비밀번호 재사용 공격이 실제 개인정보 유출·과징금·금융권 손실로 이어지는 규모를 확인합니다.",
        "FIDO 표준·상호운용성": "패스키 이동·상호운용 표준이 플랫폼 종속성과 기업 도입 비용을 낮추는지 확인합니다.",
        "비밀번호 해독 경제성 변화": "GPU 성능·임대비와 해시 강도 변화가 오프라인 비밀번호 공격의 시간·비용을 얼마나 낮추는지 확인합니다.",
        "금융·규제의 패스워드리스 전환": "금융 규정·내부통제가 비밀번호 중심에서 피싱 저항 인증으로 이동하는지 확인합니다.",
    }
    return mapping.get(cat, "실제 계정탈취·도입 규모·규제 변화를 확인합니다.")


def build_alert(events: list[dict], now: dt.datetime) -> tuple[str,str]:
    title = f"🔐 <b>계정 보안·패스키 Watch</b> · 중요 변화 {len(events)}건"
    lines = [f"<i>{now.astimezone(KST).strftime('%m/%d %H:%M KST')}</i>"]
    for idx, item in enumerate(events, 1):
        cat = item["category"]
        lines += [
            "",
            f"<b>{idx}. {html.escape(item['entity'])} · {html.escape(cat)}</b>",
            f"• {html.escape(translate_title(item['title']))}",
            f"• <b>의미</b>: {html.escape(impact(cat))}",
            f"• <b>확인</b>: 신뢰 원천",
            f'🔗 <a href="{html.escape(item["url"], quote=True)}">{html.escape(item["source"][:28])}</a>',
        ]
    lines += [
        "",
        "<b>다음 확인</b>: 패스키 기본전환 사용자수·성공률 · 금융권 전면 적용 · FIDO 상호운용 표준 · 단말/동기화/복구 경로 우회 · 세션 토큰 탈취 · 크리덴셜 스터핑 피해·과징금 · GPU 해독 시간·비용",
    ]
    return title, "\n".join(lines)


def main() -> int:
    for p in (ALERT_TITLE, ALERT_BODY, CONFIRMED_PATH):
        p.unlink(missing_ok=True)

    now = dt.datetime.now(UTC)
    state = load_state()
    errors = []
    raw = []
    successes = 0
    for q in NEWS_QUERIES:
        try:
            raw.extend(parse_google_news(q, now))
            successes += 1
        except Exception as exc:
            errors.append(f"Google News 실패: {q[:70]} / {type(exc).__name__}: {exc}")

    if successes != len(NEWS_QUERIES):
        STATUS_PATH.write_text(
            "\n".join([
                "# 계정 보안·패스키 Watch",
                "",
                f"- 조회시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
                f"- 뉴스 검색 성공: {successes}/{len(NEWS_QUERIES)}",
                "- 상태: 검색 원천 불완전으로 fail-closed",
            ] + [f"- 오류: {x}" for x in errors[:10]]) + "\n",
            encoding="utf-8",
        )
        print(f"account_passkey_feed_health=failed success={successes}/{len(NEWS_QUERIES)}")
        return 2

    unique = {}
    for row in raw:
        if material(row):
            row["fingerprint"] = fingerprint(row)
            row["category"] = category(f"{row['title']} {row['description']}")
            row["entity"] = entity(f"{row['title']} {row['description']}")
            unique[row["fingerprint"]] = row
    current = list(unique.values())

    seen = dict(state.get("seen") or {})
    watermark = _parse_iso(state.get("news_watermark_utc"))
    new_items = []
    stale_count = 0
    for item in current:
        if item["fingerprint"] in seen:
            continue
        if stale_backfill(item, watermark):
            stale_count += 1
            continue
        new_items.append(item)

    baseline = not bool(state.get("initialized"))
    if baseline:
        new_items = []

    for item in current:
        seen.setdefault(item["fingerprint"], {
            "title":item["title"],
            "source":item["source"],
            "url":item["url"],
            "published_at":item.get("published_at"),
            "category":item["category"],
            "entity":item["entity"],
            "first_seen_at":now.isoformat(),
        })

    events = sorted(new_items, key=lambda x:x.get("published_at") or "", reverse=True)[:MAX_ALERT_EVENTS]
    pending = {
        "initialized":True,
        "updated_at_kst":now.astimezone(KST).isoformat(timespec="seconds"),
        "news_watermark_utc":now.isoformat(),
        "seen":seen,
        "last_collection":{
            "raw_items":len(raw),
            "material_items":len(current),
            "new_events":len(events),
            "stale_backfill_suppressed":stale_count,
            "errors":[],
        },
    }
    save_json(PENDING_PATH,pending)

    if events:
        title,body=build_alert(events,now)
        ALERT_TITLE.write_text(title+"\n",encoding="utf-8")
        ALERT_BODY.write_text(body+"\n",encoding="utf-8")

    STATUS_PATH.write_text(
        "\n".join([
            "# 계정 보안·패스키 Watch","",
            f"- 조회시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
            f"- 최초 기준선: {'예' if baseline else '아니오'}",
            f"- 웹 수집: {len(raw)}건",
            f"- 중요 필터 통과: {len(current)}건",
            f"- 신규 중요 사건: {len(events)}건",
            f"- 과거 기사 역유입 차단: {stale_count}건",
            "- 오류: 0건",
        ])+"\n",encoding="utf-8"
    )
    print(
        f"account_passkey_baseline={str(baseline).lower()} "
        f"material={len(current)} new_events={len(events)} stale={stale_count} errors=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
