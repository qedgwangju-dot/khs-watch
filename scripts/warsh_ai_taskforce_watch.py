#!/usr/bin/env python3
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

FED_URL = "https://www.federalreserve.gov/monetarypolicy/productivity-and-jobs-task-force.htm"
STATE_PATH = Path("data/warsh_ai_taskforce_watch_state.json")
UA = "Mozilla/5.0 (compatible; khs-watch/1.3; +https://github.com/qedgwangju-dot/khs-watch)"
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
EXPECTED_BOT = (os.getenv("EXPECTED_BOT_USERNAME") or "khs8879887988798879_bot").strip().lstrip("@")
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "0") == "1"

FED_KEYWORDS = [
    "artificial intelligence", "general-purpose technologies", "productivity", "jobs",
    "employment", "inflation", "task force", "findings", "recommendations", "report",
    "productive capacity", "economic impact", "policy judgments"
]
GARTNER_QUERY='site:gartner.com Gartner (AI jobs OR workforce OR productivity OR employment OR rehire OR hiring)'
GARTNER_KEYWORDS=["AI","job","jobs","workforce","productivity","employment","rehire","hiring","role","roles"]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def clean_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def meaningful_text(text: str) -> str:
    lines = []
    for s in re.split(r"\n+|(?<=[.!?])\s+", text):
        s = re.sub(r"\s+", " ", s).strip()
        low = s.lower()
        if 20 <= len(s) <= 600 and any(k in low for k in FED_KEYWORDS):
            lines.append(s)
    return "\n".join(dict.fromkeys(lines))


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def gartner_items():
    q=urllib.parse.urlencode({'q':GARTNER_QUERY,'hl':'en-US','gl':'US','ceid':'US:en'})
    root=ET.fromstring(fetch('https://news.google.com/rss/search?'+q))
    items=[]
    for item in root.findall('./channel/item')[:30]:
        title=html.unescape((item.findtext('title') or '').strip())
        link=(item.findtext('link') or '').strip()
        source_node=item.find('source')
        source=html.unescape((source_node.text or '').strip()) if source_node is not None else ''
        pub=item.findtext('pubDate') or ''
        try:dt=email.utils.parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception:dt=datetime.min.replace(tzinfo=timezone.utc)
        low=title.lower()
        if source.lower()=='gartner' and any(k.lower() in low for k in GARTNER_KEYWORDS):
            items.append({'title':title,'url':link,'published':dt.isoformat()})
    items.sort(key=lambda x:x['published'])
    return items


