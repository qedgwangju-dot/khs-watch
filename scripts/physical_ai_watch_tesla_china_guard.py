#!/usr/bin/env python3
"""Tesla Optimus China-supply-chain discovery layer for the existing Physical-AI watcher.

This does not create a new alert system. It extends the currently active watcher so
Chinese first/industry supply-chain reports can surface material Optimus state
changes before Korean/English rewrites appear. The alert unit is the underlying
production/procurement milestone, not a specific article or URL.
"""
from __future__ import annotations

import hashlib
import re
import urllib.parse
import xml.etree.ElementTree as ET

import physical_ai_watch_figure_guard as current

base = current.base

_orig_query_news = base.query_news
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_key = base.key
_orig_clean_title = base.clean_title

TESLA_CN_SENTINEL = 'DIRECT_TESLA_OPTIMUS_CN_SUPPLY_CHAIN'

TESLA_OPT = re.compile(r'Tesla|特斯拉|테슬라', re.I)
OPTIMUS = re.compile(r'Optimus|擎天柱|옵티머스', re.I)
SCALE_ORDER = re.compile(
    r'(?:约|約|약\s*)?(?:5,?000|5000)\s*(?:台|대)?|数千\s*台|數千\s*台|수천\s*대|千台级|千台級|천\s*단위',
    re.I,
)
ORDER = re.compile(
    r'订单|訂單|下发|下發|采购|採購|批量订单|批量訂單|量产订单|量產訂單|'
    r'order|purchase\s*order|batch\s*order|발주|주문|양산\s*주문',
    re.I,
)
TRIAL = re.compile(r'数百\s*台|數百\s*台|수백\s*대|试产|試產|trial\s*production|pilot\s*order|시험\s*생산', re.I)
AUDIT = re.compile(
    r'审厂|審廠|供应商审核|供應商審核|现场审核|現場審核|走访.{0,16}供应商|走訪.{0,16}供應商|'
    r'supplier\s*audit|factory\s*audit|site\s*audit|공급업체\s*심사|현장\s*심사|공급사\s*실사|'
    r'생산\s*감사|생산\s*심사|양산\s*감사|生产审核|生產審核',
    re.I,
)
AUDIT_STARTED = re.compile(
    r'启动(?:新一轮|新一輪)?.{0,18}(?:审厂|審廠)|开启(?:新一轮|新一輪)?.{0,18}(?:审厂|審廠)|'
    r'开始(?:新一轮|新一輪)?.{0,18}(?:审厂|審廠)|已于.{0,24}(?:开启|啟動|启动).{0,18}(?:审厂|審廠)|'
    r'(?:supplier|factory)\s*audit\s*(?:started|began|launched)|'
    r'공급업체\s*심사\s*(?:시작|개시)|양산\s*심사\s*(?:시작|개시)|'
    r'(?:생산|양산)\s*(?:감사|심사)\s*(?:착수|시작|개시)|(?:生产|生產)(?:审核|審核).{0,8}(?:启动|啟動|开始|開始)',
    re.I,
)
ACTUAL_WEEKLY = re.compile(
    r'(?:实际|實際|当前|當前|目前).{0,18}(?:周产|週產|每周生产|每週生產).{0,14}(?:\d{2,5})\s*台|'
    r'(?:周产|週產|每周生产|每週生產).{0,14}(?:达到|達到|已达|已達|稳定|穩定).{0,10}(?:\d{2,5})\s*台|'
    r'actual\s+weekly\s+production.{0,20}\d{2,5}|producing.{0,20}\d{2,5}.{0,12}(?:per\s+week|weekly)|'
    r'실제\s*주간\s*생산.{0,16}\d{2,5}\s*대|주당\s*실제\s*생산.{0,16}\d{2,5}\s*대',
    re.I,
)
WEEKLY_TARGET = re.compile(
    r'(?:目标|目標|要求|供应能力|供應能力|产能目标|產能目標).{0,28}(?:周产|週產|每周|每週).{0,18}\d{2,5}\s*台|'
    r'weekly\s+(?:target|capacity|run[-\s]*rate\s*target).{0,18}\d{2,5}|'
    r'주당\s*\d{2,5}\s*대분?\s*(?:공급능력|목표)|주간\s*생산\s*목표.{0,16}\d{2,5}\s*대',
    re.I,
)
RAMP = re.compile(
    r'量产|量產|良率|产线|產線|周产|週產|产能|產能|批量供应|批量供應|'
    r'production|yield|production\s*line|weekly\s*production|capacity|mass\s*production|'
    r'양산|수율|생산라인|주간\s*생산|생산능력|대량\s*공급',
    re.I,
)
CN_LOCATIONS = re.compile(r'上海|杭州|宁波|寧波|厦门|廈門|상하이|항저우|닝보|샤먼', re.I)
OFFICIAL_CONFIRM = re.compile(r'Tesla\s+(?:said|confirmed|announced)|特斯拉(?:官方|确认|確認|宣布)|테슬라(?:가|는)?\s*(?:공식|확인|발표)', re.I)
LOW_TRUST_COMMUNITY = re.compile(
    r'雪球|xueqiu|CSDN|blog\\.csdn\\.net|财富号|財富號|caifuhao|东方财富号|東方財富號',
    re.I,
)


