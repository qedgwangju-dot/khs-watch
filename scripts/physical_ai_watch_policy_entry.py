#!/usr/bin/env python3
"""Final physical-AI watcher entrypoint with Korean rendering and policy lane."""
from __future__ import annotations

import datetime as dt
import hashlib
import html as html_lib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import display first so its rendering-only Korean hook stays active.
import physical_ai_watch_korean_display as display
import physical_ai_watch_humanoid_component_policy as policy
import physical_ai_watch_hyundai_atlas_rollout as atlas_rollout

base = atlas_rollout.base
_orig_key = base.key
_orig_load_state = base.load_state
_orig_select_diverse = base.select_diverse
_orig_query_news = base.query_news
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = atlas_rollout.ext._same_event

_CZECH_SITE = re.compile(r'체코|Czech|노쇼비체|Nosovice|Nošovice|\bHMMC\b', re.I)
_ATLAS = re.compile(r'아틀라스|\bAtlas\b|Boston\s*Dynamics|보스턴다이내믹스|보스턴\s*다이내믹스', re.I)
_STRONG_CZECH_MILESTONE = re.compile(
    r'(?:시험|테스트|실증|검증).{0,12}(?:시작|개시|완료)|'
    r'(?:배치|투입).{0,12}(?:확정|시작|개시|완료)|'
    r'\b\d{1,5}\s*대\b|설비\s*투자|투자액|capex|발주|본계약|공급\s*계약|'
    r'pilot\s+(?:start|begin)|deployment\s+(?:confirmed|start)|purchase\s+order',
    re.I,
)

# Direct first-party social discovery for Pollen Robotics / Microduck.
# Google News remains the broad discovery layer. Founder posts are material before
# publisher rewrites, so the final existing watcher also tries public X syndication.
# GitHub-hosted runners can be rate-limited by X, therefore Nitter/Twiiit and a
# read-only mirror are discovery fallbacks. Every surfaced item links back to the
# canonical X status and receives a durable status-id dedupe key.
_POLLEN_X_SENTINEL = 'DIRECT_POLLEN_FOUNDER_X'
_POLLEN_X_TIMELINE = 'https://syndication.twitter.com/srv/timeline-profile/screen-name/matth_lapeyre'
_POLLEN_NITTER_FEEDS = [
    'https://twiiit.com/matth_lapeyre/rss',
    'https://nitter.ca/matth_lapeyre/rss',
]
_POLLEN_MIRROR_URL = 'https://www.sotwe.com/matth_lapeyre?lang=en'
_POLLEN_X_SOURCE = 'Matthieu Lapeyre (Pollen Robotics/X)'
_POLLEN_CORE = re.compile(r'Microduck|Reachy\s*Mini|Pollen\s*Robotics|XL330|DYNAMIXEL|ROBOTIS|로보티즈', re.I)
_POLLEN_SIGNAL = re.compile(
    r'\b\d[\d,\.]*\b|production|produce|make|manufactur|mass\s*production|ramp|'
    r'capacity|lead\s*time|shortage|supply|supplier|delivery|deliver|ship|order|backlog|'
    r'motor|actuator|XL330|생산|양산|증설|생산능력|납기|리드타임|부족|공급|배송|출하|주문|모터|액추에이터',
    re.I,
)
_POLLEN_STRONG = re.compile(
    r'20,?000|10,?000|15,?000|XL330|lead\s*time|shortage|supply|capacity|ramp|'
    r'mass\s*production|production|produce|make|delivery|backlog|'
    r'2만|1만|생산|양산|증설|납기|리드타임|부족|공급|배송',
    re.I,
)

# One-time missed-event recovery. It is age-gated and then naturally disappears;
# it exists only so the specific high-signal post that exposed this ingestion gap
# can be delivered once after the fix rather than being silently lost forever.
_POLLEN_RECOVERY_POSTS = {
    '2098466553922494771': (
        'This is how many motors it takes to build 100 Microducks. '
        'And we’re planning to make 20,000 Microduck by early 2027. '
        'To all the makers out there looking for an XL330, sorry 🫂'
    ),
}

if _POLLEN_X_SENTINEL not in base.QUERIES:
    base.QUERIES.append(_POLLEN_X_SENTINEL)
base.OFFICIAL_OR_PRIMARY.add(_POLLEN_X_SOURCE)


