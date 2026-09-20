#!/usr/bin/env python3
import argparse
import hashlib
import html as html_lib
import re
import urllib.parse
import xml.etree.ElementTree as ET

import war_peace_reconstruction_watch_finalcompact as prev

watch = prev.watch
runner = prev.runner
base = prev.base

ENERGY_ATTACK_SENTINEL = "__RUSSIA_UKRAINE_ENERGY_ATTACK_WIDE__"

ENERGY_ATTACK_QUERIES = [
    '"Russia refinery" drone attack fire Ukraine',
    'Russia oil refinery drone attack shutdown processing fire Ukraine',
    'Russia oil depot fuel depot storage drone attack fire Ukraine',
    'Russia pipeline pumping station drone attack oil Ukraine',
    'Russia oil terminal port drone attack Ust-Luga Primorsk Tuapse Ukraine',
    'Russia gas compressor LNG terminal drone attack Ukraine',
    'Russia power plant substation energy infrastructure drone Ukraine',
    'Ukraine power plant substation energy infrastructure missile drone Russia',
    'Moscow Kapotnya Kirishi Yaroslavl Ryazan NORSI Kstovo refinery drone attack',
]

COUNTERSTRIKE_QUERIES = [
    ENERGY_ATTACK_SENTINEL,
    'site:reuters.com ("drones hit" OR "drone attack" OR "drone strike") ("oil refinery" OR refinery) Ukraine when:12h',
    'site:reuters.com ("shuts processing" OR "halted processing" OR "stopped processing" OR shutdown) refinery drone Ukraine when:2d',
    'site:reuters.com ("oil depot" OR "fuel depot" OR pipeline OR terminal OR port) Ukraine (drone OR attack OR fire) when:12h',
    'site:reuters.com Ukraine (power plant OR substation OR "energy infrastructure") (missile OR drone OR attack OR fire) Russia when:12h',
    'site:reuters.com Saratov drone civilian infrastructure governor Ukraine when:12h',
    'site:tass.com Saratov drone civilian infrastructure governor Ukraine when:12h',
    '(Saratov OR Engels OR 사라토프 OR 엥겔스) (drone OR UAV OR 드론) (civilian infrastructure OR 민간 인프라 OR refinery OR 정유공장 OR airbase OR 공군기지) when:12h',
]
watch.QUERIES = COUNTERSTRIKE_QUERIES + list(watch.QUERIES)

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_build_alert = watch.build_alert

RUSSIA_TERMS = (
    'russia','russian','moscow','kapotnya','kirishi','ryazan','yaroslavl','yanos','norsi','kstovo',
    'nizhny novgorod','tuapse','afipsky','ilsky','volgograd','saratov','novoshakhtinsk','syzran',
    'kuibyshev','novokuibyshevsk','ust-luga','primorsk','taman',
    '러시아','모스크바','카포트냐','키리시','랴잔','야로슬라블','니즈니노브고로드','투압세',
    '아피프스키','일스키','볼고그라드','사라토프','노보샤흐틴스크','시즈란','우스트루가','프리모르스크'
)
UKRAINE_TERMS = ('ukraine','ukrainian','kyiv','kiev','우크라이나','우크라','키이우','키예프')
ATTACK_TERMS = (
    'drone attack','drone strike','missile attack','missile strike','struck','hit','attack','attacked',
    'explosion','explosions','blast','fire','fires','burning','damaged','strike',
    '드론 공격','드론 공습','무인기 공격','미사일 공격','공격','공습','피격','폭발','화재','불길','타격','손상'
)
REFINERY_TERMS = (
    'oil refinery','refinery','refineries','refining plant','нефтеперераб',
    '정유공장','정유 시설','정유시설','정제시설','정제 공장'
)
STORAGE_TERMS = (
    'oil depot','fuel depot','oil storage','fuel storage','storage tank','tank farm','petroleum depot',
    '원유 저장','원유저장','연료 저장','연료저장','저유소','저장탱크','석유 저장','석유저장'
)
PIPELINE_TERMS = (
    'oil pipeline','pipeline','pumping station','pump station','pipeline station',
    '송유관','파이프라인','펌프장','가압장','송유시설'
)
TERMINAL_TERMS = (
    'oil terminal','fuel terminal','export terminal','port terminal','oil port','loading terminal',
    '석유 터미널','원유 터미널','수출 터미널','유류 터미널','항만 터미널','선적 터미널'
)
GAS_TERMS = (
    'gas facility','gas plant','gas processing','gas compressor','compressor station','lng terminal','lng plant',
    '가스 시설','가스시설','가스 처리','가스처리','압축기지','압축기지','lng 터미널','lng 시설'
)
POWER_TERMS = (
    'power plant','thermal power plant','power station','substation','transformer','power grid','electricity grid',
    '발전소','화력발전소','변전소','변압기','전력망','전력 시설','전력시설'
)
IMPACT_FIRE_TERMS = ('fire','fires','burning','blaze','explosion','explosions','smoke','화재','불길','폭발','연기')
SHUTDOWN_TERMS = (
    'shut','shutdown','shut down','halted','stopped processing','processing halted','suspended operations',
    'offline','out of service','가동 중단','가동중단','정지','처리 중단','생산 중단','운영 중단'
)
OUTPUT_CUT_TERMS = (
    'reduced output','reduced processing','cut output','throughput cut','capacity cut','processing capacity',
    '생산 감소','생산량 감소','처리량 감소','가동률 하락','처리능력 감소','캐파 감소'
)
CIV_TERMS = ('civilian infrastructure','гражданской инфраструкт','민간 인프라','민간 기반시설')
AIRBASE_TERMS = ('airbase','air base','airfield','аэродром','공군기지','비행장')
GOV_TERMS = ('governor','mayor','regional governor','주지사','시장')
TRUSTED_SOURCES = ('reuters','associated press','ap news','tass','interfax','ria','ukrinform','pravda.com.ua','president.gov.ua')


