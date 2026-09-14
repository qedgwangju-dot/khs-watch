#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
from email.utils import format_datetime

import war_peace_reconstruction_watch_hormuz_oman as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_verdict = guard._verdict

TRUTH_SENTINEL = "__TRUMP_TRUTH_SOCIAL_ENERGY_CEASEFIRE__"
TRUTH_ACCOUNT_ID = "107780257626128497"
TRUTH_URL = (
    f"https://truthsocial.com/api/v1/accounts/{TRUTH_ACCOUNT_ID}/statuses"
    "?exclude_replies=true&limit=20&with_muted=true"
)

ENERGY_CEASEFIRE_QUERIES = [
    TRUTH_SENTINEL,
    'site:reuters.com (Ukraine Russia) ("energy targets" OR "energy facilities" OR "energy infrastructure" OR refinery OR diesel) (agreed OR agree OR halt OR stop OR ceasefire OR refrain) Trump when:1d',
    'site:apnews.com (Ukraine Russia) ("energy targets" OR "energy facilities" OR "energy infrastructure" OR refinery OR diesel) (agreed OR agree OR halt OR stop OR ceasefire OR refrain) Trump when:1d',
    'site:whitehouse.gov (Ukraine Russia) (energy OR refinery OR diesel) (agreed OR ceasefire OR halt OR stop OR refrain) when:2d',
    'site:president.gov.ua (Russia energy) (ceasefire OR halt OR stop OR refrain OR reciprocate OR agreement) when:2d',
    'site:kremlin.ru (Ukraine energy) (ceasefire OR halt OR stop OR refrain OR agreement) when:2d',
    '(트럼프 OR 젤렌스키 OR 푸틴) (우크라이나 OR 우크라) (러시아 OR 러) (에너지 시설 OR 에너지 인프라 OR 정유시설 OR 경유 시설 OR 전력망) (공격 중단 OR 공격 멈추 OR 공격하지 않기로 OR 합의 OR 휴전) when:1d',
]
watch.QUERIES = ENERGY_CEASEFIRE_QUERIES + list(watch.QUERIES)

UKRAINE_TERMS = (
    'ukraine','ukrainian','zelensky','zelenskiy','kyiv','kiev',
    '우크라이나','우크라','젤렌스키','키이우','키예프',
)
RUSSIA_TERMS = (
    'russia','russian','putin','kremlin','moscow',
    '러시아','러시아군','푸틴','크렘린','모스크바',
)
ENERGY_TERMS = (
    'energy target','energy targets','energy facility','energy facilities','energy infrastructure',
    'oil refinery','oil refineries','refinery','refineries','diesel facility','diesel facilities',
    'fuel facility','fuel facilities','power grid','power infrastructure','energy grid',
    '에너지 시설','에너지시설','에너지 인프라','정유시설','정유 시설','정유공장','정유 공장',
    '경유 시설','연료 시설','전력망','전력 시설','전력 인프라',
)
MUTUAL_HALT_TERMS = (
    'agreed not to attack','agree not to attack','agreed to not attack','agree to not attack',
    'agreed to stop attacking','agree to stop attacking','agreed to stop strikes','agree to stop strikes',
    'agreed to halt attacks','agree to halt attacks','mutually refrain','mutual halt','mutual ceasefire',
    'ceasefire on energy','energy ceasefire','energy truce','moratorium on attacks','stop attacking each other',
    'both agreed','both sides agreed','likewise agreed','similarly agreed',
    '공격하지 않기로 합의','공격을 멈추기로 합의','공격 중단에 합의','공격 중단 합의',
    '상호 공격 중단','에너지 시설 공격 중단','에너지 인프라 공격 중단','에너지 휴전','부분 휴전',
)
TRUMP_TERMS = ('donald trump','president trump','trump said','trump says','truth social','트럼프','도널드 트럼프')
UKRAINE_CONFIRM_TERMS = (
    'ukraine confirmed','zelensky confirmed','zelenskiy confirmed','ukraine agreed','zelensky agreed','zelenskiy agreed',
    'ukraine will not attack','ukraine would not attack','ukraine will refrain','ukraine reciprocate','ukraine will reciprocate',
    '우크라이나 확인','젤렌스키 확인','우크라이나도 합의','젤렌스키도 합의','우크라이나는 공격하지','우크라이나는 자제',
)
RUSSIA_CONFIRM_TERMS = (
    'russia confirmed','kremlin confirmed','putin confirmed','russia agreed','kremlin agreed','putin agreed',
    'russia will not attack','russia would not attack','russia will refrain',
    '러시아 확인','크렘린 확인','푸틴 확인','러시아도 합의','푸틴도 합의','러시아는 공격하지','러시아는 자제',
)