SOURCE_KO = {
    '新浪财经': '시나재경', '新浪財經': '시나재경', 'finance.sina.com.cn': '시나재경',
    '界面新闻': '제몐뉴스', '界面新聞': '제몐뉴스',
    '21财经': '21세기경제보도', '21財經': '21세기경제보도',
    '21世纪经济报道': '21세기경제보도', '21世紀經濟報道': '21세기경제보도', 'm.21jingji.com': '21세기경제보도',
    '格隆汇': '거룽후이', '格隆匯': '거룽후이',
    '财联社': '차이롄서', '財聯社': '차이롄서', 'www.cls.cn': '차이롄서',
    '证券时报': '증권시보', '證券時報': '증권시보',
    '中国证券报': '중국증권보', '中國證券報': '중국증권보',
    '上海证券报': '상하이증권보', '上海證券報': '상하이증권보', 'paper.cnstock.com': '상하이증권보',
    '观点网': '관점망', '觀點網': '관점망', 'www.guandian.cn': '관점망',
}

if TESLA_CN_SENTINEL not in base.QUERIES:
    base.QUERIES.append(TESLA_CN_SENTINEL)
base.TRUSTED.update({
    '시나재경', '제몐뉴스', '21세기경제보도', '거룽후이', '차이롄서',
    '증권시보', '중국증권보', '상하이증권보',
})


def _query_cn_once(query: str) -> list[dict]:
    params = urllib.parse.urlencode({'q': query, 'hl': 'zh-CN', 'gl': 'CN', 'ceid': 'CN:zh-Hans'})
    root = ET.fromstring(base.fetch(f'https://news.google.com/rss/search?{params}'))
    out: list[dict] = []
    for node in root.findall('./channel/item')[:60]:
        title = base.norm(node.findtext('title'))
        link = base.norm(node.findtext('link'))
        desc = base.norm(node.findtext('description'))
        pub = base.parse_date(node.findtext('pubDate'))
        src_node = node.find('source')
        src = base.norm(src_node.text if src_node is not None else '')
        src = SOURCE_KO.get(src, src)
        if title and link:
            out.append({
                'title': title,
                'link': link,
                'description': desc,
                'published': pub.isoformat() if pub else None,
                'source': src,
                'cn_supply_chain': True,
            })
    return out


def _query_tesla_cn_supply_chain() -> list[dict]:
    queries = [
        '特斯拉 Optimus (5000台 OR 数千台 OR 千台级 OR 批量订单 OR 量产订单 OR 供应商订单)',
        '特斯拉 Optimus (审厂 OR 供应商审核 OR 现场审核 OR 走访供应商 OR 启动审厂 OR 开启审厂 OR 量产审厂 OR 上海 OR 杭州 OR 宁波 OR 厦门)',
        '特斯拉 Optimus (实际周产 OR 周产量达到 OR 当前周产 OR 良率 OR 周产 OR 产线 OR 量产 OR 产能) (供应商 OR 订单 OR 审厂 OR 产量)',
        '特斯拉 Optimus ("实际周产" OR "周产达到" OR "每周生产" OR "供应能力" OR "产能目标")',
    ]
    merged: dict[str, dict] = {}
    for q in queries:
        for item in _query_cn_once(q):
            signature = f"{item.get('title','')}|{item.get('source','')}"
            merged[signature] = item
    return list(merged.values())