def _text(row):
    return ' '.join([
        row.get('title_original',''), row.get('description',''), row.get('article_text',''),
    ]).lower()


def _source_text(row):
    return ' '.join([row.get('source',''), row.get('link',''), row.get('resolved_url','')]).lower()


def _has(t, terms):
    return any(k in t for k in terms)


def _bing_energy_rows():
    rows, seen, errors = [], set(), []
    for query in ENERGY_ATTACK_QUERIES:
        try:
            url = "https://www.bing.com/news/search?format=rss&q=" + urllib.parse.quote(query)
            root = ET.fromstring(watch.req(url, 12))
        except Exception as exc:
            errors.append(f"BingEnergy:{type(exc).__name__}")
            continue
        for item in root.findall("./channel/item")[:20]:
            title = html_lib.unescape((item.findtext("title") or "").strip())
            link = (item.findtext("link") or "").strip()
            desc = html_lib.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).strip()
            pub = (item.findtext("pubDate") or "").strip()
            source = html_lib.unescape((item.findtext("source") or "Bing News").strip())
            if not title or not link:
                continue
            try:
                p = urllib.parse.urlparse(link)
                if "bing.com" in p.netloc.lower():
                    direct = (urllib.parse.parse_qs(p.query).get("url") or [""])[0]
                    if direct.startswith(("http://","https://")):
                        link = direct
            except Exception:
                pass
            key = (title.lower(), link)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                'title': title,
                'title_original': title,
                'title_ko': '',
                'link': link,
                'published': pub,
                'source': source or 'Bing News',
                'description': desc,
                'article_text': desc,
            })
    return rows, "; ".join(errors) if errors else None


def _facility_label(t):
    pairs = (
        (('kapotnya','moscow refinery','moscow oil refinery','카포트냐','모스크바 정유'), '모스크바·카포트냐 정유공장'),
        (('yaroslavl','yanos','야로슬라블'), '야로슬라블 YANOS 정유공장'),
        (('kirishi','kinef','키리시'), '키리시 정유공장'),
        (('ryazan','랴잔'), '랴잔 정유공장'),
        (('norsi','kstovo','nizhny novgorod','니즈니노브고로드'), 'NORSI·크스토보 정유공장'),
        (('tuapse','투압세'), '투압세 정유·수출시설'),
        (('saratov','사라토프'), '사라토프 에너지시설'),
        (('ust-luga','우스트루가'), '우스트루가 수출터미널'),
        (('primorsk','프리모르스크'), '프리모르스크 수출터미널'),
    )
    for keys, label in pairs:
        if any(k in t for k in keys):
            return label
    return ''


