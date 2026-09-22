#!/usr/bin/env python3
"""종전·에너지 감시 최종 보강.

기존 war-peace 감지·상태·텔레그램 경로는 그대로 사용한다.
이란 전쟁 단계와 예멘·사우디·오만·Ansar Allah 휴전중재를 서로 섞지 않고 판정한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html as html_lib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import format_datetime

import war_peace_reconstruction_watch_energy_ceasefire as prev
import war_peace_reconstruction_watch_houthi_maritime as houthi_watch

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
BING_EMERGENCY_SENTINEL = "__BING_MIDDLE_EAST_EMERGENCY__"
IRAN_DIPLO_SENTINEL = "__IRAN_NEWYORK_DIPLOMACY_WIRE__"
IRAN_DIPLO_BACKFILL_SENTINEL = "__IRAN_NEWYORK_DIPLOMACY_BACKFILL__"
IRIB_MEETING_BACKFILL_SENTINEL = "__IRIB_ARAGHCHI_WITKOFF_NY_BACKFILL__"

BING_EMERGENCY_QUERIES = [
    '"Code 100" Iran IRGC Army security forces',
    '"The Hormuz Letter" "Code 100" Iran',
    'Trump Camp David returned White House Middle East Iran Houthi',
    '"security alert" Middle East U.S. embassy Houthi Saudi Arabia',
    'Netanyahu cut short US trip return Israel Iran',
]

BING_IRAN_DIPLOMACY_QUERIES = [
    '"Iranian delegation" "New York" "full authority" diplomacy US',
    '"Iran delegation" "New York" "full mandate" mediator United States',
    '"end hostilities" Iran mediator New York United States',
    '"concrete steps" Tehran "resume diplomacy" New York',
    '"Iranian delegation" New York diplomacy mediator Reuters',
]

FLASH_QUERIES = [
    WALTER_SENTINEL,
    BING_EMERGENCY_SENTINEL,
    IRAN_DIPLO_SENTINEL,
    IRAN_DIPLO_BACKFILL_SENTINEL,
    IRIB_MEETING_BACKFILL_SENTINEL,
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
    'site:reuters.com Iran delegation New York ("full authority" OR "full mandate" OR mediator OR diplomacy OR "concrete steps") when:1d',
    'site:iribnews.ir (Araghchi OR عراقچی) (Witkoff OR ویتکاف) (New York OR نیویورک) when:1d',
    'site:irna.ir (Araghchi OR عراقچی) (Witkoff OR ویتکاف) (New York OR نیویورک) when:1d',
    'site:presstv.ir Araghchi Witkoff New York Hormuz when:1d',
    'site:tasnimnews.com Araghchi Witkoff New York Hormuz when:1d',
    '(Araghchi OR 아라치 OR عراقچی) (Witkoff OR 위트코프 OR ویتکاف) (New York OR 뉴욕 OR نیویورک) (meeting OR met OR talks OR 회동 OR 회담 OR دیدار) when:1d',
    '(Iran OR 이란) (delegation OR 대표단) (New York OR 뉴욕) ("full authority" OR "full mandate" OR 전권 OR 완전한 권한) (diplomacy OR 협상 OR 외교) when:1d',
    '(Iran OR 이란) (mediator OR 중재자 OR 중재) (New York OR 뉴욕) ("end hostilities" OR 적대행위 종식 OR agreement OR 합의안) when:1d',
    '(Iran OR Tehran OR 이란 OR 테헤란) ("concrete steps" OR 구체적 조치) (resume diplomacy OR diplomacy OR 외교 재개 OR 협상 재개) when:1d',
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
    'site:reuters.com Trump "Camp David" ("White House" OR return OR "cut short") ("Middle East" OR Iran OR Houthi) when:1d',
    'site:apnews.com Trump "Camp David" ("White House" OR return OR "cut short") ("Middle East" OR Iran OR Houthi) when:1d',
    '(Trump OR 트럼프) ("Camp David" OR "캠프 데이비드") ("cut short" OR "returned early" OR "return to the White House" OR "백악관 복귀" OR "일정 단축") (Iran OR Houthi OR "Middle East" OR 이란 OR 후티 OR 중동) when:1d',
    '("State Department" OR "U.S. embassy" OR "US embassy" OR 국무부 OR "미국 대사관") ("Middle East" OR 중동) ("security alert" OR "heightened vigilance" OR "unforeseen escalation" OR "escalate rapidly" OR 보안경보 OR 확전) when:1d',
    '(Iran OR 이란) ("Code 100" OR "Code-100" OR "코드 100" OR 코드100) (IRGC OR Army OR "armed forces" OR 군 OR 전군 OR 혁명수비대) when:1d',
    '(Netanyahu OR 네타냐후) ("United States" OR US OR 미국 OR 방미) ("cut short" OR "return to Israel" OR "returned to Israel" OR 조기귀국 OR 귀국 OR "일정 단축") when:1d',
    '(Houthi OR Houthis OR 후티 OR Ansarallah OR "Ansar Allah") (Riyadh OR 리야드) (missile OR missiles OR 미사일) (attack OR launched OR intercepted OR 공격 OR 발사 OR 요격) when:1d',
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
WAR_TITLE_ACTOR_TERMS = ('iran', 'iranian', 'tehran', '이란', '테헤란', 'ukraine', 'ukrainian', 'zelensky', '러시아', '우크라이나', '젤렌스키', 'putin', '푸틴', 'israel', 'gaza', 'hamas', '이스라엘', '가자', '하마스', 'houthi', 'houthis', 'ansar allah', 'ansarallah', 'yemen', 'saudi', 'oman', '후티', '안사르 알라', '안사르알라', '예멘', '사우디', '오만', 'hormuz', '호르무즈')
WAR_TITLE_ACTION_TERMS = ('war', 'attack', 'strike', 'missile', 'drone', 'ceasefire', 'truce', 'peace', 'talks', 'negotiation', 'mediation', 'deal', 'reopen', 'blockade', '전쟁', '공격', '공습', '미사일', '드론', '휴전', '종전', '평화', '협상', '회담', '중재', '합의', '재개방', '봉쇄', '전후구상')

CAMP_DAVID_TERMS = ('camp david', '캠프 데이비드')
EARLY_RETURN_TERMS = ('cut short', 'returned early', 'return early', 'returned to the white house', 'return to the white house', 'unexpectedly returned', 'day early', 'ahead of schedule', '일정을 단축', '일정 단축', '조기 복귀', '예정보다 일찍', '백악관으로 복귀', '백악관 복귀')
STATE_ALERT_ACTOR_TERMS = ('state department', 'u.s. embassy', 'us embassy', 'u.s. embassies', 'us embassies', 'travel.gov', '국무부', '미국 대사관', '미 대사관')
STATE_ALERT_TERMS = ('security alert', 'security alerts', 'heightened vigilance', 'potential for unforeseen escalation', 'unforeseen escalation', 'escalate rapidly', 'reconsider travel', '보안 경보', '보안경보', '경계 강화', '예상치 못한 확전', '빠르게 확전', '여행 재고')
MIDDLE_EAST_TERMS = ('middle east', 'mideast', 'west asia', '중동', '서아시아', 'saudi', '사우디', 'iran', '이란', 'houthi', 'houthis', '후티')
CODE100_TERMS = ('code 100', 'code-100', '코드 100', '코드100')
ARMED_FORCE_TERMS = ('armed forces', 'irgc', 'army', 'security forces', 'revolutionary guards', 'military', '군', '전군', '혁명수비대', '육군', '보안군', '무장군')
NETANYAHU_TERMS = ('netanyahu', 'benjamin netanyahu', '네타냐후', '베냐민 네타냐후')
US_TRIP_TERMS = ('u.s. trip', 'us trip', 'united states trip', 'trip to the united states', 'visit to the united states', '미국 방문', '방미', '미국 일정')
RETURN_ISRAEL_TERMS = ('return to israel', 'returned to israel', 'fly back to israel', 'cut short', 'early return', '귀국', '조기 귀국', '조기귀국', '일정 단축')
RIYADH_TERMS = ('riyadh', '리야드')
MISSILE_TERMS = ('missile', 'missiles', 'ballistic missile', 'ballistic missiles', '미사일', '탄도미사일', '탄도 미사일')
MISSILE_ACTION_TERMS = ('launched', 'fired', 'attack', 'attacked', 'intercepted', 'targeted', '발사', '공격', '요격', '표적')
HOUTHI_TERMS = ('houthi', 'houthis', 'ansarallah', 'ansar allah', '후티', '안사르알라', '안사르 알라')

NEW_YORK_TERMS = ('new york', 'nyc', '뉴욕')
DELEGATION_TERMS = ('delegation', 'delegates', 'iranian delegation', 'iran delegation', '대표단', '협상단')
FULL_MANDATE_TERMS = ('full authority', 'complete authority', 'full mandate', 'complete mandate', 'fully authorized', '전권', '완전한 권한', '전적인 권한')
DIPLO_RESTART_TERMS = ('resume diplomacy', 'restart diplomacy', 'renew diplomacy', 're-engage in diplomacy', 'resume talks', 'restart talks', '외교 재개', '외교를 재개', '협상 재개')
MEDIATOR_TERMS = ('mediator', 'mediators', 'mediation', 'through mediators', '중재자', '중재를 통해', '중재')
HOSTILITIES_END_TERMS = ('end hostilities', 'ending hostilities', 'cessation of hostilities', 'end of hostilities', '종전', '적대행위 종식', '적대 행위 종식', '교전 종식')
AGREEMENT_DETAIL_TERMS = ('details of an agreement', 'agreement details', 'terms of an agreement', 'deal details', '합의안 세부', '합의 세부', '협정 세부')
CONCRETE_STEPS_TERMS = ('concrete steps', 'specific steps', 'tangible steps', '구체적인 조치', '구체적 조치', '실질적 조치')
WELCOME_TERMS = ('welcome', 'welcomes', 'ready to welcome', 'would welcome', 'open to', '환영', '열려 있', '준비')
RTRS_RELAY_TERMS = ('rtrs', 'reuters', '로이터')
WITKOFF_TERMS = ('witkoff', 'steve witkoff', '위트코프', '스티브 위트코프', 'ویتکاف')
DIRECT_MEETING_TERMS = ('met with', 'meeting with', 'held talks with', 'face-to-face', 'met', 'meeting', 'talks with', '회동', '회담', '만남', 'دیدار', 'گفتگو')
IRIB_SOURCE_TERMS = ('irib', 'iranian state tv', 'iranian state television', '이란 국영방송', '이란 국영 tv', 'صدا و سیما')
BLOCKADE_LIFT_TERMS = ('lift the blockade', 'lifting the blockade', 'lifting of the blockade', 'lifting of the naval blockade', 'lift its blockade', 'end the naval blockade', 'naval blockade lifted', '해상 봉쇄 해제', '봉쇄 즉각 해제', '봉쇄 해제')
FROZEN_ASSET_TERMS = ('frozen assets', 'frozen iranian assets', 'frozen funds', 'release frozen assets', 'release of frozen iranian assets', 'release frozen funds', '동결 자산', '동결된 이란 자산', '동결자금', '동결 자금')
ALL_FRONTS_END_TERMS = ('end the war on all fronts', 'end war on all fronts', 'end to the war on all fronts', 'war on all fronts', '모든 전선에서의 전쟁 종식', '모든 전선 종전', '전 전선 종전')

TRUSTED_EMERGENCY_SOURCES = ('reuters', 'apnews', 'associated press', 'afp', 'whitehouse.gov', 'state.gov', 'travel.state.gov', 'gov.il', 'irna.ir', 'tasnimnews', 'tasnim', 'presstv', 'saudipressagency', 'spa.gov.sa', 'arabnews')


def _clean_html(raw: str) -> str:
    raw = re.sub(r'<br\s*/?>', '\n', raw, flags=re.I)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = html_lib.unescape(raw)
    raw = re.sub(r'[ \t]+', ' ', raw)
    raw = re.sub(r'\n\s*\n+', '\n', raw)
    return raw.strip()


def _iran_diplomacy_backfill():
    """사용자가 제공한 LiveSquawk의 RTRS 중계 속보를 즉시 복구. 2026-09-23 이후 자동 비활성화."""
    today = dt.datetime.now(watch.KST).date()
    if today > dt.date(2026, 9, 23):
        return [], None
    text = (
        "Senior Iranian official to RTRS: Iranian delegation arrived in New York with full authority "
        "to resume diplomacy with the United States. Details of an agreement to end hostilities "
        "with the United States could be discussed in New York through mediators. Tehran would "
        "welcome resumption of diplomacy if the United States takes concrete steps."
    )
    return [{
        'title': 'Iranian delegation arrives in New York with full authority to resume US diplomacy — RTRS relay',
        'title_original': 'Iranian delegation arrives in New York with full authority to resume US diplomacy — RTRS relay',
        'title_ko': '',
        'link': 'https://x.com/LiveSquawk/status/2102335418322837901',
        'published': 'Tue, 22 Sep 2026 09:53:17 GMT',
        'source': 'LiveSquawk · RTRS 중계',
        'description': text,
        'article_text': text,
        'deep_signal': True,
    }], None


def _irib_meeting_backfill():
    """사용자 제공 IRIB 보도 누락 복구. 직접 회동은 IRIB 보도 단계로만 표시하며 2026-09-24 이후 자동 비활성화."""
    today = dt.datetime.now(watch.KST).date()
    if today > dt.date(2026, 9, 24):
        return [], None
    text = (
        "IRIB reported that Iranian Foreign Minister Abbas Araghchi met U.S. envoy Steve Witkoff in New York "
        "and accepted a meeting request to discuss conditions for reopening the Strait of Hormuz. "
        "The reported Iranian conditions included immediate lifting of the naval blockade, immediate release "
        "of frozen Iranian assets, and an end to the war on all fronts. "
        "Reuters separately confirmed the same day that U.S.-Iran talks were continuing and that Iran had "
        "authorized its New York delegation to revive diplomacy, but Reuters had not independently confirmed "
        "the face-to-face Araghchi-Witkoff meeting in its public report."
    )
    return [{
        'title': 'IRIB reports Araghchi-Witkoff New York meeting on Hormuz reopening conditions',
        'title_original': 'IRIB reports Araghchi-Witkoff New York meeting on Hormuz reopening conditions',
        'title_ko': '',
        'link': 'https://www.iribnews.ir/',
        'published': 'Tue, 22 Sep 2026 19:00:00 GMT',
        'source': 'IRIB 보도 · 독립확인 대기',
        'description': text,
        'article_text': text,
        'deep_signal': True,
    }], None


def _bing_iran_diplomacy_rows():
    rows, seen, errors = [], set(), []
    now = dt.datetime.now(dt.timezone.utc)
    for query in BING_IRAN_DIPLOMACY_QUERIES:
        try:
            url = "https://www.bing.com/news/search?format=rss&q=" + urllib.parse.quote(query)
            root = ET.fromstring(watch.req(url, 12))
        except Exception as exc:
            errors.append(f"BingIranDiplomacy:{type(exc).__name__}")
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
                    if direct.startswith(("http://", "https://")):
                        link = direct
            except Exception:
                pass
            key = (title.lower(), link)
            if key in seen:
                continue
            seen.add(key)
            if pub:
                try:
                    stamp = dt.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc)
                    if (now - stamp).total_seconds() > 48 * 3600:
                        continue
                except Exception:
                    pass
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
    return rows, '; '.join(errors) if errors else None


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


def _bing_emergency_rows():
    rows = []
    errors = []
    now = dt.datetime.now(dt.timezone.utc)
    seen = set()
    for query in BING_EMERGENCY_QUERIES:
        try:
            url = "https://www.bing.com/news/search?format=rss&q=" + urllib.parse.quote(query)
            root = ET.fromstring(watch.req(url, 12))
        except Exception as exc:
            errors.append(f"BingEmergency:{type(exc).__name__}")
            continue
        for item in root.findall("./channel/item")[:20]:
            title = html_lib.unescape((item.findtext("title") or "").strip())
            link = (item.findtext("link") or "").strip()
            desc = html_lib.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).strip()
            pub = (item.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            try:
                parsed = urllib.parse.urlparse(link)
                if "bing.com" in parsed.netloc.lower():
                    direct = (urllib.parse.parse_qs(parsed.query).get("url") or [""])[0]
                    if direct.startswith(("http://", "https://")):
                        link = direct
            except Exception:
                pass
            key = (title.lower(), link)
            if key in seen:
                continue
            seen.add(key)
            if pub:
                try:
                    stamp = dt.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc)
                    if (now - stamp).total_seconds() > 48 * 3600:
                        continue
                except Exception:
                    pass
            rows.append({
                "title": title,
                "title_original": title,
                "title_ko": "",
                "link": link,
                "published": pub,
                "source": "Bing News",
                "description": desc,
                "article_text": desc,
            })
    return rows, "; ".join(errors) if errors else None


def google_news(query):
    if query == WALTER_SENTINEL:
        return _walter_rows()
    if query == BING_EMERGENCY_SENTINEL:
        return _bing_emergency_rows()
    if query == IRAN_DIPLO_SENTINEL:
        return _bing_iran_diplomacy_rows()
    if query == IRAN_DIPLO_BACKFILL_SENTINEL:
        return _iran_diplomacy_backfill()
    if query == IRIB_MEETING_BACKFILL_SENTINEL:
        return _irib_meeting_backfill()
    return _prev_google_news(query)

watch.google_news = google_news


def _text(row):
    # 이전 단계가 붙인 해석 문구(signals_ko/title_ko)를 다시 사실 원문처럼 읽지 않는다.
    # 분류 오염을 막기 위해 원제목·원설명·원문만 판정에 사용한다.
    return ' '.join([row.get('title_original', ''), row.get('description', ''), row.get('article_text', '')]).lower()


def _source_text(row):
    return ' '.join([row.get('source', ''), row.get('link', ''), row.get('resolved_url', '')]).lower()


def _has(text, terms):
    return any(term in text for term in terms)


def _trusted(row):
    src = _source_text(row)
    return any(term in src for term in TRUSTED_CONFIRM_SOURCES)


def _title_text(row):
    return str(row.get('title_original', '')).lower()


def _obvious_false_positive(row):
    title = _title_text(row)
    if _has(title, FALSE_POSITIVE_TITLE_TERMS):
        return True
    if not _has(title, WAR_TITLE_ACTOR_TERMS) and not _has(title, WAR_TITLE_ACTION_TERMS):
        return True
    return False


def _houthi_diplomacy_marks(row):
    try:
        return houthi_watch._diplomacy_marks(houthi_watch._maritime_marks(row))
    except Exception:
        return []


def _trusted_emergency(row):
    src = _source_text(row)
    return any(term in src for term in TRUSTED_EMERGENCY_SOURCES)


def _emergency_marks(row):
    text = _text(row)
    marks = []

    if _has(text, IRAN_TERMS) and _has(text, CODE100_TERMS) and _has(text, ARMED_FORCE_TERMS):
        if _trusted_emergency(row):
            marks.append('이란Code100확인보도')
        else:
            marks.append('이란Code100미확인보도')

    if _has(text, TRUMP_TERMS) and _has(text, CAMP_DAVID_TERMS) and _has(text, EARLY_RETURN_TERMS):
        marks.append('트럼프캠프데이비드조기복귀')

    if _has(text, STATE_ALERT_ACTOR_TERMS) and _has(text, STATE_ALERT_TERMS) and _has(text, MIDDLE_EAST_TERMS):
        marks.append('미국중동다중보안경보')

    if _has(text, NETANYAHU_TERMS) and _has(text, RETURN_ISRAEL_TERMS) and (_has(text, US_TRIP_TERMS) or 'united states' in text or 'u.s.' in text or '미국' in text):
        if _trusted_emergency(row):
            marks.append('네타냐후조기귀국확인보도')
        else:
            marks.append('네타냐후조기귀국미확인보도')

    if _has(text, HOUTHI_TERMS) and _has(text, RIYADH_TERMS) and _has(text, MISSILE_TERMS) and _has(text, MISSILE_ACTION_TERMS):
        marks.append('후티리야드미사일위협')

    return sorted(set(marks))


def _iran_newyork_diplomacy_marks(row):
    text = _text(row)
    src = _source_text(row)
    marks = []
    if not _has(text, IRAN_TERMS):
        return marks

    newyork = _has(text, NEW_YORK_TERMS)
    delegation = _has(text, DELEGATION_TERMS)
    full_mandate = _has(text, FULL_MANDATE_TERMS)
    diplo_restart = _has(text, DIPLO_RESTART_TERMS)
    mediator = _has(text, MEDIATOR_TERMS)
    end_hostilities = _has(text, HOSTILITIES_END_TERMS)
    agreement_detail = _has(text, AGREEMENT_DETAIL_TERMS) or ('agreement' in text and ('details' in text or 'terms' in text))
    concrete = _has(text, CONCRETE_STEPS_TERMS)
    welcome = _has(text, WELCOME_TERMS)
    araghchi = _has(text, IRAN_FM_TERMS)
    witkoff = _has(text, WITKOFF_TERMS)
    direct_meeting = _has(text, DIRECT_MEETING_TERMS)
    irib_report = _has(_source_text(row) + ' ' + text, IRIB_SOURCE_TERMS)
    blockade_lift = _has(text, BLOCKADE_LIFT_TERMS)
    frozen_assets = _has(text, FROZEN_ASSET_TERMS)
    all_fronts_end = _has(text, ALL_FRONTS_END_TERMS)

    # 두 이름과 'meeting'이 기사 안에 따로 존재하는 것만으로 직접회동으로 승격하지 않는다.
    # 동일 문장·근접 문맥에서 Araghchi↔Witkoff가 실제 회동 동사로 연결될 때만 인정.
    pair_patterns = (
        r'araghchi.{0,100}(?:met with|met|meeting with|held talks with|face-to-face|sat down with).{0,100}witkoff',
        r'witkoff.{0,100}(?:met with|met|meeting with|held talks with|face-to-face|sat down with).{0,100}araghchi',
        r'araghchi.{0,80}witkoff.{0,80}(?:met|meeting|held talks|face-to-face)',
        r'witkoff.{0,80}araghchi.{0,80}(?:met|meeting|held talks|face-to-face)',
        r'(?:아라치|이란 외무장관).{0,80}(?:위트코프|스티브 위트코프).{0,80}(?:회동|회담|만났|대면)',
        r'(?:عراقچی).{0,100}(?:ویتکاف).{0,100}(?:دیدار|گفتگو)',
    )
    direct_pair = any(re.search(p, text, re.I | re.S) for p in pair_patterns)

    if newyork and araghchi and witkoff and direct_meeting and direct_pair:
        if irib_report and not ('reuters.com' in src or 'apnews.com' in src):
            marks.append('IRIB아라치위트코프뉴욕회동보도')
            marks.append('직접회동독립확인대기')
        elif _trusted(row) or 'axios.com' in src:
            marks.append('아라치위트코프뉴욕회동확인')
    if newyork and araghchi and witkoff and direct_pair and _has(text, HORMUZ_TERMS) and (blockade_lift or frozen_assets or all_fronts_end):
        marks.append('호르무즈재개방조건직접협의')
    if blockade_lift:
        marks.append('해상봉쇄해제조건')
    if frozen_assets:
        marks.append('동결자산지급조건')
    if all_fronts_end:
        marks.append('전전선종전조건')

    if newyork and delegation and full_mandate and diplo_restart:
        marks.append('이란뉴욕대표단외교전권')
    if newyork and mediator and end_hostilities and agreement_detail:
        marks.append('뉴욕중재종전합의안협의')
    if concrete and welcome and diplo_restart and (_has(text, US_TERMS) or 'united states' in text):
        marks.append('미구체조치시외교재개환영')

    if marks:
        if 'reuters.com' in src or (row.get('source') or '').lower() == 'reuters':
            marks.append('Reuters직접확인')
        elif 'livesquawk' in src or 'rtrs' in (row.get('source') or '').lower() or 'rtrs' in text:
            marks.append('RTRS중계속보')
    return sorted(set(marks))


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
    marks.extend(_iran_newyork_diplomacy_marks(row))
    marks.extend(_iran_war_stage_marks(row))
    marks.extend(_emergency_marks(row))
    return sorted(set(marks))


def _korean_title(marks):
    if '아라치위트코프뉴욕회동확인' in marks:
        return '아라치–위트코프 뉴욕 직접 회동 확인 — 호르무즈 재개방 조건 협의 단계'
    if 'IRIB아라치위트코프뉴욕회동보도' in marks:
        return 'IRIB: 아라치–위트코프 뉴욕 회동 보도 — 미국·Reuters 독립확인 대기'
    if '이란뉴욕대표단외교전권' in marks and '뉴욕중재종전합의안협의' in marks:
        return '이란 대표단, 미국과 외교 재개 전권 갖고 뉴욕 도착 — 중재 통한 적대행위 종식 합의안 협의 가능'
    if '이란뉴욕대표단외교전권' in marks:
        return '이란 대표단, 미국과 외교 재개 전권 갖고 뉴욕 도착'
    if '미구체조치시외교재개환영' in marks:
        return '이란 “미국이 구체적 조치하면 외교 재개 환영” — 뉴욕 협상 신호 강화'
    if '이란Code100확인보도' in marks:
        return '이란 전군 최고경계 “Code 100” 확인 보도 — 중동 비상단계 급상승'
    if '이란Code100미확인보도' in marks:
        return '이란 전군 최고경계 “Code 100” 보도 — 공식 확인 전 고위험 신호'
    if '미국중동다중보안경보' in marks:
        return '미 국무부·중동 미 대사관 보안경보 확대 — “빠른 확전 가능성” 경고'
    if '트럼프캠프데이비드조기복귀' in marks:
        return '트럼프, Camp David 일정 단축·백악관 조기 복귀 — 중동 긴장 동시 확대'
    if '네타냐후조기귀국확인보도' in marks:
        return '네타냐후, 미국 일정 단축·이스라엘 조기 귀국 확인 보도'
    if '네타냐후조기귀국미확인보도' in marks:
        return '네타냐후 미국 일정 단축·조기 귀국 보도 — 공식 확인 대기'
    if '후티리야드미사일위협' in marks:
        return '후티, 리야드 탄도미사일 공격·요격 신호 — 사우디 수도권 위험 상승'
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
    if '아라치위트코프뉴욕회동확인' in marks:
        out.append('🟢 아라치 이란 외무장관–Steve Witkoff 미국 특사의 뉴욕 직접 회동이 독립 확인됨 — 대표단 전권·중재 가능성에서 실제 대면협상 단계로 상승')
    if 'IRIB아라치위트코프뉴욕회동보도' in marks:
        out.append('🟡 IRIB가 아라치–Witkoff 뉴욕 회동을 보도 — Reuters는 같은 날 미·이란 협상 지속·대표단 전권을 확인했지만 공개 기사에서 두 사람의 대면 회동은 아직 독립 확인 전')
    if '직접회동독립확인대기' in marks:
        out.append('확정 수준: IRIB 보도 단계 — 미국 측·Reuters·AP의 대면 회동 독립 확인 대기')
    if '호르무즈재개방조건직접협의' in marks:
        out.append('🟡 호르무즈 재개방 조건을 직접 협의했다는 보도 — 해상 봉쇄 해제·동결자산·전 전선 종전 조건의 공식 공동확인 여부 추적')
    if '해상봉쇄해제조건' in marks:
        out.append('조건: 미국의 이란 항만·해상 봉쇄 해제')
    if '동결자산지급조건' in marks:
        out.append('조건: 동결된 이란 자산·자금 지급/해제')
    if '전전선종전조건' in marks:
        out.append('조건: 모든 전선에서의 전쟁 종식')
    if '이란뉴욕대표단외교전권' in marks:
        out.append('🟡 이란 대표단이 미국과 외교를 재개할 완전한 권한을 갖고 뉴욕에 도착했다는 고위 당국자 발언 — 단순 접촉 가능성보다 한 단계 상승')
    if '뉴욕중재종전합의안협의' in marks:
        out.append('🟡 미국과의 적대행위 종식 합의안 세부를 중재자를 통해 뉴욕에서 논의할 수 있다는 신호')
    if '미구체조치시외교재개환영' in marks:
        out.append('🟡 테헤란은 미국이 구체적 조치를 취하면 외교 재개를 환영한다는 조건부 재개 의사')
    if 'RTRS중계속보' in marks:
        out.append('확정 수준: LiveSquawk가 RTRS 발언으로 중계한 속보 — Reuters 공개 기사 원문은 후속 재확인')
    if 'Reuters직접확인' in marks:
        out.append('확정 수준: Reuters 직접 기사에서 확인')

    if '이란Code100확인보도' in marks:
        out.append('🔴 이란 전군 최고경계 Code 100이 신뢰 원천에서 확인 보도됨 — IRGC·정규군·보안군의 실제 배치·동원 후속 확인')
    if '이란Code100미확인보도' in marks:
        out.append('⚠️ 이란 Code 100 최고경계 보도 — 현재 공식·주요통신 독립확인 전이지만 사실일 경우 파급이 커서 미확인 고위험 신호로 즉시 경보')
    if '트럼프캠프데이비드조기복귀' in marks:
        out.append('🔴 트럼프가 Camp David 주말 일정을 하루 앞당겨 백악관으로 복귀 — 일정 변경 자체는 확인, 백악관은 복귀 사유를 공식 설명하지 않음')
    if '미국중동다중보안경보' in marks:
        out.append('🔴 미 국무부·중동 복수 미 대사관이 보안경보를 확대 — “예상치 못한 확전”·“군사 충돌의 빠른 확대 가능성”을 경고')
    if '네타냐후조기귀국확인보도' in marks:
        out.append('🔴 네타냐후의 미국 일정 단축·이스라엘 조기 귀국이 신뢰 원천에서 확인 보도됨 — 안보회의·군 지시 여부 후속 확인')
    if '네타냐후조기귀국미확인보도' in marks:
        out.append('⚠️ 네타냐후 미국 일정 단축·조기 귀국 보도 — 공식·주요통신 확인 전 고위험 일정 신호로 추적')
    if '후티리야드미사일위협' in marks:
        out.append('🔴 후티의 리야드 탄도미사일 공격·요격 신호 — 사우디 수도·공항·에너지 시설 추가 표적 여부 확인')
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
    emergency_marks = _emergency_marks(row)
    iran_diplomacy_marks = _iran_newyork_diplomacy_marks(row)
    tags = ['종전·협상']
    if iran_diplomacy_marks:
        tags += ['이란전쟁', '뉴욕외교', '외교재개', '중재']
        if any(m in iran_diplomacy_marks for m in ('IRIB아라치위트코프뉴욕회동보도','아라치위트코프뉴욕회동확인','호르무즈재개방조건직접협의')):
            tags += ['직접회동', '호르무즈조건']
    if emergency_marks:
        tags += ['확전', '중동비상경보']
        if any(m in emergency_marks for m in ('이란Code100미확인보도', '네타냐후조기귀국미확인보도')):
            tags += ['미확인고위험']
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
    if emergency_marks:
        if any(m in emergency_marks for m in ('이란Code100확인보도', '미국중동다중보안경보', '트럼프캠프데이비드조기복귀', '네타냐후조기귀국확인보도', '후티리야드미사일위협')):
            score = 100
        else:
            score = 97
    elif iran_diplomacy_marks:
        if '아라치위트코프뉴욕회동확인' in iran_diplomacy_marks:
            score = 100
        elif 'IRIB아라치위트코프뉴욕회동보도' in iran_diplomacy_marks:
            score = 99
        else:
            score = 100 if 'Reuters직접확인' in iran_diplomacy_marks else 99
    elif any(m in marks for m in ('종전합의', '정식휴전합의', '호르무즈실물정상화', '협상후퇴')):
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
    emergency_marks = [m for m in marks if m in (
        '이란Code100확인보도','이란Code100미확인보도','트럼프캠프데이비드조기복귀','미국중동다중보안경보',
        '네타냐후조기귀국확인보도','네타냐후조기귀국미확인보도','후티리야드미사일위협',
    )]
    if emergency_marks:
        try:
            pub = watch.parse_pub(row.get('published', ''))
            day = pub.date().isoformat() if pub else dt.datetime.now(dt.timezone.utc).date().isoformat()
        except Exception:
            day = dt.datetime.now(dt.timezone.utc).date().isoformat()
        key = 'middle-east-emergency|' + day + '|' + '|'.join(sorted(emergency_marks))
    else:
        stage_marks = [m for m in marks if m in ('IRIB아라치위트코프뉴욕회동보도','직접회동독립확인대기','아라치위트코프뉴욕회동확인','호르무즈재개방조건직접협의','해상봉쇄해제조건','동결자산지급조건','전전선종전조건','이란뉴욕대표단외교전권','뉴욕중재종전합의안협의','미구체조치시외교재개환영','RTRS중계속보','Reuters직접확인','미국단독종전협상신호', '이란직접협상확인', '정식휴전합의', '종전합의', '호르무즈실물정상화', '협상후퇴')]
        if stage_marks:
            key = 'iran-war-peace-stage-2026|' + '|'.join(sorted(stage_marks))
        elif any(m.startswith('크렘린') for m in marks):
            key = 'kremlin-energy-diplomacy-2026-09-15|' + '|'.join(marks)
        else:
            key = 'iran-china-diplomacy-2026-09-15|' + '|'.join(marks)
    return hashlib.sha256(key.encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    emarks = _emergency_marks(row)
    if emarks:
        return '중동 비상 · 복합확전 경보'
    hmarks = _houthi_diplomacy_marks(row)
    if hmarks:
        return '예멘·사우디·오만 · Ansar Allah 휴전중재'
    marks = _marks(row)
    if any(m in marks for m in ('IRIB아라치위트코프뉴욕회동보도','아라치위트코프뉴욕회동확인','호르무즈재개방조건직접협의')):
        return '이란 전쟁 · 아라치–Witkoff 뉴욕 회동'
    if any(m in marks for m in ('이란뉴욕대표단외교전권','뉴욕중재종전합의안협의','미구체조치시외교재개환영')):
        return '이란 전쟁 · 뉴욕 외교재개'
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
    marks = {m for x in flash for m in _marks(x)}
    emergency_items = [x for x in items if _emergency_marks(x)]
    emergency_marks = {m for x in emergency_items for m in _emergency_marks(x)}
    hitems = [x for x in items if _houthi_diplomacy_marks(x)]
    hmarks = {m for x in hitems for m in _houthi_diplomacy_marks(x)}
    if not marks and not hmarks and not emergency_marks:
        return _prev_verdict(items)

    lines = ['<b>투자 판정</b>']

    if emergency_marks:
        confirmed = [m for m in emergency_marks if m not in ('이란Code100미확인보도', '네타냐후조기귀국미확인보도')]
        unconfirmed = [m for m in emergency_marks if m in ('이란Code100미확인보도', '네타냐후조기귀국미확인보도')]
        if len(confirmed) >= 2:
            lines.append('- <b>중동 비상:</b> 🔴 서로 다른 확전 신호가 동시 발생 — 단일 루머가 아니라 복합 경보 단계')
        else:
            lines.append('- <b>중동 비상:</b> 🔴 고위험 확전 신호 감지 — 후속 공식 확인과 실제 군사행동을 즉시 추적')
        if '트럼프캠프데이비드조기복귀' in emergency_marks:
            lines.append('- <b>미국 일정:</b> 트럼프 Camp David 일정 단축·백악관 조기 복귀 확인. 복귀 사유 자체는 백악관 미설명')
        if '미국중동다중보안경보' in emergency_marks:
            lines.append('- <b>미국 경보:</b> 국무부·복수 중동 대사관이 예상치 못한 확전·빠른 군사확대 가능성을 경고')
        if '후티리야드미사일위협' in emergency_marks:
            lines.append('- <b>사우디:</b> 후티의 리야드 미사일 공격·요격 신호 — 수도·공항·에너지 인프라 위험 상승')
        if '이란Code100확인보도' in emergency_marks:
            lines.append('- <b>이란:</b> Code 100 전군 최고경계가 신뢰 원천에서 확인 보도됨')
        elif '이란Code100미확인보도' in emergency_marks:
            lines.append('- <b>이란 미확인:</b> Code 100 최고경계 보도는 공식·주요통신 독립확인 전. 사실일 경우 파급이 커 고위험 신호로 유지')
        if '네타냐후조기귀국확인보도' in emergency_marks:
            lines.append('- <b>이스라엘:</b> 네타냐후 미국 일정 단축·조기 귀국 확인 보도')
        elif '네타냐후조기귀국미확인보도' in emergency_marks:
            lines.append('- <b>이스라엘 미확인:</b> 네타냐후 조기 귀국 보도는 공식·주요통신 확인 전')
        lines.append('- <b>다음:</b> 이란 공식 군 경계 공지 → 미·이스라엘 안보회의 → 추가 미사일·공습 → 대사관 운영축소·대피 → 호르무즈·바브엘만데브 실제 통항 변화')

    if hmarks:
        if '후티휴전거부' in hmarks:
            lines.append('- <b>예멘 휴전:</b> 🔴 Ansar Allah가 휴전안을 거부하거나 핵심 조건 미충족을 선언 — 협상 후퇴 단계')
        elif '후티휴전수용' in hmarks:
            lines.append('- <b>예멘 휴전:</b> 🟢 Ansar Allah의 휴전 수용 확인 — 중재 제안에서 양측 합의 단계로 상승')
        elif '2주임시휴전안' in hmarks or '주말합의발표목표' in hmarks:
            lines.append('- <b>예멘 휴전:</b> 🟡 2주 임시휴전·주말 합의 발표 목표가 제시된 협상 진전 단계 — 아직 정식 합의·발효 전')
        elif '사우디오만중재요청' in hmarks:
            lines.append('- <b>예멘 휴전:</b> 🟡 사우디가 오만을 통한 Ansar Allah 중재 채널을 가동 — 공식 휴전 합의 전')
        elif '인도적요구포괄협의' in hmarks:
            lines.append('- <b>예멘 휴전:</b> 🟡 인도적 요구 전반을 휴전 협상 의제로 묶는 단계 — 세부 조건 공식 확인 필요')
        trusted = any(houthi_watch._trusted_diplomacy(x) for x in hitems)
        if trusted:
            lines.append('- <b>확정 수준:</b> Reuters·AP·오만 외교부·사우디 국영통신·유엔·당사자 계열 원천에서 확인된 보도 포함')
        else:
            lines.append('- <b>확정 수준:</b> 2주 기간·인도적 조건·주말 발표 목표는 공식 확인 전 보도 단계 — 확정 휴전으로 표시하지 않음')
        lines.append('- <b>시장:</b> 합의 진전 시 바브엘만데브·Yanbu 우회수출 경로의 해운·전쟁보험·원유 물류 위험프리미엄 완화 가능 / 결렬 시 반대')
        lines.append('- <b>다음:</b> 오만·사우디 공식 확인 → Ansar Allah 수용 여부 → 2주 휴전 발효 시각 → 인도적 조건 공개 → 실제 합의 발표')

    if 'IRIB아라치위트코프뉴욕회동보도' in marks or '아라치위트코프뉴욕회동확인' in marks:
        if '아라치위트코프뉴욕회동확인' in marks:
            lines.append('- <b>미·이란 뉴욕 회동:</b> 🟢 아라치–Witkoff 직접 회동 확인 — 외교 재개 가능성에서 실제 대면협상 단계로 상승')
            lines.append('- <b>확정 수준:</b> 독립 신뢰원 확인 단계')
        else:
            lines.append('- <b>미·이란 뉴욕 회동:</b> 🟡 IRIB가 아라치–Witkoff 회동을 보도 — Reuters는 협상 지속·이란 대표단 전권을 확인했지만 대면 회동 자체는 공개 기사에서 독립확인 전')
            lines.append('- <b>확정 수준:</b> IRIB 보도 단계 — 미국 측·Reuters·AP의 대면 회동 독립 확인 대기')
        conds = []
        if '해상봉쇄해제조건' in marks:
            conds.append('해상 봉쇄 해제')
        if '동결자산지급조건' in marks:
            conds.append('동결자산 지급/해제')
        if '전전선종전조건' in marks:
            conds.append('모든 전선 종전')
        if conds:
            lines.append('- <b>호르무즈 조건:</b> ' + ' · '.join(conds))
        lines.append('- <b>다음:</b> 미국 측 회동 확인 → 공동/각자 회담 결과 → 호르무즈 재개방 조건 문서화 → 실제 통항 회복')
    elif '이란뉴욕대표단외교전권' in marks or '뉴욕중재종전합의안협의' in marks or '미구체조치시외교재개환영' in marks:
        parts = []
        if '이란뉴욕대표단외교전권' in marks:
            parts.append('대표단 외교 재개 전권')
        if '뉴욕중재종전합의안협의' in marks:
            parts.append('중재 통한 적대행위 종식 합의안 세부 협의 가능')
        if '미구체조치시외교재개환영' in marks:
            parts.append('미국 구체 조치 시 외교 재개 환영')
        lines.append('- <b>이란 뉴욕 외교:</b> 🟡 ' + ' · '.join(parts) + ' — 아직 미·이란 최종 합의나 휴전 발효는 아님')
        if 'RTRS중계속보' in marks and 'Reuters직접확인' not in marks:
            lines.append('- <b>확정 수준:</b> RTRS 중계 속보 단계 — Reuters 공개 본문·이란 공식 발표를 후속 재확인')
        elif 'Reuters직접확인' in marks:
            lines.append('- <b>확정 수준:</b> Reuters 직접 확인 단계')
        lines.append('- <b>다음:</b> 중재자 실명·접촉 → 미국의 구체 조치 → 미·이란 회담 형식·시각 → 휴전·종전 문안 → 호르무즈 실제 정상화')
    elif '협상후퇴' in marks:
        lines.append('- <b>이란 전쟁:</b> 🔴 협상 후퇴 — 직접협상 부인·거부·결렬 신호. 종전 기대를 낮춰야 하는 변화')
    elif '호르무즈실물정상화' in marks:
        lines.append('- <b>이란 전쟁:</b> 🟢 호르무즈 실물 정상화 — 재개방 문구가 아니라 유조선·LNG선 등 실제 상선 통항 회복 확인')
    elif '종전합의' in marks:
        lines.append('- <b>이란 전쟁:</b> 🟢 종전 합의 — 휴전보다 높은 단계. 평화협정·적대행위 종료의 실제 조건과 이행 일정 확인 필요')
    elif '정식휴전합의' in marks:
        lines.append('- <b>이란 전쟁:</b> 🟢 정식 휴전 — 공격 중단 합의·발효 단계. 실제 이행과 위반 여부 후속 확인')
    elif '이란직접협상확인' in marks:
        lines.append('- <b>이란 전쟁:</b> 🟡 양측 확인 — 이란 측도 미국과 직접 협상·접촉을 확인. 아직 휴전·종전 확정은 아님')
    elif '미국단독종전협상신호' in marks:
        lines.append('- <b>이란 전쟁:</b> ⚠️ 미국 측 종전·직접접촉 주장 단계 — 이란 공식 확인 전에는 휴전·종전으로 판정하지 않음')

    if any(m in marks for m in ('IRIB아라치위트코프뉴욕회동보도','아라치위트코프뉴욕회동확인','호르무즈재개방조건직접협의')):
        lines.append('- <b>이란 단계 추적:</b> 대표단 전권 → 중재 합의안 협의 → 아라치–Witkoff 회동 보도 → 미국 측/독립 확인 → 조건 문서화 → 휴전·종전 → 호르무즈 실제 정상화')
    elif any(m in marks for m in ('이란뉴욕대표단외교전권','뉴욕중재종전합의안협의','미구체조치시외교재개환영')):
        lines.append('- <b>이란 단계 추적:</b> 뉴욕 대표단 전권 → 중재 합의안 협의 → 미국 구체 조치 → 회담 재개 → 정식 휴전 → 종전 합의 → 호르무즈 실제 정상화')
    elif any(m in marks for m in ('미국단독종전협상신호', '이란직접협상확인', '정식휴전합의', '종전합의', '협상후퇴')):
        lines.append('- <b>이란 단계 추적:</b> 미국 측 협상 신호 → 이란 측 확인 → 정식 휴전 → 종전 합의 → 호르무즈 실제 정상화')
    if '호르무즈실물정상화' in marks:
        lines.append('- <b>실물 확인:</b> 선박 수·유조선·LNG선 통항량이 지속 회복되는지 별도 추적')
    if '크렘린에너지휴전긍정평가' in marks:
        lines.append('- <b>우크라이나:</b> 🟢 크렘린이 트럼프의 에너지 표적 휴전 제안을 긍정 평가 — 러시아 측 수용 가능성이 한 단계 올라감')
        lines.append('- <b>확정 수준:</b> 긍정 평가이지 정식 휴전 합의·발효 확정은 아님')
    if '크렘린제재해제에너지가격하락발언' in marks:
        lines.append('- <b>에너지:</b> 🟡 크렘린이 제재 해제와 세계 에너지 가격 하락을 직접 연결 — 향후 제재 협상이 유가·디젤 완화 촉매가 될 수 있음')
    if '이란외무장관중국방문' in marks:
        lines.append('- <b>중동 외교:</b> 🟢 이란 외무장관의 중국 방문·왕이 회담 일정 — 중국 중재채널 확대 여부 확인')
    if '중국계위성영상제공보도' in marks:
        lines.append('- <b>미확인 리스크:</b> 🟠 중국계 주체의 이란 위성영상 제공 보도는 중국 정부 직접 관여가 확인되지 않은 단계')

    return '\n'.join(lines)

guard._verdict = _verdict

_prev_emergency_color = guard._enhanced_body_color

def _emergency_color(row):
    if _emergency_marks(row):
        return 'red'
    return _prev_emergency_color(row)

guard._enhanced_body_color = _emergency_color
guard.prev._strict_body_color = _emergency_color
guard.prev.core._body_color = _emergency_color


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