def _text(row):
    return ' '.join([
        row.get('title_original',''), row.get('title_ko',''), row.get('description',''),
        row.get('article_text',''), ' '.join(row.get('signals_ko',[])),
    ]).lower()


def _has(text, terms):
    return any(term in text for term in terms)


def _truth_social_rows():
    try:
        payload = json.loads(watch.req(TRUTH_URL, 12).decode('utf-8'))
    except Exception as exc:
        return [], f"TruthSocial: {type(exc).__name__}"

    rows = []
    now_utc = dt.datetime.now(dt.timezone.utc)
    for status in list(payload)[:20]:
        if not isinstance(status, dict):
            continue
        raw = watch.clean(status.get('content') or '')
        if not raw:
            continue
        low = raw.lower()
        if not (_has(low, UKRAINE_TERMS) and _has(low, RUSSIA_TERMS) and _has(low, ENERGY_TERMS)):
            continue
        if not (_has(low, MUTUAL_HALT_TERMS) or ('agreed' in low and ('attack' in low or 'strike' in low))):
            continue
        created_raw = str(status.get('created_at') or '')
        try:
            created = dt.datetime.fromisoformat(created_raw.replace('Z', '+00:00'))
            if created.tzinfo is None:
                created = created.replace(tzinfo=dt.timezone.utc)
            if (now_utc - created.astimezone(dt.timezone.utc)).total_seconds() > 48 * 3600:
                continue
            published = format_datetime(created.astimezone(dt.timezone.utc))
        except Exception:
            published = ''
        title = raw if len(raw) <= 280 else raw[:277].rstrip() + '...'
        rows.append({
            'title': title,
            'title_original': title,
            'link': str(status.get('url') or f"https://truthsocial.com/@realDonaldTrump/posts/{status.get('id','')}"),
            'published': published,
            'source': 'Donald J. Trump · Truth Social',
            'description': raw,
            'article_text': raw,
        })
    return rows, None


def google_news(query):
    if query == TRUTH_SENTINEL:
        return _truth_social_rows()
    return _prev_google_news(query)

watch.google_news = google_news


def _marks(row):
    text = _text(row)
    if not (_has(text, UKRAINE_TERMS) and _has(text, RUSSIA_TERMS) and _has(text, ENERGY_TERMS)):
        return []

    marks = []
    mutual = _has(text, MUTUAL_HALT_TERMS) or (
        ('agree' in text or 'agreed' in text or '합의' in text)
        and ('attack' in text or 'strike' in text or '공격' in text)
        and ('stop' in text or 'halt' in text or 'refrain' in text or '멈추' in text or '중단' in text or '하지 않' in text)
    )
    source_text = ' '.join([row.get('source',''), row.get('link','')]).lower()
    if mutual and (_has(text, TRUMP_TERMS) or 'truthsocial.com' in source_text or 'donald j. trump' in source_text):
        marks.append('트럼프상호에너지중단발표')
    if _has(text, UKRAINE_CONFIRM_TERMS):
        marks.append('우크라이나에너지중단확인')
    if _has(text, RUSSIA_CONFIRM_TERMS):
        marks.append('러시아에너지중단확인')
    if mutual and '트럼프상호에너지중단발표' not in marks:
        marks.append('상호에너지공격중단보도')
    if '우크라이나에너지중단확인' in marks and '러시아에너지중단확인' in marks:
        marks.append('양측에너지중단상호확인')
    return sorted(set(marks))


def _signals(marks):
    out = []
    if '트럼프상호에너지중단발표' in marks:
        out.append('트럼프 발표: 우크라이나와 러시아가 서로의 에너지 시설을 공격하지 않기로 했다고 밝힘')
        out.append('확정 수준: 미국 대통령 1차 발표 — 우크라이나·러시아의 별도 공식 확인과 실제 이행은 추가 확인 필요')
    if '우크라이나에너지중단확인' in marks:
        out.append('우크라이나 측 에너지 시설 공격 중단 동참·상호주의 확인 신호')
    if '러시아에너지중단확인' in marks:
        out.append('러시아·크렘린 측 에너지 시설 공격 중단 동참 확인 신호')
    if '양측에너지중단상호확인' in marks:
        out.append('양측 확인 단계: 미국 발표를 넘어 우크라이나·러시아 양측의 상호 중단 확인 신호')
    return out


