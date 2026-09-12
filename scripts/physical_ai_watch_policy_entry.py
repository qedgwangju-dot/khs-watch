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
# Google News remains the broad discovery layer, but founder posts can be material
# before any publisher rewrites them. X's public syndication timeline is polled
# directly so production/volume/lead-time/XL330 signals do not depend on news indexing.
_POLLEN_X_SENTINEL = 'DIRECT_POLLEN_FOUNDER_X'
_POLLEN_X_TIMELINE = 'https://syndication.twitter.com/srv/timeline-profile/screen-name/matth_lapeyre'
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

if _POLLEN_X_SENTINEL not in base.QUERIES:
    base.QUERIES.append(_POLLEN_X_SENTINEL)
base.OFFICIAL_OR_PRIMARY.add(_POLLEN_X_SOURCE)


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


def _fetch_pollen_founder_x() -> list[dict]:
    req = urllib.request.Request(
        _POLLEN_X_TIMELINE,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        page = response.read().decode('utf-8', errors='ignore')

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

    cutoff = base.NOW - dt.timedelta(hours=48)
    items: list[dict] = []
    seen_status: set[str] = set()
    for entry in entries:
        tweet = (entry.get('content') or {}).get('tweet') or {}
        user = tweet.get('user') or {}
        if str(user.get('screen_name') or '').lower() != 'matth_lapeyre':
            continue

        status_id = str(tweet.get('id_str') or tweet.get('id') or '').strip()
        text = str(tweet.get('full_text') or tweet.get('text') or '').strip()
        if not status_id or not text or status_id in seen_status:
            continue
        if not (_POLLEN_CORE.search(text) and _POLLEN_SIGNAL.search(text)):
            continue

        published = _parse_x_date(tweet.get('created_at'))
        # Avoid one-time historical backfill when this direct source is first enabled.
        if published is None or published < cutoff or published > base.NOW + dt.timedelta(minutes=10):
            continue

        seen_status.add(status_id)
        if re.search(r'20,?000|20\s*000', text, re.I) and re.search(r'XL330', text, re.I):
            title = 'Pollen Robotics 창업자, Microduck 2027년 초 2만대 생산 계획…XL330 수요 압박'
        elif re.search(r'lead\s*time|shortage|supply|capacity|ramp|납기|부족|공급|증설', text, re.I):
            title = 'Pollen Robotics 창업자, Microduck 생산 확대·액추에이터 수급 신규 업데이트'
        else:
            title = 'Pollen Robotics 창업자, Microduck 생산·물량 계획 신규 업데이트'

        items.append({
            'title': title,
            'link': f'https://x.com/matth_lapeyre/status/{status_id}',
            'description': text,
            'published': published.isoformat(),
            'source': _POLLEN_X_SOURCE,
            'x_status_id': status_id,
            'direct_primary': True,
        })
    return items


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
