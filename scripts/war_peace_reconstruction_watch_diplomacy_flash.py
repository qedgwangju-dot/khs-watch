#!/usr/bin/env python3
"""종전·에너지 감시 최종 보강.

기존 war-peace 감지·상태·텔레그램 경로는 그대로 사용한다.
기존 Walter Bloomberg 외교/에너지 신호에 더해 이란 전쟁은
1) 미국 측 종전·직접접촉 주장,
2) 이란 측 직접협상 확인,
3) 정식 휴전,
4) 종전 합의,
5) 호르무즈 실제 통항 정상화,
6) 협상 후퇴
를 서로 다른 단계로 판정한다.

미국 한쪽의 주장만으로 휴전·종전으로 승격하지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html as html_lib
import re
from email.utils import format_datetime

import war_peace_reconstruction_watch_energy_ceasefire as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_verdict = guard._verdict

WALTER_SENTINEL = "__WALTER_BLOOMBERG_WAR_PEACE_FLASH__"
WALTER_PUBLIC_URL = "https://t.me/s/WalterBloomberg"

FLASH_QUERIES = [
    WALTER_SENTINEL,
    'site:reuters.com (Araghchi OR "Iranian foreign minister") (China OR Beijing OR "Wang Yi") (visit OR meeting OR talks) when:2d',
    '(Araghchi OR "Iranian foreign minister" OR 아라치 OR 이란 외무장관) (China OR Beijing OR 중국 OR 베이징 OR "Wang Yi" OR 왕이) (visit OR meeting OR 회담 OR 방문) when:2d',
    'site:reuters.com (China OR Chinese) Iran ("satellite images" OR "satellite imagery") ("US base" OR "U.S. base") when:3d',
    '(Kremlin OR Peskov OR 크렘린 OR 페스코프) Trump Ukraine ("energy targets" OR "energy facilities" OR 에너지 시설 OR 에너지 표적) ("good idea" OR welcomes OR 환영 OR "좋은 생각") when:2d',
    '(Kremlin OR Peskov OR 크렘린 OR 페스코프) sanctions ("world energy prices" OR "global energy prices" OR 에너지 가격) (lower OR fall OR down OR 하락) when:2d',
    'site:reuters.com Trump Iran ("end of the war" OR "nearing the end" OR "wants a deal" OR directly OR "direct contact") when:1d',
    'site:apnews.com Trump Iran ("end of the war" OR "wants a deal" OR directly OR "direct talks") when:1d',
    'site:aljazeera.com Trump Iran ("end of war" OR "wants a deal" OR directly OR "direct talks") when:1d',
    'site:whitehouse.gov Trump Iran (deal OR talks OR ceasefire OR peace OR war) when:2d',
    '(Trump OR 트럼프) (Iran OR 이란 OR Tehran OR 테헤란) ("wants a deal" OR "end of the war" OR "direct contact" OR "direct talks" OR 직접 접촉 OR 직접 협상 OR 종전) when:1d',
    'site:reuters.com Iran US ("direct talks" OR "direct contact" OR negotiations OR denied OR rejects OR "no direct talks") when:1d',
    'site:apnews.com Iran US ("direct talks" OR negotiations OR denied OR rejects OR ceasefire) when:1d',
    'site:irna.ir Iran US ("direct talks" OR negotiations OR ceasefire OR peace) when:2d',
    'site:tasnimnews.com Iran US ("direct talks" OR negotiations OR ceasefire OR peace) when:2d',
    '(Araghchi OR "Iranian foreign ministry" OR "Iran foreign ministry" OR 아라치 OR 이란 외무부) (US OR "United States" OR 미국) ("direct talks" OR "direct contact" OR 직접 협상 OR 직접 접촉 OR 부인 OR denied OR negotiations) when:1d',
    'site:reuters.com US Iran (ceasefire OR truce OR "peace agreement" OR "end of hostilities" OR "war ended") when:1d',
    'site:apnews.com US Iran (ceasefire OR truce OR "peace agreement" OR "end of hostilities") when:1d',
    'site:whitehouse.gov Iran (ceasefire OR truce OR peace OR "end of hostilities") when:2d',
    '(US OR 미국) (Iran OR 이란) (ceasefire OR truce OR 휴전 OR 종전 OR 평화협정) (agreed OR signed OR announced OR 합의 OR 서명 OR 발표) when:1d',
    'site:reuters.com Hormuz (reopened OR "traffic resumes" OR "shipping resumes" OR tankers OR "LNG carriers") when:1d',
    'site:fm.gov.om Hormuz (reopen OR "safe navigation" OR traffic OR shipping) when:2d',
    '(Hormuz OR 호르무즈) (reopened OR "traffic resumed" OR "shipping resumed" OR 통항 재개 OR 운항 재개 OR 재개방) (tankers OR vessels OR "LNG carriers" OR 유조선 OR 선박 OR LNG선) when:1d',
]
watch.QUERIES = FLASH_QUERIES + list(watch.QUERIES)

IRAN_FM_TERMS = ('araghchi', 'iranian foreign minister', 'iran foreign minister', '아라치', '이란 외무장관')
CHINA_TERMS = ('china', 'chinese', 'beijing', 'wang yi', '중국', '중국계', '베이징', '왕이')
VISIT_TERMS = ('visit', 'visiting', 'travel to', 'meet wang yi', 'meeting with wang yi', 'talks with wang yi', '방문', '회담', '왕이와 회담', '왕이 외교부장')
SATELLITE_TERMS = ('satellite image', 'satellite images', 'satellite imagery', '위성 이미지', '위성영상', '위성 영상')
US_BASE_TERMS = ('u.s. base', 'us base', 'american base', 'u.s. military base', '미국 기지', '미군 기지')
PROVIDE_TERMS = ('provided', 'supplied', 'gave', 'provide', '제공', '넘겼', '전달')
KREMLIN_TERMS = ('kremlin', 'peskov', '크렘린', '페스코프')
TRUMP_TERMS = ('trump', 'donald trump', 'president trump', '트럼프', '도널드 트럼프')
UKRAINE_TERMS = ('ukraine', 'ukrainian', '우크라이나', '우크라')
ENERGY_TARGET_TERMS = ('energy target', 'energy targets', 'energy facility', 'energy facilities', 'energy infrastructure', 'refinery', 'diesel facility', '에너지 시설', '에너지 표적', '에너지 인프라', '정유시설', '정유 공장', '경유 시설')
POSITIVE_IDEA_TERMS = ('good idea', 'welcomes', 'welcome', 'positive idea', 'supports the proposal', 'support the proposal', '좋은 생각', '좋은 아이디어', '긍정 평가', '환영')
SANCTION_TERMS = ('sanctions are lifted', 'sanctions lifted', 'lifting sanctions', 'lift sanctions', 'sanction relief', '제재가 해제', '제재 해제', '제재 완화')
WORLD_ENERGY_PRICE_TERMS = ('world energy prices', 'global energy prices', 'energy prices', 'oil prices', 'fuel prices', '세계 에너지 가격', '글로벌 에너지 가격', '국제 에너지 가격', '유가')
PRICE_DOWN_TERMS = ('will go down', 'would go down', 'will fall', 'would fall', 'lower prices', 'bring down', 'decline', '하락', '낮아질', '떨어질')
IRAN_TERMS = ('iran', 'iranian', 'tehran', '이란', '테헤란')
US_TERMS = ('united states', 'u.s.', 'us ', 'washington', 'america', 'american', '미국', '워싱턴')
END_WAR_SIGNAL_TERMS = ('toward the end of the war', 'towards the end of the war', 'nearing the end of the war', 'near the end of the war', 'war may be nearing its end', 'end of the war', '전쟁의 끝', '전쟁 종결 임박', '전쟁이 끝나', '종전이 가까', '종전 임박')
IRAN_WANTS_DEAL_TERMS = ('iran wants a deal', 'iran very much wants a deal', 'iran is very much wanting to make a deal', 'tehran wants a deal', 'iran wants to make a deal', '이란이 합의를 원', '테헤란이 합의를 원')
DIRECT_CONTACT_TERMS = ('direct contact', 'direct contacts', 'directly contacted', 'contacted directly', 'direct talks', 'talking directly', 'talks directly', 'direct negotiations', 'reached out directly', 'heard from iran directly', 'no, directly', '직접 접촉', '직접접촉', '직접 협상', '직접협상', '직접 대화')
IRAN_OFFICIAL_TERMS = ('iranian foreign ministry', 'iran foreign ministry', 'foreign ministry spokesman', 'foreign ministry spokesperson', 'araghchi', 'abbas araghchi', 'mohsen rezaei', 'supreme national security council', 'iranian official', 'tehran said', '이란 외무부', '이란 외무장관', '아라치', '모센 레자이', '이란 당국자')
CONFIRM_TERMS = ('confirmed', 'confirms', 'acknowledged', 'acknowledges', 'said it is in direct talks', 'said they are in direct talks', 'said direct talks are under way', 'said direct talks are underway', '확인', '인정', '직접 협상 중이라고', '직접 접촉했다고')
DENY_TALKS_TERMS = ('denied direct talks', 'denies direct talks', 'no direct talks', 'not in direct talks', 'not negotiating', 'will not negotiate', 'no negotiations', 'rejects talks', 'rejected talks', 'talks collapsed', 'negotiations collapsed', 'walked away from talks', 'talks broke down', '직접 협상 부인', '직접 접촉 부인', '협상하지 않', '협상 거부', '협상 결렬', '대화 결렬')
CEASEFIRE_TERMS = ('ceasefire', 'cease-fire', 'truce', '휴전', '공격 중단')
PEACE_TERMS = ('peace agreement', 'peace deal', 'final peace', 'end of hostilities', 'war is over', 'war has ended', 'ended the war', '종전 합의', '평화협정', '전쟁 종결', '적대행위 종료')
AGREED_TERMS = ('agreed', 'agreement reached', 'signed', 'announced', 'entered into force', 'takes effect', 'came into force', '합의', '서명', '발표', '발효', '효력 발생')
PROPOSAL_ONLY_TERMS = ('proposal', 'proposed', 'calls for', 'called for', 'urged', 'hopes for', 'hope for', 'could agree', 'may agree', 'wants a ceasefire', 'seeks a ceasefire', '제안', '촉구', '희망', '가능성', '추진', '원한다')
HORMUZ_TERMS = ('hormuz', 'strait of hormuz', '호르무즈')
HORMUZ_RECOVERY_TERMS = ('reopened', 'has reopened', 'reopening completed', 'traffic resumes', 'traffic resumed', 'shipping resumes', 'shipping resumed', 'navigation resumes', 'navigation resumed', 'commercial traffic resumed', 'vessels resumed', '통항 재개', '운항 재개', '항행 재개', '선박 통항 재개', '재개방 완료')
VESSEL_TERMS = ('vessel', 'vessels', 'ship', 'ships', 'tanker', 'tankers', 'vlcc', 'lng carrier', 'lng carriers', 'container ship', '유조선', '선박', '초대형 원유운반선', 'lng선')
NEGATION_TERMS = ('not agreed', 'no agreement', 'has not agreed', 'did not agree', 'not a ceasefire', 'no ceasefire', 'not reopened', 'remains closed', 'remain closed', 'still closed', '합의하지 않', '합의가 아니', '휴전이 아니', '휴전 합의 없', '재개방되지 않', '폐쇄 유지')
TRUSTED_CONFIRM_SOURCES = ('reuters', 'apnews', 'aljazeera', 'whitehouse.gov', 'state.gov', 'irna.ir', 'tasnim', 'mehrnews', 'presstv', 'fm.gov.om', 'omannews.gov.om')
FALSE_POSITIVE_TITLE_TERMS = ('trade truce', 'trade ceasefire', '무역 휴전', '무역휴전')
WAR_TITLE_ACTOR_TERMS = ('iran', 'iranian', 'tehran', '이란', '테헤란', 'ukraine', 'ukrainian', 'zelensky', '러시아', '우크라이나', '젤렌스키', 'putin', '푸틴', 'israel', 'gaza', 'hamas', '이스라엘', '가자', '하마스', 'houthi', 'yemen', '후티', '예멘', 'hormuz', '호르무즈')
WAR_TITLE_ACTION_TERMS = ('war', 'attack', 'strike', 'missile', 'drone', 'ceasefire', 'truce', 'peace', 'talks', 'negotiation', 'deal', 'reopen', 'blockade', '전쟁', '공격', '공습', '미사일', '드론', '휴전', '종전', '평화', '협상', '회담', '합의', '재개방', '봉쇄', '전후구상')


def _clean_html(raw: str) -> str:
    raw = re.sub(r'<br\s*/?>', '\n', raw, flags=re.I)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = html_lib.unescape(raw)
    raw = re.sub(r'[ \t]+', ' ', raw)
    raw = re.sub(r'\n\s*\n+', '\n', raw)
    return raw.strip()


def _walter_rows():
    try:
        page = watch.req(WALTER_PUBLIC_URL, 15).decode('utf-8', errors='ignore')
    except Exception as exc:
        return [], f"WalterBloomberg: {type(exc).__name__}"
    chunks = page.split('<div class="tgme_widget_message_wrap js-widget_message_wrap">')[1:]
    rows = []
    now = dt.datetime.now(dt.timezone.utc)
    for chunk in chunks[-40:]:
        post = re.search(r'data-post="WalterBloomberg/(\d+)"', chunk)
        text_match = re.search(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', chunk, re.S)
        time_match = re.search(r'<time datetime="([^"]+)"', chunk)
        if not post or not text_match:
            continue
        text = _clean_html(text_match.group(1))
        if not text:
            continue
        published = ''
        if time_match:
            try:
                stamp = dt.datetime.fromisoformat(time_match.group(1).replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=dt.timezone.utc)
                stamp = stamp.astimezone(dt.timezone.utc)
                if (now - stamp).total_seconds() > 24 * 3600:
                    continue
                published = format_datetime(stamp)
            except Exception:
                pass
        title = text if len(text) <= 300 else text[:297].rstrip() + '...'
        rows.append({'title': title, 'title_original': title, 'title_ko': '', 'link': f"https://t.me/WalterBloomberg/{post.group(1)}", 'published': published, 'source': 'Walter Bloomberg', 'description': text, 'article_text': text})
    return rows, None


def google_news(query):
    if query == WALTER_SENTINEL:
        return _walter_rows()
    return _prev_google_news(query)

watch.google_news = google_news


def _text(row):
    return ' '.join([row.get('title_original', ''), row.get('title_ko', ''), row.get('description', ''), row.get('article_text', ''), ' '.join(row.get('signals_ko', []))]).lower()


def _source_text(row):
    return ' '.join([row.get('source', ''), row.get('link', ''), row.get('resolved_url', '')]).lower()


def _has(text, terms):
    return any(term in text for term in terms)


def _trusted(row):
    src = _source_text(row)
    return any(term in src for term in TRUSTED_CONFIRM_SOURCES)


def _title_text(row):
    return ' '.join([row.get('title_original', ''), row.get('title_ko', '')]).lower()


def _obvious_false_positive(row):
    title = _title_text(row)
    if _has(title, FALSE_POSITIVE_TITLE_TERMS):
        return True
    if not _has(title, WAR_TITLE_ACTOR_TERMS) and not _has(title, WAR_TITLE_ACTION_TERMS):
        return True
    return False


def _iran_war_stage_marks(row):
    text = _text(row)
    src = _source_text(row)
    marks = []
    if not _has(text, IRAN_TERMS):
        return marks
    trump_context = _has(text, TRUMP_TERMS)
    us_context = trump_context or _has(text, US_TERMS)
    if trump_context and (_has(text, END_WAR_SIGNAL_TERMS) or _has(text, IRAN_WANTS_DEAL_TERMS) or _has(text, DIRECT_CONTACT_TERMS)):
        marks.append('미국단독종전협상신호')
    denial = _has(text, DENY_TALKS_TERMS)
    if denial and (_has(text, IRAN_OFFICIAL_TERMS) or any(x in src for x in ('irna.ir', 'tasnim', 'mehrnews', 'presstv'))):
        marks.append('협상후퇴')
    iran_official_context = _has(text, IRAN_OFFICIAL_TERMS) or any(x in src for x in ('irna.ir', 'tasnim', 'mehrnews', 'presstv'))
    if not denial and us_context and iran_official_context and _has(text, DIRECT_CONTACT_TERMS) and _has(text, CONFIRM_TERMS) and _trusted(row):
        marks.append('이란직접협상확인')
    ceasefire_context = us_context and _has(text, CEASEFIRE_TERMS) and _has(text, AGREED_TERMS)
    if ceasefire_context and not _has(text, NEGATION_TERMS) and not (_has(text, PROPOSAL_ONLY_TERMS) and not _has(text, ('signed', 'entered into force', '발효', '서명'))) and _trusted(row):
        marks.append('정식휴전합의')
    peace_context = us_context and _has(text, PEACE_TERMS) and _has(text, AGREED_TERMS)
    if peace_context and not _has(text, NEGATION_TERMS) and _trusted(row):
        marks.append('종전합의')
    if _has(text, HORMUZ_TERMS) and _has(text, HORMUZ_RECOVERY_TERMS) and _has(text, VESSEL_TERMS) and not _has(text, NEGATION_TERMS) and _trusted(row):
        marks.append('호르무즈실물정상화')
    return sorted(set(marks))


def _marks(row):
    text = _text(row)
    marks = []
    if _has(text, IRAN_FM_TERMS) and _has(text, CHINA_TERMS) and _has(text, VISIT_TERMS):
        marks.append('이란외무장관중국방문')
    if ('iran' in text or '이란' in text) and _has(text, CHINA_TERMS) and _has(text, SATELLITE_TERMS) and _has(text, US_BASE_TERMS) and _has(text, PROVIDE_TERMS):
        marks.append('중국계위성영상제공보도')
    energy_context = _has(text, KREMLIN_TERMS) and _has(text, TRUMP_TERMS) and _has(text, UKRAINE_TERMS) and _has(text, ENERGY_TARGET_TERMS)
    if energy_context and _has(text, POSITIVE_IDEA_TERMS):
        marks.append('크렘린에너지휴전긍정평가')
    if _has(text, KREMLIN_TERMS) and _has(text, SANCTION_TERMS) and _has(text, WORLD_ENERGY_PRICE_TERMS) and _has(text, PRICE_DOWN_TERMS):
        marks.append('크렘린제재해제에너지가격하락발언')
    marks.extend(_iran_war_stage_marks(row))
    return sorted(set(marks))


def _korean_title(marks):
    if '협상후퇴' in marks:
        return '이란 전쟁 협상 후퇴 신호 — 직접협상 부인·거부·결렬 여부 확인'
    if '호르무즈실물정상화' in marks:
        return '호르무즈 실제 통항 정상화 신호 — 유조선·LNG선 등 상선 운항 재개'
    if '종전합의' in marks:
        return '미국·이란 종전 합의 신호 — 평화협정·적대행위 종료 단계'
    if '정식휴전합의' in marks:
        return '미국·이란 정식 휴전 합의 신호 — 공격 중단 이행 단계로 진입'
    if '이란직접협상확인' in marks:
        return '이란 측도 미국과 직접 협상·접촉을 확인 — 양측 확인 단계'
    if '미국단독종전협상신호' in marks:
        return '트럼프, 이란 종전·직접접촉 신호 강화 — 아직 미국 측 주장 단계'
    if '크렘린에너지휴전긍정평가' in marks:
        return '크렘린, 트럼프의 우크라이나 에너지 표적 휴전 제안에 “좋은 생각” 평가'
    if '크렘린제재해제에너지가격하락발언' in marks:
        return '크렘린 “제재가 해제되면 세계 에너지 가격이 하락할 것”'
    if '이란외무장관중국방문' in marks:
        return '이란 아라치 외무장관, 중국 방문·왕이 외교부장 회담 일정 신호'
    if '중국계위성영상제공보도' in marks:
        return '중국계 주체가 이란에 미군기지 위성영상을 제공했다는 보도'
    return ''


def _signals(marks):
    out = []
    if '미국단독종전협상신호' in marks:
        out.append('현재 단계: ⚠️ 협상 신호 — 트럼프의 종전 낙관·이란 합의 의향·직접접촉 주장은 확인하되 이란 측 공식 확인 전에는 휴전·종전으로 승격하지 않음')
        out.append('다음 확인: 이란 외무부·최고국가안보회의의 직접협상 인정 → 공식 회담 일정·대표단 → 휴전 문서')
    if '이란직접협상확인' in marks:
        out.append('현재 단계: 🟡 양측 확인 — 이란 측도 미국과 직접 협상·접촉을 확인한 것으로 판정')
        out.append('다음 확인: 회담 장소·대표단·의제 → 공격 중단 문구 → 발효 시각')
    if '정식휴전합의' in marks:
        out.append('현재 단계: 🟢 정식 휴전 — 양측 공격 중단 합의·발표·서명 또는 발효 문구 확인')
        out.append('다음 확인: 실제 공격 중단 이행 → 위반 여부 → 호르무즈 안전통항 합의')
    if '종전합의' in marks:
        out.append('현재 단계: 🟢 종전 합의 — 평화협정·적대행위 종료 등 전쟁 종료 문구를 휴전과 별도로 확인')
        out.append('다음 확인: 제재·핵·배상·주둔·호르무즈 조건과 실제 이행 일정')
    if '호르무즈실물정상화' in marks:
        out.append('현재 단계: 🟢 실물 정상화 — 호르무즈 재개방 문구뿐 아니라 유조선·LNG선 등 실제 상선 통항 재개까지 확인')
        out.append('시장 경로: 원유·LNG 운송 차질 및 해상보험 위험프리미엄 완화 여부를 통항량으로 후속 확인')
    if '협상후퇴' in marks:
        out.append('현재 단계: 🔴 협상 후퇴 — 이란 측 직접협상 부인·협상 거부·결렬 신호')
        out.append('다음 확인: 공격 재개·호르무즈 폐쇄 강화·중재국 회담 취소 여부')
    if '이란외무장관중국방문' in marks:
        out.append('이란 아라치 외무장관의 중국 방문·왕이 외교부장 회담 일정 신호 — 중국 중재채널 확대 여부 추적')
        out.append('확정 수준: 방문·회담 일정 단계 — 실제 회담 개최와 공동발표 내용은 후속 확인')
    if '중국계위성영상제공보도' in marks:
        out.append('보도: 중국계 주체가 미국 기지 공격 전 이란에 위성영상을 제공했다는 의혹')
        out.append('확정 수준: 중국 정부 직접 관여는 미확인 — 중국 외교부가 반박한 경우 그 반론도 함께 유지')
    if '크렘린에너지휴전긍정평가' in marks:
        out.append('크렘린: 트럼프의 우크라이나 에너지 표적 휴전 제안을 “좋은 생각”으로 긍정 평가')
        out.append('확정 수준: 러시아의 긍정 평가 단계 — 정식 합의·발효·실제 공격 중단과는 구분')
    if '크렘린제재해제에너지가격하락발언' in marks:
        out.append('크렘린: 대러 제재가 해제되면 세계 에너지 가격이 하락할 것이라고 주장')
        out.append('시장 경로: 제재 완화 → 러시아 원유·제품 공급 접근성 확대 → 유가·디젤 위험프리미엄 완화 가능성')
    return out


def score_item(row, now):
    marks = _marks(row)
    if not marks:
        if _obvious_false_positive(row):
            return 0, []
        return _prev_score(row, now)
    row['diplomacy_flash_marks'] = marks
    row['title_ko'] = _korean_title(marks) or row.get('title_ko', '')
    row['signals_ko'] = list(dict.fromkeys(_signals(marks) + list(row.get('signals_ko', []))))
    tags = ['종전·협상']
    if '미국단독종전협상신호' in marks:
        tags += ['이란전쟁', '미국측주장', '종전신호']
    if '이란직접협상확인' in marks:
        tags += ['이란전쟁', '직접협상', '양측확인']
    if '정식휴전합의' in marks:
        tags += ['이란전쟁', '휴전', '공격중단']
    if '종전합의' in marks:
        tags += ['이란전쟁', '종전', '평화협정']
    if '호르무즈실물정상화' in marks:
        tags += ['호르무즈', '실물정상화', '에너지위험완화']
    if '협상후퇴' in marks:
        tags += ['이란전쟁', '협상후퇴', '확전위험']
    if '이란외무장관중국방문' in marks:
        tags += ['이란·중국', '중동외교']
    if '중국계위성영상제공보도' in marks:
        tags += ['이란·중국', '미중긴장', '미확인보도']
    if '크렘린에너지휴전긍정평가' in marks:
        tags += ['우크라이나·러시아', '에너지부분휴전']
    if '크렘린제재해제에너지가격하락발언' in marks:
        tags += ['우크라이나·러시아', '대러제재', '에너지가격']
    row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + tags))
    if any(m in marks for m in ('종전합의', '정식휴전합의', '호르무즈실물정상화', '협상후퇴')):
        score = 100
    elif '이란직접협상확인' in marks:
        score = 99
    elif '미국단독종전협상신호' in marks:
        score = 96
    elif '크렘린에너지휴전긍정평가' in marks or '크렘린제재해제에너지가격하락발언' in marks:
        score = 94
    elif '이란외무장관중국방문' in marks:
        score = 91
    else:
        score = 86
    if len(marks) >= 2:
        score += 2
    src = _source_text(row)
    if any(x in src for x in ('reuters', 'apnews', 'aljazeera', 'whitehouse.gov', 'state.gov', 'irna.ir', 'tasnim', 'fm.gov.om', 'tass', 'kremlin.ru', 'fmprc.gov.cn', 'walterbloomberg')):
        score += 2
    age = watch.age_minutes(row, now)
    if age is not None and age <= 30:
        score += 1
    return min(score, 100), sorted(set(tags))

watch.score_item = score_item


def item_id(row):
    marks = _marks(row)
    if not marks:
        return _prev_item_id(row)
    stage_marks = [m for m in marks if m in ('미국단독종전협상신호', '이란직접협상확인', '정식휴전합의', '종전합의', '호르무즈실물정상화', '협상후퇴')]
    if stage_marks:
        key = 'iran-war-peace-stage-2026|' + '|'.join(sorted(stage_marks))
    elif any(m.startswith('크렘린') for m in marks):
        key = 'kremlin-energy-diplomacy-2026-09-15|' + '|'.join(marks)
    else:
        key = 'iran-china-diplomacy-2026-09-15|' + '|'.join(marks)
    return hashlib.sha256(key.encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    marks = _marks(row)
    if any(m in marks for m in ('미국단독종전협상신호', '이란직접협상확인', '정식휴전합의', '종전합의', '호르무즈실물정상화', '협상후퇴')):
        return '이란 전쟁 · 협상·휴전·종전·호르무즈'
    if any(m.startswith('크렘린') for m in marks):
        return '우크라이나·러시아 · 에너지 휴전·제재'
    if marks:
        return '이란·중국 · 중동 외교'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _verdict(items):
    flash = [x for x in items if _marks(x)]
    others = [x for x in items if x not in flash]
    if not flash:
        return _prev_verdict(items)
    marks = {m for x in flash for m in _marks(x)}
    lines = ['<b>투자 판정</b>']
    if '협상후퇴' in marks:
        lines.append('- <b>현재 판정:</b> 🔴 협상 후퇴 — 직접협상 부인·거부·결렬 신호. 종전 기대를 낮춰야 하는 변화')
    elif '호르무즈실물정상화' in marks:
        lines.append('- <b>현재 판정:</b> 🟢 호르무즈 실물 정상화 — 재개방 문구가 아니라 유조선·LNG선 등 실제 상선 통항 회복 확인')
    elif '종전합의' in marks:
        lines.append('- <b>현재 판정:</b> 🟢 종전 합의 — 휴전보다 높은 단계. 평화협정·적대행위 종료의 실제 조건과 이행 일정 확인 필요')
    elif '정식휴전합의' in marks:
        lines.append('- <b>현재 판정:</b> 🟢 정식 휴전 — 공격 중단 합의·발효 단계. 실제 이행과 위반 여부를 후속 확인')
    elif '이란직접협상확인' in marks:
        lines.append('- <b>현재 판정:</b> 🟡 양측 확인 — 이란 측도 미국과 직접 협상·접촉을 확인. 아직 휴전·종전 확정은 아님')
    elif '미국단독종전협상신호' in marks:
        lines.append('- <b>현재 판정:</b> ⚠️ 미국 측 종전·직접접촉 주장 단계 — 이란 공식 확인 전에는 휴전·종전으로 판정하지 않음')
    if any(m in marks for m in ('미국단독종전협상신호', '이란직접협상확인', '정식휴전합의', '종전합의', '협상후퇴')):
        lines.append('- <b>단계 추적:</b> 미국 측 협상 신호 → 이란 측 확인 → 정식 휴전 → 종전 합의 → 호르무즈 실제 정상화')
        lines.append('- <b>시장 경로:</b> 단계가 올라갈수록 유가·LNG·해상보험·운임 위험프리미엄 완화 가능성. 후퇴 시 반대 방향')
    if '호르무즈실물정상화' in marks:
        lines.append('- <b>실물 확인:</b> 선박 수·유조선·LNG선 통항량이 지속 회복되는지 별도 추적')
    if '크렘린에너지휴전긍정평가' in marks:
        lines.append('- <b>우크라이나:</b> 🟢 크렘린이 트럼프의 에너지 표적 휴전 제안을 긍정 평가 — 러시아 측 수용 가능성이 한 단계 올라감')
        lines.append('- <b>확정 수준:</b> 긍정 평가이지 정식 휴전 합의·발효 확정은 아님')
    if '크렘린제재해제에너지가격하락발언' in marks:
        lines.append('- <b>에너지:</b> 🟡 크렘린이 제재 해제와 세계 에너지 가격 하락을 직접 연결 — 향후 제재 협상이 유가·디젤 완화 촉매가 될 수 있음')
    if '이란외무장관중국방문' in marks:
        lines.append('- <b>중동 외교:</b> 🟢 이란 외무장관의 중국 방문·왕이 회담 일정 — 중국 중재채널이 다시 전면에 나오는지 확인')
    if '중국계위성영상제공보도' in marks:
        lines.append('- <b>미확인 리스크:</b> 🟠 중국계 주체의 이란 위성영상 제공 보도는 중국 정부 직접 관여가 확인되지 않은 단계')
    lines.append('- <b>다음:</b> 이란 공식 응답 → 직접협상 일정·대표단 → 휴전 발효 시각 → 종전 조건 → 호르무즈 실제 통항량')
    block = '\n'.join(lines)
    iran_stage_marks = {'미국단독종전협상신호', '이란직접협상확인', '정식휴전합의', '종전합의', '호르무즈실물정상화', '협상후퇴'}
    if marks & iran_stage_marks:
        return block
    if others:
        return block + '\n' + _prev_verdict(others)
    return block

guard._verdict = _verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--finalize', action='store_true')
    ap.add_argument('--telegram-test', action='store_true')
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == '__main__':
    main()