def _request_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, text/html,application/xhtml+xml,*/*',
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode('utf-8', errors='ignore')


def _parse_x_date(value: object) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        pass
    try:
        return base.parse_date(text)
    except Exception:
        return None


def _tweet_time_from_id(status_id: str) -> dt.datetime | None:
    try:
        # X/Twitter snowflake timestamp: high bits are milliseconds since epoch.
        ms = (int(status_id) >> 22) + 1288834974657
        return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
    except Exception:
        return None


def _clean_social_text(value: str) -> str:
    value = html_lib.unescape(value or '')
    value = re.sub(r'<br\s*/?>', ' ', value, flags=re.I)
    value = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def _make_pollen_item(status_id: str, text: str, published: dt.datetime | None) -> dict | None:
    text = _clean_social_text(text)
    if not status_id or not text:
        return None
    if not (_POLLEN_CORE.search(text) and _POLLEN_SIGNAL.search(text)):
        return None

    if published is None:
        published = _tweet_time_from_id(status_id)
    cutoff = base.NOW - dt.timedelta(hours=48)
    if published is None or published < cutoff or published > base.NOW + dt.timedelta(minutes=10):
        return None

    if re.search(r'20,?000|20\s*000', text, re.I) and re.search(r'XL330', text, re.I):
        title = 'Pollen Robotics 창업자, Microduck 2027년 초 2만대 생산 계획…XL330 수요 압박'
    elif re.search(r'lead\s*time|shortage|supply|capacity|ramp|납기|부족|공급|증설', text, re.I):
        title = 'Pollen Robotics 창업자, Microduck 생산 확대·액추에이터 수급 신규 업데이트'
    else:
        title = 'Pollen Robotics 창업자, Microduck 생산·물량 계획 신규 업데이트'

    return {
        'title': title,
        'link': f'https://x.com/matth_lapeyre/status/{status_id}',
        'description': text,
        'published': published.isoformat(),
        'source': _POLLEN_X_SOURCE,
        'x_status_id': status_id,
        'direct_primary': True,
    }


def _from_x_syndication() -> list[dict]:
    page = _request_text(_POLLEN_X_TIMELINE)
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        page,
        re.I | re.S,
    )
    if not match:
        return []

    payload = json.loads(html_lib.unescape(match.group(1)))
    entries = (
        payload.get('props', {})
        .get('pageProps', {})
        .get('timeline', {})
        .get('entries', [])
    )
    items: list[dict] = []
    for entry in entries:
        tweet = (entry.get('content') or {}).get('tweet') or {}
        user = tweet.get('user') or {}
        if str(user.get('screen_name') or '').lower() != 'matth_lapeyre':
            continue
        status_id = str(tweet.get('id_str') or tweet.get('id') or '').strip()
        text = str(tweet.get('full_text') or tweet.get('text') or '').strip()
        item = _make_pollen_item(status_id, text, _parse_x_date(tweet.get('created_at')))
        if item:
            items.append(item)
    return items


def _from_nitter_rss(url: str) -> list[dict]:
    raw = _request_text(url)
    root = ET.fromstring(raw)
    items: list[dict] = []
    for node in root.findall('.//item')[:30]:
        link = (node.findtext('link') or '').strip()
        guid = (node.findtext('guid') or '').strip()
        title = node.findtext('title') or ''
        desc = node.findtext('description') or ''
        combined = _clean_social_text(f'{title} {desc}')
        m = re.search(r'/matth_lapeyre/status/(\d+)', f'{link} {guid}', re.I)
        if not m:
            continue
        status_id = m.group(1)
        item = _make_pollen_item(status_id, combined, _parse_x_date(node.findtext('pubDate')))
        if item:
            items.append(item)
    return items


def _from_readonly_mirror() -> list[dict]:
    raw = _request_text(_POLLEN_MIRROR_URL)
    items: list[dict] = []
    # Mirrors change markup often. Use status IDs as stable anchors and inspect a
    # bounded surrounding text window rather than binding to one fragile CSS class.
    matches = list(re.finditer(r'(?:matth_lapeyre|Matthieu[^"\']*)/status/(\d+)', raw, re.I))
    for match in matches[:40]:
        status_id = match.group(1)
        lo = max(0, match.start() - 3000)
        hi = min(len(raw), match.end() + 3000)
        context = _clean_social_text(raw[lo:hi])
        item = _make_pollen_item(status_id, context, _tweet_time_from_id(status_id))
        if item:
            items.append(item)
    return items