def _counter_signals(row):
    t = _text(row)
    # 에너지시설 공격 분류는 기사 제목·요약의 현재 사건을 우선한다.
    # 긴 본문에 과거 여러 국가 사례가 함께 나오는 해설기사를 신규 공격으로 오인하지 않는다.
    h = ' '.join([row.get('title_original',''), row.get('description','')]).lower()
    signals, marks = [], []

    rus = _has(h, RUSSIA_TERMS)
    ukr = _has(h, UKRAINE_TERMS)
    attack = _has(h, ATTACK_TERMS)
    refinery = _has(h, REFINERY_TERMS)
    storage = _has(h, STORAGE_TERMS)
    pipeline = _has(h, PIPELINE_TERMS)
    terminal = _has(h, TERMINAL_TERMS)
    gas = _has(h, GAS_TERMS)
    power = _has(h, POWER_TERMS)

    # 러시아 에너지 인프라: 시설 실명이 없어도 제목·요약에서 러시아 + 자산유형 + 공격이면 잡는다.
    if rus and attack and refinery:
        marks += ['러시아정유시설공격','에너지시설공격']
        label = _facility_label(h) or '러시아 정유시설'
        signals.append(f'{label} 공격·피격 신호 — 화재·가동중단·처리량 감소 여부 후속 확인')
    if rus and attack and storage:
        marks += ['러시아저장시설공격','에너지시설공격']
        signals.append('러시아 원유·연료 저장기지 공격 신호 — 저장탱크 화재·재고 손실·출하 차질 확인')
    if rus and attack and pipeline:
        marks += ['러시아송유관공격','에너지시설공격']
        signals.append('러시아 송유관·펌프장 공격 신호 — 원유 수송량·압송 중단·우회 가능성 확인')
    if rus and attack and terminal:
        marks += ['러시아수출터미널공격','에너지시설공격']
        signals.append('러시아 석유 수출터미널·항만 공격 신호 — 선적 중단·해상수출 차질 확인')
    if rus and attack and gas:
        marks += ['러시아가스시설공격','에너지시설공격']
        signals.append('러시아 가스·LNG·압축시설 공격 신호 — 처리량·수출·압송 차질 확인')
    if rus and attack and power:
        marks += ['러시아전력시설공격','에너지시설공격']
        signals.append('러시아 발전소·변전소·전력망 공격 신호 — 정전·설비 손상·복구기간 확인')

    # 우크라이나 에너지 인프라도 대칭적으로 감시한다.
    if ukr and attack and (refinery or storage or pipeline or terminal or gas or power):
        marks += ['우크라이나에너지시설공격','에너지시설공격']
        signals.append('우크라이나 에너지 인프라 공격 신호 — 발전·가스·연료 공급 차질과 복구기간 확인')

    if marks and _has(t, IMPACT_FIRE_TERMS):
        marks.append('화재폭발확인')
        signals.append('현장 화재·폭발·연기 신호 확인 — 단순 요격이 아닌 시설 피해 가능성 상승')
    if marks and _has(t, SHUTDOWN_TERMS):
        marks.append('가동중단확인')
        signals.append('가동·처리·운영 중단 신호 — 실제 공급 감소로 연결되는 단계')
    if marks and _has(t, OUTPUT_CUT_TERMS):
        marks.append('처리량감소확인')
        signals.append('처리량·생산량 감소 신호 — 휘발유·디젤·수출제품 공급 영향을 수치로 후속 확인')

    # 기존 사라토프 민간 인프라/군사시설 추적도 유지.
    saratov = any(k in t for k in ('saratov','саратов','사라토프','engels','энгельс','엥겔스'))
    drone = any(k in t for k in ('drone','uav','бпла','드론','무인기'))
    if saratov and drone and _has(t, CIV_TERMS):
        marks += ['사라토프민간인프라','확전반대신호']
        signals.append('사라토프 지역 드론 공격으로 민간 인프라 피해 신호')
        if _has(t, GOV_TERMS):
            marks.append('주지사발표')
    if saratov and drone and _has(t, AIRBASE_TERMS):
        marks.append('군사시설가능성')
        signals.append('엥겔스 공군기지 등 군사시설 피격 여부도 별도 확인 필요')

    return list(dict.fromkeys(signals)), sorted(set(marks))


def counter_google_news(query):
    if query == ENERGY_ATTACK_SENTINEL:
        rows, err = _bing_energy_rows()
    else:
        rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _counter_signals(row)
        if marks:
            row['signals_ko'] = list(dict.fromkeys(signals + list(row.get('signals_ko', []))))
            row['counter_marks'] = marks
            row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + ['확전','에너지위험','반대신호']))
            row['deep_signal'] = True
    return rows, err

watch.google_news = counter_google_news


