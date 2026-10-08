#!/usr/bin/env python3
"""AI-RAN / Physical-AI edge-infrastructure lane for the existing watcher.

This extends the current Physical-AI alert route. It does not create a new bot,
workflow or state file. Articles, press releases and operator announcements are
discovery sources; the alert unit is a material AI-RAN commercialization or
physical-AI deployment milestone.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

import physical_ai_watch_us_autowarcom as defense

qty = defense.qty
base = defense.base

# Nickel-plated battery-can steel: verified 2026-09 qualification is a
# baseline; reported October shipments are an unconfirmed new milestone.
# Never infer Tesla Optimus / Boston Dynamics Atlas as a Dongkuk customer.
DONGKUK_NPS_RECOVERY = 'DIRECT_DONGKUK_NPS_OCT_FIRST_SHIPMENT_REPORT_20261008'
DONGKUK_NAME = re.compile(r'동국산업|Dongkuk\\s*Industr(?:y|ies)', re.I)
DONGKUK_NPS = re.compile(r'니켈\\s*도금\\s*강판|니켈도금강판|nickel[-\\s]*plated\\s*(?:steel|sheet)|\\bDiKel\\b', re.I)
DONGKUK_46 = re.compile(r'46\\s*시리즈|46시리즈|46\\s*파이|46[-\\s]*series|46\\s*mm|46mm|4680|4695|46120', re.I)
DONGKUK_SHIP_ACTUAL = re.compile(
    r'(?:10\\s*월|October).{0,100}(?:초도\\s*납품|첫\\s*납품|첫\\s*출하|initial\\s*shipments?|first\\s*deliveries?).{0,70}'
    r'(?:시작|개시|완료|진행|출하|전해|보도|started|began|commenced|delivered)|'
    r'(?:초도\\s*납품|첫\\s*출하).{0,65}(?:10\\s*월|October).{0,70}(?:시작|개시|완료|보도|전해|started|began)',
    re.I,
)
DONGKUK_QUAL = re.compile(r'품질\\s*(?:인증|승인).{0,30}(?:완료|통과|마쳤|성공)|(?:고객|고객사).{0,50}(?:품질\\s*승인|인증).{0,40}(?:완료|통과|마쳤)', re.I)
DONGKUK_CONTRACT = re.compile(r'(?:공급\\s*계약|확정\\s*발주|구매\\s*계약|납품\\s*계약|contract\\s*signed|purchase\\s*order).{0,80}(?:체결|확정|서명|signed|confirmed)|(?:체결|확정).{0,60}(?:공급\\s*계약|구매\\s*계약)', re.I)
DONGKUK_ROBOT_LINK = re.compile(
    r'(?:Optimus|옵티머스|Atlas|아틀라스|Boston\\s*Dynamics|보스턴다이내믹스).{0,90}'
    r'(?:직접\\s*납품|직접\\s*공급|공급계약\\s*체결|직접\\s*공급사)|'
    r'(?:직접\\s*납품|직접\\s*공급|공급계약\\s*체결).{0,90}'
    r'(?:Optimus|옵티머스|Atlas|아틀라스|Boston\\s*Dynamics|보스턴다이내믹스)',
    re.I,
)
DONGKUK_OFFICIAL_SOURCES = {'동국산업', 'Dongkuk Industries', 'Dongkuk Industry'}
DONGKUK_REPORT_TITLE = '동국산업 북미 46시리즈 소재 10월 초도 납품 시작 보도…공식 출하 확인 전'


def _is_dongkuk_nps(text: str) -> bool:
    return bool(DONGKUK_NAME.search(text) and DONGKUK_NPS.search(text) and DONGKUK_46.search(text))


def _dongkuk_stage(text: str, source: str = '') -> str:
    if not _is_dongkuk_nps(text):
        return ''
    if DONGKUK_SHIP_ACTUAL.search(text):
        return 'official_first_shipment' if source in DONGKUK_OFFICIAL_SOURCES else 'reported_first_shipment'
    if DONGKUK_CONTRACT.search(text) and source in DONGKUK_OFFICIAL_SOURCES:
        return 'official_contract'
    if DONGKUK_QUAL.search(text):
        return 'qualification_baseline'
    return 'background'


def _dongkuk_report_recovery() -> list[dict]:
    # Identical NewsScene article reprinted by ITInsight; original knpp URL may
    # be inaccessible. 10/08 first-delivery claim is from unnamed analyst notes,
    # whereas 09/14 qualification was announced by the company.
    return [{
        'title': DONGKUK_REPORT_TITLE,
        'link': 'https://www.itinsight.kr/news/517649',
        'description': (
            '2026-10-08 뉴스씬 정민재 보도: 동국산업 46시리즈용 니켈도금강판의 '
            '북미 고객 품질 승인 완료는 2026-09-14 회사 발표·2026-09-22 이원휘 대표 인터뷰의 기존 사실이다. '
            '새로운 증권가 탐방 전언에는 10월부터 초도 납품을 시작한 것으로 전해졌다고 기재됐다. '
            '이는 동국산업 공식 실제 출하/매출 인식 확인은 아니다. '
            '연간 판매량 2026년 약 2,000톤, 2027년 약 20,000톤(10배)은 애널리스트 예상치이며 '
            '연간 설비능력 80,000톤과 증설 가능 130,000톤, 기존 설비투자 약 1,300억원과 구별한다. '
            '북미 고객 실명과 배터리 캔 가공업체 실명 모두 비공개다. '
            '테슬라 Optimus·보스턴다이내믹스 Atlas 원통형 배터리 언급은 생태계 가능성에 불과하며 '
            '동국산업이 두 로봇에 니켈도금강판을 직접 납품한다는 계약·양산 근거가 없다.'
        ),
        'source': '뉴스씬',
        'published': '2026-10-08T00:35:00+00:00',
        'direct_recovery': True,
        'dongkuk_reported_shipment': True,
    }]


_orig_query_news = base.query_news


def query_news(q: str) -> list[dict]:
    if q == DONGKUK_NPS_RECOVERY:
        return _dongkuk_report_recovery()
    return _orig_query_news(q)


base.query_news = query_news
if DONGKUK_NPS_RECOVERY not in base.QUERIES:
    base.QUERIES.append(DONGKUK_NPS_RECOVERY)
for q in (
    '(동국산업 OR "Dongkuk Industries") (니켈도금강판 OR "nickel plated steel" OR DiKel) '
    '(46시리즈 OR 4680 OR "46 series") (초도납품 OR 출하 OR 고객승인 OR 품질인증 OR 공급계약 OR 양산 OR 납품지연)',
    '(동국산업 OR "Dongkuk Industries") (원통형 배터리 OR 니켈도금강판 OR 46파이) '
    '(북미 OR 로봇 OR 휴머노이드 OR 피지컬AI) (공급계약 OR 본계약 OR 실제출하 OR 매출 OR 양산수율)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_clean_title = base.clean_title
_orig_tag_for = base.tag_for
_orig_key = base.key
_orig_select_diverse = base.select_diverse

AIRAN_ID = re.compile(r'AI[-\s]?RAN|Aerial\s+RAN|ARC[-\s]?Pro|AI[-\s]?native\s+(?:RAN|6G)|AI\s+RAN', re.I)
PHYSICAL = re.compile(
    r'physical\s+AI|robot(?:ics)?|humanoid|vision\s+AI|drone|autonomous|edge\s+AI|'
    r'피지컬\s*AI|로봇|휴머노이드|드론|자율|엣지\s*AI',
    re.I,
)
COMMERCIAL = re.compile(
    r'pilot|trial|field\s+test|deployment|deploy|commercial|customer|operator|contract|order|'
    r'base\s+station|cell\s+site|mobile\s+switching\s+office|edge\s+site|general\s+availability|'
    r'실증|시험|현장\s*검증|배치|상용|고객|통신사|계약|수주|기지국|사이트|출시',
    re.I,
)
QUANT = re.compile(
    r'\b\d+(?:\.\d+)?\s*(?:ms|Gbps|Mbps|%|x|배|site|sites|기지국|개소|GPU|GPUs)\b|'
    r'latency|throughput|uplink|CAPEX|revenue|매출|지연시간|처리량|업링크|설비투자',
    re.I,
)
ACTORS = re.compile(r'NVIDIA|엔비디아|T-Mobile|Nokia|노키아|SK텔레콤|SKT|SoftBank|소프트뱅크|Dell|Siemens', re.I)

for q in [
    '("AI-RAN" OR "AI RAN" OR "Aerial RAN") ("physical AI" OR robotics OR robot OR humanoid OR edge AI) (NVIDIA OR T-Mobile OR Nokia OR operator OR deployment OR pilot)',
    '("AI-RAN" OR "AI RAN") (deployment OR pilot OR field trial OR commercial OR contract OR customer OR base station OR latency OR throughput)',
    '(엔비디아 OR NVIDIA) ("AI-RAN" OR "AI RAN") (피지컬AI OR 로봇 OR 휴머노이드 OR 엣지AI OR 통신사 OR 기지국 OR 실증 OR 상용화)',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)

base.OFFICIAL_OR_PRIMARY.update({'NVIDIA', 'T-Mobile', 'Nokia', 'SK텔레콤', 'SK Telecom'})
base.TRUSTED.update({'Reuters', 'Bloomberg', 'The Robot Report', 'Light Reading', 'Fierce Network'})


def _is_airan(text: str) -> bool:
    return bool(AIRAN_ID.search(text) and (PHYSICAL.search(text) or COMMERCIAL.search(text)) and ACTORS.search(text))


def topic_group(text: str) -> str | None:
    if _is_dongkuk_nps(text):
        return 'dongkuk_nps'
    if _is_airan(text):
        return 'airan'
    return _orig_topic_group(text)


def _stage(text: str) -> str:
    if re.search(r'contract|order|commercial\s+agreement|revenue|paid|수주|계약|매출|유료', text, re.I):
        return 'commercial'
    if re.search(r'deployment|deploy|field\s+test|pilot|trial|실증|현장\s*검증|배치', text, re.I):
        return 'field'
    if QUANT.search(text):
        return 'quantified'
    return 'platform'


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) == 'dongkuk_nps':
        stage = _dongkuk_stage(text, item.get('source') or '')
        return {'reported_first_shipment': 33, 'official_first_shipment': 46,
                'official_contract': 44, 'qualification_baseline': 0,
                'background': 0}.get(stage, 0)
    if topic_group(text) != 'airan':
        return _orig_score(item)
    s = 18
    if item.get('source') in base.OFFICIAL_OR_PRIMARY:
        s += 8
    elif item.get('source') in base.TRUSTED:
        s += 4
    stage = _stage(text)
    if stage == 'commercial':
        s += 12
    elif stage == 'field':
        s += 9
    elif stage == 'quantified':
        s += 7
    if PHYSICAL.search(text):
        s += 7
    if QUANT.search(text):
        s += 5
    return s


def category(text: str, group: str) -> str:
    if group == 'dongkuk_nps':
        return {
            'reported_first_shipment': '동국산업 46시리즈 · 10월 초도 납품 보도',
            'official_first_shipment': '동국산업 46시리즈 · 첫 출하 공식 확인',
            'official_contract': '동국산업 46시리즈 · 정식 공급계약',
        }.get(_dongkuk_stage(text), '동국산업 46시리즈 · 품질 인증 기존 기준선')
    if group == 'airan':
        stage = _stage(text)
        if stage == 'commercial':
            return '엔비디아 AI-RAN · 상용계약·매출'
        if stage == 'field':
            return '엔비디아 AI-RAN · Physical AI 현장 실증·배치'
        if stage == 'quantified':
            return '엔비디아 AI-RAN · 지연시간·처리량 정량 개선'
        return '엔비디아 AI-RAN · Physical AI 엣지 인프라'
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    if cat.startswith('동국산업 46시리즈 · '):
        if '초도 납품 보도' in cat:
            return ('9월 14일 고객 품질인증 완료·4분기 공급 예정은 기존 회사 발표입니다. '
                    '10월 8일 신규 내용은 10월 초도 납품을 시작했다는 증권가 탐방 전언으로, '
                    '회사 확인 출하·매출은 아직 아닙니다. 2026년 약 2,000톤→2027년 약 2만톤은 '
                    '애널리스트 전망이며, 기존 1,300억원 설비·연산 8만톤과 구분합니다. '
                    '실제 출하량×검증된 톤당 평균판매단가가 매출로 연결되는지가 핵심입니다.')
        if '첫 출하 공식 확인' in cat:
            return ('동국산업이 북미 46시리즈 소재 첫 실제 출하를 자체 발표한 단계입니다. '
                    '출하 톤수·배터리 캔 가공업체·원화 단가·매출 인식 분기를 확인합니다.')
        if '정식 공급계약' in cat:
            return ('기존 품질인증을 넘어 신규 공급계약의 실제 체결·구매 물량·기간이 '
                    '회사 공식자료로 확인된 단계입니다. 계약금액과 기인식 매출을 분리합니다.')
        return '기존 고객 품질인증·4분기 양산 계획의 재보도는 신규 상업 매출로 인정하지 않습니다.'
    if not cat.startswith('엔비디아 AI-RAN'):
        return _orig_meaning(cat)
    if '상용계약' in cat:
        return ('AI-RAN이 통신 연구개발을 넘어 실제 통신사·산업 고객의 상용 인프라 매출로 전환되는 신호입니다. '
                '기지국·엣지 사이트 수, GPU/서버 물량, 계약금액과 반복 매출을 확인합니다.')
    if '현장 실증' in cat:
        return ('로봇·비전 AI의 무거운 추론을 단말에서 통신망 엣지로 일부 이전하는 Physical AI 배치 인프라 신호입니다. '
                '통신사 실명, 실제 현장, 지연시간·업링크와 이후 상용 전환 여부를 추적합니다.')
    if '정량 개선' in cat:
        return ('AI-RAN의 투자 논리가 실제 저지연·고업링크·엣지 추론 효율 개선으로 검증되는 신호입니다. '
                '같은 장비·같은 트래픽 조건에서의 지연시간·처리량과 사이트당 경제성을 봅니다.')
    return ('AI-RAN이 통신망을 단순 연결망이 아니라 분산 AI 추론 인프라로 전환하는지 보는 신호입니다. '
            'Physical AI 고객·사이트·GPU 물량과 Edge Computing 매출 연결을 확인합니다.')


def risk(cat: str) -> str:
    if cat.startswith('동국산업 46시리즈 · '):
        return ('테슬라 Optimus·보스턴다이내믹스 Atlas의 원통형 배터리 언급은 '
                '동국산업의 두 로봇 직접 공급 증거가 아닙니다. 북미 실제 고객·캔 공급사도 비공개입니다. '
                '연산 8만톤 대비 애널리스트의 내년 2만톤 전망은 가동률 단순 환산 25%에 불과하며 '
                '단가·납품검수·도금 균일도·캔 성형수율·재작업·보증충당금이 사업성을 좌우합니다. '
                '가장 먼저 확인할 것은 4분기 실제 출하 톤수와 매출 인식입니다.')
    if not cat.startswith('엔비디아 AI-RAN'):
        return _orig_risk(cat)
    return ('AI-RAN과 휴머노이드 직접 채택은 아직 같은 의미가 아닙니다. 현재 공식 실증은 비전 AI·도시·유틸리티·드론 등도 포함하므로 '
            '테슬라·피겨 같은 휴머노이드 고객이 AI-RAN을 실제 사용하는지는 별도로 확인합니다. '
            '현장 지연시간·사이트당 비용·통신사 설비투자와 상용 계약이 먼저 드러나는 조기 지표입니다.')


def verification(item: dict, group: str, text: str) -> str:
    if group == 'dongkuk_nps':
        stage = _dongkuk_stage(text, item.get('source') or '')
        if stage == 'reported_first_shipment':
            return '10/08 뉴스씬 증권가 전언 · 실제 10월 출하 회사 미확인 · 9/14 회사발표·9/22 대표인터뷰로 고객 인증만 검증'
        if stage in {'official_first_shipment', 'official_contract'}:
            return '동국산업 1차자료 단계 · 계약·검수·실적 반영 별도 확인'
        return '9월 기존 인증 기준선 · 신규 출하 아님'
    if group != 'airan':
        return _orig_verification(item, group, text)
    source = item.get('source') or ''
    if source in base.OFFICIAL_OR_PRIMARY:
        return '엔비디아·통신사 공식자료'
    if source in base.TRUSTED:
        return '신뢰 매체 보도 · 엔비디아/통신사 공식자료 교차확인'
    return '보도 단계 · 엔비디아·통신사 1차 자료 후속 확인'


def clean_title(title: str, source: str) -> str:
    text = f'{title} {source}'
    if _is_dongkuk_nps(text):
        stage = _dongkuk_stage(text, source)
        if stage == 'reported_first_shipment':
            return DONGKUK_REPORT_TITLE
        if stage == 'official_first_shipment':
            return '동국산업, 북미 46시리즈 니켈도금강판 첫 출하 공식 확인'
        if stage == 'official_contract':
            return '동국산업, 북미 46시리즈 니켈도금강판 정식 공급계약'
    if _is_airan(text):
        stage = _stage(text)
        if stage == 'commercial':
            return '엔비디아 AI-RAN, Physical AI 상용계약·매출 단계 변화'
        if stage == 'field':
            return '엔비디아 AI-RAN, Physical AI 현장 실증·배치 확대'
        if stage == 'quantified':
            return '엔비디아 AI-RAN, 지연시간·처리량 정량 개선'
        return '엔비디아 AI-RAN, Physical AI 엣지 인프라 신규 변화'
    return _orig_clean_title(title, source)


def tag_for(group: str) -> str:
    if group == 'dongkuk_nps':
        return '동국산업 46시리즈 소재'
    if group == 'airan':
        return '엔비디아AI-RAN'
    return _orig_tag_for(group)


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) == 'dongkuk_nps':
        stage = _dongkuk_stage(text, item.get('source') or '')
        # Event + evidence tier, not publisher/article or unrelated robot claims.
        return hashlib.sha256(f'dongkuk-nps|north-america-46|{stage}|2026-10'.encode()).hexdigest()
    # Final semantic-key guard for Samsung SDI SolidStack humanoid milestones.
    # Later Figure/other wrappers may otherwise fall back to publisher/title keys.
    if getattr(base, '_is_sdi_solidstack_robot', lambda _t: False)(text):
        stage = base._sdi_solidstack_stage(text)
        context = base._sdi_solidstack_context(text)
        return hashlib.sha256(f"samsung-sdi|solidstack-humanoid|{stage}|{context}".encode()).hexdigest()
    if topic_group(text) != 'airan':
        return _orig_key(item)
    try:
        pub = dt.datetime.fromisoformat(item.get('published') or '')
        day = pub.astimezone(base.KST).strftime('%Y-%m-%d')
    except Exception:
        day = base.NOW.astimezone(base.KST).strftime('%Y-%m-%d')
    actors = []
    for name, pat in [
        ('tmobile', r'T-Mobile'),
        ('nokia', r'Nokia|노키아'),
        ('skt', r'SK텔레콤|SK\s*Telecom|\bSKT\b'),
        ('softbank', r'SoftBank|소프트뱅크'),
        ('nvidia', r'NVIDIA|엔비디아'),
    ]:
        if re.search(pat, text, re.I):
            actors.append(name)
    return hashlib.sha256(f"airan|{_stage(text)}|{day}|{','.join(actors)}".encode()).hexdigest()


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    dongkuk = next((x for x in candidates if x.get('group') == 'dongkuk_nps'), None)
    if dongkuk and not any(x.get('key') == dongkuk.get('key') for x in chosen):
        chosen = ([dongkuk, *chosen] if len(chosen) < limit else [dongkuk, *chosen[:-1]])
    airan = next((x for x in candidates if x.get('group') == 'airan'), None)
    if not airan or any(x.get('key') == airan.get('key') for x in chosen):
        return chosen
    if len(chosen) < limit:
        return [airan, *chosen]
    return [airan, *chosen[:-1]]


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.clean_title = clean_title
base.tag_for = tag_for
base.key = key
base.select_diverse = select_diverse


def _finalize_airan_criteria() -> None:
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding='utf-8')
    marker = '<b>판정 기준</b>'
    if marker in text:
        body = text.split(marker, 1)[0].rstrip()
        text = (
            body
            + '\n'
            + '<b>판정 기준</b>  실적·수급·시간표를 바꾸는 새 사실만 알림. '
              '단순 주가·ETF·테마 반복은 제외.'
        )
    base.ALERT_PATH.write_text(text.strip(), encoding='utf-8')


if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    qty.current.opt.current.fig.legacy.repair_pending_seen(pre_state)
    qty.current.opt._finalize_alert_text()
    qty.current._append_value_estimate()
    qty.enrich_quantity_values()
    _finalize_airan_criteria()