def _fetch_pollen_founder_x() -> list[dict]:
    gathered: dict[str, dict] = {}
    errors: list[str] = []

    for label, fn in [
        ('X syndication', _from_x_syndication),
        *[(f'Nitter {url}', lambda u=url: _from_nitter_rss(u)) for url in _POLLEN_NITTER_FEEDS],
        ('read-only mirror', _from_readonly_mirror),
    ]:
        try:
            for item in fn():
                gathered[item['x_status_id']] = item
            if gathered:
                break
        except Exception as exc:
            errors.append(f'{label}: {type(exc).__name__}: {exc}')

    # Recover the specific fresh post that revealed this source gap. Snowflake time
    # keeps it age-gated; after 48h this block produces nothing and cannot backfill history.
    for status_id, text in _POLLEN_RECOVERY_POSTS.items():
        item = _make_pollen_item(status_id, text, _tweet_time_from_id(status_id))
        if item:
            gathered.setdefault(status_id, item)

    if not gathered and errors:
        raise RuntimeError(' | '.join(errors))
    return list(gathered.values())


def query_news_with_pollen_x(q: str) -> list[dict]:
    if q == _POLLEN_X_SENTINEL:
        return _fetch_pollen_founder_x()
    return _orig_query_news(q)


def _is_pollen_direct_item(item: dict) -> bool:
    return bool(item.get('x_status_id') and item.get('source') == _POLLEN_X_SOURCE)


def _is_pollen_direct_text(text: str) -> bool:
    return bool(
        _POLLEN_CORE.search(text)
        and re.search(r'Matthieu\s*Lapeyre|Pollen\s*Robotics|Microduck|XL330', text, re.I)
        and _POLLEN_STRONG.search(text)
    )


def score_with_pollen_x(item: dict) -> int:
    score = _orig_score(item)
    if _is_pollen_direct_item(item):
        # Direct founder volume/supply commentary should outrank derivative rewrites.
        score = max(score, 24)
        text = f"{item.get('title','')} {item.get('description','')}"
        if re.search(r'20,?000|2만|XL330|lead\s*time|shortage|capacity|supply|납기|부족|생산능력', text, re.I):
            score += 6
    return score


def category_with_pollen_x(text: str, group: str) -> str:
    if group == 'robotis' and _is_pollen_direct_text(text):
        return '로보티즈 · Pollen 생산계획·XL330 수급'
    return _orig_category(text, group)


def meaning_with_pollen_x(cat: str) -> str:
    if cat.split(' · ', 1)[-1] == 'Pollen 생산계획·XL330 수급':
        return (
            'Pollen Robotics의 실제 생산 목표가 ROBOTIS XL330 수요로 연결되는 1차 수요 신호입니다. '
            'Microduck 공식 사양은 대당 모터 15개이므로 2만대 계획이 전량 같은 구성을 유지하면 '
            '이론상 최대 30만개 모터 수요가 대응되며, 실제 발주·납품·수율과 생산능력 전환을 추적합니다.'
        )
    return _orig_meaning(cat)


def risk_with_pollen_x(cat: str) -> str:
    if cat.split(' · ', 1)[-1] == 'Pollen 생산계획·XL330 수급':
        return (
            '생산 계획과 ROBOTIS 확정 발주·매출 인식은 다릅니다. 또한 Microduck 초기 배송 지연을 '
            'XL330 부족으로 자동 귀속하지 않고, 사출금형·조립·교정·검사와 액추에이터 납기를 각각 확인합니다.'
        )
    return _orig_risk(cat)


def verification_with_pollen_x(item: dict, group: str, text: str) -> str:
    if group == 'robotis' and _is_pollen_direct_item(item):
        return 'Pollen Robotics 창업자 X 1차 자료 · Microduck 공식 사양 교차확인'
    return _orig_verification(item, group, text)

# One underlying Sep-2026 Czech/Nošovice discussion event was already delivered
# before the persistent event key existed. Future publisher rewrites of that same
# discussion should share this key, while stronger operating milestones keep their
# original keys and can alert normally.
_CZECH_DISCUSSION_KEY = hashlib.sha256(b'hyundai_atlas_czech_nosovice_discussion').hexdigest()
_LEGACY_CZECH_DISCUSSION_TITLES = [
    "현대차, 체코공장도 '아틀라스' 도입 검토…美 이어 글로벌 확대 시동",
    "현대차 체코공장, 휴머노이드 '아틀라스' 도입 추진",
    "현대차, 美 이어 유럽도 휴머노이드 투입…체코공장 '아틀라스' 도입 검토",
]
_LEGACY_CZECH_DISCUSSION_KEYS = {
    _orig_key({'title': title}) for title in _LEGACY_CZECH_DISCUSSION_TITLES
}


