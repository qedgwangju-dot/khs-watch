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
FOUNDRY_TRACK_VERSION = 1
FOUNDRY_RECOVERY_TRACK_VERSION = 1
FOUNDRY_PRICING_RANGE_TRACK_VERSION = 1
GLASS_SUBSTRATE_TRACK_VERSION = 3
HBM_GENERATION_PRICE_TRACK_VERSION = 1
MARKET_PRICING_TRACK_VERSION = 1
EXTRA_QUERIES = [
    '(HBM4 OR HBM4E) (24Gb OR 32Gb OR 36GB OR 48GB OR 적층 OR 용량)',
    'DDR5 RDIMM (premium OR spot OR contract OR 현물 OR 고정거래)',
    '(HBM OR DDR5) (wafer OR 웨이퍼 OR "glass carrier" OR 글라스 캐리어 OR P5) (allocation OR 비중 OR 세정 OR 가동)',
    '(Malaysia OR 말레이시아) 8542323000 HBM (Intel OR ASE OR "TF-AMD" OR MAPC OR packaging)',
    '(Bernstein OR "J.P. Morgan" OR UBS OR Citi OR "Morgan Stanley") HBM (revenue OR 매출 OR share OR 점유율)',
    '(J.P. Morgan OR JPMorgan OR UBS OR Citi OR "Morgan Stanley" OR BofA OR "Goldman Sachs") Samsung HBM (ASP OR "average selling price" OR 8-Hi OR 12-Hi OR 16-Hi OR 평균판매단가 OR 8단 OR 12단 OR 16단)',
    'TrendForce 2027 HBM (Blended ASP OR 평균판매가격 OR 8-Hi OR 8단 OR per-Gb OR Gb당) (121 OR 10 OR 20)',
    '(TSMC OR ASE) (advanced packaging OR CoWoS OR 후공정) (testing OR tester OR capex OR 설비투자)',
    '(디아이 OR 디지털프론티어 OR 와이씨 OR 엑시콘 OR 인텍플러스 OR 펨트론 OR ISC) HBM (검사 OR 테스트 OR 수주 OR 검증)',
    '(Samsung OR 삼성) HBM4 (base die OR 베이스다이) (4nm OR 4나노) (풀가동 OR 증설 OR 가격 OR capacity)',
    '(Samsung OR 삼성) HBM5 (2nm OR 2나노) (base die OR 베이스다이 OR GAA OR TSV OR 생산라인 OR 투자)',
    '(Samsung OR 삼성) foundry (operating loss OR loss OR 적자 OR 영업손실) (HBM4 OR base die OR 베이스다이 OR 41.8 OR 42)',
    '(Samsung OR 삼성) foundry (2nm OR 2나노) (design win OR HPC OR CSP OR Taylor OR 테일러 OR tapeout OR qualification OR mass production OR 수주 OR 양산)',
    '(Samsung OR 삼성) Taylor foundry (mass production OR production OR 2027 OR customer OR contract OR negotiation)',
    '("510x515" OR "510×515" OR "515x510" OR "515×510") (glass substrate OR glass core OR TGV OR 유리기판 OR 유리 기판) (TSMC OR CoPoS OR Corning OR AGC OR NEG OR SCHOTT)',
    '(TSMC OR CoPoS) (glass core OR glass substrate OR 유리기판) (310x310 OR 510x515 OR 2030 OR pilot OR mass production OR 양산)',
    '(Philoptics OR 필옵틱스 OR JNTC OR 제이앤티씨 OR Absolics OR 앱솔릭스 OR SKC OR GlaSSEM OR 삼성전기 OR "LG Innotek" OR LG이노텍 OR Chemtronics OR 켐트로닉스) (TGV OR glass substrate OR glass interposer OR 유리기판 OR 유리 인터포저) (yield OR 수율 OR sample OR 샘플 OR customer evaluation OR 고객 평가 OR 고객 검증 OR purchase order OR PO OR 양산 OR pilot OR 삼성전자 OR Samsung OR 설비투자 OR 공정시간 OR "12시간" OR "분 단위")',
    '(JNTC OR 제이앤티씨) (TGV OR 유리기판) ("12시간" OR "분 단위" OR 공정시간) (단축 OR 개발)',
    '(JNTC OR 제이앤티씨) (TGV OR 유리기판) (김천 OR Gimcheon) (3470억 OR 10개 OR 설비투자)',
    '(SemiAnalysis OR TrendForce OR Micron OR Citi OR JPMorgan OR "J.P. Morgan" OR BofA) 2027 (HBM3E OR HBM4 OR HBM4E) (price OR pricing OR ASP OR "$/Gb" OR "per Gb" OR 가격)',
    '"HBM3E" "HBM4" "HBM4E" 2027 (price OR ASP OR "$/Gb")',
]
COMPANIES = {'samsung': r'삼성(?:전자)?|Samsung(?: Electronics)?',
             'skhynix': r'SK\s?하이닉스|SK\s*hynix', 'micron': r'마이크론|Micron'}
OFFICIAL = {'news.samsung.com': 'samsung', 'semiconductor.samsung.com': 'samsung',
            'news.skhynix.com': 'skhynix', 'investors.micron.com': 'micron', 'micron.com': 'micron',
            'nvidianews.nvidia.com': 'nvidia', 'developer.nvidia.com': 'nvidia',
            'chemtronics.co.kr': 'chemtronics', 'www.chemtronics.co.kr': 'chemtronics',
            'kind.krx.co.kr': 'krx'}
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
    'semianalysis': (r'SemiAnalysis', r'semianalysis'),
    'micron': (r'\bMicron\b', r'마이크론'),
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
    if h in ('trendforce.com', 'dramexchange.com', 'counterpointresearch.com', 'semianalysis.com', 'newsletter.semianalysis.com'):
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
        r'(?:Bernstein|번스타인|J[.]?P[.]? Morgan|JPMorgan|UBS|Citi|Morgan\s+Stanley|BofA|Goldman\s+Sachs).*HBM|'
        r'(?:삼성|Samsung).*HBM.*(?:ASP|average\s+selling\s+price|평균판매단가|평균\s+판매단가|8[- ]?Hi|12[- ]?Hi|16[- ]?Hi|8단|12단|16단)|'
        r'(?:TrendForce|트렌드포스).*HBM.*(?:Blended\s+ASP|평균판매가격|평균판매단가|8[- ]?Hi|12[- ]?Hi|8단|12단|Gb당|per[- ]?Gb)|'
        r'(?:TSMC|ASE|디아이|디지털\s*프론티어|와이씨|엑시콘|인텍플러스|펨트론|ISC|고영|네오셈|넥스틴).*'
        r'(?:CoWoS|후공정|패키징|검사|테스트|tester|수주|품질\s*검증|정식\s*계약|설비투자|capex)|'
        r'(?:삼성|Samsung).*HBM.*(?:베이스\s*다이|base\s*die|4\s*나노|4nm|2\s*나노|2nm).*'
        r'(?:풀가동|full\s*utilization|증설|expand|가격\s*인상|price\s*increase|생산라인|production\s*line|투자|investment)|'
        r'(?:삼성|Samsung).*(?:파운드리|foundry).*(?:영업\s*손실|영업손실|적자|operating\s*loss|41[.]8\s*%|42\s*%).*(?:HBM4|베이스\s*다이|base\s*die|4nm|4\s*나노)|'
        r'(?:삼성|Samsung).*(?:파운드리|foundry).*(?:2\s*나노|2nm).*(?:design\s*win|HPC|CSP|Taylor|테일러|tapeout|qualification|mass\s*production|수주|양산)|'
        r'(?:삼성|Samsung).*(?:Taylor|테일러).*(?:foundry|파운드리|mass\s*production|양산|customer|contract|수주|negotiation|협상)|'
        r'(?:510\s*[x×]\s*515|515\s*[x×]\s*510).*(?:glass\s*(?:substrate|core|panel)|TGV|유리\s*기판)|'
        r'(?:TSMC|CoPoS).*(?:glass\s*(?:substrate|core)|유리\s*기판).*(?:310\s*[x×]\s*310|510\s*[x×]\s*515|2030|pilot|mass\s*production|양산)|'
        r'(?:Philoptics|필옵틱스|JNTC|Absolics|GlaSSEM|삼성전기|Chemtronics|켐트로닉스).*(?:TGV|glass\s*(?:substrate|core|interposer)|유리\s*(?:기판|인터포저)).*(?:yield|수율|sample|샘플|customer\s*(?:evaluation|validation)|고객\s*(?:평가|검증)|purchase\s*order|\bPO\b|pilot|mass\s*production|양산|검증|Samsung|삼성전자)|'
        r'(?:SemiAnalysis|TrendForce|Micron|Citi|J[.]?P[.]?\s*Morgan|BofA).*(?:2027|27E).*(?:HBM3E|HBM4|HBM4E).*(?:price|pricing|ASP|\$/Gb|per\s+Gb|가격)',
        text, re.I))


def read_document(raw):
    from selectolax.lexbor import LexborHTMLParser as HTMLParser
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


def _trillion_krw(text, patterns):
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return float(m.group(1).replace(',', ''))
    return None


