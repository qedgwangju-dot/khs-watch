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
]
COMPANIES = {'samsung': r'삼성(?:전자)?|Samsung(?: Electronics)?',
             'skhynix': r'SK\s?하이닉스|SK\s*hynix', 'micron': r'마이크론|Micron'}
OFFICIAL = {'news.samsung.com': 'samsung', 'semiconductor.samsung.com': 'samsung',
            'news.skhynix.com': 'skhynix', 'investors.micron.com': 'micron', 'micron.com': 'micron',
            'nvidianews.nvidia.com': 'nvidia', 'developer.nvidia.com': 'nvidia'}
RANK = {'user_capture': 0, 'reported': 1, 'research': 2, 'official': 3}


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
        r'말레이시아.*(?:8542[.]?32[.]?3000|HBM)|Malaysia.*(?:8542[.]?32[.]?3000|HBM)',
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


def parse_records(item, body):
    records, gaps = [], []
    published = item.get('published_at_kst', '')
    malaysia = _malaysia_export_record(item, body)
    if malaysia:
        records.append(malaysia)
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
    if seeds and not state.get('version'):
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
             'malaysia_hsk10_export': '한국→말레이시아 HBM 관련 HSK10 수출'}
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
    if r['axis'] == 'malaysia_hsk10_export':
        lines.append('• HSK 8542323000은 HBM 포함 복합구조칩 집적회로로 HBM 전용 통계가 아닙니다.')
        if r['value'].get('weight_rounded_from_public_text'):
            lines.append('• 중량은 공개 보도 반올림값이면 중량당 단가를 정밀 계산하지 않습니다. 관세청 직접 원값 확인 시 갱신합니다.')
    label = {'official': '회사 공식자료', 'research': '조사기관 자료', 'reported': '보도 단계', 'user_capture': '사용자 캡처 기준선'}[r['evidence']]
    lines += [f'• 근거 단계: {label}', '• 근거 제목: ' + html.escape(r['source_title']) +
              ' · <a href="' + html.escape(r['source_url'], quote=True) + '">원문</a>']
    return '\n'.join(lines)


def main():
    import samsung_hbm_watch as legacy
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    baseline = json.loads((ROOT / 'data/hbm_memory_baselines.json').read_text(encoding='utf-8'))
    original_descriptor = legacy.event_state_descriptor
    rejected_generic = []
    def guarded_descriptor(e):
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
    legacy.TRUSTED += ('글로벌이코노믹', 'g-enews', 'dramexchange', 'sk하이닉스', 'micron')
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
