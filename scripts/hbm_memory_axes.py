"""Typed memory-state extension of the existing Samsung HBM collector.
No new bot or schedule. Missing dates, denominators or raw prices are coverage gaps.
"""
from __future__ import annotations
import copy
import hashlib
import html
import json
import math
import pathlib
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'out'
VERSION = 1
EXTRA_QUERIES = [
    '(HBM4 OR HBM4E) (24Gb OR 32Gb OR 36GB OR 32GB OR 48GB) (capacity OR 용량 OR 적층)',
    'DDR5 RDIMM (premium OR spot OR contract OR 현물 OR 고정거래)',
    '(HBM OR DDR5) (wafer OR 웨이퍼) (allocation OR 비중 OR 배분)',
    'HBM ("glass carrier" OR "글라스 캐리어" OR "유리 지지판") (cleaning OR 세정)',
    '(P5 OR Fab1) (삼성 OR Samsung) (가동 OR 양산 OR production OR delay)',
    '말레이시아 8542323000 HBM 수출 8월 16억2454만달러',
    'Malaysia 8542323000 HBM exports Intel ASE TF-AMD MAPC advanced packaging',
    'Bernstein HBM revenue estimate Samsung SK hynix 3Q26 exports regression',
    'J.P. Morgan HBM revenue estimate Samsung SK hynix Micron quarter forecast',
    'UBS HBM revenue estimate Samsung SK hynix Micron quarter forecast',
    'TSMC advanced packaging testing tester shortage capex CoWoS',
    'ASE advanced packaging testing capex 10.5 billion AI',
    '디아이 디지털프론티어 와이씨 엑시콘 HBM 검사장비 수주',
    '인텍플러스 CoWoS 파일럿 품질검증 정식계약',
    '펨트론 HBM 검사장비 SK하이닉스 수주',
    'ISC HBM 테스트 솔루션 메모리 3사 공급',
    '삼성 HBM4 베이스다이 4나노 풀가동 증설 가격 인상',
    'Samsung HBM4 base die 4nm full utilization expansion price increase',
    '삼성 HBM5 베이스다이 2나노 신규 생산라인 투자 GAA',
    'Samsung HBM5 2nm base die production line investment GAA TSV',
]
COMPANIES = {'samsung': r'삼성(?:전자)?|Samsung(?: Electronics)?',
             'skhynix': r'SK\s?하이닉스|SK\s*hynix', 'micron': r'마이크론|Micron'}
OFFICIAL = {'news.samsung.com': 'samsung', 'semiconductor.samsung.com': 'samsung',
            'news.skhynix.com': 'skhynix', 'investors.micron.com': 'micron', 'micron.com': 'micron',
            'nvidianews.nvidia.com': 'nvidia', 'developer.nvidia.com': 'nvidia'}
RANK = {'user_capture': 0, 'reported': 1, 'research': 2, 'official': 3}
POSTPROCESS_ENTITIES = {
    'tsmc': (r'\bTSMC\b', r'대만적체전로'),
    'ase': (r'\bASE\b', r'Advanced Semiconductor Engineering'),
    'di': (r'(?<![A-Za-z])디아이(?![A-Za-z])',),
    'digital_frontier': (r'디지털\s*프론티어', r'Digital Frontier'),
    'yc': (r'(?<![A-Za-z])와이씨(?![A-Za-z])',),
    'exicon': (r'엑시콘', r'Exicon'),
    'intekplus': (r'인텍플러스', r'Intekplus'),
    'pemtron': (r'펨트론', r'Pemtron'),
    'isc': (r'(?<![A-Za-z])ISC(?![A-Za-z])',),
    'kohyoung': (r'고영', r'Koh Young'),
    'neosem': (r'네오셈', r'Neosem'),
    'nextein': (r'넥스틴', r'NEXTIN'),
}
STAGE_RANK = {
    'mentioned': 0,
    'development': 1,
    'pilot': 2,
    'pilot_passed': 3,
    'po_pending': 4,
    'po_signed': 5,
    'equipment_move_in': 6,
    'mass_production': 7,
}

INSTITUTIONS = {
    'bernstein': (r'Bernstein', r'번스타인'),
    'jpmorgan': (r'J[.]?P[.]?\s*Morgan', r'JP\s*Morgan', r'제이피모건'),
    'ubs': (r'\bUBS\b',),
    'morgan_stanley': (r'Morgan\s+Stanley', r'모건스탠리'),
    'citi': (r'\bCiti\b', r'Citigroup', r'씨티'),
    'bofa': (r'BofA', r'Bank\s+of\s+America', r'뱅크오브아메리카'),
    'goldman_sachs': (r'Goldman\s+Sachs', r'골드만삭스'),
}


def dump(path, value):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def host(url):
    return (urlparse(url).hostname or '').lower().removeprefix('www.')


def evidence(url):
    h = host(url)
    if h in OFFICIAL:
        return 'official'
    if h in ('trendforce.com', 'dramexchange.com', 'counterpointresearch.com'):
        return 'research'
    return 'reported'


def concrete_state_evidence(event):
    """Reject a new headline about tight supply without a changed fact or stage."""
    text = event.get('title', '') + ' ' + event.get('description', '')
    quantified = re.search(r'\d[\d,.]*\s*(?:%|배|만\s*장|장|Gb\b|GB\b|TB\b|달러|billion\b|million\b)', text)
    transition = re.search(
        r'인증\s*완료|검증\s*완료|양산\s*(?:시작|개시)|출하\s*시작|샘플\s*출하|계약\s*체결|'
        r'착공|준공|가동\s*시작|허가\s*취득|인증\s*실패|계약\s*(?:취소|해지)|'
        r'qualification completed|validation completed|begins? (?:shipment|mass production)|'
        r'starts? (?:shipment|production)|contract signed|contract cancelled', text, re.I)
    return bool(quantified or transition)


def product_capacity(die_gb, layers, stacks=1):
    if not all(isinstance(x, (float, int)) and math.isfinite(x) and x > 0 for x in (die_gb, layers, stacks)):
        raise ValueError('positive numeric density/layers/stacks required')
    if int(layers) != layers or int(stacks) != stacks:
        raise ValueError('layers and stacks must be integers')
    return die_gb * layers * stacks / 8.0


def capacity_comparison(old_gb, new_gb, old_stacks=1, new_stacks=1):
    if min(old_gb, new_gb, old_stacks, new_stacks) <= 0:
        raise ValueError('invalid capacity')
    old, new = old_gb * old_stacks, new_gb * new_stacks
    return {'old_total_gb': old, 'new_total_gb': new,
            'capacity_change_pct': (new / old - 1) * 100,
            'gpu_growth_break_even_pct': (old / new - 1) * 100}


def premium(spot, contract):
    if spot <= 0 or contract <= 0:
        raise ValueError('prices must be positive')
    return (spot / contract - 1) * 100


def rdimm_driver(old, new):
    if not all(k in old and k in new for k in ('spot', 'contract')):
        return '가격 쌍 부족: 원인 판정 보류'
    if new['contract'] > old['contract'] and new['spot'] >= old['spot']:
        return '고정거래가격 추격: 프리미엄 축소만으로 수요 악화 아님'
    if new['spot'] < old['spot'] and new['contract'] <= old['contract']:
        return '현물가격 약화: 주문·납기 동반 약화 여부 확인 필요'
    return '현물·고정거래가격 혼재: 프리미엄만으로 수급 단정 금지'


def date_only(text):
    m = re.search(r'(?<!\d)(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})(?:일)?', text)
    if not m:
        return ''
    try:
        return datetime(*map(int, m.groups())).date().isoformat()
    except ValueError:
        return ''


def resolve_relative_years(text, published):
    if re.match(r'^20\d{2}-', published):
        year = int(published[:4])
        text = re.sub(r'내년|next year', str(year + 1) + '년', text, flags=re.I)
        text = re.sub(r'올해|금년|this year', str(year) + '년', text, flags=re.I)
    return text


def local_period(text, published):
    text = resolve_relative_years(text, published)
    m = re.search(r'(?<!\d)(20\d{2})\s*(?:년)?\s*(?:말|연말|year.end)', text, re.I)
    if m:
        return m[1] + '-YE'
    m = re.search(r'(?<!\d)(20\d{2})\s*년?\s*(\d{1,2})\s*월', text)
    if m:
        return f'{m[1]}-{int(m[2]):02d}'
    m = re.search(r'(?<!\d)(20\d{2})(?!\d)', text)
    return m[1] if m else ''


def is_axis_text(text):
    return bool(re.search(
        r'RDIMM|현물.*프리미엄|spot.*premium|글라스 캐리어|glass carrier|유리 지지판|P5|'
        r'HBM.*(?:공급 부족|증산|웨이퍼|wafer|supply)|HBM4E?.*(?:\d+\s*Gb|\d+\s*GB|\d+\s*단)|'
        r'말레이시아.*(?:8542[.]?32[.]?3000|HBM)|Malaysia.*(?:8542[.]?32[.]?3000|HBM)|'
        r'HBM.*(?:매출|revenue).*(?:전망|estimate|forecast|regression)|'
        r'(?:Bernstein|번스타인|J[.]?P[.]? Morgan|UBS).*HBM|'
        r'(?:TSMC|ASE|디아이|디지털\s*프론티어|와이씨|엑시콘|인텍플러스|펨트론|ISC|고영|네오셈|넥스틴).*'
        r'(?:CoWoS|후공정|패키징|검사|테스트|tester|수주|품질\s*검증|정식\s*계약|설비투자|capex)|'
        r'(?:삼성|Samsung).*HBM.*(?:베이스\s*다이|base\s*die|4\s*나노|4nm|2\s*나노|2nm).*'
        r'(?:풀가동|full\s*utilization|증설|expand|가격\s*인상|price\s*increase|생산라인|production\s*line|투자|investment)',
        text, re.I))