def parse_foundry_recovery_records(item, body):
    text = re.sub(r'\s+', ' ', body or '')
    if not re.search(r'(?:삼성|Samsung)', text, re.I) or not re.search(r'(?:파운드리|foundry)', text, re.I):
        return []
    published = item.get('published_at_kst','')
    asof = published[:10]
    rows = []

    if re.search(r'(?:영업\s*손실|영업손실|operating\s*loss|losses?)', text, re.I):
        loss_2025 = _trillion_krw(text, (
            r'2025[^.]{0,120}?(?:영업\s*손실|영업손실|operating\s*loss|loss)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*(?:조원|trillion\s*won)',
            r'(?:from|지난해|작년)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*(?:조원|trillion\s*won)[^.]{0,100}?(?:2025|to|에서)',
        ))
        loss_2026 = _trillion_krw(text, (
            r'2026[^.]{0,120}?(?:영업\s*손실|영업손실|operating\s*loss|loss)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*(?:조원|trillion\s*won)',
            r'(?:to|올해|금년)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*(?:조원|trillion\s*won)[^.]{0,100}?(?:2026|this\s*year)',
        ))
        pair = re.search(
            r'([0-9]+(?:\.[0-9]+)?)\s*(?:조원|trillion\s*won)[^.]{0,90}?2025[^.]{0,140}?'
            r'([0-9]+(?:\.[0-9]+)?)\s*(?:조원|trillion\s*won)[^.]{0,90}?2026',
            text, re.I)
        if pair:
            if loss_2025 is None:
                loss_2025 = float(pair.group(1))
            if loss_2026 is None:
                loss_2026 = float(pair.group(2))
        shrink = None
        sm = re.search(r'(?:축소|감소|narrow|shrink|reduc)[^%]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%', text, re.I)
        if sm:
            shrink = float(sm.group(1))
        if shrink is None and loss_2025 and loss_2026:
            shrink = (1.0 - loss_2026 / loss_2025) * 100.0

        q3_loss = None
        q3 = re.search(
            r'(?:3Q|Q3|3분기)[^.]{0,120}?(?:손실|loss)[^\d]{0,60}?'
            r'([0-9,]+(?:\.[0-9]+)?)\s*(억원|조원|billion\s*won|trillion\s*won)',
            text, re.I)
        if q3:
            n = float(q3.group(1).replace(',', ''))
            unit = q3.group(2).lower()
            if '억원' in unit:
                q3_loss = n / 10000.0
            elif 'billion' in unit:
                q3_loss = n / 1000.0
            else:
                q3_loss = n

        if loss_2025 is not None or loss_2026 is not None or shrink is not None or q3_loss is not None:
            rec = make_record(
                'foundry_loss_outlook', ['samsung','Foundry_SystemLSI','2026'],
                {'loss_2025_krw_trn': loss_2025, 'loss_2026e_krw_trn': loss_2026,
                 'loss_shrink_pct': shrink, 'q3_2026e_loss_krw_trn': q3_loss},
                'KRW_trillion,pct', '2026', item,
                '삼성 파운드리+System LSI 합산 영업손실 전망',
                as_of=asof, scope='broker_estimate_foundry_plus_system_lsi_combined_not_foundry_standalone')
            if 'trendforce.com/news/' in (item.get('direct_link') or ''):
                rec['evidence'] = 'reported'
            rows.append(rec)

    if re.search(r'(?:2\s*나노|2nm)', text, re.I):
        stage = ''
        if re.search(r'(?:양산\s*(?:시작|개시)|mass\s*production\s*(?:began|started|commenced)|commenced\s*mass\s*production)', text, re.I):
            stage = 'mass_production'
        elif re.search(r'(?:qualification|고객\s*인증|인증\s*완료|검증\s*완료)', text, re.I):
            stage = 'qualification'
        elif re.search(r'(?:tape[- ]?out|테이프아웃)', text, re.I):
            stage = 'tapeout'
        elif re.search(r'(?:design\s*wins?|secured[^.]{0,80}?projects?|수주[^.]{0,60}?(?:확보|증가)|프로젝트[^.]{0,60}?(?:확보|수주))', text, re.I):
            stage = 'design_win'
        elif re.search(r'(?:discussion|negotiation|talks?|협의|논의|협상)', text, re.I):
            stage = 'discussion'
        hpc = True if re.search(r'(?:HPC|고성능\s*컴퓨팅)', text, re.I) else None
        us_orders = True if (
            re.search(r'(?:U[.]?S[.]?|미국)[^.]{0,100}?(?:orders?|수주)[^.]{0,60}?(?:strong|증가|확대|견조)', text, re.I)
            or re.search(r'(?:strong|견조|증가|확대)[^.]{0,60}?(?:orders?|수주)[^.]{0,100}?(?:U[.]?S[.]?|미국)', text, re.I)
        ) else None
        gen2_mobile_plan = True if (
            re.search(r'(?:2nm|2\s*나노)[^.]{0,120}?(?:second[- ]generation|2세대)[^.]{0,100}?(?:mobile|모바일)[^.]{0,100}?(?:ramp|양산|생산)', text, re.I)
            or re.search(r'(?:ramp|양산|생산)[^.]{0,100}?(?:second[- ]generation|2세대)[^.]{0,100}?(?:2nm|2\s*나노)[^.]{0,100}?(?:mobile|모바일)', text, re.I)
        ) else None
        if stage or hpc is not None or us_orders is not None or gen2_mobile_plan is not None:
            rows.append(make_record(
                'foundry_external_2nm', ['samsung','external_2nm','current'],
                {'stage': stage or 'discussion', 'hpc_design_win': hpc,
                 'us_orders_strong': us_orders, 'gen2_mobile_ramp_plan': gen2_mobile_plan},
                'stage,direction', 'current', item,
                '삼성 외부 2나노 AI·HPC 수주·양산 전환 단계',
                as_of=asof, scope='external_2nm_pipeline_design_win_not_revenue_until_mass_production'))

    if re.search(r'(?:Taylor|테일러)', text, re.I):
        mp_year = None
        for pat in (
            r'(?:Taylor|테일러)[^.]{0,180}?(?:mass\s*production|양산)[^.]{0,80}?(20\d{2})',
            r'(20\d{2})[^.]{0,100}?(?:Taylor|테일러)[^.]{0,100}?(?:mass\s*production|양산)',
        ):
            m = re.search(pat, text, re.I)
            if m:
                mp_year = int(m.group(1))
                break
        negotiations = True if re.search(r'(?:major\s+tech|customer|고객)[^.]{0,120}?(?:discussion|negotiation|talks|협의|논의|협상)', text, re.I) else None
        if mp_year is not None or negotiations is not None:
            rows.append(make_record(
                'foundry_taylor_schedule', ['samsung','Taylor_Fab1'],
                {'mass_production_year': mp_year, 'external_customer_negotiations': negotiations},
                'year,direction', 'Taylor_Fab1', item,
                '삼성 Taylor Fab1 양산 일정·외부고객 협상 단계',
                as_of=asof, scope='taylor_schedule_not_customer_2nm_revenue'))

    return rows


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
        full = True if re.search(r'풀가동|풀생산|full\s*(?:utilization|capacity|production)', text, re.I) else None
        if re.search(r'가동률\s*(?:하락|완화)|풀가동\s*(?:해소|종료)|utilization\s*(?:eased|fell|declined)', text, re.I):
            full = False
        if alloc_min is not None or total_wpm is not None or full is not None:
            rows.append(make_record(
                'foundry_base_die_allocation', ['samsung','4nm','HBM4'],
                {'total_capacity_wpm': total_wpm, 'allocation_pct_min': alloc_min,
                 'allocation_pct_max': alloc_max, 'full_utilization': full},
                'wafers/month,pct', 'current', item,
                '삼성 4나노 생산능력 중 HBM4 베이스다이 배정·가동률',
                as_of=asof, scope='reported_foundry_capacity_not_hbm_finished_goods'))

        # 4nm expansion status.
        if re.search(r'증설|생산능력\s*확대|capacity\s*expansion|expand', text, re.I):
            stage = 'mentioned'
            if re.search(r'(?:4\s*나노|4nm)[^.]{0,160}?(?:증설|생산능력\s*확대)[^.]{0,80}?(?:검토|review|consider)', text, re.I) or re.search(r'(?:증설|생산능력\s*확대)[^.]{0,80}?(?:검토|review|consider)[^.]{0,120}?(?:4\s*나노|4nm)', text, re.I):
                stage = 'review'
            elif re.search(r'(?:4\s*나노|4nm)[^.]{0,160}?(?:증설\s*확정|투자\s*확정|approved|confirmed)', text, re.I):
                stage = 'confirmed'
            elif re.search(r'(?:4\s*나노|4nm)[^.]{0,160}?장비\s*발주', text, re.I):
                stage = 'equipment_order'
            elif re.search(r'(?:4\s*나노|4nm)[^.]{0,160}?장비\s*반입', text, re.I):
                stage = 'move_in'
            rows.append(make_record(
                'foundry_node_expansion', ['samsung','4nm','HBM4_base_die'],
                {'stage': stage}, 'stage', 'current', item,
                '삼성 HBM4 베이스다이 대응 4나노 증설 단계',
                as_of=asof, scope='foundry_expansion_stage'))

        # Price increases are a separate state from physical capacity.
        new_order_up = True if re.search(r'(?:4\s*나노|4nm)[^.]{0,100}?(?:신규\s*수주|new\s*orders?)[^.]{0,80}?(?:가격(?:을|이|은|는)?\s*(?:인상|상향)|price\s*(?:increase|hike))', text, re.I) else None
        if re.search(r'(?:4\s*나노|4nm)[^.]{0,100}?(?:신규\s*수주|new\s*orders?)[^.]{0,80}?(?:가격\s*(?:인하|하향)|price\s*(?:cut|decrease))', text, re.I):
            new_order_up = False
        base_die_up = True if re.search(r'(?:베이스\s*다이|base\s*die)[^.]{0,80}?(?:가격\s*(?:인상|상향)|가격[^.]{0,20}?(?:올린|올렸다)|price\s*(?:increase|hike))', text, re.I) else None
        if re.search(r'(?:베이스\s*다이|base\s*die)[^.]{0,80}?(?:가격\s*(?:인하|하향)|price\s*(?:cut|decrease))', text, re.I):
            base_die_up = False
        pct = None
        pct_min = pct_max = None
        prm = re.search(r'(?:가격[^.]{0,30}?(?:인상|상승)|price[^.]{0,30}?(?:increase|hike|rose))[^%]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*(?:~|[-–—]|to)\s*([0-9]+(?:\.[0-9]+)?)\s*%', text, re.I)
        if prm:
            pct_min, pct_max = float(prm[1]), float(prm[2])
        else:
            pm = re.search(r'(?:가격\s*인상|price\s*(?:increase|hike))[^%]{0,30}?([0-9]+(?:\.[0-9]+)?)\s*%', text, re.I)
            if pm:
                pct = float(pm[1])
        if new_order_up or base_die_up or pct is not None or pct_min is not None:
            rows.append(make_record(
                'foundry_pricing', ['samsung','4nm','HBM4_base_die'],
                {'new_order_price_up': new_order_up, 'base_die_price_up': base_die_up,
                 'price_change_pct': pct, 'price_change_pct_min': pct_min, 'price_change_pct_max': pct_max},
                'direction,pct', 'current', item,
                '삼성 4나노 신규수주·HBM4 베이스다이 가격 변화',
                as_of=asof, scope='reported_foundry_pricing'))

    # HBM5: distinguish the technology plan from a real 2nm production-line investment stage.
    if re.search(r'HBM5', text, re.I) and re.search(r'(?:2\s*나노|2nm)', text, re.I):
        investment_stage = ''
        if re.search(r'신규\s*생산라인|생산라인\s*(?:구축|투자)|new\s*production\s*line|new\s*line', text, re.I):
            investment_stage = 'mentioned'
            if re.search(r'(?:HBM5|2\s*나노|2nm)[^.]{0,180}?(?:신규\s*생산라인|생산라인)[^.]{0,80}?(?:검토|review|consider)', text, re.I) or re.search(r'(?:신규\s*생산라인|생산라인)[^.]{0,80}?(?:검토|review|consider)[^.]{0,120}?(?:HBM5|2\s*나노|2nm)', text, re.I):
                investment_stage = 'review'
            elif re.search(r'(?:HBM5|2\s*나노|2nm)[^.]{0,180}?(?:신규\s*생산라인|생산라인)[^.]{0,80}?(?:확정|approved|confirmed)', text, re.I):
                investment_stage = 'confirmed'
            elif re.search(r'(?:HBM5|2\s*나노|2nm)[^.]{0,180}?장비\s*발주', text, re.I):
                investment_stage = 'equipment_order'
            elif re.search(r'(?:HBM5|2\s*나노|2nm)[^.]{0,180}?장비\s*반입', text, re.I):
                investment_stage = 'move_in'
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
                 'gaa': True if re.search(r'GAA|게이트올어라운드', text, re.I) else None,
                 'tsv_density_up': True if re.search(r'TSV|실리콘\s*관통\s*전극', text, re.I) else None},
                'stage,pct', 'HBM5', item,
                '삼성 HBM5 2나노 베이스다이 기술·투자 단계',
                as_of=asof, scope='technology_plan_and_line_investment_separated'))

    return rows


