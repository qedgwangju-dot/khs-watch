#!/usr/bin/env python3
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

RSS_URL = "https://www.federalreserve.gov/feeds/speeches.xml"
SPEECH_ARCHIVE_URL = f"https://www.federalreserve.gov/newsevents/{datetime.now(timezone.utc).year}-speeches.htm"
STATE_PATH = Path("data/warsh_speech_watch_state.json")
UA = "Mozilla/5.0 (compatible; khs-watch/1.2; +https://github.com/qedgwangju-dot/khs-watch)"
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
EXPECTED_BOT = (os.getenv("EXPECTED_BOT_USERNAME") or "khs8879887988798879_bot").strip().lstrip("@")
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "0") == "1"

POLICY_KEYWORDS = [
    "inflation", "prices", "interest rate", "federal funds", "restrictive",
    "financial conditions", "full employment", "labor market", "work to do",
    "forward guidance", "monetary policy", "rate hike", "raise rates",
    "further tightening", "rate cut", "lower rates"
]

AI_KEYWORDS = [
    "artificial intelligence", " ai ", "ai-related", "new factor of production",
    "new variable", "token sales", "tokens", "productivity", "capital intensity",
    "capital-light", "chipmakers", "energy producers", "cloud providers",
    "scarce assets", "cap-ex", "capital expenditures", "second derivative",
    "secular stagnation", "saving glut", "hinge point", "hyper–moore", "hyper-moore",
    "scaling laws", "productivity and jobs"
]

# 'hike' by itself is not a monetary-policy signal. Jackson Hole trail/hiking jokes are excluded.
HIKING_CONTEXT = [
    "trail", "trails", "hiking", "stroll", "rockefeller preserve", "kohn day",
    "bernanke day", "don kohn", "ben bernanke", "wellness check"
]
MONETARY_HIKE_CONTEXT = [
    "rate hike", "interest-rate hike", "interest rate hike", "hike rates",
    "hiking rates", "raise rates", "raising rates", "federal funds rate"
]

HAWKISH_TERMS = [
    "predominant focus", "prices", "inflation", "work to do", "not restrictive",
    "hard pressed to describe broad financial conditions as restrictive",
    "rate hike", "raise rates", "raising rates", "further tightening",
    "short-term interest rates are the predominant tool"
]
DOVISH_TERMS = [
    "rate cut", "lower rates", "lowering rates", "labor market deterioration",
    "downside risks to employment", "unemployment has risen", "policy is restrictive"
]


SCENARIOS_LINK = "https://www.federalreserve.gov/newsevents/speech/warsh20261116a.htm"
SCENARIOS_VERSION = 1
# GitHub Actions 43922758516, job 133494254719, 2026-11-16 17:54 UTC.
LEGACY_MESSAGE_ID = 151
LEGACY_BOT = "hshs8879_bot"
LEGACY_PUB_DATE = "Mon, 16 Nov 2026 17:00:00 GMT"


def warsh_source(url):
    return bool(re.fullmatch(r"https://www\.federalreserve\.gov/newsevents/speech/warsh20\d{6}[a-z]?\.htm", url))