def get_bot_username() -> str:
    if not TOKEN: raise RuntimeError("Telegram token missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    return str((data.get("result") or {}).get("username") or "")


def link(label,url):return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'


def has_korean(text: str) -> bool:
    return bool(re.search(r'[가-힣]', text or ''))


def gartner_title_ko(title: str) -> str:
    """Never expose an untranslated English Gartner headline in Telegram."""
    raw=(title or '').strip()
    low=raw.lower()
    known=[
        (r'identifies?\s+4\s+shifts?.*future of work', 'Gartner, 미래 일자리·업무 구조를 바꿀 4가지 변화 제시'),
        (r'more jobs than it eliminates.*2028|create more jobs than.*2028', 'Gartner, 2028년부터 AI가 없애는 일자리보다 더 많은 일자리를 창출할 것으로 전망'),
        (r'30%.*laid off.*ai.*rehir|rehir.*30%.*2029', 'Gartner, AI 대체로 감원한 직원의 최대 30%가 2029년까지 재채용될 수 있다고 전망'),
        (r'skills strategy.*falling behind ai evolution', 'Gartner, AI 진화 속도를 따라가지 못하는 인력 기술 전략을 경고'),
        (r'workforce costs?', 'Gartner, AI 도입에 따른 숨은 인력 비용 증가 가능성을 경고'),
        (r'role redesign|job redesign|job chaos', 'Gartner, AI 확산에 맞춘 직무 재설계 지연과 고용 구조 혼선을 경고'),
        (r'38%.*chro.*cio|chro.*cio.*future of work', 'Gartner, 인사·정보기술 책임자의 AI 일자리 영향 인식 격차를 경고'),
        (r'job impacts?', 'Gartner, AI가 일자리 구조에 미치는 영향 전망을 업데이트'),
        (r'labor market|employment', 'Gartner, AI와 고용·노동시장 구조 전망을 업데이트'),
        (r'workforce.*ai|ai.*workforce', 'Gartner, AI 도입에 따른 인력 구조 변화 전망을 업데이트'),
    ]
    for pat,ko in known:
        if re.search(pat,low,re.I):
            return ko
    if has_korean(raw):
        return raw
    return 'Gartner, AI 고용·인력 구조 전망을 업데이트'


def canonical_gartner_item(item):
    """Only a directly attributable, dated Gartner Newsroom release can trigger."""
    raw_url = str(item.get('url') or '').strip()
    parsed = urllib.parse.urlsplit(raw_url)
    if (parsed.hostname or '').lower() not in {
        'gartner.com', 'www.gartner.com', 'gcom.pdo.aws.gartner.com'
    }:
        return None
    path = re.sub(r'/+    """Summarize topic changes in Korean instead of forwarding raw English Fed text."""
    low=(core or '').lower()
    bullets=[]
    if 'productiv' in low:
        bullets.append('• 생산성과 잠재 생산능력 관련 공식 내용에 변화가 확인됐습니다.')
    if 'job' in low or 'employment' in low:
        bullets.append('• 고용과 직무 구조에 대한 태스크포스 관련 내용에 변화가 확인됐습니다.')
    if 'artificial intelligence' in low or 'general-purpose technologies' in low:
        bullets.append('• AI가 경제의 새로운 생산요소가 될 수 있는지에 관한 공식 검토 내용이 갱신됐습니다.')
    if 'inflation' in low or 'policy judgment' in low or 'economic impact' in low:
        bullets.append('• 생산성·고용 변화가 물가와 통화정책 판단에 미치는 영향에 관한 내용이 포함돼 있습니다.')
    if not bullets:
        bullets.append('• 연준의 AI 생산성·고용 태스크포스 공식 페이지에 새로운 변화가 확인됐습니다.')
    return bullets[:4]


def send(text: str):
    if not TOKEN or not CHAT_ID: raise RuntimeError("Telegram token/chat id missing")
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}")
    payload = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text[:4090], "parse_mode":"HTML", "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.loads(r.read().decode("utf-8"))
    if not result.get("ok"): raise RuntimeError(f"Telegram send failed: {result}")
    message_id = (result.get("result") or {}).get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram message_id 확인 실패 — 중복 상태를 갱신하지 않습니다.")
    return message_id


def load_state():
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fed_message(core):
    return '\n'.join([
        '[연준 AI 생산성·고용 태스크포스 변화]','',
        *fed_update_ko(core), '',
        '<b>판정</b>',
        '• AI가 잠재성장률·생산성·고용·중립금리 판단에 실제 반영되는 단계로 넘어가는지 확인합니다.','',
        '<b>원천</b>',link('미국 연방준비제도 공식자료',FED_URL)
    ])


def gartner_message(item):
    return '\n'.join([
        '[AI 고용 구조 전망 변화] Gartner','',
        f"• {html.escape(gartner_title_ko(item['title']))}",'',
        '<b>왜 중요하나</b>',
        '• 워시가 던진 “AI가 노동을 대체하는가, 보완하는가”라는 질문에 직접 연결되는 구조적 고용 전망입니다.',
        '• Gartner 전망은 매월 고용지표가 아니라 중장기 직무 재설계·재채용·생산성 구조가 바뀔 때만 알립니다.',
        '• 총고용 숫자보다 직무 변화 속도, 재채용 비용, AI 인력 임금 프리미엄이 기업의 실제 투자수익률을 바꾸는지 확인합니다.','',
        '<b>원천</b>',link('Gartner 원문',item['url'])
    ])


def main():
    old = load_state()
    new = dict(old)
    errors = []

    # The Fed taskforce and Gartner feeds fail independently; a single outage cannot
    # erase another source's baseline or cause a false Gartner change.
    fed_changed = False
    try:
        text = clean_text(fetch(FED_URL))
        core = meaningful_text(text)
        fed_fp = fingerprint(core)
        old_fp = old.get('fed_fingerprint') or old.get('fingerprint')
        fed_changed = bool(old_fp and fed_fp != old_fp)
        if FORCE_NOTIFY or fed_changed:
            send(fed_message(core))
        new['fed_fingerprint'] = fed_fp
    except Exception as exc:
        errors.append(f"연준 공식 태스크포스 조회 실패: {type(exc).__name__}")

    gartner_sent = False
    message_id = None
    gartner_added = []
    gartner_seen = list(old.get('gartner_seen_keys') or [])
    seen = set(gartner_seen)
    migration = not bool(old.get('gartner_dedup_version'))
    candidates = []
    try:
        source_items = gartner_items()
        for item in source_items:
            article = canonical_gartner_item(item)
            if article and article['key'] not in {x['key'] for x in candidates}:
                candidates.append(article)
        candidates.sort(key=lambda x: (x['published'], x['key']))
    except Exception as exc:
        errors.append(f"Gartner 공식자료 조회 실패: {type(exc).__name__}")

    if candidates:
        if migration:
            # Seed all currently visible official releases. Never re-alert on
            # articles published before the dedup upgrade.
            for article in candidates:
                if article['key'] not in seen:
                    seen.add(article['key'])
                    gartner_seen.append(article['key'])
                    gartner_added.append(article['key'])
            new['gartner_dedup_version'] = 2
        else:
            for article in candidates:
                if article['key'] in seen:
                    continue
                if not gartner_recent_enough(article):
                    # Resurfaced historical items are recorded silently.
                    seen.add(article['key'])
                    gartner_seen.append(article['key'])
                    gartner_added.append(article['key'])
                    continue
                # One genuinely new Gartner article per iteration, not one per
                # changed feed-headline or rotating Google News RSS link.
                message_id = send(gartner_message(article))
                gartner_sent = True
                seen.add(article['key'])
                gartner_seen.append(article['key'])
                gartner_added.append(article['key'])
                deliveries = list(old.get('gartner_deliveries') or [])
                deliveries.append({
                    'key':article['key'], 'message_id':message_id,
                    'url':article['url'], 'sent_at_utc':datetime.now(timezone.utc).isoformat()
                })
                new['gartner_deliveries'] = deliveries[-150:]
                break

        latest = candidates[-1]
        new['gartner_latest'] = {
            'title':latest['title'], 'url':latest['url'],
            'published':latest['published']
        }
        new['gartner_latest_key'] = latest['key']
        new['gartner_seen_keys'] = gartner_seen[-500:]
        new['gartner_source_status'] = 'Gartner 공식 Newsroom 검증 완료'
    else:
        # No official articles: hold all old Gartner baseline and avoid Google
        # News fallback alerts. A transient RSS/HTML failure is not a news event.
        new['gartner_source_status'] = 'Gartner 공식자료 없음·신규 판정 보류'
        if migration:
            new.pop('gartner_dedup_version', None)

    if errors:
        new['last_errors'] = errors
    else:
        new.pop('last_errors', None)

    if new != old:
        save_state(new)
    print(json.dumps({
        'first_run':not bool(old),
        'fed_changed':fed_changed,
        'gartner_dedup_migration':migration and bool(candidates),
        'gartner_candidates':len(candidates),
        'gartner_new_records':len(gartner_added),
        'gartner_sent':gartner_sent,
        'message_id':message_id,
        'gartner_source_status':new.get('gartner_source_status'),
        'errors':errors,
    }, ensure_ascii=False))

if __name__ == "__main__": main()
, '', parsed.path.lower())
    match = re.search(r'/en/newsroom/press-releases/(20\d{2})-(\d{1,2})-(\d{1,2})-', path)
    if not match:
        return None
    try:
        date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
    except ValueError:
        return None
    if date.date() > datetime.now(timezone.utc).date():
        return None
    title = str(item.get('title') or '').strip()
    if len(title) < 20:
        return None
    # All mirrors and query-string variants share one permanent Gartner path.
    normalized_url = 'https://www.gartner.com' + path
    return {
        'key': 'gartner:' + path,
        'title': title,
        'url': normalized_url,
        'published': date.isoformat(),
    }