def counter_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _counter_signals(x)
    if marks:
        if '에너지시설공격' in marks:
            score += 52
        if '화재폭발확인' in marks:
            score += 8
        if '가동중단확인' in marks:
            score += 14
        if '처리량감소확인' in marks:
            score += 12
        if '사라토프민간인프라' in marks:
            score += 20
        src = _source_text(x)
        if any(k in src for k in TRUSTED_SOURCES):
            score += 12
        age = watch.age_minutes(x, now)
        if age is not None:
            if age <= 30:
                score += 8
            elif age <= 180:
                score += 5
        tags = sorted(set(tags + ['확전','에너지위험','반대신호']))
        x['counter_marks'] = marks
        if signals:
            x['signals_ko'] = list(dict.fromkeys(signals + list(x.get('signals_ko', []))))
            x['deep_signal'] = True
    return score, tags

watch.score_item = counter_score_item


def counter_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _counter_signals(x)
    if not marks:
        return base_id
    stages = [m for m in marks if m in (
        '러시아정유시설공격','러시아저장시설공격','러시아송유관공격','러시아수출터미널공격',
        '러시아가스시설공격','러시아전력시설공격','우크라이나에너지시설공격',
        '화재폭발확인','가동중단확인','처리량감소확인','사라토프민간인프라'
    )]
    key = base_id + '|energy-wide|' + '|'.join(stages)
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]

watch.item_id = counter_item_id


def topic_label(x):
    _, marks = _counter_signals(x)
    if any(m in marks for m in (
        '러시아정유시설공격','러시아저장시설공격','러시아송유관공격','러시아수출터미널공격',
        '러시아가스시설공격','러시아전력시설공격','우크라이나에너지시설공격'
    )):
        return '러시아·우크라이나 · 에너지 인프라 공격'
    return _prev_topic_label(x)

watch.topic_label = topic_label


def _inject_counter(text, items):
    marks = set()
    for x in items:
        _, m = _counter_signals(x)
        marks.update(m)
    if not marks:
        return text

    marker = '<b>투자 판정</b>\n'
    pos = text.find(marker)
    if pos == -1:
        return text
    head = text[:pos].rstrip()

    refinery_chain = any(m in marks for m in (
        '러시아정유시설공격','러시아저장시설공격','러시아송유관공격','러시아수출터미널공격'
    ))
    if refinery_chain:
        core = '러시아 정유·저장·송유·수출 인프라 공격을 시설 실명과 무관하게 전수 추적 — 단순 화재보다 가동중단·처리량 감소가 핵심'
        market = '정유공장·터미널·송유관 실제 중단 시 휘발유·디젤·해상수출 공급 차질과 유가·제품마진 위험프리미엄 상승 가능'
        nxt = '피격 시설 실명 → 손상 공정·탱크·펌프 → 가동중단 시간 → 처리량·생산량 감소 → 수출·내수 연료가격 영향 → 복구기간'
    elif '러시아가스시설공격' in marks or '러시아전력시설공격' in marks or '우크라이나에너지시설공격' in marks:
        core = '전력·가스·LNG 인프라 공격 확대 — 군사시설과 분리해 실물 에너지 공급 차질을 우선 확인'
        market = '가스 압송·발전·송전 중단이 실제 발생하면 지역 정전·산업가동·유럽 에너지 위험프리미엄에 영향 가능'
        nxt = '시설 실명 → 정전·압송중단 규모 → 복구시간 → 산업·수출 영향 → 후속 보복 여부'
    else:
        core = '종전 협상과 별개로 장거리 공격 지속 — 실제 군사·에너지 완화는 아직 미확인'
        market = '시설 피해가 공급 차질로 이어지는지 확인 전까지 가격 영향은 제한적으로 판정'
        nxt = '피해 대상 실명 → 사상자·가동중단 → 후속 보복·협상 영향'

    rows = [
        '<b>투자 판정</b>',
        f'- <b>핵심:</b> {core}',
        f'- <b>시장:</b> {market}',
        f'- <b>다음:</b> {nxt}',
    ]
    return head + '\n\n' + '\n'.join(rows)


def counter_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    return _inject_counter(text, items).strip()[:4000] + '\n'

watch.build_alert = counter_build_alert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--finalize', action='store_true')
    ap.add_argument('--telegram-test', action='store_true')
    args = ap.parse_args()
    if args.finalize:
        watch.finalize(); return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)

if __name__ == '__main__':
    main()