def hbm_stack_revenue_break_even(old_layers=12, new_layers=8, premium_min_pct=0.0, premium_max_pct=0.0):
    if min(old_layers, new_layers) <= 0:
        raise ValueError("stack layers must be positive")
    if premium_min_pct < -100 or premium_max_pct < -100 or premium_min_pct > premium_max_pct:
        raise ValueError("invalid premium range")
    bit_ratio = float(new_layers) / float(old_layers)
    low_revenue_ratio = bit_ratio * (1.0 + float(premium_min_pct) / 100.0)
    high_revenue_ratio = bit_ratio * (1.0 + float(premium_max_pct) / 100.0)
    if min(low_revenue_ratio, high_revenue_ratio) <= 0:
        raise ValueError("invalid revenue ratio")
    return {
        "stack_bit_change_pct": (bit_ratio - 1.0) * 100.0,
        "gpu_growth_break_even_min_pct": (1.0 / high_revenue_ratio - 1.0) * 100.0,
        "gpu_growth_break_even_max_pct": (1.0 / low_revenue_ratio - 1.0) * 100.0,
    }


def parse_hbm_market_pricing(item, body):
    text = re.sub(r"\s+", " ", f"{item.get('title','')} {item.get('description','')} {body or ''}").strip()
    low = text.lower()
    if "hbm" not in low or "2027" not in text:
        return []
    if "trendforce" not in low and "트렌드포스" not in text:
        return []

    blended = None
    for pat in (
        r"(?:Blended\s+ASP|평균판매가격|평균판매단가|혼합\s*ASP)[^%]{0,140}?(?:전년\s*대비\s*)?(?:\+|상승\s*)?([0-9]{2,3}(?:\.[0-9]+)?)\s*%",
        r"2027[^.]{0,180}?HBM[^.]{0,180}?(?:Blended\s+ASP|평균판매가격|평균판매단가)[^%]{0,100}?([0-9]{2,3}(?:\.[0-9]+)?)\s*%",
    ):
        m = re.search(pat, text, re.I)
        if m:
            blended = float(m.group(1))
            break

    pmin = pmax = None
    for pat in (
        r"8\s*(?:단|[- ]?Hi)[^.]{0,160}?12\s*(?:단|[- ]?Hi)[^.]{0,160}?([0-9]{1,2}(?:\.[0-9]+)?)\s*(?:~|∼|[-–—]|to)\s*([0-9]{1,2}(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:높|premium|비싸)",
        r"8\s*(?:단|[- ]?Hi)[^.]{0,160}?(?:Gb당|per[- ]?Gb)[^.]{0,100}?([0-9]{1,2}(?:\.[0-9]+)?)\s*(?:~|∼|[-–—]|to)\s*([0-9]{1,2}(?:\.[0-9]+)?)\s*%",
    ):
        m = re.search(pat, text, re.I)
        if m:
            pmin, pmax = float(m.group(1)), float(m.group(2))
            break

    mainstream = None
    if re.search(r"8\s*(?:단|[- ]?Hi)[^.]{0,150}?(?:주류|우선\s*적용|lead(?:s|ing)?\s+shipments|mainstream|비중도\s*확대)", text, re.I):
        mainstream = 8
    elif re.search(r"12\s*(?:단|[- ]?Hi)[^.]{0,150}?(?:주류|우선\s*적용|lead(?:s|ing)?\s+shipments|mainstream)", text, re.I):
        mainstream = 12

    if blended is None and pmin is None and mainstream is None:
        return []

    value = {
        "blended_asp_yoy_pct": blended,
        "eight_hi_premium_min_pct": pmin,
        "eight_hi_premium_max_pct": pmax,
        "mainstream_layers": mainstream,
        "reference_layers": 12 if mainstream == 8 or pmin is not None else None,
    }
    if pmin is not None and pmax is not None:
        value.update(hbm_stack_revenue_break_even(12, 8, pmin, pmax))

    record = make_record(
        "hbm_market_pricing",
        ["trendforce", "industry", "2027"],
        value,
        "pct",
        "2027",
        item,
        text,
        scope="market_blended_asp_and_stack_mix_not_company_specific",
        research_reference_url="https://www.trendforce.com/research/download/RP260922FJ3",
    )
    return [record]


HBM_GENERATIONS = ("HBM2E", "HBM3", "HBM3E", "HBM4", "HBM4E")


def _generation_price_source(text, item):
    combined = " ".join((item.get('source',''), item.get('title',''), item.get('direct_link',''), text[:800]))
    inst = _institution(combined)
    if inst:
        return inst
    h = host(item.get('direct_link',''))
    if 'semianalysis' in h:
        return 'semianalysis'
    if 'micron' in h:
        return 'micron'
    if 'trendforce' in h:
        return 'trendforce'
    return re.sub(r'[^a-z0-9]+', '_', h.split('.')[0].lower()).strip('_') or 'unknown'


def _generation_price_points(text):
    out = {}
    for gen in HBM_GENERATIONS:
        gen_pat = re.escape(gen)
        # Keep stack height in the key when stated. 8-Hi and 12-Hi prices are not interchangeable.
        patterns = (
            rf'\b{gen_pat}\b[^.\n]{{0,100}}?(?:(8|12|16|20)\s*[- ]?(?:Hi|단)[^.\n]{{0,60}}?)?(?:US\$|\$)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:US\$\s*/\s*Gb|\$\s*/\s*Gb|/\s*Gb|per\s+Gb)',
            rf'(?:US\$|\$)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:US\$\s*/\s*Gb|\$\s*/\s*Gb|/\s*Gb|per\s+Gb)[^.\n]{{0,100}}?\b{gen_pat}\b(?:[^.\n]{{0,50}}?(8|12|16|20)\s*[- ]?(?:Hi|단))?',
        )
        m = re.search(patterns[0], text, re.I)
        if m:
            layer, price = m.group(1), float(m.group(2))
        else:
            m = re.search(patterns[1], text, re.I)
            if not m:
                continue
            price, layer = float(m.group(1)), m.group(2)
        if not (0.1 <= float(price) <= 20):
            continue
        key = gen + (f'_{int(layer)}Hi' if layer else '_stack_unspecified')
        out[key] = float(price)
    return out


def parse_hbm_generation_pricing(item, body):
    text = re.sub(r'\s+', ' ', f"{item.get('title','')} {item.get('description','')} {body or ''}").strip()
    low = text.lower()
    if 'hbm' not in low or not re.search(r'\b2027\b|\b27E\b', text, re.I):
        return []
    if not re.search(r'HBM(?:2E|3|3E|4|4E)', text, re.I):
        return []

    source = _generation_price_source(text, item)
    if source == 'unknown':
        return []

    points = _generation_price_points(text)
    explicit_breadth = (
        source == 'semianalysis'
        and bool(re.search(
            r'(?:every|all|across|multiple)[^.]{0,50}?HBM[^.]{0,80}?(?:generation|세대)[^.]{0,80}?(?:rise|step(?:s|ped)?\s+up|increase|reset|상승|인상|리셋)'
            r'|(?:HBM[^.]{0,50}?(?:전\s*세대|모든\s*세대))[^.]{0,80}?(?:상승|인상|리셋)',
            text, re.I
        ))
    )
    mentioned = [g for g in HBM_GENERATIONS if re.search(rf'\b{re.escape(g)}\b', text, re.I)]
    broad = explicit_breadth or len(points) >= 3
    legacy = any(k.startswith('HBM3_') or k.startswith('HBM3E_') for k in points)
    if not points and not explicit_breadth:
        return []

    value = {
        'broad_step_up_2027': broad,
        'generation_count': len({k.split('_')[0] for k in points}) if points else len(mentioned),
        'generations_mentioned': mentioned,
        'legacy_generation_price_visible': legacy,
        'price_usd_per_gb': points,
        'exact_numeric_public_text': bool(points),
    }
    return [make_record(
        'hbm_generation_pricing', [source, '2027'], value, 'USD/Gb,stage', '2027',
        item, text,
        scope='institution_specific_generation_curve_stack_height_preserved_not_blended_asp'
    )]


GLASS_TSMC_STATUS_RANK = {
    'unconfirmed': 0,
    'reported_candidate': 1,
    'official_evaluation': 2,
    'official_adopted': 3,
}
GLASS_HVM_STAGE_RANK = {
    'sample': 0,
    'customer_evaluation': 1,
    'po_pending': 2,
    'po_signed': 3,
    'pilot': 4,
    'mass_production': 5,
}


def _glass_entity(text):
    pairs = (
        ('philoptics', (r'Philoptics', r'필옵틱스')),
        ('jntc', (r'\bJNTC\b', r'제이앤티씨')),
        ('absolics', (r'Absolics', r'앱솔릭스', r'\bSKC\b')),
        ('glassem', (r'GlaSSEM', r'글라스셈')),
        ('samsung_electromechanics', (r'Samsung\s+Electro[- ]?Mechanics', r'삼성전기')),
        ('lg_innotek', (r'LG\s*Innotek', r'LG이노텍')),
        ('chemtronics', (r'Chemtronics', r'켐트로닉스')),
    )
    found = [name for name, pats in pairs if any(re.search(p, text, re.I) for p in pats)]
    return found[0] if len(found) == 1 else ''