def gartner_recent_enough(item, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        date = datetime.fromisoformat(item['published'])
    except (KeyError, ValueError, TypeError):
        return False
    return timedelta(days=-4) <= now - date <= timedelta(days=4) and date <= now


def fed_update_ko(core: str):
    """Summarize topic changes in Korean instead of forwarding raw English Fed text."""
    low=(core or '').lower()
    bullets=[]
    if 'productiv' in low:
        bullets.append('• 생산성과 잠재 생산능력 관련 공식 내용에 변화가 확인됐습니다.')
    if 'job' in low or 'employment' in low:
        bullets.append('• 고용과 직무 구조에 대한 태스크포스 관련 내용에 변화가 확인됐습니다.')
    if 'artificial intelligence' in low or 'general-purpose technologies' in low:
        bullets.append('• AI가 경제의 새로운 생산요소가 될 수 있는지에 관한 공식 검토 내용이 갱신됐습니다.')
    if 'inflation' in low or 'policy judgment' in low or 'economic impact' in low:
        bullets.append('• 생산성·고용 변화가 물가와 통화정책 판단에 미치는 영향에 관한 내용이 포함돼 있습니다.')
    if not bullets:
        bullets.append('• 연준의 AI 생산성·고용 태스크포스 공식 페이지에 새로운 변화가 확인됐습니다.')
    return bullets[:4]


def send(text: str):
    if not TOKEN or not CHAT_ID: raise RuntimeError("Telegram token/chat id missing")
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}")
    payload = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text[:4090], "parse_mode":"HTML", "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.loads(r.read().decode("utf-8"))
    if not result.get("ok"): raise RuntimeError(f"Telegram send failed: {result}")