def query_news(q: str) -> list[dict]:
    if q == TESLA_CN_SENTINEL:
        return _query_tesla_cn_supply_chain()
    return _orig_query_news(q)


def _is_tesla_supply_text(text: str) -> bool:
    return bool(TESLA_OPT.search(text) and OPTIMUS.search(text) and (ORDER.search(text) or AUDIT.search(text) or RAMP.search(text)))


def _stage(text: str) -> str:
    scaled = bool(SCALE_ORDER.search(text) and ORDER.search(text))
    actual_weekly = bool(ACTUAL_WEEKLY.search(text))
    weekly_target = bool(WEEKLY_TARGET.search(text))
    audit_started = bool(AUDIT_STARTED.search(text))
    if actual_weekly:
        return 'actual_weekly_production'
    if weekly_target:
        return 'weekly_capacity_target'
    audit = bool(AUDIT.search(text))
    if audit_started:
        return 'supplier_audit_started'
    if scaled and audit:
        return 'scale_order_audit'
    if scaled:
        return 'scale_order'
    if audit:
        return 'supplier_audit'
    if RAMP.search(text):
        return 'production_ramp'
    return ''


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    s = _orig_score(item)
    if not _is_tesla_supply_text(text):
        return s
    source = item.get('source') or ''
    # Investor-community/aggregator posts are useful discovery leads but are not
    # promoted to high-signal on their own. Wait for a trusted/official corroboration.
    if LOW_TRUST_COMMUNITY.search(source):
        return 0
    s = max(s, 18)
    stage = _stage(text)
    if stage in {'scale_order', 'scale_order_audit'}:
        s += 10
    if stage in {'supplier_audit', 'scale_order_audit'}:
        s += 8
    if stage == 'supplier_audit_started':
        s += 12
    if stage == 'actual_weekly_production':
        s += 15
    if stage == 'weekly_capacity_target':
        s += 6
    if TRIAL.search(text):
        s += 4
    if CN_LOCATIONS.search(text):
        s += 3
    if RAMP.search(text):
        s += 5
    if item.get('source') in base.TRUSTED:
        s += 3
    return s