def parse_glass_substrate_records(item, body):
    text = re.sub(r'\s+', ' ', body or '')
    low = text.lower()
    if not re.search(r'glass\s*(?:substrate|core|panel|interposer)|through[- ]?glass\s+via|\bTGV\b|유리\s*(?:기판|인터포저)|글라스\s*코어', text, re.I):
        return []
    asof = (item.get('published_at_kst') or '')[:10]
    rows = []

    # Industry convergence: only emit when multiple suppliers are named together,
    # so a single supplier product page cannot accidentally downgrade the count.
    if re.search(r'(?:510\s*[x×]\s*515|515\s*[x×]\s*510)', text, re.I):
        supplier_patterns = {
            'Corning': (r'Corning', r'코닝'),
            'AGC': (r'\bAGC\b',),
            'NEG': (r'Nippon\s+Electric\s+Glass', r'\bNEG\b', r'일본전기초자', r'일본전기유리'),
            'SCHOTT': (r'\bSCHOTT\b', r'쇼트'),
        }
        suppliers = [name for name, pats in supplier_patterns.items() if any(re.search(p, text, re.I) for p in pats)]
        if len(suppliers) >= 3:
            status = 'unconfirmed'
            if re.search(r'(?:TSMC)[^.]{0,180}?(?:officially\s+(?:adopt|standard)|confirmed[^.]{0,50}?(?:510|515)|공식[^.]{0,60}?(?:채택|확정))', text, re.I):
                status = 'official_adopted'
            elif re.search(r'(?:TSMC)[^.]{0,180}?(?:evaluate|evaluation|검토|평가)', text, re.I):
                status = 'official_evaluation' if host(item.get('direct_link','')).endswith('tsmc.com') else 'reported_candidate'
            elif re.search(r'(?:TSMC|CoPoS)', text, re.I):
                status = 'reported_candidate'
            rows.append(make_record(
                'glass_panel_standard', ['industry','510x515'],
                {'width_mm':510, 'height_mm':515, 'supplier_count':len(suppliers),
                 'suppliers':sorted(suppliers), 'tsmc_status':status},
                'mm,count,stage', 'current', item,
                '510×515mm 유리기판·TGV 생태계 규격 수렴',
                as_of=asof, scope='industry_convergence_not_tsmc_official_standard'))

    # TSMC's current public CoPoS roadmap stays separate from the post-2030
    # 510x515 glass-core inference.
    if re.search(r'\bTSMC\b', text, re.I) and re.search(r'CoPoS', text, re.I):
        panel = re.search(r'(310)\s*[x×]\s*(310)', text, re.I)
        validation = (
            re.search(r'(2026)[^.]{0,80}?(?:validation|검증)', text, re.I)
            or re.search(r'(?:validation|검증)[^.]{0,80}?(2026)', text, re.I)
        )
        pilot = (
            re.search(r'(2027)[^.]{0,80}?(?:pilot|시험\s*생산|파일럿)', text, re.I)
            or re.search(r'(?:pilot|시험\s*생산|파일럿)[^.]{0,80}?(2027)', text, re.I)
        )
        mass = (
            re.search(r'(2028)[^.]{0,100}?(?:mass\s*production|양산)', text, re.I)
            or re.search(r'(?:mass\s*production|양산)[^.]{0,100}?(2028)', text, re.I)
        )
        post2030 = bool(re.search(r'(?:after|post)[ -]?2030|2030\s*년\s*이후', text, re.I))
        if panel or validation or pilot or mass or post2030:
            rows.append(make_record(
                'glass_tsmc_roadmap', ['tsmc','CoPoS_GlassCore'],
                {'copos_width_mm':310 if panel else None,
                 'copos_height_mm':310 if panel else None,
                 'validation_year':2026 if validation else None,
                 'pilot_year':2027 if pilot else None,
                 'mass_production_year':2028 if mass else None,
                 'mass_production_half':'H2' if mass and re.search(r'(?:second\s+half|H2|하반기)[^.]{0,100}?(?:2028|mass\s*production|양산)|2028[^.]{0,100}?(?:second\s+half|H2|하반기)', text, re.I) else None,
                 'glass_core_commercial_after_year':2030 if post2030 else None},
                'mm,year,stage', 'roadmap', item,
                'TSMC CoPoS 현재 패널 규격과 Glass Core 상용화 로드맵',
                as_of=asof, scope='trendforce_roadmap_current_copos_310_not_510x515_confirmation'))

    entity = _glass_entity(text)
    if entity:
        # Whole-panel or explicitly labeled mass-production yield only.
        ym = re.search(r'(?:mass\s*production\s*yield|panel\s*yield|electrical\s*yield|양산\s*수율|패널\s*수율|전기\s*수율)[^%]{0,80}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%', text, re.I)
        if not ym:
            ym = re.search(r'([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:mass\s*production\s*yield|panel\s*yield|electrical\s*yield|양산\s*수율|패널\s*수율|전기\s*수율)', text, re.I)
        if ym:
            rows.append(make_record(
                'glass_panel_yield', [entity,'current'],
                {'yield_pct':float(ym.group(1))},
                'pct', 'current', item,
                '유리기판 패널·양산 수율',
                as_of=asof, scope='reported_panel_or_mass_production_yield_not_tgv_hole_ppm'))

        stage = ''
        if re.search(r'(?:mass\s*production\s*(?:begins?|starts?|commences?)|양산\s*(?:시작|개시))', text, re.I):
            stage = 'mass_production'
        elif re.search(r'(?:pilot\s*(?:production|line)|파일럿\s*(?:생산|라인)|시험\s*생산)', text, re.I):
            stage = 'pilot'
        elif re.search(r'(?:purchase\s*order|PO\s*(?:signed|received)|정식\s*수주|발주\s*확정|수주\s*확정)', text, re.I):
            stage = 'po_signed'
        elif re.search(r'(?:pending\s*(?:purchase\s*)?order|final\s+purchase[- ]?order\s+process|본계약\s*대기|발주\s*대기|수주\s*대기)', text, re.I):
            stage = 'po_pending'
        elif re.search(
            r'(?:customer\s*(?:validation|evaluation)|reliability\s*(?:evaluation|test)|고객\s*(?:검증|평가)|신뢰성\s*평가|'
            r'샘플[^.]{0,80}?(?:평가가?\s*(?:이어|진행|계속|중)|평가\s*중)|'
            r'sample[^.]{0,80}?(?:evaluation|validation)[^.]{0,40}?(?:ongoing|underway|continues?))',
            text, re.I
        ):
            stage = 'customer_evaluation'
        elif re.search(r'(?:sample\s*(?:supply|shipment|delivery)|샘플\s*(?:공급|출하|납품|전달)|샘플[^.]{0,30}?(?:공급|출하|납품|전달))', text, re.I):
            stage = 'sample'
        target_year = None
        tm = re.search(r'(?:mass\s*production|양산)[^.]{0,80}?(20\d{2})|(20\d{2})[^.]{0,80}?(?:mass\s*production|양산)', text, re.I)
        if tm:
            target_year = int(tm.group(1) or tm.group(2))
        if stage or target_year:
            value = {'stage':stage or 'customer_evaluation','mass_production_target_year':target_year}
            scope = 'stage_transition_customer_evaluation_to_hvm'
            if entity == 'jntc':
                m_pilot = re.search(r'(?:파일럿\s*라인|pilot\s*line)[^0-9]{0,25}(\d+)\s*(?:개|line)', text, re.I)
                m_cap = re.search(r'(?:월|monthly)[^0-9]{0,25}(1\s*만|10,?000)\s*[~～-]\s*(1\s*만\s*(?:2\s*천|2000)|12,?000)\s*(?:개|units?)', text, re.I)
                m_nda = re.search(r'(?:NDA|비밀유지계약)[^0-9]{0,20}(\d+)\s*곳|(\d+)\s*곳(?:과|와)?[^.]{0,20}(?:NDA|비밀유지계약)', text, re.I)
                m_end = re.search(r'(?:최종\s*수요기업|end\s*customers?)[^0-9]{0,30}(\d+)\s*곳', text, re.I)
                m_paid = re.search(r'(?:유상\s*샘플|paid\s*samples?)[^0-9]{0,35}(?:전환한\s*고객사도\s*)?(\d+)\s*곳', text, re.I)
                value.update({
                    'pilot_line_count': int(m_pilot.group(1)) if m_pilot else None,
                    'pilot_capacity_units_per_month_min': 10000 if m_cap else None,
                    'pilot_capacity_units_per_month_max': 12000 if m_cap else None,
                    'nda_customer_count': int(m_nda.group(1) or m_nda.group(2)) if m_nda else None,
                    'end_customer_count': int(m_end.group(1)) if m_end else None,
                    'paid_sample_customer_count': int(m_paid.group(1)) if m_paid else None,
                    'target_product_thickness_mm': 2 if re.search(r'2027[^.]{0,80}?2\s*mm|2\s*mm[^.]{0,80}?2027', text, re.I) else None,
                    'next_product_thickness_mm': 3 if re.search(r'3\s*mm[^.]{0,80}?(?:개발|develop)', text, re.I) else None,
                    'gimcheon_groundbreaking_period': '2027H2' if re.search(r'2027\s*년?\s*하반기[^.]{0,40}?착공|착공[^.]{0,40}?2027\s*년?\s*하반기', text, re.I) else None,
                    'initial_line_count_min': 2 if re.search(r'2\s*[~～-]\s*3\s*개\s*(?:생산)?라인', text, re.I) else None,
                    'initial_line_count_max': 3 if re.search(r'2\s*[~～-]\s*3\s*개\s*(?:생산)?라인', text, re.I) else None,
                    'initial_customer_commercialization_period': '2028_mid' if re.search(r'2028\s*년?\s*(?:중반|중)', text, re.I) else None,
                    'mass_ramp_line_count_min': 10 if re.search(r'10\s*개\s*이상[^.]{0,40}?(?:라인|확대)|(?:라인|확대)[^.]{0,40}?10\s*개\s*이상', text, re.I) else None,
                })
                scope = 'jntc_customer_evaluation_paid_samples_pilot_and_gimcheon_ramp'
            if entity == 'absolics':
                value.update({
                    'embedding_preliminary_evaluation_passed': bool(re.search(r'preliminary\s+evaluations?[^.]{0,40}?(?:completed|passed)|예비\s*평가[^.]{0,40}?(?:완료|통과)', text, re.I)),
                    'embedding_reliability_evaluation_ongoing': bool(re.search(r'reliability\s*(?:evaluation|test)|신뢰성\s*평가', text, re.I)),
                    'non_embedding_supplier_selection_ongoing': bool(re.search(r'non[- ]?embedding[^.]{0,120}?(?:supplier\s*selection|공급사\s*선정)', text, re.I)),
                    'non_embedding_poc_target_year': 2026 if re.search(r'non[- ]?embedding[^.]{0,160}?(?:PoC|proof\s+of\s+concept)[^.]{0,60}?(?:within\s+the\s+year|연내)', text, re.I) else None,
                })
                scope = 'absolics_customer_validation_not_mass_production'
            if entity == 'chemtronics' and re.search(r'(?:삼성전자|Samsung(?: Electronics)?)', text, re.I):
                value.update({
                    'customer': 'Samsung Electronics',
                    'product': 'glass_interposer',
                    'sample_delivered': bool(re.search(r'(?:샘플)[^.]{0,40}?(?:납품|공급|전달)|(?:sample)[^.]{0,50}?(?:delivered|supplied|shipped)', text, re.I)),
                    'evaluation_ongoing': bool(re.search(r'(?:평가|검증)[^.]{0,40}?(?:이어|진행|계속)|(?:evaluation|validation)[^.]{0,50}?(?:ongoing|continues?|underway)', text, re.I)),
                    'issue_response_ongoing': bool(re.search(r'(?:이슈|문제)[^.]{0,50}?(?:대응|보완)|(?:issue|problem)[^.]{0,50}?(?:address|remediat|respond|fix)', text, re.I)),
                    'sample_process': 'existing_method' if re.search(r'(?:기존\s*방식|existing\s+(?:method|process))', text, re.I) else None,
                    'new_metal_fill_stage': 'development' if re.search(r'(?:새롭게|신규|new)[^.]{0,80}?(?:금속\s*충진|metal\s*fill)', text, re.I) else None,
                    'new_metal_fill_sample_delivered': False if re.search(r'(?:새롭게|신규|new)[^.]{0,100}?(?:금속\s*충진|metal\s*fill)[^.]{0,120}?(?:샘플)[^.]{0,60}?(?:나가지는\s*않|미공급|아직\s*.*않)|(?:new)[^.]{0,100}?(?:metal\s*fill)[^.]{0,120}?(?:sample)[^.]{0,60}?(?:not\s+(?:yet\s+)?(?:delivered|shipped|supplied))', text, re.I) else None,
                    'mass_production_supply_confirmed': bool(re.search(r'(?:양산\s*(?:공급|계약)\s*(?:확정|체결)|mass\s*production\s+supply\s+(?:confirmed|contracted))', text, re.I)),
                })
                scope = 'chemtronics_samsung_glass_interposer_reported_customer_evaluation_not_mass_production'
            rows.append(make_record(
                'glass_hvm_stage', [entity,'current'],
                value,
                'stage,year', 'current', item,
                '유리기판·유리 인터포저 고객검증·장비발주·파일럿·양산 단계',
                as_of=asof, scope=scope))

        if entity == 'jntc' and re.search(r'12\s*시간|12\s*hours?|720\s*분|분\s*단위|cycle\s*time|공정\s*시간', text, re.I):
            cycle_sentences = [
                x for x in re.split(r'[.!?。]\s*', text)
                if re.search(r'12\s*시간|12\s*hours?|720\s*분|분\s*단위|cycle\s*time|공정\s*시간', x, re.I)
            ]
            cycle_text = ' '.join(cycle_sentences) or text
            before_minutes = 720 if re.search(r'12\s*시간|12\s*hours?', cycle_text, re.I) else None
            after_minutes = None
            after_class = None
            m_after = re.search(
                r'(?:단축|shorten|reduce|현재|개선)[^0-9]{0,60}([0-9]+(?:\.[0-9]+)?)\s*(?:분|minutes?)',
                cycle_text, re.I)
            if not m_after:
                m_after = re.search(
                    r'([0-9]+(?:\.[0-9]+)?)\s*(?:분|minutes?)[^.]{0,60}?(?:단축|shorten|reduce|소요|걸리)',
                    cycle_text, re.I)
            if m_after:
                after_minutes = float(m_after.group(1))
                after_class = 'exact_minutes'
            elif re.search(r'분\s*단위|minute[- ]?scale|within\s+minutes', cycle_text, re.I):
                after_class = 'minute_scale'
            process_name = 'unverified_core_process'
            if re.search(r'metalliz|plating|도금|금속화', cycle_text, re.I):
                process_name = 'metallization'
            elif re.search(r'etch|식각', cycle_text, re.I):
                process_name = 'etching'
            elif re.search(r'laser|레이저|홀\s*가공|via\s*drill', cycle_text, re.I):
                process_name = 'via_formation'
            rows.append(make_record(
                'glass_process_cycle_time', ['jntc','current'],
                {'process_name':process_name, 'before_minutes':before_minutes,
                 'after_minutes_exact':after_minutes, 'after_time_class':after_class,
                 'body_direct_verified':bool(process_name != 'unverified_core_process' and (after_minutes is not None or after_class))},
                'minutes,stage', 'current', item,
                '제이앤티씨 TGV 유리기판 핵심공정 시간 단축',
                as_of=asof, scope='cycle_time_exact_after_minutes_required_for_speedup_math'))

        if entity == 'jntc' and re.search(r'김천|Gimcheon', text, re.I) and re.search(r'TGV|유리\s*기판|glass\s*substrate', text, re.I):
            capex = 347_000_000_000 if re.search(r'3\s*,?470\s*억\s*원|3470\s*억\s*원', text, re.I) else None
            initial_pair = bool(re.search(r'2\s*[~～-]\s*3\s*개\s*(?:생산)?라인', text, re.I))
            start_year = 2027 if re.search(r'2027', text) else None
            end_year = 2030 if re.search(r'2030', text) else None
            employees = 430 if re.search(r'430\s*(?:명|여명|people|employees?)', text, re.I) else None
            area_pyeong = 30000 if re.search(r'3\s*만\s*평|30,?000\s*(?:평|pyeong)', text, re.I) else None
            groundbreaking = '2027H2' if re.search(r'2027\s*년?\s*하반기[^.]{0,40}?착공|착공[^.]{0,40}?2027\s*년?\s*하반기', text, re.I) else None
            commercialization = '2028_mid' if re.search(r'2028\s*년?\s*(?:중반|중)[^.]{0,80}?(?:상용화|물량)', text, re.I) else None
            mass_lines = 10 if re.search(r'10\s*개\s*이상[^.]{0,50}?(?:라인|확대)|(?:라인|확대)[^.]{0,50}?10\s*개\s*이상', text, re.I) else None
            values = (capex, start_year, end_year, employees, area_pyeong, groundbreaking, commercialization, mass_lines)
            if initial_pair or any(x is not None for x in values):
                rows.append(make_record(
                    'glass_capex', ['jntc','gimcheon'],
                    {'investment_krw':capex,
                     'line_count_min_initial':2 if initial_pair else None,
                     'line_count_max_initial':3 if initial_pair else None,
                     'line_count_mass_ramp_min':mass_lines,
                     'start_year':start_year, 'end_year':end_year,
                     'groundbreaking_period':groundbreaking,
                     'initial_customer_commercialization_period':commercialization,
                     'employees':employees, 'site_area_pyeong':area_pyeong,
                     'capacity_panels_per_month':None, 'stage':'reported_investment'},
                    'KRW,count,year', '2027-2030', item,
                    '제이앤티씨 김천 TGV 유리기판 설비투자',
                    as_of=asof, scope='capex_line_ramp_not_physical_output_capacity'))

    return rows