def load_state():
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fed_message(core):
    return '\n'.join([
        '[연준 AI 생산성·고용 태스크포스 변화]','',
        *fed_update_ko(core), '',
        '<b>판정</b>',
        '• AI가 잠재성장률·생산성·고용·중립금리 판단에 실제 반영되는 단계로 넘어가는지 확인합니다.','',
        '<b>원천</b>',link('미국 연방준비제도 공식자료',FED_URL)
    ])


def gartner_message(item):
    return '\n'.join([
        '[AI 고용 구조 전망 변화] Gartner','',
        f"• {html.escape(gartner_title_ko(item['title']))}",'',
        '<b>왜 중요하나</b>',
        '• 워시가 던진 “AI가 노동을 대체하는가, 보완하는가”라는 질문에 직접 연결되는 구조적 고용 전망입니다.',
        '• Gartner 전망은 매월 고용지표가 아니라 중장기 직무 재설계·재채용·생산성 구조가 바뀔 때만 알립니다.',
        '• 총고용 숫자보다 직무 변화 속도, 재채용 비용, AI 인력 임금 프리미엄이 기업의 실제 투자수익률을 바꾸는지 확인합니다.','',
        '<b>원천</b>',link('Gartner 원문',item['url'])
    ])


def main():
    text = clean_text(fetch(FED_URL)); core = meaningful_text(text); fed_fp=fingerprint(core)
    gis=gartner_items(); latest=gis[-1] if gis else None
    old=load_state(); old_fed=old.get('fed_fingerprint') or old.get('fingerprint')
    first=not bool(old)
    fed_changed=old_fed not in (None,fed_fp)
    latest_key=f"{latest['published']}|{latest['title']}" if latest else None
    old_g=old.get('gartner_latest_key')
    g_changed=(old_g is not None and latest_key is not None and old_g!=latest_key)

    if FORCE_NOTIFY or (not first and fed_changed):send(fed_message(core))
    if FORCE_NOTIFY or (not first and g_changed):send(gartner_message(latest))

    save_state({'fed_fingerprint':fed_fp,'gartner_latest_key':latest_key,'gartner_latest':latest})
    print(json.dumps({'first_run':first,'fed_changed':fed_changed,'gartner_changed':g_changed,'gartner_latest_ko':gartner_title_ko(latest['title']) if latest else None},ensure_ascii=False))

if __name__ == "__main__": main()