def fetch(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace"), r.geturl()


def clean_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def parse_date(value: str) -> datetime:
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def latest_warsh_item(xml_text: str):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        blob = f"{title}\n{desc}".lower()
        if "warsh" not in blob and "kevin" not in blob:
            continue
        if not warsh_source(link):
            continue
        items.append((parse_date(pub), title, link, pub))
    if not items:
        return None
    items.sort(key=lambda x: x[0])
    return items[-1]


def latest_warsh_archive_item():
    """Official annual speeches-page fallback when the short RSS window omits Warsh."""
    try:
        raw, _ = fetch(SPEECH_ARCHIVE_URL)
    except Exception:
        return None
    rows = []
    for m in re.finditer(
        r"""href=["']([^"']*/newsevents/speech/warsh(20\d{6})[a-z]?\.htm)["'][^>]*>(.*?)</a>""",
        raw, re.I | re.S
    ):
        href = urllib.parse.urljoin(SPEECH_ARCHIVE_URL, m.group(1))
        if not warsh_source(href):
            continue
        ds = m.group(2)
        title = re.sub(r'<[^>]+>', ' ', m.group(3))
        title = ' '.join(html.unescape(title).split()).strip() or 'Kevin Warsh 공식 연설'
        dt = datetime.strptime(ds, '%Y%m%d').replace(tzinfo=timezone.utc)
        rows.append((dt, title, href, dt.strftime('%a, %d %b %Y 00:00:00 +0000')))
    if not rows:
        return None
    rows.sort(key=lambda x: x[0])
    return rows[-1]


def is_hiking_only(sentence: str) -> bool:
    low = sentence.lower()
    has_hike = bool(re.search(r"\bhikes?\b|\bhiking\b", low))
    if not has_hike:
        return False
    if any(term in low for term in MONETARY_HIKE_CONTEXT):
        return False
    return any(term in low for term in HIKING_CONTEXT)


def split_sentences(text: str):
    return re.split(r"(?<=[.!?])\s+|\n+", text)


def select_lines(text: str, keywords: list[str], limit: int = 7):
    out, seen = [], set()
    for chunk in split_sentences(text):
        s = re.sub(r"\s+", " ", chunk).strip(" -•\t")
        low = f" {s.lower()} "
        if len(s) < 25 or len(s) > 500:
            continue
        if is_hiking_only(s):
            continue
        if any(k in low for k in keywords):
            key = low[:180]
            if key not in seen:
                seen.add(key)
                out.append(s)
        if len(out) >= limit:
            break
    return out


def classify_policy_tone(text: str) -> tuple[str, int, int]:
    low = text.lower()
    cleaned = " ".join(
        s for s in split_sentences(low)
        if s and not is_hiking_only(s)
    )
    hawk = sum(1 for term in HAWKISH_TERMS if term in cleaned)
    dove = sum(1 for term in DOVISH_TERMS if term in cleaned)
    if hawk >= dove + 2:
        tone = "매파 강화"
    elif dove >= hawk + 2:
        tone = "비둘기 강화"
    else:
        tone = "조건부/혼합"
    return tone, hawk, dove


def classify_ai_regime(text: str) -> str:
    low = text.lower()
    structural = any(term in low for term in [
        "new factor of production", "new variable", "secular stagnation", "saving glut",
        "hinge point", "hyper–moore", "hyper-moore", "potential for substantially higher growth"
    ])
    demand = any(term in low for term in [
        "capital expenditures", "cap-ex", "ai-related infrastructure", "capital intensity",
        "chipmakers", "energy producers", "cloud providers"
    ])
    if structural and demand:
        return "AI 구조적 성장 + 단기 투자수요 동시 강화"
    if structural:
        return "AI 잠재성장률/생산성 체제변화 신호"
    if demand:
        return "AI 투자수요/금융여건 신호"
    return "AI 핵심 체제변화 신호 없음"


def speech_title_ko(title: str) -> str:
    raw = (title or "").strip()
    low = raw.lower()
    known = [
        (r"\bin our time\b", "우리 시대에"),
        (r"financial innovation.*payments.*policy", "금융혁신이 지급결제와 정책에 미치는 영향"),
        (r"productivity.*jobs|jobs.*productivity", "생산성과 일자리"),
        (r"inflation|price stability", "물가안정과 통화정책"),
        (r"monetary policy", "통화정책"),
    ]
    for pat, ko in known:
        if re.search(pat, low, re.I):
            return ko
    if re.search(r"[가-힣]", raw):
        return raw
    return "Kevin Warsh 공식 연설 새 게시물"


def speech_signals_ko(text: str):
    low = (text or "").lower()
    ai = []
    policy = []

    if "artificial intelligence" in low or " ai " in f" {low} ":
        ai.append("• AI가 생산성·성장·고용 구조를 바꾸는 경로에 관한 발언이 포함됐습니다.")
    if "new factor of production" in low or "new variable" in low:
        ai.append("• AI를 새로운 생산요소 또는 경제의 새로운 변수로 보는 관점이 제시됐습니다.")
    if "productivity" in low:
        ai.append("• 생산성 향상이 잠재성장률과 물가 압력에 미치는 영향을 언급했습니다.")
    if "capital expenditures" in low or "cap-ex" in low or "capital intensity" in low:
        ai.append("• AI 관련 설비투자와 자본집약도 변화가 단기 수요와 금융여건에 미치는 영향을 언급했습니다.")
    if "chipmakers" in low or "energy producers" in low or "cloud providers" in low:
        ai.append("• 반도체·에너지·클라우드 공급망이 AI 투자 확대의 핵심 실물 경로로 언급됐습니다.")

    if "inflation" in low or "prices" in low or "price stability" in low:
        policy.append("• 물가안정과 인플레이션의 2% 목표 복귀 여부가 정책 판단의 핵심으로 유지됐습니다.")
    if "financial conditions" in low or "restrictive" in low:
        policy.append("• 현재 금융여건이 충분히 긴축적인지에 대한 평가가 포함됐습니다.")
    if "full employment" in low or "labor market" in low or "employment" in low:
        policy.append("• 완전고용과 노동시장 안정 여부를 정책 판단의 한 축으로 다뤘습니다.")
    if "forward guidance" in low:
        policy.append("• 미리 정해진 금리 경로보다 회의별 데이터 판단을 중시하는 소통 원칙이 포함됐습니다.")
    if any(x in low for x in ["rate hike", "raise rates", "raising rates", "further tightening"]):
        policy.append("• 추가 금리인상 또는 추가긴축 선택지를 열어두는 문맥이 확인됐습니다.")
    if any(x in low for x in ["rate cut", "lower rates", "lowering rates"]):
        policy.append("• 금리인하 가능성을 언급하는 문맥이 확인됐습니다.")

    if not ai:
        ai.append("• AI·생산성·성장 관련 핵심 체제변화 신호는 새로 확인되지 않았습니다.")
    if not policy:
        policy.append("• 물가·고용·금리 경로의 직접적인 새 정책 신호는 제한적입니다.")
    return ai[:5], policy[:6]


def speech_date_ko(dt: datetime) -> str:
    return f"{dt.year}년 {dt.month}월 {dt.day}일"


def speech_message(link, title, dt):
    if not warsh_source(link):
        raise ValueError("Unexpected Federal Reserve speech URL")
    raw, final = fetch(link)
    if final != link:
        raise ValueError("Federal Reserve speech redirected away from its identified source")
    text = clean_text(raw)
    if link == SCENARIOS_LINK:
        # Require the event and each substantive claim in the retrieved official speech.
        source = " ".join(text.lower().replace("’", "'").split())
        markers = (
            "productivity and jobs task force", "supercharge idea generation",
            "structurally to the upside", "illustrative scenarios, not forecasts",
            "shared broadly across labor", "stays close to full employment",
            "widespread automation", "above levels consistent with full employment",
            "equity valuations could fall", "without the productivity gains",
            "critical infrastructures", "important implications for monetary policy down the road",
        )
        if not all(phrase in source for phrase in markers):
            raise ValueError("The November 16 Federal Reserve speech could not be verified")
        return "\n".join((
            "[워시 연준 의장 | 초지능과 성장·고용]",
            "샌프란시스코 연은 생산성·일자리 회의 개회사 · 한국시간 2026년 11월 17일 오전 2시",
            "",
            "■ 워시는 초지능이 아이디어 창출을 가속할 수 있지만 최근 생산성 개선이 구조적 추세인지는 아직 확인하기 어렵다고 평가했습니다.",
            "■ 연준 실무진은 향후 수년을 대비해 세 가지 경로를 검토했으며 각 경로의 실현 확률이나 12월 금리 방향을 제시하지 않았습니다.",
            "■ 생산성 향상의 이익을 노동자와 자본 소유자가 폭넓게 공유하면 실질 성장률은 장기 평균을 지속적으로 웃돌고 경제는 완전고용에 가깝게 유지됩니다.",
            "■ 자동화로 일자리가 대체되고 새 일자리로 옮기는 데 시간이 걸리면 성장률이 장기 평균을 웃돌아도 실업률은 완전고용에 부합하는 수준을 넘어설 수 있습니다.",
            "■ 대규모 설비투자 뒤 기대수익과 주가가 하락하면 경기가 둔화하고 실업률이 더 크게 오르며, 경기 회복 후에도 예상한 생산성 개선이 실현되지 않을 수 있습니다.",
            "■ 워시는 악의적 이용으로 핵심 기반시설이 피해를 볼 위험과 기술 확산의 규모·범위·시기가 향후 통화정책에 미칠 영향을 함께 짚었습니다.",
            "",
            link,
        ))
    tone, hawk, dove = classify_policy_tone(text)
    ai_regime = classify_ai_regime(text)
    ai_lines, policy_lines = speech_signals_ko(text)
    msg = [
        "[Kevin Warsh 공식 발언 변화 감지]",
        f"제목: {speech_title_ko(title)}",
        f"발표: {speech_date_ko(dt)}",
        f"정책 톤: {tone} (매파 문맥 {hawk} / 비둘기 문맥 {dove})",
        f"AI 체제판정: {ai_regime}",
        "",
        "[AI·생산성·성장]",
        *ai_lines,
        "",
        "[물가·고용·금리]",
        *policy_lines,
        "",
        "오탐 필터: 산책·등산·인명 관련 문맥은 금리인상 신호에서 제외합니다.",
        f"원문: {final}",
        "",
        "판정: AI 생산성·잠재성장률과 단기 설비투자 수요를 분리하고, 물가·금융여건·완전고용·추가긴축 선택지와 함께 재확인합니다.",
    ]
    return "\n".join(msg)


class TelegramRejected(RuntimeError):
    """Telegram expressly rejected this request before delivering a message."""


def telegram(method, fields=None):
    if not TOKEN:
        raise ValueError("Telegram token missing")
    data = urllib.parse.urlencode(fields).encode() if fields else None
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except (ValueError, OSError):
            body = {}
        if exc.code == 400 and method == "editMessageText" and "message is not modified" in str(body.get("description", "")).lower():
            return None
        if 400 <= exc.code < 500 and body.get("ok") is False and body.get("error_code") == exc.code:
            raise TelegramRejected(f"Telegram rejected {method} (HTTP {exc.code})") from None
        raise RuntimeError(f"Telegram {method} response unconfirmed") from None
    except (OSError, ValueError):
        raise RuntimeError(f"Telegram {method} response unconfirmed") from None
    if body.get("ok") is not True or not isinstance(body.get("result"), dict):
        raise RuntimeError(f"Telegram {method} returned an unverified result")
    return body["result"]


def verified_route():
    if not CHAT_ID or not EXPECTED_BOT:
        raise ValueError("Telegram route missing")
    bot = telegram("getMe")
    if bot.get("is_bot") is not True or str(bot.get("username", "")).lower() != EXPECTED_BOT.lower() or type(bot.get("id")) is not int:
        raise ValueError("Wrong Telegram bot")
    chat = telegram("getChat", {"chat_id": CHAT_ID})
    chat_id = chat.get("id")
    if type(chat_id) is not int or not (
        str(chat_id) == CHAT_ID or
        (CHAT_ID.startswith("@") and CHAT_ID[1:].lower() == str(chat.get("username", "")).lower())
    ):
        raise ValueError("Wrong Telegram chat")
    # Match immutable IDs even if a channel handle is later reassigned.
    key = hashlib.sha256(f"warsh-speech:1:{bot['id']}:{chat_id}".encode()).hexdigest()
    return chat_id, key


def deliver(text, chat_id, message_id=None, legacy_reply=False):
    fields = {"chat_id": chat_id, "text": text[:4090], "disable_web_page_preview": "true"}
    if message_id is not None:
        if type(message_id) is not int or message_id <= 0:
            raise ValueError("Invalid previous Telegram message ID")
        fields["message_id"] = message_id
        result = telegram("editMessageText", fields)
        if result is None:
            return message_id  # Same text already present on the verified prior message.
    else:
        if legacy_reply:
            fields["reply_parameters"] = json.dumps({
                "message_id": LEGACY_MESSAGE_ID,
                "quote": SCENARIOS_LINK,
                "allow_sending_without_reply": False,
            })
        result = telegram("sendMessage", fields)
        if legacy_reply:
            parent = result.get("reply_to_message") or {}
            sender = parent.get("from") or {}
            if (parent.get("message_id") != LEGACY_MESSAGE_ID or
                    parent.get("chat", {}).get("id") != chat_id or
                    sender.get("is_bot") is not True or
                    str(sender.get("username", "")).lower() != LEGACY_BOT or
                    SCENARIOS_LINK not in parent.get("text", "")):
                raise RuntimeError("Telegram did not verify the original Warsh alert")
    mid = result.get("message_id")
    if result.get("chat", {}).get("id") != chat_id or type(mid) is not int or mid <= 0 or (message_id is not None and mid != message_id):
        raise RuntimeError("Telegram recipient or message ID could not be confirmed")
    return mid


def load_state():
    if not STATE_PATH.exists():
        return {}
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Invalid Warsh speech state")
    return state


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def send_recorded(state, link, text, chat_id, route_key, legacy_reply=False):
    pending = state.setdefault("pending_sends", {})
    if link in pending:
        raise RuntimeError("Unconfirmed Warsh speech send: reconcile its receipt before retrying")
    # Telegram may accept the message before a network failure. The existing
    # workflow retains this marker across its retry and persists failed runs.
    pending[link] = {"route_key": route_key, "started_at_utc": datetime.now(timezone.utc).isoformat()}
    save_state(state)
    try:
        mid = deliver(text, chat_id, legacy_reply=legacy_reply)
    except TelegramRejected:
        del pending[link]
        save_state(state)
        raise
    receipt = {
        "message_id": mid, "recipient_verified": True, "route_key": route_key,
        "version": SCENARIOS_VERSION if link == SCENARIOS_LINK else 0,
    }
    if legacy_reply:
        receipt["reply_to_message_id"] = LEGACY_MESSAGE_ID
    state.setdefault("receipts", {})[link] = receipt
    del pending[link]
    save_state(state)
    return mid


def upgrade_scenarios(state):
    receipt = state.get("receipts", {}).get(SCENARIOS_LINK)
    if not receipt:
        if not state.get("legacy_scenarios_pending"):
            return None
        if EXPECTED_BOT.lower() != LEGACY_BOT:
            raise ValueError("Configured route does not use the original Warsh bot")
        if SCENARIOS_LINK in state.get("pending_sends", {}):
            raise RuntimeError("Unconfirmed Warsh upgrade: reconcile its receipt before retrying")
        text = speech_message(SCENARIOS_LINK, "", None)
        chat_id, route_key = verified_route()
        followup = send_recorded(state, SCENARIOS_LINK, text, chat_id, route_key, legacy_reply=True)
        print(json.dumps({"upgraded_with_reply": followup, "reply_to_message_id": LEGACY_MESSAGE_ID, "recipient_verified": True}))
        return followup
    if receipt.get("version", 0) >= SCENARIOS_VERSION:
        return None
    if receipt.get("recipient_verified") is not True or not receipt.get("route_key"):
        raise ValueError("Missing verified original Warsh speech receipt")
    message_id = receipt.get("message_id")
    if type(message_id) is not int or message_id <= 0:
        raise ValueError("Missing original Warsh speech message ID")
    chat_id, route_key = verified_route()
    if receipt["route_key"] != route_key:
        raise ValueError("Original Warsh speech receipt belongs to another route")
    text = speech_message(SCENARIOS_LINK, "", None)
    deliver(text, chat_id, message_id)
    receipt.update(version=SCENARIOS_VERSION, edited_at_utc=datetime.now(timezone.utc).isoformat())
    save_state(state)
    print(json.dumps({"edited_in_place": message_id, "recipient_verified": True}))
    return message_id


def process_latest(state):
    rss, _ = fetch(RSS_URL)
    item = latest_warsh_item(rss) or latest_warsh_archive_item()
    last = state.get("last_link")
    if not item:
        state["source_status"] = "연준 RSS·연간 공식 연설목록에서 신규 Warsh 연설 없음"
        save_state(state)
        print(json.dumps({"first_run": not bool(last), "changed": False, "sent": False, "latest": last, "source_status": state["source_status"]}, ensure_ascii=False))
        return
    dt, title, link, pub = item
    if last and link != last and warsh_source(last) and link < last:
        print(json.dumps({"sent": False, "stale_source": link, "latest": last}))
        return
    first_run = not bool(last)
    changed = bool(last and link != last)
    receipts = state.get("receipts", {})
    mid = None
    if link in state.get("pending_sends", {}) and not (link == SCENARIOS_LINK and state.get("legacy_scenarios_pending")):
        raise RuntimeError("Warsh speech has an unconfirmed previous send; reconcile its receipt before retrying")
    if (FORCE_NOTIFY or (changed and link not in receipts)) and not (link == SCENARIOS_LINK and (link in receipts or last == link)):
        text = speech_message(link, title, dt)
        chat_id, route_key = verified_route()
        mid = send_recorded(state, link, text, chat_id, route_key)
    state.update(last_link=link, last_title=title, last_pub_date=pub)
    state.pop("source_status", None)
    save_state(state)
    print(json.dumps({"first_run": first_run, "changed": changed, "sent": bool(mid), "message_id": mid, "latest": link}, ensure_ascii=False))


def main():
    state = load_state()
    if "receipts" not in state and state.get("last_link") == SCENARIOS_LINK and state.get("last_pub_date") == LEGACY_PUB_DATE:
        # Only the legacy baseline that corresponds to the logged original send.
        state["legacy_scenarios_pending"] = True
    state.setdefault("receipts", {})
    process_latest(state)
    upgrade_scenarios(state)
    if state.get("legacy_scenarios_pending") and SCENARIOS_LINK in state["receipts"]:
        del state["legacy_scenarios_pending"]
        save_state(state)


if __name__ == "__main__":
    main()