def category(text: str, group: str) -> str:
    if group == 'tesla' and _is_tesla_supply_text(text):
        stage = _stage(text)
        if stage == 'actual_weekly_production':
            return 'Optimus 실제 주간 완제품 생산량'
        if stage == 'weekly_capacity_target':
            return 'Optimus 주간 공급능력·생산 목표'
        if stage == 'scale_order_audit':
            return 'Optimus 천 단위 발주·공급업체 심사'
        if stage == 'scale_order':
            return 'Optimus 천 단위 양산 발주'
        if stage == 'supplier_audit_started':
            return 'Optimus 공급업체 양산 심사 실제 개시'
        if stage == 'supplier_audit':
            return 'Optimus 공급업체 심사·양산 준비'
        if stage == 'production_ramp':
            return 'Optimus 생산라인·수율 램프업'
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    if cat == 'Optimus 실제 주간 완제품 생산량':
        return ('옵티머스가 공급망 목표나 부품 발주가 아니라 실제 완제품 주간 생산량으로 넘어갔는지를 보는 최상위 양산 신호입니다. '
                '주당 생산량·수율·완성품 출하·내부 배치 대수를 분리해 확인하고, 이전 목표 대비 실제 달성률을 계산합니다.')
    if cat == 'Optimus 주간 공급능력·생산 목표':
        return ('주당 몇 대분을 공급할 수 있어야 하는지 또는 생산 목표가 얼마인지 보여주는 선행 시간표 신호입니다. '
                '실제 완제품 생산량과 혼동하지 않고 목표→실생산 전환 시점을 별도 추적합니다.')
    if cat == 'Optimus 천 단위 발주·공급업체 심사':
        return ('수백 대 시험 생산 물량에서 약 5,000대 규모로 알려진 첫 천 단위 공급망 주문과 중국 공급업체 심사가 동시에 포착된 단계 변화입니다. '
                '양산 가능성을 공급망에서 검증하는 신호로 보고 실제 공급업체별 배정 수량·납기·출하·생산 수율을 이어서 추적합니다.')
    if cat == 'Optimus 천 단위 양산 발주':
        return ('수백 대 시험 물량에서 천 단위 부품 발주로 주문 규모가 한 단계 올라간 공급망 신호입니다. '
                '실제 부품사별 발주 수량·납기·반복 주문이 확인되면 양산 매출 가시성이 높아집니다.')
    if cat == 'Optimus 공급업체 양산 심사 실제 개시':
        return ('기존 약 5,000대 규모 공급망 주문의 후속으로, 공급업체 심사가 예정·방문 단계에서 실제 양산 심사 개시로 넘어간 신호입니다. '
                '심사 통과·정식 공급업체 선정·최종 발주 배정·실제 출하 순으로 다음 상태 변화를 추적합니다.')
    if cat == 'Optimus 공급업체 심사·양산 준비':
        return ('테슬라가 중국 공급업체의 현장 생산능력·품질·공정 준비를 직접 확인하는 단계로 해석되는 공급망 신호입니다. '
                '심사 통과, 최종 공급업체 선정, 양산 발주와 실제 출하를 분리해 추적합니다.')
    if cat == 'Optimus 생산라인·수율 램프업':
        return ('옵티머스가 설계 검증에서 반복 가능한 제조로 넘어가는지를 보는 신호입니다. '
                '주간 생산량·수율·라인 가동률·부품 병목과 실제 내부 배치를 확인합니다.')
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    if cat == 'Optimus 실제 주간 완제품 생산량':
        return ('공급망 기사에서 주당 수량이 언급돼도 실제 완제품 생산실적과 부품 공급능력 목표는 다를 수 있습니다. '
                '테슬라 공식자료 또는 복수의 독립 공급망 자료에서 실제 생산·출하가 확인되지 않으면 공식 실적처럼 표기하지 않습니다.')
    if cat == 'Optimus 주간 공급능력·생산 목표':
        return ('공급능력 목표는 실제 생산량이 아닙니다. 수율·부품 병목·라인 안정화가 늦으면 목표치와 실제 주간 완제품 생산량의 격차가 커질 수 있습니다.')
    if cat in {'Optimus 천 단위 발주·공급업체 심사', 'Optimus 천 단위 양산 발주'}:
        return ('약 5,000대 발주는 현재 중국 공급망 보도이며 테슬라 공식 공시로 확인된 수량은 아닙니다. '
                '공급업체 심사와 주문 보도가 실제 완제품 5,000대 생산·출하를 뜻하지 않으므로 공급업체 실명·발주서·납기·출하와 테슬라 공식 생산량을 별도로 확인합니다.')
    if cat == 'Optimus 공급업체 양산 심사 실제 개시':
        return ('심사 실제 개시는 최종 공급업체 선정·양산 수주 확정과 다릅니다. '
                '품질·원가·수율·납기 기준에서 탈락하거나 재심사가 발생하면 실제 출하 일정이 다시 늦어질 수 있습니다.')
    if cat == 'Optimus 공급업체 심사·양산 준비':
        return ('공급업체 심사 시작은 최종 선정이나 양산 수주 확정과 다릅니다. '
                '품질·원가·수율·납기 기준 미달 시 공급업체 변경 또는 양산 일정 지연이 먼저 나타날 수 있습니다.')
    if cat == 'Optimus 생산라인·수율 램프업':
        return ('생산라인 설치와 실제 안정 양산은 다릅니다. 수율과 주간 생산량이 목표에 못 미치면 부품 발주와 공급업체 증설이 다시 지연될 수 있습니다.')
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group == 'tesla' and _is_tesla_supply_text(text):
        if OFFICIAL_CONFIRM.search(text) or item.get('source') == 'Tesla':
            return '테슬라 공식·1차 자료'
        if _stage(text) == 'actual_weekly_production':
            return '실제 주간 생산량 보도 · 테슬라 공식자료 또는 복수 공급망 자료로 교차확인 필요'
        if _stage(text) == 'weekly_capacity_target':
            return '공급망 생산능력·목표 보도 · 실제 완제품 생산량과 분리'
        if _stage(text) in {'scale_order', 'scale_order_audit'}:
            return '중국 공급망 복수 보도 · 테슬라 공식 양산계획과 교차확인 · 약 5,000대 발주 수량은 테슬라 공식 확인 전'
        if _stage(text) == 'supplier_audit_started':
            return '중국 공급망 후속 보도 · 9월 17일 새 양산 심사 개시 보도 · 테슬라 공식 공급업체 선정 결과는 미확인'
        if _stage(text) == 'supplier_audit':
            return '중국 공급망 보도 · 공급업체 심사 진행 여부를 당사자·공식자료로 후속 확인'
    return _orig_verification(item, group, text)


