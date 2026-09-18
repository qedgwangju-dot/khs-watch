#!/usr/bin/env python3
"""Final physical-AI watcher with Figure AI first-party milestone detection.

This layer keeps the existing watcher intact and adds a Figure AI lane for
material first-party schedule/AI/commercialization changes. Articles and social
posts are discovery sources; the alert unit is the underlying business/technical
state change, not a specific headline or URL.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_policy_entry as legacy

base = legacy.base
ext = legacy.atlas_rollout.ext

# The old Microduck one-off recovery has already served its purpose. Disable it
# here so the live system contains no permanent specific-post backfill target.
legacy._POLLEN_RECOVERY_POSTS.clear()

_orig_query_news = base.query_news
_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_key = base.key
_orig_clean_title = base.clean_title
_orig_select_diverse = base.select_diverse
_orig_same_event = ext._same_event

FIGURE_X_SENTINEL = 'DIRECT_FIGURE_BRETT_X'
FIGURE_NEWS_SENTINEL = 'DIRECT_FIGURE_OFFICIAL_NEWS'
FIGURE_NEWS_URL = 'https://www.figure.ai/news'
FIGURE_X_TIMELINE = 'https://syndication.twitter.com/srv/timeline-profile/screen-name/adcock_brett'
FIGURE_NITTER_FEEDS = [
    'https://twiiit.com/adcock_brett/rss',
    'https://nitter.ca/adcock_brett/rss',
]
FIGURE_MIRRORS = [
    'https://x-sou.com/ja/u/adcock_brett',
    'https://dailyjournal.news/perfis/ia-tecnologia/adcock_brett',
]
FIGURE_X_SOURCE = 'Brett Adcock (Figure AI/X)'

FIGURE_ID = re.compile(
    r'Figure\s*AI|Figure\s*Robotics|Figure\s*0?3|Figure\s*0?2|Figure\s*0?1|'
    r'@Figure_robot|Brett\s*Adcock|\bHelix(?:[-\s]?0?2)?\b|Figure\s+robot|'
    r'피겨\s*AI|피겨\s*0?3|브렛\s*애드콕',
    re.I,
)
FIGURE_AI = re.compile(
    r'\bAI\b|artificial\s+intelligence|physical\s+intelligence|robotics|humanoid|'
    r'VLA|vision[-\s]*language[-\s]*action|Helix|autonomy|autonomous|model|'
    r'general\s+robotics|human[-\s]*level|reasoning|policy|neural|'
    r'인공지능|피지컬\s*AI|휴머노이드|자율|모델|로봇',
    re.I,
)
FIGURE_SIGNAL = re.compile(
    r'breakthrough|step\s*change|critical\s+update|major\s+update|AI\s+update|'
    r'announc|reveal|release|launch|coming\s+tomorrow|tomorrow|in\s+the\s+morning|'
    r'see\s+you\s+in\s+the\s+AM|performance|benchmark|success\s+rate|latency|'
    r'generaliz|deployment|customer|BMW|production|scale|scaling\s+law|pretrain|zero[-\s]*shot|Index|capabilit|state\s+of\s+the\s+art|'
    r'돌파구|중대\s*업데이트|공개|발표|내일|익일|성능|벤치마크|성공률|지연|스케일링\s*법칙|사전학습|제로샷|'
    r'배치|고객|양산|생산|역량|성능\s*향상',
    re.I,
)
FIGURE_PREANNOUNCE = re.compile(
    r'coming\s+tomorrow|tomorrow|in\s+the\s+morning|see\s+you\s+in\s+the\s+AM|'
    r'release\s+(?:it\s+)?tomorrow|reveal\s+tomorrow|announce\s+tomorrow|'
    r'내일\s*(?:공개|발표|업데이트)|익일\s*(?:공개|발표)|공개\s*예정|발표\s*예정',
    re.I,
)
FIGURE_BREAKTHROUGH = re.compile(
    r'breakthrough|step\s*change|state\s+of\s+the\s+art|critical\s+update|major\s+update|'
    r'new\s+AI\s+update|new\s+model|Helix|general\s+robotics|human[-\s]*level|'
    r'돌파구|중대\s*업데이트|신규\s*모델|성능\s*향상',
    re.I,
)
FIGURE_COMMERCIAL = re.compile(
    r'customer|BMW|deployment|deployed|production|factory|order|contract|revenue|'
    r'고객|배치|생산|공장|주문|수주|계약|매출',
    re.I,
)

FIGURE_ACTUAL_REVEAL = re.compile(
    r'Helix\s*2\.5|zero[-\s]*shot|30[-\s]*home|30개.{0,30}(?:가정|주택)|'
    r'9%[^\n]{0,50}56%|human[-\s]*to[-\s]*humanoid.{0,60}scaling|'
    r'Index.{0,100}(?:scaling|doubl|8x|8×)|제로샷|스케일링\s*법칙',
    re.I | re.S,
)


for q in [
    FIGURE_X_SENTINEL,
    FIGURE_NEWS_SENTINEL,
    '("Figure AI" OR "Figure Robotics" OR "Figure 03" OR Helix OR "Brett Adcock") (breakthrough OR "AI update" OR announcement OR reveal OR tomorrow OR model OR autonomy OR VLA OR performance OR benchmark OR deployment OR customer)',
    '("Figure AI" OR "Figure 03" OR Helix) (BMW OR customer OR deployment OR production OR autonomy OR benchmark OR success rate OR generalization OR "general robotics")',
    '("Figure AI" OR Helix OR Index) ("scaling law" OR pretraining OR "zero shot" OR "unseen homes" OR "human-to-humanoid" OR "data doubling")',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)
base.OFFICIAL_OR_PRIMARY.update({FIGURE_X_SOURCE, 'Figure', 'Figure AI', 'Figure Robotics'})
base.TRUSTED.update({'Reuters', 'TechCrunch', 'The Robot Report'})


def _is_figure_text(text: str) -> bool:
    return bool(FIGURE_ID.search(text) and FIGURE_AI.search(text) and FIGURE_SIGNAL.search(text))


def _make_figure_item(status_id: str, text: str, published: dt.datetime | None) -> dict | None:
    text = legacy._clean_social_text(text)
    if not status_id or not text:
        return None
    # On Brett Adcock's own feed, explicit Figure naming is not required if the
    # post clearly refers to AI/robotics and contains a material milestone signal.
    if not (FIGURE_AI.search(text) and FIGURE_SIGNAL.search(text)):
        return None
    if published is None:
        published = legacy._tweet_time_from_id(status_id)
    cutoff = base.NOW - dt.timedelta(hours=48)
    if published is None or published < cutoff or published > base.NOW + dt.timedelta(minutes=10):
        return None

    if FIGURE_ACTUAL_REVEAL.search(text):
        title = 'Figure AI, Helix 2.5 실제 공개…휴머노이드 스케일링 법칙 확인'
    elif FIGURE_PREANNOUNCE.search(text) and FIGURE_BREAKTHROUGH.search(text):
        title = 'Figure AI, AI 돌파구 공개 예고…익일 발표 예정'
    elif FIGURE_BREAKTHROUGH.search(text):
        title = 'Figure AI, 신규 AI 돌파구·성능 업데이트 공개'
    elif FIGURE_COMMERCIAL.search(text):
        title = 'Figure AI, 고객·현장 배치 상용화 단계 변화'
    else:
        title = 'Figure AI, AI·휴머노이드 핵심 업데이트'

    return {
        'title': title,
        'link': f'https://x.com/adcock_brett/status/{status_id}',
        'description': text,
        'published': published.isoformat(),
        'source': FIGURE_X_SOURCE,
        'x_status_id': status_id,
        'direct_primary': True,
    }


def _from_figure_x_syndication() -> list[dict]:
    page = legacy._request_text(FIGURE_X_TIMELINE)
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', page, re.I | re.S)
    if not m:
        return []
    payload = json.loads(legacy.html_lib.unescape(m.group(1)))
    entries = payload.get('props', {}).get('pageProps', {}).get('timeline', {}).get('entries', [])
    out: list[dict] = []
    for entry in entries:
        tweet = (entry.get('content') or {}).get('tweet') or {}
        user = tweet.get('user') or {}
        if str(user.get('screen_name') or '').lower() != 'adcock_brett':
            continue
        sid = str(tweet.get('id_str') or tweet.get('id') or '').strip()
        text = str(tweet.get('full_text') or tweet.get('text') or '').strip()
        item = _make_figure_item(sid, text, legacy._parse_x_date(tweet.get('created_at')))
        if item:
            out.append(item)
    return out


def _from_figure_nitter(url: str) -> list[dict]:
    raw = legacy._request_text(url)
    root = ET.fromstring(raw)
    out: list[dict] = []
    for node in root.findall('.//item')[:40]:
        link = (node.findtext('link') or '').strip()
        guid = (node.findtext('guid') or '').strip()
        combined = legacy._clean_social_text(f"{node.findtext('title') or ''} {node.findtext('description') or ''}")
        m = re.search(r'/adcock_brett/status/(\d+)', f'{link} {guid}', re.I)
        if not m:
            continue
        item = _make_figure_item(m.group(1), combined, legacy._parse_x_date(node.findtext('pubDate')))
        if item:
            out.append(item)
    return out


def _from_figure_mirror(url: str) -> list[dict]:
    raw = legacy._request_text(url)
    out: list[dict] = []
    # Different mirrors use different markup; status id is the stable anchor.
    matches = list(re.finditer(r'(?:adcock_brett[^\d]{0,120}status[/=: ]+|/status/)(\d{15,22})', raw, re.I))
    for m in matches[:60]:
        sid = m.group(1)
        lo = max(0, m.start() - 3500)
        hi = min(len(raw), m.end() + 3500)
        context = legacy._clean_social_text(raw[lo:hi])
        item = _make_figure_item(sid, context, legacy._tweet_time_from_id(sid))
        if item:
            out.append(item)
    return out


def _fetch_figure_founder_x() -> list[dict]:
    gathered: dict[str, dict] = {}
    errors: list[str] = []
    sources = [
        ('X syndication', _from_figure_x_syndication),
        *[(f'Nitter {u}', lambda u=u: _from_figure_nitter(u)) for u in FIGURE_NITTER_FEEDS],
        *[(f'mirror {u}', lambda u=u: _from_figure_mirror(u)) for u in FIGURE_MIRRORS],
    ]
    for label, fn in sources:
        try:
            for item in fn():
                gathered[item['x_status_id']] = item
            if gathered:
                break
        except Exception as exc:
            errors.append(f'{label}: {type(exc).__name__}: {exc}')
    if not gathered and errors:
        raise RuntimeError(' | '.join(errors))
    return list(gathered.values())

MONTHS = {
    'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
    'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12,
}


def _figure_date_from_text(text: str) -> dt.datetime | None:
    m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\\s+(\\d{1,2}),\\s+(20\\d{2})', text)
    if not m:
        return None
    return dt.datetime(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)), 12, 0, tzinfo=dt.timezone.utc)


def _fetch_figure_official_news() -> list[dict]:
    index = legacy._request_text(FIGURE_NEWS_URL)
    slugs: list[str] = []
    for m in re.finditer(r"href=['\\\"](/news/[A-Za-z0-9_-]+)['\\\"]", index, re.I):
        path = m.group(1)
        if path == '/news' or path in slugs:
            continue
        slugs.append(path)
    out: list[dict] = []
    cutoff = base.NOW - dt.timedelta(days=4)
    for path in slugs[:30]:
        try:
            url = f'https://www.figure.ai{path}'
            raw = legacy._request_text(url)
            clean = legacy._clean_social_text(raw)
            pub = _figure_date_from_text(clean)
            if pub is None or pub < cutoff or pub > base.NOW + dt.timedelta(days=1):
                continue
            h1 = re.search(r'<h1[^>]*>(.*?)</h1>', raw, re.I | re.S)
            title = legacy._clean_social_text(h1.group(1) if h1 else '')
            if not title:
                mt = re.search(r'<title[^>]*>(.*?)</title>', raw, re.I | re.S)
                title = legacy._clean_social_text(mt.group(1) if mt else path.rsplit('/', 1)[-1].replace('-', ' '))
            text = f'{title} {clean}'
            if not _is_figure_text(text):
                continue
            out.append({
                'title': title,
                'link': url,
                'description': clean[:7000],
                'published': pub.isoformat(),
                'source': 'Figure AI',
                'direct_primary': True,
                'figure_official_slug': path.rsplit('/', 1)[-1],
            })
        except Exception:
            continue
    return out


def query_news(q: str) -> list[dict]:
    if q == FIGURE_X_SENTINEL:
        return _fetch_figure_founder_x()
    if q == FIGURE_NEWS_SENTINEL:
        return _fetch_figure_official_news()
    return _orig_query_news(q)


def topic_group(text: str) -> str | None:
    if _is_figure_text(text):
        return 'figure_ai'
    return _orig_topic_group(text)


def _is_figure_direct(item: dict) -> bool:
    return bool(item.get('x_status_id') and item.get('source') == FIGURE_X_SOURCE)


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'figure_ai':
        return _orig_score(item)
    s = 19
    if base.NUMERIC.search(text):
        s += 3
    if _is_figure_direct(item) or item.get('source') in {'Figure', 'Figure AI', 'Figure Robotics'}:
        s += 8
    elif item.get('source') in base.TRUSTED:
        s += 3
    if FIGURE_PREANNOUNCE.search(text):
        s += 8
    if FIGURE_BREAKTHROUGH.search(text):
        s += 8
    if re.search(r'benchmark|success\s+rate|latency|generaliz|hours?\s+without\s+(?:a\s+)?failure|벤치마크|성공률|지연', text, re.I):
        s += 7
    if re.search(r'scaling\s+law|human[-\s]*to[-\s]*humanoid|Index.{0,80}(?:doubl|8x|8×)|zero[-\s]*shot.{0,80}(?:home|generaliz)|'
                 r'스케일링\s*법칙|제로샷.{0,80}(?:가정|주택|일반화)|30개.{0,40}(?:가정|주택)|9%[^\n]{0,40}56%', text, re.I | re.S):
        s += 12
    if FIGURE_COMMERCIAL.search(text):
        s += 6
    return s


def _figure_subcat(text: str) -> str:
    if re.search(r'scaling\s+law|human[-\s]*to[-\s]*humanoid|Index.{0,80}(?:doubl|8x|8×)|zero[-\s]*shot.{0,80}(?:home|generaliz)|'
                 r'스케일링\s*법칙|제로샷.{0,80}(?:가정|주택|일반화)|30개.{0,40}(?:가정|주택)|9%[^\n]{0,40}56%', text, re.I | re.S):
        return '인간→휴머노이드 스케일링 법칙'
    if FIGURE_PREANNOUNCE.search(text):
        return '공식 사전예고·공개 시간표'
    if FIGURE_COMMERCIAL.search(text) and re.search(r'customer|BMW|deployment|order|contract|revenue|고객|배치|수주|계약|매출', text, re.I):
        return '고객·현장 배치 상용화'
    if re.search(r'data|dataset|compute|GPU|Nscale|Index|데이터|연산', text, re.I):
        return '데이터·연산 확장'
    return 'AI 모델·성능 돌파구'


def category(text: str, group: str) -> str:
    if group == 'figure_ai':
        return f'피겨 AI · {_figure_subcat(text)}'
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '인간→휴머노이드 스케일링 법칙':
        return '인간 행동 사전학습 데이터가 늘어날수록 다음 로봇 행동 예측 성능이 예측 가능하게 개선되는지를 보는 핵심 재평가 신호입니다. 데이터 배수·성공률·미지 환경 수·모델 크기·연산량을 함께 추적해 실제 로봇 일반화가 스케일링되는지 확인합니다.'
    if raw == '공식 사전예고·공개 시간표':
        return '피겨 AI 경영진이 공개 시점을 직접 예고한 시간표 신호입니다. 다음 공개에서 Helix 모델 변화, 작업 성공률·지연시간·일반화 범위, 실제 로봇 자율작업과 고객 배치까지 무엇이 구체화되는지 연속 추적합니다.'
    if raw == 'AI 모델·성능 돌파구':
        return '피겨 AI의 기술 업데이트가 데모를 넘어 실제 자율작업 성능 개선으로 이어지는지 보는 신호입니다. 모델명, 벤치마크, 실패율, 사람 개입률, 연속 가동시간과 실제 Figure 03 적용 여부를 확인합니다.'
    if raw == '고객·현장 배치 상용화':
        return 'AI 성능 향상이 실제 고객·공장·가정 배치와 반복 주문으로 이어지는 단계입니다. 고객 실명, 배치 대수, 작업시간, 가동률과 매출 인식 경로를 확인합니다.'
    if raw == '데이터·연산 확장':
        return '데이터와 연산 투입이 Helix의 차세대 성능으로 전환되는지 보는 선행 신호입니다. 데이터 증가율·GPU 투입과 실제 모델 성능·현장 작업 성공률의 연결을 확인합니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '인간→휴머노이드 스케일링 법칙':
        return '스케일링 법칙은 데이터 범위와 평가 과제에 종속될 수 있습니다. 가장 먼저 볼 실패 지표는 데이터 2배 증가에도 미지 환경 성공률이 더 이상 개선되지 않거나 모델·연산 증가 대비 성능 향상이 둔화되는지입니다.'
    if raw == '공식 사전예고·공개 시간표':
        return '사전예고는 기술 성과가 검증됐다는 뜻이 아닙니다. 가장 현실적인 실패 경로는 공개 내용이 단일 데모에 그치고 정량 성능·고객·배치 정보가 없는 경우이며, 실제 공개 후 별도 신규 사건으로 재평가합니다.'
    if raw == 'AI 모델·성능 돌파구':
        return '시연 성공과 반복 가능한 현장 성능은 다릅니다. 성공률·지연시간·사람 개입률·연속 가동·안전 검증이 공개되지 않으면 기술 재평가를 제한합니다.'
    if raw == '고객·현장 배치 상용화':
        return '파일럿과 대량 상용화는 다릅니다. 배치 대수·계약금액·반복 주문·가동률이 확인되지 않으면 매출 민감도는 낮게 봅니다.'
    if raw == '데이터·연산 확장':
        return '데이터·GPU 투입 증가가 곧 성능 향상을 보장하지 않습니다. 학습 효율과 실제 로봇 작업 성능이 따라오지 않으면 자본집약도만 높아질 수 있습니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group != 'figure_ai':
        return _orig_verification(item, group, text)
    if _is_figure_direct(item):
        return '브렛 애드콕 엑스(X) 1차 자료 · 실제 공개 내용은 피겨 AI 공식자료로 후속 확인'
    if item.get('source') in {'Figure', 'Figure AI', 'Figure Robotics'}:
        return '피겨 AI 공식자료'
    if item.get('source') in base.TRUSTED:
        return '신뢰 매체 보도 · 피겨 AI/브렛 애드콕 1차 자료 교차확인'
    return '보도 단계 · 피겨 AI 공식자료 재확인 필요'


def clean_title(title: str, source: str) -> str:
    if FIGURE_ACTUAL_REVEAL.search(title):
        return '피겨 AI, Helix 2.5 실제 공개…인간→휴머노이드 스케일링 법칙 확인'
    if re.search(r'scaling\s+law|human[-\s]*to[-\s]*humanoid|zero[-\s]*shot.{0,50}(?:home|generaliz)|'
                 r'제로샷.{0,50}(?:가정|주택|일반화)|Helix\s*2\.5.{0,80}30개', title, re.I):
        return '피겨 AI, 인간→휴머노이드 스케일링 법칙 확인…미지 환경 일반화 개선'
    if re.search(r'Figure\s*AI|Figure\s*0?3|Helix|Brett\s*Adcock', title, re.I):
        if FIGURE_PREANNOUNCE.search(title):
            return '피겨 AI, AI 돌파구 공개 예고…익일 발표 예정'
    return _orig_clean_title(title, source)


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')}"
    if re.search(r'Helix\\s*2\\.5|30[-\\s]*home|30개.{0,40}(?:가정|주택)|9%[^\\n]{0,40}56%|human[-\\s]*to[-\\s]*humanoid.{0,40}scaling|스케일링\\s*법칙', text, re.I | re.S):
        return hashlib.sha256(b'figure-ai|helix-2.5|human-to-humanoid-scaling-law').hexdigest()
    if _is_figure_direct(item):
        return hashlib.sha256(f"x:adcock_brett:{item['x_status_id']}".encode()).hexdigest()
    return _orig_key(item)


def same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'figure_ai' or b.get('group') != 'figure_ai':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    # Syndicated copies of one teaser are one event. The actual next-day reveal is
    # intentionally NOT collapsed into the teaser because it changes the state.
    if FIGURE_PREANNOUNCE.search(ta) and FIGURE_PREANNOUNCE.search(tb):
        return True
    scaling = r'scaling\s+law|human[-\s]*to[-\s]*humanoid|Helix\s*2\.5|30[-\s]*home|Index'
    if re.search(scaling, ta, re.I) and re.search(scaling, tb, re.I):
        return True
    return False


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    figure = next((x for x in candidates if x.get('group') == 'figure_ai'), None)
    if not figure or any(x.get('key') == figure.get('key') for x in chosen):
        return chosen
    if len(chosen) < limit:
        return [figure, *chosen]
    return [figure, *chosen[:-1]]


base.query_news = query_news
base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.clean_title = clean_title
base.key = key
base.select_diverse = select_diverse
ext._same_event = same_event

if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    legacy.repair_pending_seen(pre_state)
    if base.ALERT_PATH.exists():
        rendered = base.ALERT_PATH.read_text(encoding='utf-8')
        base.ALERT_PATH.write_text(legacy.display._inline_original_link(rendered), encoding='utf-8')
