#!/usr/bin/env python3
"""Final Physical-AI wrapper: Figure scaling + Optimus run-rate + NVIDIA AI-RAN.

Keeps the existing GitHub Actions -> Python -> Telegram route. Adds a strict
NVIDIA AI-RAN / Physical-AI lane while preserving all existing alert and
quantity-enrichment logic. The alert unit is a material state change, not an
article or URL.
"""
from __future__ import annotations

import hashlib
import re

import physical_ai_watch_quantity_enrichment as current

base = current.base

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_key = base.key
_orig_select_diverse = base.select_diverse

AIRAN_ID = re.compile(r'NVIDIA|엔비디아', re.I)
AIRAN = re.compile(r'AI[-\s]*RAN|AI\s*Aerial|Aerial\s*(?:RAN|platform)|AI[-\s]*native\s+(?:RAN|network)', re.I)
PHYSICAL = re.compile(r'physical\s*AI|robot(?:ics?)?|humanoid|autonomous\s+(?:machine|vehicle)|피지컬\s*AI|로봇|휴머노이드|자율\s*기계', re.I)
MILESTONE = re.compile(
    r'commercial|commercialization|deploy|field\s*trial|live\s*field|over[-\s]*the[-\s]*air|'
    r'integrat|launch|pilot|operator|carrier|latency|uplink|throughput|benchmark|'
    r'상용|상용화|배치|현장\s*시험|실증|통합|출시|통신사|지연|업링크|처리량|벤치마크',
    re.I,
)
CARRIER = re.compile(r'T-Mobile|SoftBank|SK\s*Telecom|SKT|Nokia|NTT|Deutsche\s*Telekom|BT\s*Group|Indosat|IOH|소프트뱅크|SK텔레콤|노키아', re.I)

for q in [
    '(NVIDIA OR 엔비디아) ("AI-RAN" OR "AI Aerial") ("physical AI" OR robot OR robotics OR 로봇) (deployment OR commercial OR "field trial" OR latency OR uplink OR 배치 OR 상용 OR 실증)',
    '(NVIDIA OR 엔비디아) ("AI-RAN" OR "AI Aerial") (T-Mobile OR SoftBank OR Nokia OR "SK Telecom" OR SKT) (robot OR "physical AI" OR edge)',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)

base.OFFICIAL_OR_PRIMARY.update({'NVIDIA', 'NVIDIA Newsroom', 'NVIDIA Developer'})
base.TRUSTED.update({'Reuters', 'Bloomberg', 'Light Reading', 'Fierce Network'})


def _is_airan(text: str) -> bool:
    return bool(AIRAN_ID.search(text) and AIRAN.search(text) and PHYSICAL.search(text) and MILESTONE.search(text))


def topic_group(text: str) -> str | None:
    if _is_airan(text):
        return 'nvidia_airan'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'nvidia_airan':
        return _orig_score(item)
    s = 20
    src = item.get('source') or ''
    if src in {'NVIDIA', 'NVIDIA Newsroom', 'NVIDIA Developer'}:
        s += 8
    elif src in base.TRUSTED:
        s += 3
    if CARRIER.search(text):
        s += 5
    if re.search(r'commercial|commercialization|상용|상용화|launch|출시', text, re.I):
        s += 8
    if re.search(r'field\s*trial|live\s*field|over[-\s]*the[-\s]*air|deployment|pilot|현장\s*시험|실증|배치', text, re.I):
        s += 7
    if re.search(r'\b\d+(?:\.\d+)?\s*(?:ms|x|Gbps|Mbps|%|devices?|robots?)\b|\b\d{1,3}(?:,\d{3})+\b', text, re.I):
        s += 6
    return s


def _subcat(text: str) -> str:
    if re.search(r'commercial|commercialization|상용|상용화|launch|출시', text, re.I):
        return 'AI-RAN 상용화'
    if re.search(r'latency|uplink|throughput|benchmark|\bms\b|Gbps|지연|업링크|처리량|벤치마크', text, re.I):
        return 'AI-RAN 성능 검증'
    if re.search(r'robot|robotics|humanoid|로봇|휴머노이드', text, re.I):
        return 'AI-RAN 로봇·엣지 연결'
    return 'AI-RAN 통신사·현장 배치'


def category(text: str, group: str) -> str:
    if group == 'nvidia_airan':
        return f'엔비디아 · {_subcat(text)}'
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == 'AI-RAN 상용화':
        return '통신망 GPU가 연결 기능뿐 아니라 로봇·카메라·자율기계의 엣지 추론 인프라로 실제 상용화되는 단계입니다. 통신사 실명·상용 지역·GPU 배치·유료 서비스·로봇 연결 대수를 추적합니다.'
    if raw == 'AI-RAN 성능 검증':
        return '대규모 피지컬AI가 요구하는 저지연·고업링크·엣지 연산 병목이 숫자로 개선되는지 보는 신호입니다. 지연시간·업링크 배수·동시 단말 수·GPU 활용률을 실제 현장 조건에서 비교합니다.'
    if raw == 'AI-RAN 로봇·엣지 연결':
        return '로봇의 무거운 인지·추론 일부를 네트워크 엣지 GPU로 오프로딩할 수 있는지 확인하는 신호입니다. 실제 로봇 제조사 통합·작업 지연·안전한 연결 유지가 상용화 핵심입니다.'
    if raw == 'AI-RAN 통신사·현장 배치':
        return 'AI-RAN이 연구실에서 통신사 현장망으로 이동하는 단계입니다. 실증이 상용 기지국·모바일 교환국·산업현장 배치로 확장되는지 확인합니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw.startswith('AI-RAN'):
        return 'AI-RAN 실증이 곧 휴머노이드 대량 매출을 뜻하지 않습니다. 통신사 상용 구축비·GPU 추가수요·로봇 제조사 통합·지연시간·가동률이 실제 계약과 반복매출로 연결되는지 확인해야 합니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group != 'nvidia_airan':
        return _orig_verification(item, group, text)
    src = item.get('source') or ''
    if src in {'NVIDIA', 'NVIDIA Newsroom', 'NVIDIA Developer'}:
        return '엔비디아 공식자료'
    if src in base.TRUSTED:
        return '신뢰 매체 보도 · 엔비디아/통신사 공식자료 교차확인'
    return '보도 단계 · 엔비디아·통신사 공식자료 재확인 필요'


def _airan_signature(text: str, item: dict) -> str:
    carriers = sorted({m.group(0).lower().replace(' ', '') for m in CARRIER.finditer(text)})
    stage = _subcat(text)
    nums = re.findall(r'\b\d+(?:\.\d+)?\s*(?:ms|x|Gbps|Mbps|%|devices?|robots?)\b', text, re.I)
    core = '|'.join(carriers[:3]) + '|' + stage + '|' + '|'.join(n.lower().replace(' ', '') for n in nums[:3])
    if not core.strip('|'):
        core = re.sub(r'\W+', ' ', item.get('title','').lower()).strip()
    return core


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) == 'nvidia_airan':
        return hashlib.sha256(f'nvidia-airan|{_airan_signature(text,item)}'.encode()).hexdigest()
    return _orig_key(item)


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    airan = next((x for x in candidates if x.get('group') == 'nvidia_airan'), None)
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
base.key = key
base.select_diverse = select_diverse


if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    current.current.opt.current.fig.legacy.repair_pending_seen(pre_state)
    current.current.opt._finalize_alert_text()
    current.current._append_value_estimate()
    current.enrich_quantity_values()