def score_item(row, now):
    marks = _marks(row)
    if not marks:
        return _prev_score(row, now)
    sig = _signals(marks)
    if sig:
        row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))
    row['energy_ceasefire_marks'] = marks
    row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + ['종전·협상','에너지부분휴전','우크라이나·러시아']))

    if '양측에너지중단상호확인' in marks:
        score = 96
    elif '우크라이나에너지중단확인' in marks or '러시아에너지중단확인' in marks:
        score = 90
    elif '트럼프상호에너지중단발표' in marks:
        score = 92
    else:
        score = 84
    src = ' '.join([row.get('source',''), row.get('link',''), row.get('resolved_url','')]).lower()
    if any(k in src for k in ('truthsocial.com','reuters','apnews.com','whitehouse.gov','president.gov.ua','kremlin.ru')):
        score += 4
    age = watch.age_minutes(row, now)
    if age is not None and age <= 30:
        score += 2
    return score, ['에너지부분휴전','우크라이나·러시아','종전·협상']

watch.score_item = score_item


def item_id(row):
    marks = _marks(row)
    if not marks:
        return _prev_item_id(row)
    stage_order = (
        '트럼프상호에너지중단발표',
        '우크라이나에너지중단확인',
        '러시아에너지중단확인',
        '양측에너지중단상호확인',
        '상호에너지공격중단보도',
    )
    stages = [m for m in stage_order if m in marks]
    key = 'ukraine-russia-energy-strike-halt|' + '|'.join(stages)
    return hashlib.sha256(key.encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    if _marks(row):
        return '우크라이나·러시아 · 에너지 부분휴전'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _verdict(items):
    ec = [x for x in items if _marks(x)]
    others = [x for x in items if x not in ec]
    if ec:
        marks = {m for x in ec for m in _marks(x)}
        if '양측에너지중단상호확인' in marks:
            headline = '🟢 우크라이나·러시아 양측의 에너지 시설 상호 공격 중단 확인 단계로 진전'
            certainty = '양측 확인 신호가 잡혔지만 발효 시각·대상 시설·위반 판정 기준은 별도 확인 필요'
        elif '트럼프상호에너지중단발표' in marks:
            headline = '🟢 트럼프: 우크라이나·러시아가 서로의 에너지 시설 공격 중단에 합의했다고 발표'
            certainty = '미국 대통령 1차 발표 단계 — 양측의 별도 공식 확인 전에는 완전한 확정 합의로 단정하지 않음'
        elif '우크라이나에너지중단확인' in marks or '러시아에너지중단확인' in marks:
            headline = '🟢 에너지 시설 공격 중단에 대한 당사자 확인이 추가됨'
            certainty = '한쪽 확인만으로 상호 이행 완료로 보지 않고 반대편 확인을 계속 추적'
        else:
            headline = '🟢 우크라이나·러시아 에너지 시설 상호 공격 중단 보도 감지'
            certainty = '당사자 공식 확인과 실제 이행 여부를 후속 검증'
        block = (
            '<b>투자 판정</b>\n'
            f'- <b>핵심:</b> {headline}\n'
            f'- <b>확정 수준:</b> {certainty}\n'
            '- <b>현재 단계:</b> 전면 종전이 아니라 정유시설·전력망 등 에너지 표적에 한정된 부분적 긴장완화 신호\n'
            '- <b>시장:</b> 실제 이행 시 러시아 경유·정유 공급 차질과 우크라이나 전력망 파괴 위험이 줄어 디젤·유가·유럽 전력 위험프리미엄 완화 요인\n'
            '- <b>다음:</b> 우크라 대통령실·크렘린 별도 확인 → 발효 시각·기간·대상시설 → 24시간·72시간 실제 공격 중단 → 위반 여부'
        )
        if others:
            return block + '\n' + _prev_verdict(others)
        return block
    return _prev_verdict(items)

guard._verdict = _verdict


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