def parse_records(item, body):
    records, gaps = [], []
    published = item.get('published_at_kst', '')
    malaysia = _malaysia_export_record(item, body)
    if malaysia:
        records.append(malaysia)
    records.extend(parse_hbm_revenue_estimates(item, body))
    records.extend(parse_hbm_market_pricing(item, body))
    records.extend(parse_hbm_generation_pricing(item, body))
    records.extend(parse_postprocess_records(item, body))
    records.extend(parse_foundry_recovery_records(item, body))
    records.extend(parse_foundry_hbm_records(item, body))
    records.extend(parse_glass_substrate_records(item, body))
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
    from selectolax.lexbor import LexborHTMLParser as HTMLParser
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
    if new['axis'] == 'hbm_market_pricing':
        reasons = []
        av, bv = a.get('blended_asp_yoy_pct'), b.get('blended_asp_yoy_pct')
        if av is not None and bv is not None and abs(float(bv) - float(av)) >= 10:
            reasons.append(f"시장 Blended ASP 전망 {float(av):+.0f}%→{float(bv):+.0f}% YoY ({float(bv)-float(av):+.0f}%p)")
        elif av is None and bv is not None:
            reasons.append(f"시장 Blended ASP 전망 {float(bv):+.0f}% YoY 신규 확인")
        for field, label in (
            ('eight_hi_premium_min_pct','8단 Gb당 프리미엄 하단'),
            ('eight_hi_premium_max_pct','8단 Gb당 프리미엄 상단'),
        ):
            av, bv = a.get(field), b.get(field)
            if av is not None and bv is not None and abs(float(bv) - float(av)) >= 5:
                reasons.append(f"{label} {float(av):.0f}%→{float(bv):.0f}%")
            elif av is None and bv is not None:
                reasons.append(f"{label} {float(bv):.0f}% 신규 확인")
        av, bv = a.get('mainstream_layers'), b.get('mainstream_layers')
        if av is not None and bv is not None and int(av) != int(bv):
            reasons.append(f"시장 주류 적층 {int(av)}단→{int(bv)}단")
        elif av is None and bv is not None:
            reasons.append(f"시장 주류 적층 {int(bv)}단 신규 확인")
        return reasons
    if new['axis'] == 'hbm_generation_pricing':
        reasons = []
        amap, bmap = a.get('price_usd_per_gb') or {}, b.get('price_usd_per_gb') or {}
        for key in sorted(set(amap) | set(bmap)):
            av, bv = amap.get(key), bmap.get(key)
            if av is not None and bv is not None:
                pct = (float(bv) / float(av) - 1.0) * 100 if float(av) else 0
                if abs(float(bv)-float(av)) >= 0.20 or abs(pct) >= 10:
                    reasons.append(f"{key} {float(av):.2f}→{float(bv):.2f}달러/Gb ({pct:+.1f}%)")
            elif av is None and bv is not None:
                reasons.append(f"{key} {float(bv):.2f}달러/Gb 신규 확인")
        if a.get('broad_step_up_2027') != b.get('broad_step_up_2027') and b.get('broad_step_up_2027') is not None:
            reasons.append('2027 전 세대 동반 가격상승 신호 ' + ('확인' if b.get('broad_step_up_2027') else '해제'))
        if a.get('legacy_generation_price_visible') != b.get('legacy_generation_price_visible') and b.get('legacy_generation_price_visible'):
            reasons.append('HBM3/HBM3E 구세대 가격상승 숫자 확인')
        av, bv = a.get('generation_count'), b.get('generation_count')
        if av is not None and bv is not None and int(av) != int(bv):
            reasons.append(f"가격 곡선 확인 세대 수 {int(av)}→{int(bv)}개")
        return reasons
    if new['axis'] == 'glass_panel_standard':
        reasons = []
        if (a.get('width_mm'), a.get('height_mm')) != (b.get('width_mm'), b.get('height_mm')):
            reasons.append(f"패널 규격 {a.get('width_mm')}×{a.get('height_mm')}→{b.get('width_mm')}×{b.get('height_mm')}mm")
        av, bv = a.get('supplier_count'), b.get('supplier_count')
        if av is not None and bv is not None and int(av) != int(bv):
            reasons.append(f"510×515mm 수렴 소재사 {int(av)}→{int(bv)}곳")
        old_status, new_status = a.get('tsmc_status','unconfirmed'), b.get('tsmc_status','unconfirmed')
        if old_status != new_status:
            reasons.append(f"TSMC 510×515 상태 {old_status}→{new_status}")
        return reasons
    if new['axis'] == 'glass_tsmc_roadmap':
        reasons = []
        for field, label in (
            ('validation_year','CoPoS 장비·소재 검증'),
            ('pilot_year','CoPoS 시험생산'),
            ('mass_production_year','CoPoS 양산'),
            ('glass_core_commercial_after_year','Glass Core 상업규모 기준'),
        ):
            av, bv = a.get(field), b.get(field)
            if av is not None and bv is not None and int(av) != int(bv):
                reasons.append(f"{label} {int(av)}→{int(bv)}년")
            elif av is None and bv is not None:
                reasons.append(f"{label} {int(bv)}년 신규 확인")
        if (a.get('copos_width_mm'),a.get('copos_height_mm')) != (b.get('copos_width_mm'),b.get('copos_height_mm')):
            reasons.append(f"CoPoS 패널 규격 {a.get('copos_width_mm')}×{a.get('copos_height_mm')}→{b.get('copos_width_mm')}×{b.get('copos_height_mm')}mm")
        return reasons
    if new['axis'] == 'glass_panel_yield':
        av, bv = a.get('yield_pct'), b.get('yield_pct')
        if av is None or bv is None:
            return [f"패널·양산 수율 {float(bv):.1f}% 신규 확인"] if bv is not None else []
        reasons = []
        if abs(float(bv)-float(av)) >= 5:
            reasons.append(f"패널·양산 수율 {float(av):.1f}%→{float(bv):.1f}%")
        for threshold in (85,90):
            if (float(av) < threshold <= float(bv)) or (float(av) >= threshold > float(bv)):
                reasons.append(f"수율 {threshold}% 기준 {'상향 돌파' if float(bv)>=threshold else '하향 이탈'}")
        return reasons
    if new['axis'] == 'glass_process_cycle_time':
        reasons = []
        if a.get('process_name') != b.get('process_name') and b.get('process_name'):
            reasons.append(f"핵심공정 식별 {a.get('process_name') or '미확인'}→{b.get('process_name')}")
        av, bv = a.get('after_minutes_exact'), b.get('after_minutes_exact')
        if av is None and bv is not None:
            reasons.append(f"개선 후 정확한 공정시간 {float(bv):g}분 최초 공개")
        elif av is not None and bv is not None and abs(float(bv)-float(av)) >= max(1.0, abs(float(av))*0.1):
            reasons.append(f"개선 후 공정시간 {float(av):g}→{float(bv):g}분")
        if a.get('after_time_class') != b.get('after_time_class') and b.get('after_time_class'):
            reasons.append(f"공정시간 표현 {a.get('after_time_class') or '미확인'}→{b.get('after_time_class')}")
        if a.get('body_direct_verified') is not True and b.get('body_direct_verified') is True:
            reasons.append("기사 본문에서 공정명·시간 직접 검증 완료")
        return reasons
    if new['axis'] == 'glass_capex':
        reasons = []
        av, bv = a.get('investment_krw'), b.get('investment_krw')
        if av is None and bv is not None:
            reasons.append(f"김천 TGV 설비투자 {float(bv)/1e8:,.0f}억원 최초 확인")
        elif av and bv:
            pct = (float(bv)/float(av)-1)*100
            if abs(pct) >= 10:
                reasons.append(f"김천 TGV 설비투자 {float(av)/1e8:,.0f}→{float(bv)/1e8:,.0f}억원 ({pct:+.1f}%)")
        for field, label in (
            ('line_count_min_initial','초기 라인 수 하단'),
            ('line_count_max_initial','초기 라인 수 상단'),
            ('line_count_mass_ramp_min','대량양산 라인 수 하단'),
            ('start_year','투자 시작'),('end_year','투자 종료'),
            ('groundbreaking_period','착공 시점'),
            ('initial_customer_commercialization_period','고객 초기 상용화 시점'),
            ('employees','고용'),('site_area_pyeong','부지')
        ):
            av, bv = a.get(field), b.get(field)
            if av is not None and bv is not None and av != bv:
                reasons.append(f"{label} {av}→{bv}")
            elif av is None and bv is not None:
                reasons.append(f"{label} {bv} 신규 확인")
        av, bv = a.get('capacity_panels_per_month'), b.get('capacity_panels_per_month')
        if av is None and bv is not None:
            reasons.append(f"김천 실제 생산능력 월 {float(bv):,.0f}장 최초 공개")
        elif av and bv:
            pct=(float(bv)/float(av)-1)*100
            if abs(pct)>=10:
                reasons.append(f"김천 실제 생산능력 월 {float(av):,.0f}→{float(bv):,.0f}장 ({pct:+.1f}%)")
        if a.get('stage') != b.get('stage') and b.get('stage'):
            reasons.append(f"설비투자 단계 {a.get('stage') or '미확인'}→{b.get('stage')}")
        return reasons
    if new['axis'] == 'glass_hvm_stage':
        reasons = []
        old_stage, new_stage = a.get('stage','sample'), b.get('stage','sample')
        if old_stage != new_stage:
            reasons.append(f"양산 전환 단계 {old_stage}→{new_stage}")
        av, bv = a.get('mass_production_target_year'), b.get('mass_production_target_year')
        if av is not None and bv is not None and int(av) != int(bv):
            reasons.append(f"양산 목표 {int(av)}→{int(bv)}년")
        elif av is None and bv is not None:
            reasons.append(f"양산 목표 {int(bv)}년 신규 확인")
        for field, label in (
            ('sample_delivered','고객 샘플 납품'),
            ('evaluation_ongoing','고객 평가 진행'),
            ('issue_response_ongoing','평가 이슈 보완 대응'),
            ('mass_production_supply_confirmed','양산 공급 확정'),
        ):
            if a.get(field) != b.get(field) and b.get(field) is not None:
                reasons.append(label + (' 확인' if b.get(field) else ' 해소·철회'))
        if a.get('customer') != b.get('customer') and b.get('customer'):
            reasons.append(f"고객 실명 {a.get('customer') or '미확인'}→{b.get('customer')}")
        if a.get('sample_process') != b.get('sample_process') and b.get('sample_process'):
            reasons.append(f"샘플 공정 {a.get('sample_process') or '미확인'}→{b.get('sample_process')}")
        if a.get('new_metal_fill_stage') != b.get('new_metal_fill_stage') and b.get('new_metal_fill_stage'):
            reasons.append(f"신규 금속 충진 공정 {a.get('new_metal_fill_stage') or '미확인'}→{b.get('new_metal_fill_stage')}")
        if a.get('new_metal_fill_sample_delivered') != b.get('new_metal_fill_sample_delivered') and b.get('new_metal_fill_sample_delivered') is not None:
            reasons.append('신규 금속 충진 샘플 고객 전달' if b.get('new_metal_fill_sample_delivered') else '신규 금속 충진 샘플 미전달 확인')
        for field, label in (
            ('pilot_line_count','파일럿 라인 수'),
            ('pilot_capacity_units_per_month_min','파일럿 월 생산능력 하단'),
            ('pilot_capacity_units_per_month_max','파일럿 월 생산능력 상단'),
            ('nda_customer_count','NDA 고객 수'),
            ('end_customer_count','최종 수요기업 수'),
            ('paid_sample_customer_count','유상 샘플 고객 수'),
            ('initial_line_count_min','김천 초기 라인 수 하단'),
            ('initial_line_count_max','김천 초기 라인 수 상단'),
            ('mass_ramp_line_count_min','대량양산 라인 수 하단'),
        ):
            av, bv = a.get(field), b.get(field)
            if av is not None and bv is not None and av != bv:
                reasons.append(f"{label} {av}→{bv}")
            elif av is None and bv is not None:
                reasons.append(f"{label} {bv} 신규 확인")
        for field, label in (
            ('gimcheon_groundbreaking_period','김천 착공 시점'),
            ('initial_customer_commercialization_period','고객 초기 상용화 시점'),
        ):
            av, bv = a.get(field), b.get(field)
            if av != bv and bv:
                reasons.append(f"{label} {av or '미확인'}→{bv}")
        for field, label in (
            ('embedding_preliminary_evaluation_passed','Embedding 예비평가 통과'),
            ('embedding_reliability_evaluation_ongoing','Embedding 신뢰성 평가 진행'),
            ('non_embedding_supplier_selection_ongoing','Non-Embedding 공급사 선정 진행'),
        ):
            if a.get(field) != b.get(field) and b.get(field) is True:
                reasons.append(label)
        av, bv = a.get('non_embedding_poc_target_year'), b.get('non_embedding_poc_target_year')
        if av != bv and bv:
            reasons.append(f"Non-Embedding PoC 목표 {av or '미확인'}→{bv}년")
        return reasons
    if new['axis'] == 'foundry_loss_outlook':
        reasons = []
        for field, label, threshold in (
            ('loss_2026e_krw_trn','2026E 합산 영업손실',0.5),
            ('q3_2026e_loss_krw_trn','3Q26E 합산 영업손실',0.2),
        ):
            av, bv = a.get(field), b.get(field)
            if av is not None and bv is not None:
                pct = abs(float(bv) / float(av) - 1.0) * 100 if float(av) else 0
                if abs(float(bv)-float(av)) >= threshold or pct >= 10:
                    reasons.append(f"{label} {float(av):.3f}조→{float(bv):.3f}조")
            elif av is None and bv is not None:
                reasons.append(f"{label} {float(bv):.3f}조 신규 확인")
        av, bv = a.get('loss_shrink_pct'), b.get('loss_shrink_pct')
        if av is not None and bv is not None and abs(float(bv)-float(av)) >= 5:
            reasons.append(f"연간 손실 축소율 {float(av):.1f}%→{float(bv):.1f}%")
        elif av is None and bv is not None:
            reasons.append(f"연간 손실 축소율 {float(bv):.1f}% 신규 확인")
        return reasons
    if new['axis'] == 'foundry_external_2nm':
        reasons = []
        old_stage, new_stage = a.get('stage','discussion'), b.get('stage','discussion')
        if old_stage != new_stage:
            reasons.append(f"외부 2나노 단계 {old_stage}→{new_stage}")
        for field, label in (
            ('hpc_design_win','2나노 HPC design win'),
            ('us_orders_strong','미국 고객 수주 강세'),
            ('gen2_mobile_ramp_plan','2나노 2세대 모바일 램프 계획'),
        ):
            if a.get(field) != b.get(field) and b.get(field) is not None:
                reasons.append(label + (' 확인' if b.get(field) else ' 해소·철회'))
        return reasons
    if new['axis'] == 'foundry_taylor_schedule':
        reasons = []
        av, bv = a.get('mass_production_year'), b.get('mass_production_year')
        if av is not None and bv is not None and int(av) != int(bv):
            reasons.append(f"Taylor Fab1 양산 목표 {int(av)}→{int(bv)}년")
        elif av is None and bv is not None:
            reasons.append(f"Taylor Fab1 양산 목표 {int(bv)}년 신규 확인")
        if a.get('external_customer_negotiations') != b.get('external_customer_negotiations') and b.get('external_customer_negotiations') is not None:
            reasons.append('Taylor 외부 고객 협상 확인' if b.get('external_customer_negotiations') else 'Taylor 외부 고객 협상 약화·철회')
        return reasons
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
        for field, label in (('price_change_pct_min','가격 인상 범위 하단'),('price_change_pct_max','가격 인상 범위 상단')):
            av, bv = a.get(field), b.get(field)
            if av is not None and bv is not None and abs(float(bv)-float(av)) >= 5:
                reasons.append(f"{label} {float(av):.1f}%→{float(bv):.1f}%")
            elif av is None and bv is not None:
                reasons.append(f"{label} {float(bv):.1f}% 신규 확인")
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
        if int(state.get('foundry_track_version') or 0) < FOUNDRY_TRACK_VERSION:
            for r in seeds:
                if str(r.get('axis','')).startswith('foundry_'):
                    state['last_notified'][r['key']] = copy.deepcopy(r)
                    state['latest'][r['key']] = copy.deepcopy(r)
                    state['pending'].pop(r['key'], None)
            state['foundry_track_version'] = FOUNDRY_TRACK_VERSION
        if int(state.get('foundry_recovery_track_version') or 0) < FOUNDRY_RECOVERY_TRACK_VERSION:
            for r in seeds:
                if r.get('axis') in ('foundry_loss_outlook', 'foundry_external_2nm', 'foundry_taylor_schedule'):
                    state['last_notified'][r['key']] = copy.deepcopy(r)
                    state['latest'][r['key']] = copy.deepcopy(r)
                    state['pending'].pop(r['key'], None)
            state['foundry_recovery_track_version'] = FOUNDRY_RECOVERY_TRACK_VERSION
        if int(state.get('foundry_pricing_range_track_version') or 0) < FOUNDRY_PRICING_RANGE_TRACK_VERSION:
            for r in seeds:
                if r.get('axis') == 'foundry_pricing':
                    current = state['last_notified'].get(r['key'])
                    if current:
                        merged = copy.deepcopy(current)
                        merged_value = copy.deepcopy(current.get('value') or {})
                        for field in ('price_change_pct_min','price_change_pct_max'):
                            if (r.get('value') or {}).get(field) is not None:
                                merged_value[field] = r['value'][field]
                        merged['value'] = merged_value
                        state['last_notified'][r['key']] = merged
                        state['latest'][r['key']] = copy.deepcopy(merged)
                        state['pending'].pop(r['key'], None)
            state['foundry_pricing_range_track_version'] = FOUNDRY_PRICING_RANGE_TRACK_VERSION
        if int(state.get('glass_substrate_track_version') or 0) < GLASS_SUBSTRATE_TRACK_VERSION:
            for r in seeds:
                if r.get('axis') in ('glass_panel_standard','glass_tsmc_roadmap','glass_panel_yield','glass_hvm_stage','glass_process_cycle_time','glass_capex'):
                    state['last_notified'][r['key']] = copy.deepcopy(r)
                    state['latest'][r['key']] = copy.deepcopy(r)
                    state['pending'].pop(r['key'], None)
            state['glass_substrate_track_version'] = GLASS_SUBSTRATE_TRACK_VERSION
        if int(state.get('hbm_generation_price_track_version') or 0) < HBM_GENERATION_PRICE_TRACK_VERSION:
            for r in seeds:
                if r.get('axis') == 'hbm_generation_pricing':
                    state['last_notified'][r['key']] = copy.deepcopy(r)
                    state['latest'][r['key']] = copy.deepcopy(r)
                    state['pending'].pop(r['key'], None)
            state['hbm_generation_price_track_version'] = HBM_GENERATION_PRICE_TRACK_VERSION
        if int(state.get('market_pricing_track_version') or 0) < MARKET_PRICING_TRACK_VERSION:
            for r in seeds:
                if r.get('axis') == 'hbm_market_pricing':
                    state['last_notified'][r['key']] = copy.deepcopy(r)
                    state['latest'][r['key']] = copy.deepcopy(r)
                    state['pending'].pop(r['key'], None)
            state['market_pricing_track_version'] = MARKET_PRICING_TRACK_VERSION
    state['version'] = VERSION
    grouped = {}
    for r in records:
        if not r.get('as_of') or not r.get('source_url') or not r.get('period'):
            continue
        if r['as_of'][:10] > now.date().isoformat():
            continue
        grouped.setdefault(r['key'], []).append(r)
    sparse_axes = {'foundry_base_die_allocation', 'foundry_pricing', 'foundry_hbm5_2nm', 'foundry_loss_outlook', 'foundry_external_2nm', 'foundry_taylor_schedule', 'glass_panel_standard', 'glass_tsmc_roadmap', 'glass_panel_yield', 'glass_hvm_stage', 'glass_process_cycle_time', 'glass_capex', 'hbm_generation_pricing', 'hbm_market_pricing'}
    for key, rows in grouped.items():
        rows.sort(key=lambda x: (x['as_of'], RANK.get(x['evidence'], 0)))
        prior = state['latest'].get(key) or state['last_notified'].get(key)
        if prior and rows and rows[-1].get('axis') in sparse_axes:
            normalized = []
            for row in rows:
                merged = copy.deepcopy(row)
                merged_value = copy.deepcopy(prior.get('value') or {})
                for field, value in (row.get('value') or {}).items():
                    if value is not None:
                        merged_value[field] = value
                merged['value'] = merged_value
                normalized.append(merged)
            rows = normalized
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
             'hbm_market_pricing': '시장 HBM 평균판매단가·8단/12단 구조 변화',
             'postprocess_capex': 'HBM 후공정 설비투자·병목 변화',
             'postprocess_order': 'HBM 후공정 장비 수주 변화',
             'postprocess_stage': 'HBM 후공정 고객 검증·양산 단계 변화',
             'hbm_generation_pricing': 'HBM 세대별 2027 가격 리셋',
             'glass_panel_standard': '유리기판 510×515mm 규격 수렴·TSMC 채택 상태',
             'glass_tsmc_roadmap': 'TSMC CoPoS·Glass Core 양산 로드맵',
             'glass_panel_yield': '유리기판 패널·양산 수율',
             'glass_hvm_stage': '유리기판 고객검증→발주→HVM 전환 단계',
             'glass_process_cycle_time': '제이앤티씨 TGV 핵심공정 시간 단축',
             'glass_capex': '제이앤티씨 김천 TGV 설비투자',
             'foundry_loss_outlook': '삼성 파운드리+System LSI 손실 축소 전망',
             'foundry_external_2nm': '삼성 외부 2나노 AI·HPC 수주·양산 전환',
             'foundry_taylor_schedule': '삼성 Taylor Fab1 양산 일정·외부 고객 협상',
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
        if record['axis'] == 'hbm_generation_pricing':
            parts = []
            points = v.get('price_usd_per_gb') or {}
            if points:
                parts.append(' · '.join(f"{k} {float(val):.2f}달러/Gb" for k,val in sorted(points.items())))
            if v.get('broad_step_up_2027'):
                parts.append("전 세대 동반상승 신호")
            if v.get('legacy_generation_price_visible'):
                parts.append("HBM3/HBM3E 구세대 포함")
            if not points:
                parts.append("정확한 세대별 숫자 공개 확인 전")
            return " / ".join(parts)
        if record['axis'] == 'glass_panel_standard':
            suppliers = ', '.join(v.get('suppliers') or [])
            return f"{v.get('width_mm')}×{v.get('height_mm')}mm / 소재사 {v.get('supplier_count')}곳 ({suppliers}) / TSMC {v.get('tsmc_status')}"
        if record['axis'] == 'glass_tsmc_roadmap':
            parts = []
            if v.get('copos_width_mm'):
                parts.append(f"현 CoPoS {v['copos_width_mm']}×{v['copos_height_mm']}mm")
            if v.get('validation_year'):
                parts.append(f"검증 {v['validation_year']}년")
            if v.get('pilot_year'):
                parts.append(f"시험생산 {v['pilot_year']}년")
            if v.get('mass_production_year'):
                half = v.get('mass_production_half') or ''
                parts.append(f"양산 {v['mass_production_year']}년{half}")
            if v.get('glass_core_commercial_after_year'):
                parts.append(f"Glass Core 상업규모 {v['glass_core_commercial_after_year']}년 이후")
            return " / ".join(parts)
        if record['axis'] == 'glass_panel_yield':
            return f"패널·양산 수율 {v.get('yield_pct'):.1f}%"
        if record['axis'] == 'glass_process_cycle_time':
            before = f"{float(v['before_minutes']):g}분" if v.get('before_minutes') is not None else "개선 전 미확인"
            if v.get('after_minutes_exact') is not None:
                after = f"{float(v['after_minutes_exact']):g}분"
            elif v.get('after_time_class') == 'minute_scale':
                after = "분 단위(정확한 분 수 미공개)"
            else:
                after = "개선 후 미확인"
            return f"{v.get('process_name') or '공정 미확인'} / {before}→{after}"
        if record['axis'] == 'glass_capex':
            parts = []
            if v.get('investment_krw') is not None:
                parts.append(f"투자 {float(v['investment_krw'])/1e8:,.0f}억원")
            if v.get('line_count_min_initial') is not None:
                parts.append(f"초기 {int(v['line_count_min_initial'])}~{int(v.get('line_count_max_initial') or v['line_count_min_initial'])}개 라인")
            if v.get('line_count_mass_ramp_min') is not None:
                parts.append(f"대량양산 {int(v['line_count_mass_ramp_min'])}개 이상")
            if v.get('groundbreaking_period'):
                parts.append(f"착공 {v['groundbreaking_period']}")
            if v.get('initial_customer_commercialization_period'):
                parts.append(f"고객 초기 상용화 {v['initial_customer_commercialization_period']}")
            if v.get('start_year') or v.get('end_year'):
                parts.append(f"투자기간 {v.get('start_year') or '?'}~{v.get('end_year') or '?'}년")
            if v.get('site_area_pyeong') is not None:
                parts.append(f"부지 {int(v['site_area_pyeong']):,}평")
            if v.get('employees') is not None:
                parts.append(f"고용 {int(v['employees']):,}명")
            parts.append(f"생산능력 월 {float(v['capacity_panels_per_month']):,.0f}장" if v.get('capacity_panels_per_month') is not None else "실제 물량 생산능력 미공개")
            return " / ".join(parts)
        if record['axis'] == 'glass_hvm_stage':
            labels = {'sample':'샘플','customer_evaluation':'고객 검증','po_pending':'정식 발주 대기','po_signed':'정식 수주','pilot':'파일럿','mass_production':'양산'}
            text = labels.get(v.get('stage'),v.get('stage',''))
            if v.get('customer'):
                text += f" / 고객 {v['customer']}"
            if v.get('product') == 'glass_interposer':
                text += " / 유리 인터포저"
            if v.get('sample_delivered'):
                text += " / 샘플 납품 확인"
            if v.get('evaluation_ongoing'):
                text += " / 평가 진행"
            if v.get('mass_production_target_year'):
                text += f" / 양산 목표 {int(v['mass_production_target_year'])}년"
            if v.get('pilot_capacity_units_per_month_min') is not None:
                text += f" / 파일럿 월 {int(v['pilot_capacity_units_per_month_min']):,}~{int(v.get('pilot_capacity_units_per_month_max') or v['pilot_capacity_units_per_month_min']):,}개"
            if v.get('paid_sample_customer_count') is not None:
                text += f" / 유상샘플 {int(v['paid_sample_customer_count'])}곳"
            if v.get('nda_customer_count') is not None:
                text += f" / NDA {int(v['nda_customer_count'])}곳"
            return text
        if record['axis'] == 'foundry_loss_outlook':
            parts = []
            if v.get('loss_2025_krw_trn') is not None:
                parts.append(f"2025 손실 {v['loss_2025_krw_trn']:.2f}조원")
            if v.get('loss_2026e_krw_trn') is not None:
                parts.append(f"2026E {v['loss_2026e_krw_trn']:.2f}조원")
            if v.get('loss_shrink_pct') is not None:
                parts.append(f"손실 축소 {v['loss_shrink_pct']:.1f}%")
            if v.get('q3_2026e_loss_krw_trn') is not None:
                parts.append(f"3Q26E {v['q3_2026e_loss_krw_trn']:.3f}조원")
            return " / ".join(parts)
        if record['axis'] == 'foundry_external_2nm':
            labels = {'discussion':'협의·논의','design_win':'설계수주·프로젝트 확보','tapeout':'테이프아웃','qualification':'고객 인증','mass_production':'양산'}
            parts = [labels.get(v.get('stage'), v.get('stage',''))]
            if v.get('hpc_design_win'):
                parts.append("2나노 HPC")
            if v.get('us_orders_strong'):
                parts.append("미국 고객 수주 강세")
            if v.get('gen2_mobile_ramp_plan'):
                parts.append("2나노 2세대 모바일 램프 계획")
            return " / ".join(x for x in parts if x)
        if record['axis'] == 'foundry_taylor_schedule':
            parts = []
            if v.get('mass_production_year'):
                parts.append(f"Fab1 양산 목표 {int(v['mass_production_year'])}년")
            if v.get('external_customer_negotiations'):
                parts.append("외부 고객 협상")
            return " / ".join(parts)
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
            elif v.get('price_change_pct_min') is not None:
                parts.append(f"{v['price_change_pct_min']:.1f}~{v['price_change_pct_max']:.1f}%")
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
        if record['axis'] == 'hbm_market_pricing':
            parts = []
            if v.get('blended_asp_yoy_pct') is not None:
                parts.append(f"2027 Blended ASP {v['blended_asp_yoy_pct']:+.0f}% YoY")
            if v.get('mainstream_layers') is not None:
                parts.append(f"주류 {int(v['mainstream_layers'])}단")
            if v.get('eight_hi_premium_min_pct') is not None:
                parts.append(f"8단 Gb당 프리미엄 {v['eight_hi_premium_min_pct']:.0f}~{v['eight_hi_premium_max_pct']:.0f}%")
            return " / ".join(parts)
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
    if r['axis'] == 'hbm_generation_pricing':
        lines.append('• 기관별 가격곡선을 서로 합치지 않습니다. 동일 기관·동일 세대·동일 적층 조건만 전후 비교합니다.')
        lines.append('• 8단·12단 등 적층 높이가 다르면 별도 가격으로 저장하며 Blended ASP와 세대별 $/Gb를 합치지 않습니다.')
        lines.append('• 사용자 캡처는 방향 기준선일 뿐, 판독이 모호한 숫자는 저장하지 않습니다. 공개 원문에서 확인되는 숫자만 가격 상태값으로 승격합니다.')
    if r['axis'] == 'glass_panel_standard':
        lines.append('• 510×515mm 규격 수렴과 TSMC 공식 채택은 별개입니다. DIGITIMES의 공급망 추정은 reported_candidate로만 저장합니다.')
    if r['axis'] == 'glass_tsmc_roadmap':
        lines.append('• 현재 공개 로드맵은 CoPoS 310×310mm: 2026 검증→2027 시험생산→2028년 하반기 양산, Glass Core 상업규모는 2030년 이후입니다.')
    if r['axis'] == 'glass_panel_yield':
        lines.append('• TGV 홀 단일 불량률과 전체 패널 전기수율은 다른 지표입니다. 패널·양산 수율만 이 축에서 비교합니다.')
        lines.append('• ±5%p 또는 85%·90% 기준선 돌파/이탈 시 재알림합니다.')
    if r['axis'] == 'glass_process_cycle_time':
        v = r['value']
        lines.append('• 12시간=720분으로 환산합니다. “분 단위”만으로 개선 후 정확한 분 수나 속도배수를 임의 계산하지 않습니다.')
        if v.get('process_name') == 'unverified_core_process':
            lines.append('• 공정명이 직접 확인되기 전에는 도금·식각·레이저 중 특정 공정으로 단정하지 않습니다.')
        if v.get('after_minutes_exact') is not None and v.get('before_minutes'):
            speed = float(v['before_minutes']) / float(v['after_minutes_exact'])
            lines.append(f"• 직접 확인 숫자 기준 공정시간 단축배수: {speed:.1f}배")
    if r['axis'] == 'glass_capex':
        lines.append('• 설비투자 총액과 라인 수를 실제 월 생산장수로 치환하지 않습니다. 토지·건물·기계장치·공통설비가 섞일 수 있습니다.')
        lines.append('• 투자액·라인수와 실제 양산 수율·월 생산능력·고객 매출은 별도 상태로 추적합니다.')
    if r['axis'] == 'glass_hvm_stage':
        lines.append('• 샘플→고객 검증→정식 발주 대기→정식 수주→파일럿→양산을 구분하며 기사상 기대감을 양산매출로 승격하지 않습니다.')
        v = r['value']
        if v.get('customer') == 'Samsung Electronics':
            lines.append('• 고객 실명 삼성전자는 딜사이트 보도 단계로 저장합니다. 켐트로닉스·삼성전자 공식 공시 전에는 확정 공급계약·양산매출로 승격하지 않습니다.')
        if v.get('sample_process') == 'existing_method':
            lines.append('• 현재 삼성전자에 전달된 샘플은 보도상 기존 방식 제품입니다.')
        if v.get('new_metal_fill_stage'):
            status = '고객 샘플 전달' if v.get('new_metal_fill_sample_delivered') else '아직 고객 샘플 미전달'
            lines.append(f"• 신규 금속 충진 방식: {v.get('new_metal_fill_stage')} · {status}")
        if v.get('issue_response_ongoing'):
            lines.append('• 현재는 평가 중 이슈 보완 대응 단계이며 평가 통과·정식 발주·양산 시점은 아직 확정되지 않았습니다.')
    if r['axis'] == 'foundry_loss_outlook':
        lines.append('• 주의: 파운드리 단독 손익이 아니라 파운드리+System LSI 합산 증권사 전망입니다. 회사 확정 실적과 분리합니다.')
        lines.append('• 2026E 손실 ±0.5조원 또는 10% 이상, 3Q26E ±0.2조원 또는 10% 이상, 손실 축소율 ±5%p 이상을 재알림합니다.')
    if r['axis'] == 'foundry_external_2nm':
        lines.append('• 설계수주→테이프아웃→고객 인증→양산을 분리하며, 설계수주를 양산매출로 간주하지 않습니다.')
    if r['axis'] == 'foundry_taylor_schedule':
        lines.append('• Taylor 양산 일정과 외부 고객 협상은 삼성전자 공식자료·Reuters 등 확인된 변화만 반영하며 특정 고객을 2나노 양산으로 임의 연결하지 않습니다.')
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
    if r['axis'] == 'hbm_market_pricing':
        v = r['value']
        if v.get('stack_bit_change_pct') is not None:
            lines.append(f"• 12단→8단 동일 스택 수 가정: 스택당 비트 {v['stack_bit_change_pct']:+.1f}%")
        if v.get('gpu_growth_break_even_min_pct') is not None:
            lines.append(
                f"• 8단 Gb당 프리미엄을 반영하면 기존 12단 매출 상쇄에 필요한 GPU·ASIC 출하 증가는 "
                f"약 {v['gpu_growth_break_even_min_pct']:.1f}~{v['gpu_growth_break_even_max_pct']:.1f}%"
            )
        lines.append("• 시장 전체 TrendForce 전망이며 삼성전자·SK하이닉스·Micron 개별 ASP와 합치지 않습니다.")
        lines.append("• +121%는 2026년=100일 때 2027년 가격 레벨 221을 뜻하며, 계약가 범위와 Blended ASP는 별도 상태입니다.")
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
        structured_market_pricing = (
            ('trendforce' in text or '트렌드포스' in text)
            and 'hbm' in text
            and any(k in text for k in ('blended asp', '평균판매가격', '평균판매단가', '8-hi', '8hi', '8단', 'gb당'))
        )
        structured_foundry = (
            ('samsung' in text or '삼성' in text)
            and 'hbm' in text
            and any(k in text for k in ('base die', '베이스다이', '베이스 다이', '4nm', '4나노', '2nm', '2나노'))
            and any(k in text for k in ('full utilization', '풀가동', '증설', 'expand', 'price increase', '가격 인상', 'production line', '생산라인', 'investment', '투자'))
        )
        structured_generation_pricing = (
            any(k in text for k in ('semianalysis','trendforce','micron','citi','j.p. morgan','jpmorgan','bofa'))
            and ('2027' in text or '27e' in text)
            and any(k in text for k in ('hbm3e','hbm4','hbm4e'))
            and any(k in text for k in ('$/gb','per gb','price','pricing','asp','가격'))
        )
        structured_glass = (
            any(k in text for k in ('glass substrate','glass core','glass panel','glass interposer','tgv','유리기판','유리 기판','유리 인터포저','글라스 코어'))
            and any(k in text for k in ('510x515','510×515','515x510','515×510','copos','yield','수율','sample','샘플','customer evaluation','customer validation','고객 평가','고객 검증','purchase order','po ','pilot','양산','samsung','삼성전자','12시간','분 단위','cycle time','공정시간','3470억','김천','설비투자','investment'))
        )
        structured_foundry_recovery = (
            ('samsung' in text or '삼성' in text)
            and ('foundry' in text or '파운드리' in text)
            and (
                any(k in text for k in ('operating loss', '영업손실', '영업 손실', '적자', '41.8%', '42%'))
                or (
                    any(k in text for k in ('2nm', '2나노', 'taylor', '테일러'))
                    and any(k in text for k in ('design win', 'hpc', 'csp', 'customer', 'contract', '수주', 'tapeout', 'qualification', 'mass production', '양산', 'negotiation', '협상'))
                )
            )
        )
        if structured_revenue or structured_postprocess or structured_market_pricing or structured_generation_pricing or structured_foundry or structured_foundry_recovery or structured_glass:
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
        'futunn', 'futu news', 'bernstein', 'hilo research', 'xxquant',
        '머니투데이', 'moneytoday', 'mt.co.kr', '한국경제tv', 'wowtv', 'v.daum.net',
        'digitimes', 'semianalysis', 'newsletter.semianalysis', 'corning', 'agc', 'nippon electric glass', 'schott',
        'philoptics', '필옵틱스', 'jntc', '제이앤티씨', 'absolics', '앱솔릭스',
        'samsung electro-mechanics', '삼성전기', 'edaily', '이데일리',
        'dealsite', '딜사이트', 'chemtronics', '켐트로닉스', 'kind.krx.co.kr',
        'thelec', 'the elec', 'thelec.kr', '국민일보', 'kmib', 'kmib.co.kr',
        'lg innotek', 'lginnotek', 'samsung electro-mechanics', 'samsungsem', 'skc'
    )
    legacy.relevant = lambda text: original_relevant(text) or is_axis_text(text)
    observed, coverage = [], []
    body_cache = {}
    def gather():
        events = original_read()
        eligible = []
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
            eligible.append(e)
        eligible.sort(key=lambda e: (e.get('rank', 0), e.get('published_at_kst') or ''), reverse=True)
        max_body_fetches = 32
        if len(eligible) > max_body_fetches:
            coverage.append(f'원문 조회 예산 적용: 후보 {len(eligible)}건 중 우선순위 상위 {max_body_fetches}건 정밀 확인')
        for e in eligible[:max_body_fetches]:
            url = e.get('direct_link', '')
            try:
                if url not in body_cache:
                    raw = legacy.fetch(url, timeout=8).decode('utf-8', errors='replace')
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
        foundry_axes = {'foundry_loss_outlook','foundry_external_2nm','foundry_taylor_schedule','foundry_base_die_allocation','foundry_node_expansion','foundry_pricing','foundry_hbm5_2nm'}
        glass_axes = {'glass_panel_standard','glass_tsmc_roadmap','glass_panel_yield','glass_hvm_stage','glass_process_cycle_time','glass_capex'}
        generation_price_axes = {'hbm_generation_pricing'}
        regular = [k for k in chosen if state['pending'][k]['record']['axis'] not in foundry_axes | glass_axes | generation_price_axes]
        foundry = [k for k in chosen if state['pending'][k]['record']['axis'] in foundry_axes]
        glass = [k for k in chosen if state['pending'][k]['record']['axis'] in glass_axes]
        generation_price = [k for k in chosen if state['pending'][k]['record']['axis'] in generation_price_axes]
        sections = []
        if regular:
            blocks = ['<b>HBM·서버 D램 연계 상태 변화</b>']
            blocks.extend(render(state['pending'][key], rate) for key in regular)
            sections.append('\n\n'.join(blocks))
        if foundry:
            blocks = ['<b>삼성 파운드리 HBM4·2나노 회복 감시</b>']
            blocks.extend(render(state['pending'][key], rate) for key in foundry)
            sections.append('\n\n'.join(blocks))
        if glass:
            blocks = ['<b>유리기판·유리 인터포저 고객검증·HVM 전환 감시</b>']
            blocks.extend(render(state['pending'][key], rate) for key in glass)
            sections.append('\n\n'.join(blocks))
        if generation_price:
            blocks = ['<b>HBM 전 세대 가격 리셋 감시</b>']
            blocks.extend(render(state['pending'][key], rate) for key in generation_price)
            sections.append('\n\n'.join(blocks))
        if rate and sections:
            sections[-1] += '\n\n환율 기준: ' + html.escape(basis)
        payload = '\n\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n'.join(sections)
        legacy.ALERT.write_text(existing.rstrip() + ('\n\n' if existing else '') + payload + '\n', encoding='utf-8')
        for key in chosen:
            state['last_notified'][key] = state['pending'][key]['record']
            del state['pending'][key]
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