def read_document(raw):
    from selectolax.parser import HTMLParser
    tree = HTMLParser(raw)
    pub = ''
    for selector in ('meta[property="article:published_time"]', 'meta[name="date"]'):
        node = tree.css_first(selector)
        if node:
            pub = node.attributes.get('content', '')
            break
    for node in tree.css('script,style,nav,footer,header,aside,noscript'):
        node.decompose()
    body = None
    for selector in ('[itemprop="articleBody"]', '#articleBody', '#article-view-content-div', '.article_view', '.article_txt', 'article'):
        body = tree.css_first(selector)
        if body:
            break
    body = body or tree.body
    return (body.text(separator='\n', strip=True)[:60000] if body else ''), pub


def make_record(axis, key_parts, value, unit, period, item, excerpt, **extra):
    return {'key': '|'.join([axis, *key_parts]), 'axis': axis, 'value': value,
            'unit': unit, 'period': period, 'as_of': extra.pop('as_of', item.get('data_as_of') or item.get('published_at_kst', '')[:10]),
            'evidence': evidence(item.get('direct_link', '')), 'source_url': item.get('direct_link', ''),
            'source_title': item.get('title', ''), 'source': item.get('source', ''),
            'excerpt': excerpt[:800], **extra}


def _korean_dollar_amount(text):
    m = re.search(r'([\d,.]+)\s*억\s*([\d,.]+)?\s*만?\s*달러', text)
    if m:
        eok = float(m[1].replace(',', ''))
        man = float((m[2] or '0').replace(',', ''))
        return eok * 100_000_000 + man * 10_000
    m = re.search(r'\$\s*([\d,.]+)\s*(billion|million|B|M)\b', text, re.I)
    if m:
        n = float(m[1].replace(',', ''))
        return n * (1_000_000_000 if m[2].lower() in ('billion','b') else 1_000_000)
    return None


def _malaysia_export_record(item, body):
    text = re.sub(r'\s+', ' ', body)
    if not re.search(r'(?:말레이시아|Malaysia)', text, re.I):
        return None
    if not re.search(r'8542[.]?32[.]?3000|8542323000', text):
        return None

    published = item.get('published_at_kst', '')
    pub_year = int(published[:4]) if re.match(r'^20\d{2}', published) else None
    mm = re.search(r'(?:지난\s*)?([1-9]|1[0-2])\s*월\s*말레이시아향[^.]{0,140}?(?:수출액은|exports?[^.]{0,30}?reached)\s*([^,.]+(?:억[^,.]+만달러|억달러|\$[^,.]+(?:billion|million|B|M)))', text, re.I)
    if not mm or pub_year is None:
        return None
    month = int(mm[1])
    amount = _korean_dollar_amount(mm[2])
    if amount is None:
        # English recaps usually place the amount immediately after the HS-code clause.
        nearby = text[max(0, mm.start()-80):mm.end()+160]
        amount = _korean_dollar_amount(nearby)
    if amount is None:
        return None

    yoy = None
    ym = re.search(r'(?:전년\s*(?:동기|동월)\s*대비|year[- ]on[- ]year|yoy)[^%]{0,30}?([\d.]+)\s*%', text, re.I)
    if ym:
        yoy = float(ym[1])

    current_weight_kg = None
    previous_weight_kg = None
    wm = re.search(r'(?:수출\s*중량|export volume)[^.]{0,100}?([\d.]+)\s*(?:톤|t)\s*(?:에서|to)\s*([\d.]+)\s*(?:톤|t)', text, re.I)
    if wm:
        previous_weight_kg = float(wm[1]) * 1000
        current_weight_kg = float(wm[2]) * 1000

    taiwan_amount = None
    tm = re.search(r'(?:대만향|exports? to Taiwan)[^.]{0,90}?([\d,.]+\s*억\s*[\d,.]*\s*만?\s*달러|\$\s*[\d,.]+\s*(?:billion|million|B|M))', text, re.I)
    if tm:
        taiwan_amount = _korean_dollar_amount(tm[1])

    ratio = None
    rm = re.search(r'(?:대만향[^.]{0,60}?)([\d.]+)\s*%\s*(?:까지|수준|of)', text, re.I)
    if rm:
        ratio = float(rm[1])
    elif taiwan_amount:
        ratio = amount / taiwan_amount * 100

    jan_aug = None
    jm = re.search(r'(?:1\s*[~-]\s*8월|Jan(?:uary)?[-– ]Aug(?:ust)?)[^.]{0,100}?([\d,.]+\s*억\s*[\d,.]*\s*만?\s*달러|\$\s*[\d,.]+\s*(?:billion|million|B|M))', text, re.I)
    if jm:
        jan_aug = _korean_dollar_amount(jm[1])

    period = f'{pub_year}-{month:02d}'
    value = {
        'amount_usd': amount,
        'weight_kg': current_weight_kg,
        'weight_kg_previous_yoy': previous_weight_kg,
        'yoy_pct': yoy,
        'taiwan_amount_usd': taiwan_amount,
        'malaysia_vs_taiwan_pct': ratio,
        'jan_aug_amount_usd': jan_aug,
        'weight_rounded_from_public_text': bool(current_weight_kg),
    }
    return make_record(
        'malaysia_hsk10_export', ['KR','MY','8542323000'], value, 'USD/kg', period,
        item, '말레이시아향 HSK 8542323000 월간 수출·중량·대만 대비 비중',
        scope='HBM_included_multichip_IC_not_HBM_only')


def _institution(text):
    for name, patterns in INSTITUTIONS.items():
        if any(re.search(p, text, re.I) for p in patterns):
            return name
    return ''


def _quarter(text, published=''):
    patterns = (
        r'\b([1-4])Q\s*(20\d{2})\b',
        r'\b([1-4])Q(\d{2})\b',
        r'\b(20\d{2})\s*년\s*([1-4])\s*분기\b',
    )
    for i, pat in enumerate(patterns):
        m = re.search(pat, text, re.I)
        if not m:
            continue
        if i == 0:
            q, year = m[1], m[2]
        elif i == 1:
            q, yy = m[1], int(m[2]); year = str(2000 + yy)
        else:
            year, q = m[1], m[2]
        return f'{year}Q{q}'
    return ''


