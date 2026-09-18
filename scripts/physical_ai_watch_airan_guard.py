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

import physical_ai_watch_quantity_enrichment as qty

base = qty.base

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
    if not cat.startswith('엔비디아 AI-RAN'):
        return _orig_risk(cat)
    return ('AI-RAN과 휴머노이드 직접 채택은 아직 같은 의미가 아닙니다. 현재 공식 실증은 비전 AI·도시·유틸리티·드론 등도 포함하므로 '
            '테슬라·피겨 같은 휴머노이드 고객이 AI-RAN을 실제 사용하는지는 별도로 확인합니다. '
            '현장 지연시간·사이트당 비용·통신사 설비투자와 상용 계약이 먼저 드러나는 조기 지표입니다.')


def verification(item: dict, group: str, text: str) -> str:
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
    if group == 'airan':
        return '엔비디아AI-RAN'
    return _orig_tag_for(group)


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
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
    old = '공식 사전예고·신규 AI 모델/성능 공개·천 단위 공급망 발주·공급업체 심사·수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·기술 재평가·수급·시간표를 바꾸는 내용만 알림.'
    new = '공식 사전예고·신규 AI 모델/성능 공개·천 단위 공급망 발주·공급업체 심사·수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·AI-RAN Physical AI 실증·상용계약·기관 지분 변화처럼 돈 버는 능력·기술 재평가·수급·시간표를 바꾸는 내용만 알림.'
    text = text.replace(old, new)
    base.ALERT_PATH.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    qty.current.opt.current.fig.legacy.repair_pending_seen(pre_state)
    qty.current.opt._finalize_alert_text()
    qty.current._append_value_estimate()
    qty.enrich_quantity_values()
    _finalize_airan_criteria()