def _is_czech_discussion_rewrite(item: dict) -> bool:
    title = item.get('title', '')
    text = f"{title} {item.get('description', '')} {item.get('source', '')}"
    return bool(
        _CZECH_SITE.search(text)
        and _ATLAS.search(text)
        and atlas_rollout.HMG.search(text)
        and not _STRONG_CZECH_MILESTONE.search(title)
    )


def persistent_event_key(item: dict) -> str:
    """Use durable keys for direct social posts and already-reported Czech rewrites."""
    if _is_pollen_direct_item(item):
        return hashlib.sha256(f"x:matth_lapeyre:{item['x_status_id']}".encode()).hexdigest()
    if _is_czech_discussion_rewrite(item):
        return _CZECH_DISCUSSION_KEY
    return _orig_key(item)


def load_state_with_czech_migration() -> dict:
    """Migrate previously delivered Czech discussion rewrites to the durable key."""
    state = _orig_load_state()
    seen = list(state.get('seen', []))
    seen_set = set(seen)
    if seen_set.intersection(_LEGACY_CZECH_DISCUSSION_KEYS):
        if _CZECH_DISCUSSION_KEY not in seen_set:
            seen.append(_CZECH_DISCUSSION_KEY)
        state['seen'] = seen[-3500:]
    return state


def same_event_with_czech_rollout_dedupe(a: dict, b: dict) -> bool:
    """Collapse syndicated Czech Atlas discussion stories without hiding new milestones."""
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'hyundai_atlas_rollout' or b.get('group') != 'hyundai_atlas_rollout':
        return False

    ta = f"{a.get('title', '')} {a.get('description', '')}"
    tb = f"{b.get('title', '')} {b.get('description', '')}"
    title_a = a.get('title', '')
    title_b = b.get('title', '')

    # Same Czech/Nošovice rollout discussion is often rewritten as
    # '검토', '추진', or '글로벌 확대'. Treat these as one event unless
    # either headline contains a genuinely stronger operating milestone.
    if _CZECH_SITE.search(ta) and _CZECH_SITE.search(tb) and _ATLAS.search(ta) and _ATLAS.search(tb):
        if not _STRONG_CZECH_MILESTONE.search(title_a) and not _STRONG_CZECH_MILESTONE.search(title_b):
            return True
    return False


base.query_news = query_news_with_pollen_x
base.score = score_with_pollen_x
base.category = category_with_pollen_x
base.meaning = meaning_with_pollen_x
base.risk = risk_with_pollen_x
base.verification = verification_with_pollen_x
base.key = persistent_event_key
base.load_state = load_state_with_czech_migration
atlas_rollout.ext._same_event = same_event_with_czech_rollout_dedupe


def select_diverse_with_ess_priority(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    """Keep the separate stationary ESS lane from being crowded out by other lanes."""
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    ess = next((x for x in candidates if x.get('group') == 'ess_battery'), None)
    if not ess or any(x.get('key') == ess.get('key') for x in chosen):
        return chosen

    if len(chosen) < limit:
        return [ess, *chosen]

    # Preserve the limit while guaranteeing that one new ESS policy/price event
    # can surface when many physical-AI lanes fire at the same time.
    return [ess, *chosen[:-1]]


def repair_pending_seen(pre_state: dict) -> None:
    """Do not mark high-signal items as seen until they were actually selected.

    The base watcher intentionally seeds every current item on its very first run.
    After that baseline exists, only selected alerts should enter the dedup state;
    otherwise an item that lost the MAX_ALERTS competition can disappear forever
    without ever reaching Telegram.
    """
    if not pre_state.get('seeded') or not base.PENDING_PATH.exists():
        return

    pending = json.loads(base.PENDING_PATH.read_text(encoding='utf-8'))
    old_seen = list(pre_state.get('seen', []))
    old_seen_set = set(old_seen)
    repaired = list(old_seen)
    for key in pending.get('last_selected', []):
        if key not in old_seen_set:
            repaired.append(key)
            old_seen_set.add(key)
    pending['seen'] = repaired[-3500:]
    base.PENDING_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


base.select_diverse = select_diverse_with_ess_priority

if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    repair_pending_seen(pre_state)
    if base.ALERT_PATH.exists():
        rendered = base.ALERT_PATH.read_text(encoding='utf-8')
        base.ALERT_PATH.write_text(display._inline_original_link(rendered), encoding='utf-8')
