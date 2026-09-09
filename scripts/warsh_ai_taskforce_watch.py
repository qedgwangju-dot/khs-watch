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
from datetime import datetime, timezone
from pathlib import Path

FED_URL = "https://www.federalreserve.gov/monetarypolicy/productivity-and-jobs-task-force.htm"
STATE_PATH = Path("data/warsh_ai_taskforce_watch_state.json")
UA = "Mozilla/5.0 (compatible; khs-watch/1.2; +https://github.com/qedgwangju-dot/khs-watch)"
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
    lines=core.splitlines()[:10]
    return '\n'.join([
        '[연준 AI 생산성·고용 태스크포스 변화]',
        '워시가 AI를 잠재적으로 새로운 생산요소로 본 뒤 나온 연준의 공식 업데이트입니다.','',
        *[f"• {html.escape(x)}" for x in lines], '',
        '<b>판정</b>',
        '• AI가 잠재성장률·생산성·고용·중립금리 판단에 실제 반영되는 단계로 넘어가는지 확인합니다.','',
        '<b>원천</b>',link('Federal Reserve 공식자료',FED_URL)
    ])


def gartner_message(item):
    return '\n'.join([
        '[AI 고용 구조 전망 변화] Gartner','',
        f"• {html.escape(item['title'])}",'',
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
    print(json.dumps({'first_run':first,'fed_changed':fed_changed,'gartner_changed':g_changed,'gartner_latest':latest['title'] if latest else None},ensure_ascii=False))

if __name__ == "__main__": main()