def clean_title(title: str, source: str) -> str:
    text = f'{title} {source}'
    if _is_tesla_supply_text(text):
        stage = _stage(text)
        if stage == 'actual_weekly_production':
            return '테슬라 옵티머스, 실제 주간 완제품 생산량 신규 확인'
        if stage == 'weekly_capacity_target':
            return '테슬라 옵티머스, 주간 공급능력·생산 목표 신규 변화'
        if stage == 'scale_order_audit':
            return '테슬라 옵티머스, 약 5,000대 공급망 주문·중국 공급업체 심사 진행 보도'
        if stage == 'scale_order':
            return '테슬라 옵티머스, 약 5,000대 천 단위 공급망 주문 보도'
        if stage == 'supplier_audit_started':
            return '테슬라 옵티머스, 기존 약 5,000대 주문 후속…중국 공급업체 양산 심사 실제 개시 보도'
        if stage == 'supplier_audit':
            return '테슬라 옵티머스, 중국 공급업체 심사·현장 방문 진행 보도'
        if stage == 'production_ramp':
            return '테슬라 옵티머스, 생산라인·수율 램프업 신규 변화'
    return _orig_clean_title(title, source)


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')}"
    if _is_tesla_supply_text(text):
        stage = _stage(text)
        if stage == 'actual_weekly_production':
            m = re.search(r'(?<!\d)(\d{2,5})(?:\s*台|\s*대|\s*(?:per\s+week|weekly))', text, re.I)
            qty = m.group(1) if m else 'unknown'
            return hashlib.sha256(f'tesla-optimus|actual-weekly-production|{qty}'.encode()).hexdigest()
        if stage == 'weekly_capacity_target':
            m = re.search(r'(?<!\d)(\d{2,5})(?:\s*台|\s*대|\s*(?:per\s+week|weekly))', text, re.I)
            qty = m.group(1) if m else 'unknown'
            return hashlib.sha256(f'tesla-optimus|weekly-capacity-target|{qty}'.encode()).hexdigest()
        if stage == 'supplier_audit_started':
            return hashlib.sha256(b'tesla-optimus|2026-09-17|supplier-production-audit-started').hexdigest()
        if stage == 'scale_order_audit':
            return hashlib.sha256(b'tesla-optimus|scale-order-5000|supplier-audit').hexdigest()
        if stage == 'scale_order':
            return hashlib.sha256(b'tesla-optimus|scale-order-5000').hexdigest()
        if stage == 'supplier_audit':
            return hashlib.sha256(b'tesla-optimus|supplier-audit').hexdigest()
    return _orig_key(item)


base.query_news = query_news
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.clean_title = clean_title
base.key = key


def _finalize_alert_text() -> None:
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding='utf-8')
    upgraded = '공식 사전예고·신규 AI 모델/성능 공개·천 단위 공급망 발주·공급업체 심사·수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·기술 재평가·수급·시간표를 바꾸는 내용만 알림.'
    for old in [
        '신규 수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·수급·시간표를 바꾸는 내용만 알림.',
        '공식 사전예고·신규 AI 모델/성능 공개·수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·기술 재평가·수급·시간표를 바꾸는 내용만 알림.',
    ]:
        text = text.replace(old, upgraded)
    base.ALERT_PATH.write_text(current.fig.legacy.display._inline_original_link(text), encoding='utf-8')


if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    current.fig.legacy.repair_pending_seen(pre_state)
    _finalize_alert_text()