def _usd_amount_near_hbm_revenue(text):
    patterns = (
        r'(?:HBM\s*(?:revenue|sales)|HBM\s*매출)[^$\d]{0,80}(?:US\$|\$)\s*([\d.]+)\s*(B|billion|M|million)\b',
        r'(?:US\$|\$)\s*([\d.]+)\s*(B|billion|M|million)\b[^.]{0,90}(?:HBM\s*(?:revenue|sales)|HBM\s*매출)',
        r'(?:HBM\s*매출)[^\d]{0,80}([\d.]+)\s*(?:십억\s*달러|billion\s*dollars?)',
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        n = float(m[1])
        scale = m[2].lower() if len(m.groups()) >= 2 and m[2] else 'billion'
        return n * (1_000_000 if scale in ('m','million') else 1_000_000_000)
    return None


def _pct_near(text, labels):
    for label in labels:
        patterns = (
            re.escape(label) + r'[^%]{0,50}?([+-]?\d+(?:\.\d+)?)\s*%',
            r'([+-]?\d+(?:\.\d+)?)\s*%[^.]{0,50}?' + re.escape(label),
        )
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                return float(m[1])
    return None


def parse_hbm_revenue_estimates(item, body):
    text = re.sub(r'\s+', ' ', body)
    inst = _institution(item.get('title','') + ' ' + item.get('source','') + ' ' + text[:5000])
    if not inst or not re.search(r'HBM', text, re.I):
        return []

    published = item.get('published_at_kst', '')
    rows = []
    paragraphs = [p.strip() for p in re.split(r'(?<=[.!?])\s+(?=[A-Z가-힣])|\n+', body) if p.strip()]
    for company, pat in COMPANIES.items():
        candidates = [p for p in paragraphs if re.search(pat, p, re.I) and re.search(r'HBM', p, re.I)
                      and re.search(r'매출|revenue|sales', p, re.I)]
        if not candidates:
            continue
        for p in candidates:
            period = _quarter(p, published) or _quarter(item.get('title',''), published)
            if not period:
                continue
            amount = _usd_amount_near_hbm_revenue(p)
            if amount is None:
                continue

            low = p.lower()
            method = 'regression_proxy' if re.search(r'regression|회귀', p, re.I) else (
                'formal_forecast' if re.search(r'forecast|estimate|전망|추정', p, re.I) else 'reported_estimate')
            qoq = _pct_near(p, ('QoQ','전분기','sequential'))
            if qoq is not None and re.search(r'down|decline|감소|하락', p, re.I) and qoq > 0:
                qoq = -qoq

            prior = None
            pm = re.search(r'(?:forecast|기존\s*전망|previous\s*forecast)[^$]{0,50}(?:US\$|\$)\s*([\d.]+)\s*(B|billion|M|million)', p, re.I)
            if pm:
                prior = float(pm[1]) * (1_000_000 if pm[2].lower() in ('m','million') else 1_000_000_000)

            alt = None
            am = re.search(r'(?:could\s+reach|alternative|상단|대안)[^$]{0,70}(?:US\$|\$)\s*([\d.]+)\s*(B|billion|M|million)', p, re.I)
            if am:
                alt = float(am[1]) * (1_000_000 if am[2].lower() in ('m','million') else 1_000_000_000)

            value = {
                'estimate_usd': amount,
                'qoq_pct': qoq,
                'prior_formal_forecast_usd': prior,
                'alternative_usd': alt,
                'method': method,
            }
            rows.append(make_record(
                'hbm_revenue_estimate', [inst, company, period, method], value, 'USD/quarter', period,
                item, p, scope='institutional_estimate_not_company_reported_revenue'))
            break
    return rows


def _entity(text):
    matches = []
    for name, pats in POSTPROCESS_ENTITIES.items():
        if any(re.search(p, text, re.I) for p in pats):
            matches.append(name)
    return matches[0] if len(matches) == 1 else ''


def _krw_amount(text):
    m = re.search(r'([\d,.]+)\s*억원', text)
    if m:
        return float(m[1].replace(',', '')) * 100_000_000
    m = re.search(r'([\d,.]+)\s*조\s*([\d,.]+)?\s*억원', text)
    if m:
        jo = float(m[1].replace(',', ''))
        eok = float((m[2] or '0').replace(',', ''))
        return jo * 1_000_000_000_000 + eok * 100_000_000
    return None


def _usd_billion(text):
    m = re.search(r'(?:US\$|\$)?\s*([\d.]+)\s*(?:billion|B)\b', text, re.I)
    return float(m[1]) * 1_000_000_000 if m else None


def _postprocess_stage(text):
    low = text.lower()
    if re.search(r'양산\s*(?:시작|개시)|mass\s*production', text, re.I):
        return 'mass_production'
    if re.search(r'장비\s*반입|equipment\s*(?:move[- ]?in|installation)', text, re.I):
        return 'equipment_move_in'
    if re.search(r'정식\s*계약.*(?:앞두|준비)|본계약.*(?:앞두|준비)|prepar(?:e|ing)\s+for\s+(?:a\s+)?formal\s+contract', text, re.I):
        return 'po_pending'
    if re.search(r'정식\s*(?:계약|수주)|본계약|purchase\s*order|\bPO\b|contract\s*signed', text, re.I):
        return 'po_signed'
    if re.search(r'품질\s*검증.*통과|품질\s*테스트.*통과|pilot.*(?:passed|qualified)|qualification\s*passed', text, re.I):
        return 'pilot_passed'
    if re.search(r'파일럿|시범\s*장비|pilot', text, re.I):
        return 'pilot'
    if re.search(r'개발|R&D|국책과제|development', text, re.I):
        return 'development'
    return ''


def parse_postprocess_records(item, body):
    text = re.sub(r'\s+', ' ', body)
    published = item.get('published_at_kst', '')
    year = published[:4] if re.match(r'^20\d{2}', published) else 'unknown'
    rows = []

    # TSMC: total CapEx + backend allocation + explicit tester bottleneck.
    if re.search(r'(?<![A-Za-z0-9])TSMC(?![A-Za-z0-9])', text, re.I):
        total_min = total_max = None
        rm = re.search(r'(?:USD|US\$|\$)?\s*([\d.]+)\s*(?:billion|B)[^\d]{0,30}(?:to|[-~–])\s*(?:USD|US\$|\$)?\s*([\d.]+)\s*(?:billion|B)', text, re.I)
        if rm:
            total_min, total_max = float(rm[1]) * 1e9, float(rm[2]) * 1e9
        else:
            rm_kr = re.search(r'([\d.]+)\s*억\s*(?:~|[-–]|에서|to)\s*([\d.]+)\s*억\s*달러', text, re.I)
            if rm_kr:
                total_min, total_max = float(rm_kr[1]) * 1e8, float(rm_kr[2]) * 1e8
        pm = re.search(r'(?:10\s*(?:to|[-~–])\s*20|10\s*~\s*20)\s*%', text, re.I)
        tester_shortage = bool(re.search(r'tester[^.]{0,30}shortage|테스터[^.]{0,30}부족|테스트\s*장비[^.]{0,30}부족', text, re.I))
        if total_min or pm or tester_shortage:
            value = {
                'total_capex_usd_min': total_min,
                'total_capex_usd_max': total_max,
                'backend_alloc_pct_min': 10.0 if pm else None,
                'backend_alloc_pct_max': 20.0 if pm else None,
                'tester_shortage': tester_shortage,
            }
            rows.append(make_record(
                'postprocess_capex', ['tsmc', year], value, 'USD/pct', year,
                item, 'TSMC 첨단패키징·테스트 설비투자 및 테스터 병목',
                scope='backend_bucket_includes_packaging_testing_mask_and_others'))

    # ASE: annual CapEx revision.
    if re.search(r'(?<![A-Za-z0-9])ASE(?![A-Za-z0-9])|Advanced Semiconductor Engineering', text, re.I) and re.search(r'capex|설비투자', text, re.I):
        vals = [float(x) * 1e9 for x in re.findall(r'(?:USD|US\$|\$)?\s*([\d.]+)\s*(?:billion|B)', text, re.I)]
        vals += [float(x) * 1e8 for x in re.findall(r'([\d.]+)\s*억\s*달러', text)]
        if vals:
            current = max(vals)
            prior = min(vals) if len(vals) > 1 and min(vals) != current else None
            rows.append(make_record(
                'postprocess_capex', ['ase', year],
                {'total_capex_usd': current, 'prior_capex_usd': prior},
                'USD/year', year, item, 'ASE 연간 설비투자 변경',
                scope='company_capex_not_all_advanced_packaging'))

    # Korean equipment orders: only when vendor and explicit order/contract amount coexist.
    vendor_customer = {
        'di': ('삼성전자', 'samsung'),
        'digital_frontier': ('SK하이닉스', 'skhynix'),
        'yc': ('삼성전자', 'samsung'),
        'exicon': ('', 'multiple'),
        'pemtron': ('SK하이닉스', 'skhynix'),
    }
    for vendor, (customer_text, customer_key) in vendor_customer.items():
        pats = POSTPROCESS_ENTITIES[vendor]
        if not any(re.search(p, text, re.I) for p in pats):
            continue
        # Use the nearest sentence/segment to avoid assigning another vendor's amount.
        segments = re.split(r'(?<=[.!?])\s+|\n+', body)
        for seg in segments:
            if not any(re.search(p, seg, re.I) for p in pats):
                continue
            if not re.search(r'수주|계약|order|contract', seg, re.I):
                continue
            amount = _krw_amount(seg)
            if amount is None:
                continue
            if customer_text and customer_text not in seg:
                # Customer can be inherited from a compact research sentence only if unique.
                if text.count(customer_text) != 1:
                    customer_key = 'unknown'
            count_m = re.search(r'총?\s*(\d+)\s*건|(?:received|won)\s*(\d+)\s*orders?', seg, re.I)
            count = int(next(x for x in count_m.groups() if x)) if count_m else None
            product = 'hbm4_wafer_tester' if re.search(r'HBM4.*Wafer\s*Tester|HBM4.*웨이퍼\s*테스터', seg, re.I) else (
                'hbm_inspection' if re.search(r'HBM.*검사', seg, re.I) else (
                    'clt_ssd_tester' if re.search(r'CLT|SSD', seg, re.I) else 'memory_test_equipment'))
            rows.append(make_record(
                'postprocess_order', [vendor, customer_key, product, year],
                {'amount_krw': amount, 'contract_count': count, 'stage': 'po_signed'},
                'KRW/order', year, item, seg,
                scope='confirmed_or_reported_equipment_order_not_industry_theme'))
            break

    # Validation / PO / move-in / mass-production stage changes.
    for vendor in ('intekplus', 'pemtron', 'isc', 'kohyoung', 'neosem', 'nextein'):
        pats = POSTPROCESS_ENTITIES[vendor]
        if not any(re.search(p, text, re.I) for p in pats):
            continue
        segments = re.split(r'(?<=[.!?])\s+|\n+', body)
        for seg in segments:
            if not any(re.search(p, seg, re.I) for p in pats):
                continue
            stage = _postprocess_stage(seg)
            if not stage:
                continue
            process = 'cowos' if re.search(r'CoWoS', seg, re.I) else (
                'hbm_test' if re.search(r'HBM.*(?:검사|테스트|test)', seg, re.I) else 'advanced_packaging')
            customer = 'taiwan_osat' if re.search(r'대만\s*OSAT|Taiwan(?:ese)?\s*OSAT', seg, re.I) else (
                'global_memory_3' if re.search(r'메모리\s*3사|memory\s*3', seg, re.I) else 'undisclosed')
            rows.append(make_record(
                'postprocess_stage', [vendor, customer, process],
                {'stage': stage}, 'stage', year, item, seg,
                scope='stage_transition_requires_explicit_evidence'))
            break

    return rows


FOUNDRY_STAGE_RANK = {
    'mentioned': 0,
    'review': 1,
    'confirmed': 2,
    'equipment_order': 3,
    'move_in': 4,
    'trial_production': 5,
    'mass_production': 6,
}


def _foundry_stage(text):
    if re.search(r'양산\s*(?:시작|개시)|mass\s*production', text, re.I):
        return 'mass_production'
    if re.search(r'시험\s*생산|test\s*production|trial\s*production', text, re.I):
        return 'trial_production'
    if re.search(r'장비\s*반입|equipment\s*(?:move[- ]?in|installation)', text, re.I):
        return 'move_in'
    if re.search(r'장비\s*발주|equipment\s*order', text, re.I):
        return 'equipment_order'
    if re.search(r'투자\s*확정|증설\s*확정|라인\s*확정|approved|confirmed\s*(?:investment|expansion|line)', text, re.I):
        return 'confirmed'
    if re.search(r'검토|채비|review|consider|plan(?:ning)?', text, re.I):
        return 'review'
    return ''


def _wpm(text):
    patterns = (
        r'월\s*([\d,.]+)\s*만\s*장',
        r'([\d,.]+)\s*만\s*장\s*(?:/\s*월|월간|매월)?',
        r'([\d,]+)\s*(?:wafers?|wafer starts?)\s*(?:per month|/month|monthly)',
    )
    for i, pat in enumerate(patterns):
        m = re.search(pat, text, re.I)
        if not m:
            continue
        n = float(m[1].replace(',', ''))
        return n * 10000 if i < 2 else n
    return None


def parse_foundry_hbm_records(item, body):
    text = re.sub(r'\s+', ' ', body)
    if not re.search(r'(?:삼성|Samsung)', text, re.I) or not re.search(r'HBM', text, re.I):
        return []
    published = item.get('published_at_kst','')
    asof = published[:10]
    rows = []

    # 4nm HBM4 base-die allocation and utilization.
    if re.search(r'(?:4\s*나노|4nm)', text, re.I) and re.search(r'(?:베이스\s*다이|base\s*die)', text, re.I):
        alloc_min = alloc_max = None
        am = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*[~–-]\s*([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:HBM4|베이스\s*다이|base\s*die)', text, re.I)
        if not am:
            am = re.search(r'(?:HBM4|베이스\s*다이|base\s*die)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*[~–-]\s*([0-9]+(?:\.[0-9]+)?)\s*%', text, re.I)
        if am:
            alloc_min, alloc_max = float(am[1]), float(am[2])
        elif re.search(r'(?:절반\s*이상|50\s*%\s*이상)', text):
            alloc_min = 50.0

        total_wpm = _wpm(text)
        full = bool(re.search(r'풀가동|풀생산|full\s*(?:utilization|capacity|production)', text, re.I))
        if alloc_min is not None or total_wpm is not None or full:
            rows.append(make_record(
                'foundry_base_die_allocation', ['samsung','4nm','HBM4'],
                {'total_capacity_wpm': total_wpm, 'allocation_pct_min': alloc_min,
                 'allocation_pct_max': alloc_max, 'full_utilization': full},
                'wafers/month,pct', 'current', item,
                '삼성 4나노 생산능력 중 HBM4 베이스다이 배정·가동률',
                as_of=asof, scope='reported_foundry_capacity_not_hbm_finished_goods'))

        # 4nm expansion status.
        if re.search(r'증설|생산능력\s*확대|capacity\s*expansion|expand', text, re.I):
            stage = _foundry_stage(text) or 'mentioned'
            rows.append(make_record(
                'foundry_node_expansion', ['samsung','4nm','HBM4_base_die'],
                {'stage': stage}, 'stage', 'current', item,
                '삼성 HBM4 베이스다이 대응 4나노 증설 단계',
                as_of=asof, scope='foundry_expansion_stage'))

        # Price increases are a separate state from physical capacity.
        new_order_up = bool(re.search(r'(?:4\s*나노|4nm)[^.]{0,100}?(?:신규\s*수주|new\s*orders?)[^.]{0,80}?(?:가격\s*인상|price\s*(?:increase|hike))', text, re.I))
        base_die_up = bool(re.search(r'(?:베이스\s*다이|base\s*die)[^.]{0,80}?(?:가격\s*인상|price\s*(?:increase|hike))', text, re.I))
        pct = None
        pm = re.search(r'(?:가격\s*인상|price\s*(?:increase|hike))[^%]{0,30}?([0-9]+(?:\.[0-9]+)?)\s*%', text, re.I)
        if pm:
            pct = float(pm[1])
        if new_order_up or base_die_up or pct is not None:
            rows.append(make_record(
                'foundry_pricing', ['samsung','4nm','HBM4_base_die'],
                {'new_order_price_up': new_order_up, 'base_die_price_up': base_die_up,
                 'price_change_pct': pct},
                'direction,pct', 'current', item,
                '삼성 4나노 신규수주·HBM4 베이스다이 가격 변화',
                as_of=asof, scope='reported_foundry_pricing'))

    # HBM5: distinguish the technology plan from a real 2nm production-line investment stage.
    if re.search(r'HBM5', text, re.I) and re.search(r'(?:2\s*나노|2nm)', text, re.I):
        investment_stage = ''
        if re.search(r'신규\s*생산라인|생산라인\s*(?:구축|투자)|new\s*production\s*line|new\s*line', text, re.I):
            investment_stage = _foundry_stage(text) or 'mentioned'
        speed = None
        sm = re.search(r'(?:동작\s*속도|speed)[^%]{0,50}?([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:이상\s*)?(?:향상|increase|faster)', text, re.I)
        if not sm:
            sm = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:이상\s*)?(?:향상|increase|faster)[^.]{0,60}?(?:HBM4E|동작\s*속도|speed)', text, re.I)
        if sm:
            speed = float(sm[1])
        if investment_stage or speed is not None or re.search(r'GAA|TSV', text, re.I):
            rows.append(make_record(
                'foundry_hbm5_2nm', ['samsung','2nm','HBM5'],
                {'investment_stage': investment_stage or 'technology_plan',
                 'speed_uplift_target_pct': speed,
                 'gaa': bool(re.search(r'GAA|게이트올어라운드', text, re.I)),
                 'tsv_density_up': bool(re.search(r'TSV|실리콘\s*관통\s*전극', text, re.I))},
                'stage,pct', 'HBM5', item,
                '삼성 HBM5 2나노 베이스다이 기술·투자 단계',
                as_of=asof, scope='technology_plan_and_line_investment_separated'))

    return rows


def parse_records(item, body):
    records, gaps = [], []
    published = item.get('published_at_kst', '')
    malaysia = _malaysia_export_record(item, body)
    if malaysia:
        records.append(malaysia)
    records.extend(parse_hbm_revenue_estimates(item, body))
    records.extend(parse_postprocess_records(item, body))
    records.extend(parse_foundry_hbm_records(item, body))
    paragraphs = [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n+|(?<=[.!?])\s+(?=[A-Z가-힣])', body) if p.strip()]
    for original in paragraphs:
        p = resolve_relative_years(original, published)
        owners = [k for k, pat in COMPANIES.items() if re.search(pat, p, re.I)]
        owner = owners[0] if len(owners) == 1 else OFFICIAL.get(host(item.get('direct_link', '')), '')
        if not owner:
            title_owners = [k for k, pat in COMPANIES.items() if re.search(pat, item.get('title', ''), re.I)]
            owner = title_owners[0] if len(title_owners) == 1 and not owners else ''
        for m in re.finditer(r'(?:DDR5\s+)?RDIMM\s+(\d+)GB|(?:DDR5\s+)?(\d+)GB\s+RDIMM', p):
            gb = int(m[1] or m[2])
            if len(re.findall(r'RDIMM', p)) > 1:
                gaps.append('RDIMM 복수 규격 문장: 가격 귀속 보류'); continue
            speed = re.search(r'((?:\d{4}/)*\d{4})\s*(?:MT/s|Mbps)', p, re.I)
            asof = date_only(p)
            a = re.search(r'(?:spot(?: price)?|현물(?:가격)?)\s*[:=]?\s*(?:\$|USD\s*)?([\d,]+(?:\.\d+)?)\s*(?:달러|USD|dollars)?', p, re.I)
            b = re.search(r'(?:contract(?: price)?|고정거래(?:가격)?)\s*[:=]?\s*(?:\$|USD\s*)?([\d,]+(?:\.\d+)?)\s*(?:달러|USD|dollars)?', p, re.I)
            contract_period = re.search(r'(?:contract period|고정거래 기준)\s*[:=]?\s*(20\d{2}[-./]\d{2}(?:[-./]\d{2})?)', p, re.I)
            if re.search(r'유로|EUR|JPY|원화', p):
                gaps.append('RDIMM 통화 혼재: 비교 보류'); continue
            if not (a and b and speed and asof and contract_period and re.search(r'달러|USD|\$', p)):
                gaps.append(f'RDIMM {gb}GB: 현물·고정거래 원값/규격/기준기간 미확보'); continue
            s, c = float(a[1].replace(',', '')), float(b[1].replace(',', ''))
            cp = contract_period[1].replace('/', '-').replace('.', '-')
            if cp[:7] != asof[:7]:
                gaps.append(f'RDIMM {gb}GB: 현물일과 고정거래 기준월 불일치'); continue
            if min(s, c) <= 0:
                continue
            records.append(make_record('rdimm', [host(item['direct_link']), f'DDR5_{gb}GB', speed[1]],
                {'spot': s, 'contract': c, 'premium_pct': premium(s, c), 'contract_period': cp},
                'USD/module', asof[:7], item, original, as_of=asof, capacity_gb=gb, speed=speed[1]))
        matches = list(re.finditer(r'(?<![A-Za-z0-9])(HBM4E|HBM4|HBM3E)(?![A-Za-z0-9])', p, re.I))
        for i, match in enumerate(matches):
            part = p[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(p)]
            density = re.findall(r'(?<!\d)(\d+)\s*Gb(?![A-Za-z])', part)
            layers = re.findall(r'(?<!\d)(\d+)\s*(?:단|[Hh][Ii]|-[Hh][Ii]|[Hh](?![A-Za-z]))', part)
            capacity = re.findall(r'(?<!\d)(\d+)\s*GB(?![A-Za-z])', part)
            if owner and len(density) == len(layers) == len(capacity) == 1:
                d, h, g = int(density[0]), int(layers[0]), int(capacity[0])
                if product_capacity(d, h) != g:
                    gaps.append('HBM 구성 산술 불일치: 발송 보류'); continue
                product = match[1].upper()
                records.append(make_record('hbm_config', [owner, product, str(h) + 'Hi', 'catalog'],
                    {'die_gbit': d, 'layers': h, 'stack_gbyte': g}, 'GB/stack', local_period(part, published) or 'catalog',
                    item, original, scope='product_capability_not_customer_contract'))
        metric_patterns = (
            ('wafer_share', r'(?:HBM.{0,70}(?:웨이퍼|wafer).{0,45}(?:비중|share)|(?:웨이퍼|wafer).{0,70}HBM.{0,50}(?:비중|share)|HBM wafer input)'),
            ('bit_share', r'(?:HBM.{0,70}(?:비트|bit).{0,45}(?:비중|share)|(?:비트|bit).{0,70}HBM.{0,50}(?:비중|share)|HBM bit supply)'),
        )
        metric_hits = [(metric, pat) for metric, pat in metric_patterns if re.search(pat, p, re.I)]
        if len(metric_hits) > 1:
            gaps.append('웨이퍼·비트 분모 혼재 문장: 값 귀속 보류')
            metric_hits = []
        for metric, pat in metric_hits:
            if not re.search(r'연말|년\s*말|\b(?:year[- ]end|end of|by the end)\b', p, re.I) or re.search(r'연평균|annual average', p, re.I):
                gaps.append(metric + ': 연말 분모가 명확하지 않아 비교 보류'); continue
            authority = 'trendforce' if re.search(r'TrendForce|트렌드포스', body, re.I) else owner
            if not authority: continue
            periods = re.findall(r'(20\d{2})\s*년?\s*(?:말|연말|year.end)?', p, re.I)
            values = re.findall(r'(\d+(?:\.\d+)?)\s*%', p)
            if len(periods) == len(values) and 1 <= len(periods) <= 4:
                for y, v in zip(periods, values):
                    if 0 <= float(v) <= 100:
                        records.append(make_record(metric, [authority, 'industry', y + '-YE'], float(v), 'pct',
                            y + '-YE', item, original, scope='year_end_forecast'))
            else:
                gaps.append(metric + ': 연도별 값 연결 불명확')
        if owner and re.search(r'글라스 캐리어|유리 지지판|glass carrier', p, re.I) and re.search(r'세정|clean', p, re.I):
            for y, n, tenk in re.findall(r'(20\d{2})\s*년?[^.\n]{0,12}?(?:월|monthly)\s*([\d,.]+)\s*(만)?\s*(?:장|pieces)', p, re.I):
                value = float(n.replace(',', '')) * (10000 if tenk else 1)
                records.append(make_record('carrier_cleaning', [owner, y], value, 'cleaning_passes/month', y,
                    item, original, scope='reusable_carrier_service_not_wafer_output'))
        if owner and re.search(r'P5', p, re.I) and re.search(r'Fab\s*1', p, re.I) and re.search(r'가동|양산|production|operation', p, re.I):
            years = re.findall(r'(?<!\d)(20\d{2})(?!\d)', p)
            if len(set(years)) == 1:
                stage = 'cancelled' if re.search(r'취소|cancel', p, re.I) else ('delayed' if re.search(r'지연|delay', p, re.I) else ('plan' if re.search(r'목표|계획|예정|target|plan|expect', p, re.I) else 'reported_operation'))
                records.append(make_record('fab_stage', [owner, 'P5_Fab1'], {'year': int(years[0]), 'stage': stage},
                    'year/stage', years[0], item, original, scope='fab_start_not_full_output'))
    return records, list(dict.fromkeys(gaps))


def public_spot_quotes(raw, checked):
    from selectolax.parser import HTMLParser
    tree = HTMLParser(raw)
    full = tree.body.text(separator=' ', strip=True) if tree.body else ''
    result = []
    for row in tree.css('tr'):
        cells = row.css('td,th')
        if len(cells) < 6:
            continue
        name = re.sub(r'\s+', ' ', cells[0].text(strip=True))
        module = re.search(r'DDR5\s+RDIMM\s+(32|64|128|256)GB\s+([\d/]+)', name)
        chip = re.search(r'DDR5\s+16Gb\s+\(2Gx8\)\s+([\d/]+)', name)
        if not (module or chip):
            continue
        table = row.parent
        while table and table.tag != 'table':
            table = table.parent
        if not table:
            continue
        headers = table.css_first('tr')
        labels = [re.sub(r'\s+', '', x.text()).lower() for x in headers.css('td,th')] if headers else []
        try:
            index = labels.index('sessionaverage')
            value = float(cells[index].text(strip=True).replace(',', ''))
        except (ValueError, IndexError):
            continue
        offset = full.find(name)
        if offset < 0:
            continue
        dates = list(re.finditer(r'Last\s*Update\s*:\s*([A-Za-z]{3})\.?\s*(\d{1,2})\s+(20\d{2})', full[:offset], re.I))
        if not dates:
            continue
        dt = dates[-1]
        try:
            asof = datetime.strptime(f'{dt[1]} {dt[2]} {dt[3]}', '%b %d %Y').date().isoformat()
        except ValueError:
            continue
        if asof > checked.date().isoformat() or value <= 0:
            continue
        capacity = int(module[1]) if module else 16
        speed = module[2] if module else chip[1]
        axis = 'rdimm_quote' if module else 'ddr5_chip_quote'
        item = {'direct_link':'https://www.dramexchange.com/', 'source':'DRAMeXchange',
                'published_at_kst':asof, 'title':name + ' 공개 현물가격'}
        result.append(make_record(axis, ['dramexchange', str(capacity), speed], value,
            'USD/module' if module else 'USD/chip', asof[:7], item,
            name + ': Session Average (공개 화면)', as_of=asof, capacity_gb=capacity if module else None,
            density_gbit=None if module else 16, speed=speed))
    return result


def comparison(old, new):
    a, b = old['value'], new['value']
    if new['axis'] == 'foundry_base_die_allocation':
        reasons = []
        aw, bw = a.get('total_capacity_wpm'), b.get('total_capacity_wpm')
        if aw and bw:
            dp = (float(bw) / float(aw) - 1) * 100
            if abs(dp) >= 10 or abs(float(bw)-float(aw)) >= 5000:
                reasons.append(f"4나노 생산능력 {dp:+.1f}%")
        for field, label in (('allocation_pct_min','HBM4 베이스다이 배정 하단'), ('allocation_pct_max','HBM4 베이스다이 배정 상단')):
            av, bv = a.get(field), b.get(field)
            if av is not None and bv is not None and abs(float(bv)-float(av)) >= 5:
                reasons.append(f"{label} {float(bv)-float(av):+.1f}%p")
        if a.get('full_utilization') != b.get('full_utilization'):
            reasons.append('4나노 풀가동 진입' if b.get('full_utilization') else '4나노 풀가동 완화')
        return reasons
    if new['axis'] == 'foundry_node_expansion':
        old_stage = a.get('stage','mentioned')
        new_stage = b.get('stage','mentioned')
        return [f"4나노 증설 단계 {old_stage}→{new_stage}"] if old_stage != new_stage else []
    if new['axis'] == 'foundry_pricing':
        reasons = []
        for field, label in (('new_order_price_up','4나노 신규수주 가격 인상'), ('base_die_price_up','HBM4 베이스다이 가격 인상')):
            if a.get(field) != b.get(field):
                reasons.append(label + (' 확인' if b.get(field) else ' 해소·철회'))
        av, bv = a.get('price_change_pct'), b.get('price_change_pct')
        if av is not None and bv is not None and abs(float(bv)-float(av)) >= 5:
            reasons.append(f"가격 인상률 {float(bv)-float(av):+.1f}%p")
        elif av is None and bv is not None:
            reasons.append(f"가격 인상률 {float(bv):.1f}% 확인")
        return reasons
    if new['axis'] == 'foundry_hbm5_2nm':
        reasons = []
        old_stage = a.get('investment_stage','technology_plan')
        new_stage = b.get('investment_stage','technology_plan')
        if old_stage != new_stage:
            reasons.append(f"HBM5 2나노 투자 단계 {old_stage}→{new_stage}")
        av, bv = a.get('speed_uplift_target_pct'), b.get('speed_uplift_target_pct')
        if av is not None and bv is not None and abs(float(bv)-float(av)) >= 10:
            reasons.append(f"동작속도 향상 목표 {float(bv)-float(av):+.1f}%p")
        return reasons
    if new['axis'] == 'postprocess_capex':
        reasons = []
        if old.get('period') != new.get('period'):
            reasons.append(f"새 설비투자 연도 {old.get('period')}→{new.get('period')}")
        for field, label in (('total_capex_usd_min','설비투자 하단'), ('total_capex_usd_max','설비투자 상단'), ('total_capex_usd','설비투자')):
            av, bv = a.get(field), b.get(field)
            if av and bv:
                dp = (bv / av - 1) * 100
                if abs(dp) >= 10 or abs(bv-av) >= 1_000_000_000:
                    reasons.append(f"{label} {dp:+.1f}%")
        for field, label in (('backend_alloc_pct_min','후공정 배정 하단'), ('backend_alloc_pct_max','후공정 배정 상단')):
            av, bv = a.get(field), b.get(field)
            if av is not None and bv is not None and abs(float(bv) - float(av)) >= 5:
                reasons.append(f"{label} {float(bv)-float(av):+.1f}%p")
        if a.get('tester_shortage') != b.get('tester_shortage'):
            reasons.append('테스터 부족 확인' if b.get('tester_shortage') else '테스터 부족 해소·완화 확인')
        return reasons
    if new['axis'] == 'postprocess_order':
        reasons = []
        av, bv = float(a.get('amount_krw') or 0), float(b.get('amount_krw') or 0)
        if av and bv:
            dp = (bv / av - 1) * 100
            if abs(dp) >= 10 or abs(bv-av) >= 10_000_000_000:
                reasons.append(f"수주액 {dp:+.1f}%")
        if a.get('stage') != b.get('stage'):
            reasons.append(f"수주 단계 {a.get('stage')}→{b.get('stage')}")
        return reasons
    if new['axis'] == 'postprocess_stage':
        old_stage, new_stage = a.get('stage','mentioned'), b.get('stage','mentioned')
        if old_stage != new_stage:
            return [f"검증·양산 단계 {old_stage}→{new_stage}"]
        return []
    if new['axis'] == 'hbm_revenue_estimate':
        reasons = []
        old_est = float(a.get('estimate_usd') or 0)
        new_est = float(b.get('estimate_usd') or 0)
        if old_est and new_est:
            delta_usd = new_est - old_est
            delta_pct = (new_est / old_est - 1) * 100
            if abs(delta_usd) >= 1_000_000_000 or abs(delta_pct) >= 10:
                reasons.append(f"분기 HBM 매출 추정 {delta_pct:+.1f}% ({delta_usd/1e9:+.1f}십억달러)")
        old_q = a.get('qoq_pct')
        new_q = b.get('qoq_pct')
        if old_q is not None and new_q is not None and abs(new_q - old_q) >= 10:
            reasons.append(f"전분기 증감률 전망 {new_q-old_q:+.1f}%p")
        if a.get('method') != b.get('method'):
            reasons.append(f"추정방법 {a.get('method')}→{b.get('method')}")
        return reasons
    if new['axis'] == 'malaysia_hsk10_export':
        reasons = []
        if old.get('period') != new.get('period'):
            reasons.append(f"새 월 {old.get('period')}→{new.get('period')}")
        if a.get('amount_usd') and b.get('amount_usd'):
            change = (b['amount_usd'] / a['amount_usd'] - 1) * 100
            if abs(change) >= 10 or old.get('period') != new.get('period'):
                reasons.append(f"수출액 {change:+.1f}%")
        if a.get('malaysia_vs_taiwan_pct') is not None and b.get('malaysia_vs_taiwan_pct') is not None:
            dp = b['malaysia_vs_taiwan_pct'] - a['malaysia_vs_taiwan_pct']
            if abs(dp) >= 10 or ((a['malaysia_vs_taiwan_pct'] < 50) != (b['malaysia_vs_taiwan_pct'] < 50)):
                reasons.append(f"대만 대비 비중 {dp:+.1f}%p")
        return reasons
    if new['axis'] in ('rdimm_quote', 'ddr5_chip_quote'):
        change = (b / a - 1) * 100
        return [f'동일 규격 현물가격 {change:+.1f}%'] if abs(change) >= 5 else []
    if new['axis'] == 'rdimm':
        reasons = []
        for field, label in (('spot', '현물가격'), ('contract', '고정거래가격')):
            change = (b[field] / a[field] - 1) * 100
            if abs(change) >= 5:
                reasons.append(f'{label} {change:+.1f}%')
        dp = b['premium_pct'] - a['premium_pct']
        if abs(dp) >= 10 or ((a['premium_pct'] > 100) != (b['premium_pct'] > 100)):
            reasons.append(f'현물 프리미엄 {dp:+.1f}%p')
        if b['contract_period'] != a['contract_period']:
            reasons.append('새 고정거래 기준기간')
        if reasons:
            reasons.append(rdimm_driver(a, b))
        return reasons
    return [] if a == b else ['동일 대상·동일 단위의 상태값 변경']


def update_state(state, records, now, seeds=None):
    state = copy.deepcopy(state or {})
    for name in ('last_notified', 'latest', 'pending', 'coverage'):
        state.setdefault(name, {})
    if seeds:
        for r in seeds:
            state['last_notified'].setdefault(r['key'], r)
            state['latest'].setdefault(r['key'], r)
    state['version'] = VERSION
    grouped = {}
    for r in records:
        if not r.get('as_of') or not r.get('source_url') or not r.get('period'):
            continue
        if r['as_of'][:10] > now.date().isoformat():
            continue
        grouped.setdefault(r['key'], []).append(r)
    for key, rows in grouped.items():
        rows.sort(key=lambda x: (x['as_of'], RANK.get(x['evidence'], 0)))
        r = rows[-1]
        same = [x for x in rows if x['as_of'] == r['as_of'] and x['evidence'] == r['evidence']]
        if len({fingerprint(x['value']) for x in same}) > 1:
            state['coverage'][key] = '동일 기준일 원값 불일치: 발송 보류'
            state['pending'].pop(key, None)
            continue
        previous_latest = state['latest'].get(key)
        if previous_latest and r['as_of'] < previous_latest.get('as_of', ''):
            continue
        old = state['last_notified'].get(key)
        if old and RANK.get(r['evidence'], 0) < RANK.get(old['evidence'], 0):
            state['coverage'][key] = '하위 증거는 기존 확정값을 덮어쓰지 않음'
            continue
        state['latest'][key] = r
        if r['axis'] in ('rdimm', 'rdimm_quote', 'ddr5_chip_quote') and r['as_of'] < (now - timedelta(days=10)).date().isoformat():
            state['coverage'][key] = '지연 원자료: 현재 가격 알림 보류'
            if not old:
                state['last_notified'][key] = r
            state['pending'].pop(key, None)
            continue
        reasons = comparison(old, r) if old else ['새 비교 가능한 상태']
        if old and r['value'] == old['value'] and RANK.get(r['evidence'], 0) > RANK.get(old['evidence'], 0):
            reasons.append('근거 등급 상향')
        fresh = r['as_of'] >= (now - timedelta(days=14)).date().isoformat()
        if not old and not fresh:
            state['last_notified'][key] = r
            continue
        if not reasons:
            state['pending'].pop(key, None)
            continue
        state['pending'][key] = {'record': r, 'old': old, 'reasons': reasons}
    return state


def render(change, rate=None):
    r, old = change['record'], change.get('old')
    names = {'rdimm_quote': '서버 RDIMM 공개 현물가격', 'ddr5_chip_quote': 'DDR5 16Gb 칩 현물가격', 'rdimm': '서버 DDR5 가격·프리미엄', 'hbm_config': 'HBM 칩 용량·적층 구성',
             'wafer_share': 'HBM 웨이퍼 배분 전망', 'bit_share': 'HBM 비트 공급 비중 전망',
             'carrier_cleaning': 'HBM 유리 지지판 세정 처리량', 'fab_stage': 'P5 Fab1 공급 일정',
             'malaysia_hsk10_export': '한국→말레이시아 HBM 관련 HSK10 수출',
             'hbm_revenue_estimate': '기관 HBM 분기 매출 추정 변화',
             'postprocess_capex': 'HBM 후공정 설비투자·병목 변화',
             'postprocess_order': 'HBM 후공정 장비 수주 변화',
             'postprocess_stage': 'HBM 후공정 고객 검증·양산 단계 변화',
             'foundry_base_die_allocation': '삼성 HBM4 베이스다이 4나노 배정·가동 변화',
             'foundry_node_expansion': '삼성 HBM4 대응 4나노 증설 단계 변화',
             'foundry_pricing': '삼성 4나노·HBM4 베이스다이 가격 변화',
             'foundry_hbm5_2nm': '삼성 HBM5 2나노 베이스다이 투자 단계 변화'}
    def fmt(record):
        v = record['value']
        if record['axis'] == 'rdimm':
            def money(n):
                return f'{n:,.2f}달러' + (f'(약 {n * rate:,.0f}원)' if rate else '(원화 환율 확인 불가)')
            return f"현물 {money(v['spot'])} / 고정거래 {money(v['contract'])} / 프리미엄 {v['premium_pct']:.1f}%"
        if record['axis'] in ('rdimm_quote', 'ddr5_chip_quote'):
            return f'{v:,.3f}달러' + (f'(약 {v * rate:,.0f}원)' if rate else '(원화 환율 확인 불가)')
        if record['axis'] == 'hbm_config':
            return f"{v['die_gbit']}Gb × {v['layers']}단 ÷ 8 = {v['stack_gbyte']}GB"
        if record['axis'] == 'fab_stage':
            labels = {'plan': '계획', 'delayed': '지연', 'cancelled': '취소', 'reported_operation': '가동 보도'}
            return f"{v['year']}년 · {labels.get(v['stage'], v['stage'])}"
        if record['axis'] == 'foundry_base_die_allocation':
            parts = []
            if v.get('total_capacity_wpm'):
                parts.append(f"4나노 월 {v['total_capacity_wpm']/10000:.1f}만장")
            if v.get('allocation_pct_min') is not None:
                if v.get('allocation_pct_max') is not None:
                    parts.append(f"HBM4 베이스다이 {v['allocation_pct_min']:.0f}~{v['allocation_pct_max']:.0f}%")
                else:
                    parts.append(f"HBM4 베이스다이 {v['allocation_pct_min']:.0f}% 이상")
            if v.get('full_utilization'):
                parts.append("풀가동")
            return " / ".join(parts)
        if record['axis'] == 'foundry_node_expansion':
            labels = {'mentioned':'언급','review':'증설 검토','confirmed':'투자·증설 확정','equipment_order':'장비 발주','move_in':'장비 반입','trial_production':'시험생산','mass_production':'양산'}
            return labels.get(v.get('stage'), v.get('stage',''))
        if record['axis'] == 'foundry_pricing':
            parts = []
            if v.get('new_order_price_up'):
                parts.append("4나노 신규수주 가격 인상")
            if v.get('base_die_price_up'):
                parts.append("HBM4 베이스다이 가격 인상")
            if v.get('price_change_pct') is not None:
                parts.append(f"{v['price_change_pct']:.1f}%")
            return " / ".join(parts)
        if record['axis'] == 'foundry_hbm5_2nm':
            labels = {'technology_plan':'2나노 기술 적용 계획','mentioned':'신규라인 언급','review':'신규라인 투자 검토','confirmed':'신규라인 투자 확정','equipment_order':'장비 발주','move_in':'장비 반입','trial_production':'시험생산','mass_production':'양산'}
            text = labels.get(v.get('investment_stage'), v.get('investment_stage',''))
            if v.get('speed_uplift_target_pct') is not None:
                text += f" / 속도 +{v['speed_uplift_target_pct']:.0f}% 목표"
            return text
        if record['axis'] == 'postprocess_capex':
            if 'total_capex_usd_min' in v and v.get('total_capex_usd_min'):
                text = f"설비투자 {v['total_capex_usd_min']/1e9:.1f}~{v['total_capex_usd_max']/1e9:.1f}십억달러"
                if v.get('backend_alloc_pct_min') is not None:
                    text += f" / 후공정 묶음 {v['backend_alloc_pct_min']:.0f}~{v['backend_alloc_pct_max']:.0f}%"
                if v.get('tester_shortage'):
                    text += " / 테스터 부족 확인"
                return text
            amount = v.get('total_capex_usd') or 0
            text = f"설비투자 {amount/1e9:.1f}십억달러"
            if v.get('prior_capex_usd'):
                text += f" / 직전 {v['prior_capex_usd']/1e9:.1f}십억달러"
            return text
        if record['axis'] == 'postprocess_order':
            amount = v.get('amount_krw') or 0
            text = f"수주 {amount/1e8:,.0f}억원"
            if v.get('contract_count'):
                text += f" / {v['contract_count']}건"
            return text
        if record['axis'] == 'postprocess_stage':
            labels = {
                'development':'개발', 'pilot':'파일럿', 'pilot_passed':'파일럿 품질검증 통과',
                'po_pending':'정식 발주 대기', 'po_signed':'정식 수주', 'equipment_move_in':'장비 반입',
                'mass_production':'양산'
            }
            return labels.get(v.get('stage'), v.get('stage',''))
        if record['axis'] == 'hbm_revenue_estimate':
            amount = v.get('estimate_usd') or 0
            text = f"분기 추정 {amount/1e9:.1f}십억달러"
            if rate:
                text += f"(약 {amount*rate/1e12:.2f}조원)"
            if v.get('qoq_pct') is not None:
                text += f" / 전분기 {v['qoq_pct']:+.1f}%"
            if v.get('prior_formal_forecast_usd'):
                text += f" / 기존 공식 전망 참조 {v['prior_formal_forecast_usd']/1e9:.1f}십억달러"
            if v.get('alternative_usd'):
                text += f" / 대안 시나리오 {v['alternative_usd']/1e9:.1f}십억달러"
            return text
        if record['axis'] == 'malaysia_hsk10_export':
            amount = v.get('amount_usd') or 0
            text = f"수출 {amount/1e9:.3f}십억달러"
            if rate:
                text += f"(약 {amount*rate/1e12:.2f}조원)"
            if v.get('weight_kg'):
                text += f" / 중량 약 {v['weight_kg']/1000:.1f}t"
            if v.get('yoy_pct') is not None:
                text += f" / 전년동월 +{v['yoy_pct']:.1f}%"
            if v.get('malaysia_vs_taiwan_pct') is not None:
                text += f" / 대만 대비 {v['malaysia_vs_taiwan_pct']:.1f}%"
            return text
        return str(v) + ('%' if record['unit'] == 'pct' else '회/월')
    lines = [f"<b>{names[r['axis']]}</b>", f"• 현재: {html.escape(fmt(r))}"]
    if old:
        lines.append('• 직전 알림 기준: ' + html.escape(fmt(old)))
    lines += ['• 변화: ' + html.escape(' / '.join(change['reasons'])),
              f"• 대상기간: {html.escape(r['period'])} · 자료 기준일 {html.escape(r['as_of'])}"]
    if r['axis'] == 'rdimm':
        lines += [f"• 규격: {r['capacity_gb']}GB RDIMM · {html.escape(r['speed'])} MT/s",
                  f"• 고정거래 기준: {r['value']['contract_period']} · 프리미엄은 이익률이 아님"]
    if r['axis'] in ('rdimm_quote', 'ddr5_chip_quote'):
        lines.append('• 고정거래 원값이 없으면 프리미엄을 추정하지 않으며, 16Gb 칩과 GB 모듈은 별도입니다.')
    if r['axis'] == 'hbm_config':
        lines.append('• 제품 사양과 고객 채택을 분리하며, 묶음 수 미확인 시 GPU 전체 용량을 추정하지 않습니다.')
        if r['value']['stack_gbyte'] == 32:
            lines.append('• 비교 시나리오: 36→32GB는 −11.1%·출하 +12.5% 상쇄 / 48→32GB는 −33.3%·출하 +50% 상쇄. 고객 실제 채택과 별개입니다.')
        if old:
            comp = capacity_comparison(old['value']['stack_gbyte'], r['value']['stack_gbyte'])
            lines.append(f"• 동일 묶음 수 가정: 용량 {comp['capacity_change_pct']:+.1f}% · 총 비트 유지 출하 증감률 {comp['gpu_growth_break_even_pct']:+.1f}%")
    if r['axis'] == 'carrier_cleaning':
        lines.append('• 재사용 세정 처리량이며 웨이퍼 생산·칩 출하·수주금액으로 치환하지 않습니다.')
    if r['axis'] in ('wafer_share', 'bit_share'):
        lines.append('• 연말 전망이며 연간 평균·실제 확정 생산량과 비교하지 않습니다.')
    if r['axis'] == 'foundry_base_die_allocation':
        lines.append('• 4나노 웨이퍼 배정률은 HBM 완제품 출하량과 동일하지 않으며 수율·베이스다이 크기·패키징 수율을 별도로 봅니다.')
    if r['axis'] == 'foundry_node_expansion':
        lines.append('• 증설 검토와 투자 확정·장비 발주·장비 반입·시험생산·양산을 각각 다른 단계로 추적합니다.')
    if r['axis'] == 'foundry_pricing':
        lines.append('• 가격 인상 보도와 실제 평균판매단가를 구분하며 인상률이 공개되면 숫자 상태로 갱신합니다.')
    if r['axis'] == 'foundry_hbm5_2nm':
        lines.append('• 2나노 기술 적용 계획과 HBM5 전용 신규 생산라인 설비투자는 서로 다른 상태입니다.')
    if r['axis'] == 'postprocess_capex':
        lines.append('• 설비투자 총액과 후공정·테스트 배정액을 분리하며, TSMC 10~20% 묶음에는 패키징·테스트·마스크·기타가 함께 포함됩니다.')
    if r['axis'] == 'postprocess_order':
        lines.append('• 기사 관심종목이 아니라 고객·금액이 확인된 실제 수주만 상태값으로 올립니다.')
    if r['axis'] == 'postprocess_stage':
        lines.append('• 파일럿→품질검증→정식 발주→장비 반입→양산의 단계 상승만 신규 상태로 봅니다.')
    if r['axis'] == 'hbm_revenue_estimate':
        method_labels = {'regression_proxy':'수출 회귀식 대용지표', 'formal_forecast':'기관 공식 전망', 'reported_estimate':'보도 추정'}
        lines.append('• 성격: ' + method_labels.get(r['value'].get('method'), r['value'].get('method','')) + '이며 회사 확정 매출이 아닙니다.')
        lines.append('• 회귀식 추정치와 기관의 정식 실적 전망을 같은 값으로 합치지 않습니다.')
    if r['axis'] == 'malaysia_hsk10_export':
        lines.append('• HSK 8542323000은 HBM 포함 복합구조칩 집적회로로 HBM 전용 통계가 아닙니다.')
        if r['value'].get('weight_rounded_from_public_text'):
            lines.append('• 중량은 공개 보도 반올림값이면 중량당 단가를 정밀 계산하지 않습니다. 관세청 직접 원값 확인 시 갱신합니다.')
    label = {'official': '회사 공식자료', 'research': '조사기관 자료', 'reported': '보도 단계', 'user_capture': '사용자 캡처 기준선'}[r['evidence']]
    source_title = r.get('source_title','')
    if not re.search(r'[가-힣]', source_title):
        source_title = names.get(r['axis'], 'HBM 상태 변화') + ' 관련 보도'
    lines += [f'• 근거 단계: {label}', '• 근거 제목(한국어): ' + html.escape(source_title) +
              ' · <a href="' + html.escape(r['source_url'], quote=True) + '">원문</a>']
    return '\n'.join(lines)


def main():
    import samsung_hbm_watch as legacy
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    baseline = json.loads((ROOT / 'data/hbm_memory_baselines.json').read_text(encoding='utf-8'))
    original_descriptor = legacy.event_state_descriptor
    rejected_generic = []
    def guarded_descriptor(e):
        text = (e.get('title','') + ' ' + e.get('description','')).lower()
        structured_revenue = (
            'hbm' in text
            and any(k in text for k in ('bernstein', '번스타인', 'j.p. morgan', 'jp morgan', 'ubs', 'morgan stanley', 'citi', 'bofa', 'goldman sachs'))
            and any(k in text for k in ('revenue', '매출', 'qoq', '전분기', 'forecast', 'estimate', '회귀', 'regression'))
            and not any(k in text for k in ('2배', 'double', '3배', 'triple', 'wafer', '웨이퍼', 'capacity', '생산능력', '캐파'))
        )
        structured_postprocess = (
            any(k in text for k in (
                'tsmc', 'ase', '디아이', '디지털 프론티어', '디지털프론티어', '와이씨',
                '엑시콘', '인텍플러스', '펨트론', 'isc', '고영', '네오셈', '넥스틴'
            ))
            and any(k in text for k in (
                'cowos', '후공정', '패키징', '검사', '테스트', 'tester',
                '수주', '품질 검증', '정식 계약', '설비투자', 'capex'
            ))
        )
        if structured_revenue or structured_postprocess:
            rejected_generic.append(e.get('id') or fingerprint(e.get('title', '')))
            return '', '', ''
        if not concrete_state_evidence(e):
            rejected_generic.append(e.get('id') or fingerprint(e.get('title', '')))
            return '', '', ''
        return original_descriptor(e)
    legacy.event_state_descriptor = guarded_descriptor
    initial = legacy.load_state()
    for e in baseline.get('recovered_deliveries', []):
        key, signature, label = legacy.event_state_descriptor(e)
        if key:
            initial.setdefault('topic_states', {}).setdefault(key, {
                'signature': signature, 'observed_at': e['published_at_kst'], 'state': label,
                'recovered_message_id': e['message_id']})
    legacy.save_state(initial)
    original_read, original_relevant = legacy.read_events, legacy.relevant
    legacy.QUERIES = list(dict.fromkeys(legacy.QUERIES + EXTRA_QUERIES))
    legacy.TRUSTED += (
        '글로벌이코노믹', 'g-enews', 'dramexchange', 'sk하이닉스', 'micron',
        'futunn', 'futu news', 'bernstein', 'hilo research', 'xxquant'
    )
    legacy.relevant = lambda text: original_relevant(text) or is_axis_text(text)
    observed, coverage = [], []
    body_cache = {}
    def gather():
        events = original_read()
        for e in events:
            if not is_axis_text(e.get('title', '') + ' ' + e.get('description', '')):
                continue
            try:
                published = datetime.fromisoformat(e.get('published_at_kst') or '')
                if published.tzinfo is None or published < now - timedelta(hours=96) or published > now + timedelta(minutes=10):
                    continue
            except ValueError:
                coverage.append('자료 게시일 미확인: 원문 상태 추출 보류')
                continue
            url = e.get('direct_link', '')
            try:
                if url not in body_cache:
                    raw = legacy.fetch(url, timeout=14).decode('utf-8', errors='replace')
                    body_cache[url] = read_document(raw)
                body, pub = body_cache[url]
                source = dict(e)
                if pub:
                    source['published_at_kst'] = pub
                rows, gaps = parse_records(source, body)
                observed.extend(rows)
                coverage.extend(gaps)
            except Exception as exc:
                coverage.append('원문 확인 실패: ' + host(url) + ' / ' + type(exc).__name__)
        return [e for e in events if original_relevant(e.get('title', '') + ' ' + e.get('description', ''))]
    legacy.read_events = gather
    legacy.main()
    try:
        raw = legacy.fetch('https://www.dramexchange.com/', timeout=14).decode('utf-8', errors='replace')
        quotes = public_spot_quotes(raw, now)
        observed.extend(quotes)
        if not quotes:
            coverage.append('DRAMeXchange 공개 원값·날짜 확인 불가: 회원가격을 추정하지 않음')
        elif all(q['as_of'] < (now - timedelta(days=10)).date().isoformat() for q in quotes):
            coverage.append('공개 현물 원자료 지연: 과거 값을 현재값으로 발송하지 않음')
    except Exception as exc:
        coverage.append('DRAMeXchange 공개 조회 실패: ' + type(exc).__name__)
    paired = sum(r['axis'] == 'rdimm' for r in observed)
    if not paired:
        coverage.append('RDIMM 동일 규격·기준기간의 현물/고정거래 가격 쌍 미확보: 실시간 프리미엄 계산 보류')
    candidate = legacy.load_state()
    if candidate.get('malaysia_public_available') and candidate.get('malaysia_hsk10_amount_usd') is not None:
        month = str(candidate.get('official_month') or '')
        period = month[:4] + '-' + month[4:6] if len(month) == 6 else month
        item = {
            'direct_link': 'https://www.data.go.kr/data/15100475/openapi.do',
            'source': '관세청 공공데이터포털',
            'published_at_kst': now.isoformat(timespec='seconds'),
            'title': '관세청 품목별 국가별 수출입실적 HSK 8542323000 말레이시아',
        }
        record = make_record(
            'malaysia_hsk10_export', ['KR','MY','8542323000'],
            {
                'amount_usd': candidate.get('malaysia_hsk10_amount_usd'),
                'weight_kg': candidate.get('malaysia_hsk10_weight_kg'),
                'weight_kg_previous_yoy': None,
                'yoy_pct': None,
                'taiwan_amount_usd': None,
                'malaysia_vs_taiwan_pct': None,
                'jan_aug_amount_usd': None,
                'weight_rounded_from_public_text': False,
            },
            'USD/kg', period, item, '관세청 국가별 HSK10 직접값',
            as_of=now.date().isoformat(), scope='HBM_included_multichip_IC_not_HBM_only')
        record['evidence'] = 'official'
        observed.append(record)
    state = update_state(initial.get('memory_axes'), observed, now, baseline.get('records', []))
    state['reference_capture'] = baseline.get('user_capture', {})
    state['calculation_cases'] = baseline.get('calculation_cases', [])
    state['coverage'].update({'last_checked_at_kst': now.isoformat(timespec='seconds'),
        'gaps': list(dict.fromkeys(coverage))[-40:], 'observations': len(observed),
        'rdimm_paired_observations': paired, 'non_concrete_generic_evidence_suppressed': len(set(rejected_generic))})
    chosen = list(state['pending'])[:3]
    existing = legacy.ALERT.read_text(encoding='utf-8') if legacy.ALERT.exists() else ''
    if chosen:
        rate, basis = legacy.fx_quote()
        blocks = ['<b>HBM·서버 D램 연계 상태 변화</b>']
        for key in chosen:
            blocks.append(render(state['pending'][key], rate))
            state['last_notified'][key] = state['pending'][key]['record']
            del state['pending'][key]
        if rate:
            blocks.append('환율 기준: ' + html.escape(basis))
        legacy.ALERT.write_text(existing.rstrip() + ('\n\n' if existing else '') + '\n\n'.join(blocks) + '\n', encoding='utf-8')
    candidate['memory_axes'] = state
    candidate['memory_axes_version'] = VERSION
    legacy.save_state(candidate)
    dump(OUT / 'hbm_memory_axes_status.json', {
        'version': VERSION, 'observations': len(observed), 'alerts_prepared': len(chosen),
        'pending_changes': len(state['pending']), 'rdimm_pairs': paired,
        'non_concrete_generic_evidence_suppressed': len(set(rejected_generic)),
        'gaps': state['coverage']['gaps'], 'checked_at_kst': now.isoformat(timespec='seconds')})
    print(f'hbm_memory_axes=true observations={len(observed)} alerts_prepared={len(chosen)}')


if __name__ == '__main__':
    main()
