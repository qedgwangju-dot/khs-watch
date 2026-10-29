#!/usr/bin/env python3
import email.utils
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, date as date_type

import warsh_press_conference_watch as base

FOMC_STATE=Path('data/warsh_fomc_event_watch_state.json')
FED_HOME='https://www.federalreserve.gov/'

# One verified supplement for the Oct 28 policy-framework developments.
# The ordinary FOMC decision and press-conference alerts have already run.
STRUCTURAL_DATE='2026-10-28'
STRUCTURAL_KEY='2026-10-28|Warsh|FOMC-Structural-Verified-v1'
STRUCTURAL_FED='https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm'
STRUCTURAL_IMPL='https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a1.htm'
BALANCE_ADDENDUM_KEY='2026-10-28|Warsh|BalanceTaskforceQ1-Verified-v1'
KOREA_ADDENDUM_KEY='2026-10-28|Warsh|Korea-AI-SupplyChain-QA-Verified-v1'
KOREA_REPORTS=(
    ('뉴스1','https://www.news1.kr/world/international-economy/6335584','ko'),
    ('연합뉴스','https://stock.mk.co.kr/news/view/1183879','ko'),
    ('코리아헤럴드','https://www.koreaherald.com/article/10919364','en'),
    ('아주프레스','https://m.ajupress.com/amp/20261029104304880','en'),
)

STRUCTURAL_URLS={
    'productivity':'https://www.investing.com/news/economy-news/feds-warsh-says-us-economy-not-running-too-hot-4980529',
    'balance':'https://kfgo.com/2026/10/28/feds-policy-committee-to-weigh-balance-sheet-issues-early-next-year-warsh-says/',
    'strategy':'https://kfgo.com/2026/10/28/feds-warsh-announces-changes-in-how-future-fomc-meetings-will-go/',
    'korea':'https://www.news1.kr/world/international-economy/6335584',
    'ai_rates':'https://www2.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01538326645617840',
    'hearing':'https://www.investing.com/news/economy-news/warsh-to-attend-fed-jobs-and-productivity-task-force-hearing-to-refine-views-4980494',
}
STRUCTURAL_PROOFS={
    'productivity':('reuters','warsh','productivity','not running too hot'),
    'balance':('reuters','warsh','balance sheet','first quarter'),
    'strategy':('reuters','warsh','2027','2028','strategy'),
    'korea':('워시','한국','일본','싱가포르'),
    'ai_rates':('워시','ai','금리','투자'),
    'hearing':('reuters','warsh','november 16','productivity'),
}


def source_text(url):
    """Only a directly fetched, correctly hosted article can prove an alert."""
    try:
        raw, final = base.fetch(url, timeout=8)
        expected = (urllib.parse.urlsplit(url).hostname or '').lower()
        actual = (urllib.parse.urlsplit(final).hostname or '').lower()
        if expected != actual:
            return ''
        cleaned = re.sub(r'(?is)<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>', ' ', raw)
        cleaned = html.unescape(re.sub(r'(?s)<[^>]+>', ' ', cleaned))
        # Reuters syndication embeds invisible format characters inside words.
        cleaned = re.sub(r'[\u200b-\u200f\u2060\ufeff]', '', cleaned)
        return ' '.join(cleaned.split()).lower()
    except Exception:
        return ''


def verified_structural_sources():
    """Official FOMC vote + independent report texts, not search snippets."""
    fed = source_text(STRUCTURAL_FED)
    if not (re.search(r'10\s*[–—-]\s*2\s+vote', fed)
            and all(x in fed for x in (
                'lisa d. cook','beth m. hammack',
                'productivity growth is strong','3-3/4 to 4 percent'))):
        return None
    verified = {}
    for topic, url in STRUCTURAL_URLS.items():
        text = source_text(url)
        # Date and exact article vocabulary protect against paywalls, nav text
        # and a publisher landing page being mistaken for the reported speech.
        dated = bool(re.search(
            r'oct(?:ober)?\s+28|2026[-./ ]10[-./ ]2[89]|2026년\s*10월\s*2[89]일',
            text
        ))
        verified[topic] = dated and all(term in text for term in STRUCTURAL_PROOFS[topic])
    return verified


def verified_korea_addendum_sources():
    """Verify event via Fed statement plus two distinct, directly read reports."""
    fed=source_text(STRUCTURAL_FED)
    if not (re.search(r'10\s*[–—-]\s*2\s+vote',fed)
            and 'lisa d. cook' in fed and 'beth m. hammack' in fed
            and '3-3/4 to 4 percent' in fed):
        return None
    evidence=[]
    for publisher,url,lang in KOREA_REPORTS:
        body=source_text(url)
        dated=bool(re.search(r'2026[./ -]10[./ -]2[89]|oct(?:ober)?\.?\s+2[89],?\s+2026',body))
        if lang=='ko':
            quoted=(all(x in body for x in ('워시','한국 경제','일본','싱가포르','선박'))
                    and any(x in body for x in ('비행기','항공기')))
        else:
            quoted=(all(x in body for x in ('warsh','korea','japan','singapore','ship'))
                    and ('plane' in body or 'aircraft' in body))
        if dated and quoted:
            evidence.append({'publisher':publisher,'url':url})
    return evidence if len(evidence)>=2 else None


def korea_addendum_message(evidence):
    lines=[
        '<b>[Warsh | 한국 첨단기술 공급망 발언 추가 검증]</b>',
        '2026년 10월 28일 FOMC 기자회견 · 앞선 정책·대차대조표 알림과 별개의 내용',
        '',
        '<b>추가 확인</b>',
        '• 워시는 신기술 투자에 필요한 투입재가 한국·일본, 일부는 싱가포르에서 온다고 설명했습니다.',
        '• 한국 경제와 미국행 항공기·선박의 화물 흐름이 미국 기술투자 현황을 읽는 단서라고 말했습니다.',
        '• 한국 기자는 대차대조표 축소가 해외 국채 보유자·달러 조달시장에 미칠 영향을 물었습니다. 워시는 구체적인 시장 안정 조치를 제시하지 않았습니다.',
        '',
        '<b>정책과 실적 구분</b>',
        '• 해당 발언은 한국 첨단기술 공급망의 중요성을 인정한 것이며 특정 회사 수주·매출 발표가 아닙니다.',
        '• 태스크포스 권고안의 2027년 1분기 검토는 기존 알림으로 처리됐습니다. 2027년 2분기 정책 시행은 확정되지 않았습니다.',
        '',
        '<b>후속 확인</b>',
        '• 한국 반도체 수출 물량·평균판매단가, 미국 AI 설비투자 실제 집행과 신용 스프레드',
        '• 연준 공식 태스크포스 보고서·시행지침, 미국 2년물·장기금리와 달러 조달시장',
        '',
        '<b>근거</b>',
        base.link('연준 FOMC 공식 성명',STRUCTURAL_FED),
    ]
    lines.extend(base.link(x['publisher']+' 독립 보도',x['url']) for x in evidence)
    result='\n'.join(lines)
    if len(result)>3900:
        raise RuntimeError('한국 공급망 후속 Telegram 메시지 길이 초과')
    return result


def structural_message(verified):
    lines=[
        '<b>[Warsh | 10월 FOMC 구조 변화 추가 검증]</b>',
        '기준: 2026년 10월 28일 FOMC · 기존 결정·기자회견 알림의 중복 없는 보충',
        '',
        '<b>공식 확정</b>',
        '• 금리 3.75~4.00% 동결, 찬성 10명·반대 2명. Lisa Cook·Beth Hammack은 0.25%포인트 인상을 요구했습니다.',
        '• 연준 성명은 생산성·설비투자 강세와 여전히 높은 물가를 동시에 명시했습니다.',
    ]
    if verified.get('productivity'):
        lines.append('• <b>성장 해석</b>: 워시는 높은 성장률 자체를 수요 과열로 단정하지 않았습니다. 생산성 향상 규모는 불확실합니다.')
    if verified.get('ai_rates'):
        lines.append('• <b>AI 자금조달</b>: AI 설비투자도 금리·신용비용에 영향을 받습니다. 투자계획보다 실제 집행·신용스프레드를 함께 확인합니다.')
    if verified.get('balance'):
        lines.append('• <b>대차대조표</b>: 태스크포스 권고안은 2027년 1분기 초 논의 가능성이 제시됐습니다. 정책 채택·2027년 2분기 시행은 확정되지 않았습니다.')
    if verified.get('strategy'):
        lines.append('• <b>FOMC 운영</b>: 워시는 2027년 8회 중 1회, 2028년 2회를 금리표결 없는 전략 논의 회의로 운영할 계획을 설명했습니다. 공식 달력 반영은 별도 확인 대상입니다.')
    if verified.get('hearing'):
        lines.append('• <b>후속 일정</b>: 11월 16일 생산성·고용 태스크포스 현장 청문회에서 AI 생산성·고용 영향을 추가 검토할 계획입니다.')
    if verified.get('korea'):
        lines.append('• <b>한국 공급망</b>: 워시는 한국·일본·싱가포르의 신기술 투입재를 미국 경제 판단의 단서로 언급했습니다. 특정 기업 수주 확정 발언은 아닙니다.')
    lines += [
        '',
        '<b>시장·정책 구분</b>',
        '• 2년물 하락과 10년물 상승은 단기 인상 기대와 장기 기간프리미엄의 분리를 시사할 수 있으나, 이 알림에는 미검증 실시간 금리를 기입하지 않습니다.',
        '• Cook의 반대 이유를 정치적 동기라고 단정하지 않습니다. 금리 동결은 추가 인상 종료 선언도 아닙니다.',
        '',
        '<b>다음 검증</b>',
        '• 공식 기자회견 전문·태스크포스 보고서·FOMC 시행지침과 실제 대차대조표 H.4.1',
        '• AI 설비투자 실제 집행, 신용스프레드, 미국 2년·10년물과 한국 반도체 수출 물량',
        '',
        '<b>원천</b>',
        base.link('연준 10월 FOMC 성명',STRUCTURAL_FED),
    ]
    for topic in ('productivity','ai_rates','balance','strategy','hearing','korea'):
        if verified.get(topic):
            lines.append(base.link({
                'productivity':'Reuters 생산성 발언',
                'ai_rates':'이데일리 AI 금리 민감도',
                'balance':'Reuters 대차대조표',
                'strategy':'Reuters FOMC 운영 변경',
                'hearing':'Reuters 생산성 청문회',
                'korea':'뉴스1 한국 공급망 발언'
            }[topic],STRUCTURAL_URLS[topic]))
    msg='\n'.join(lines)
    if len(msg)>3900:
        raise RuntimeError('FOMC 구조변화 보충 알림 길이 초과')
    return msg


def structural_eligible(verified):
    return bool(verified and sum(bool(verified.get(x)) for x in (
        'balance','strategy','korea','ai_rates','hearing'))>=2)


def balance_addendum_message(verified):
    lines=[
        '<b>[Warsh | 대차대조표 TF 일정 추가 검증]</b>',
        '2026년 10월 28일 기자회견 · 앞서 보낸 AI·FOMC 운영 알림과 다른 추가 확인',
        '',
        '• <b>권고안 일정</b>: Reuters에 따르면 태스크포스 권고가 2027년 1분기 초 FOMC에 전달될 가능성이 있습니다. 워시는 일정이 바뀔 수 있다고 밝혔습니다.',
        '• <b>현재 시행지침</b>: 충분한 은행 준비금 유지, 미 국채 원금의 만기 재투자, 기관채 원금의 단기국채 재투자를 지속합니다.',
        '• <b>중요한 구분</b>: 2027년 2분기 대차대조표 축소 시행은 확정되지 않았습니다. 권고 제출·FOMC 채택·시행지침 변경·실제 자산 감소는 각각 다른 단계입니다.',
        '• <b>시장 영향</b>: 국채 보유량·은행 준비금·단기자금 조달비용을 함께 봅니다. 단순 자산 구성 변경을 새로운 양적긴축으로 부르지 않습니다.',
    ]
    if verified.get('korea'):
        lines.append('• <b>한국 공급망</b>: 워시의 한국·일본·싱가포르 기술 투입재 언급은 공급망 중요성에 관한 발언이지 특정 기업의 수주 확정은 아닙니다.')
    lines += [
        '',
        '<b>다음 실제 알림 조건</b>',
        '• 공식 태스크포스 권고안 공개, FOMC 승인, 시행지침 변경 또는 H.4.1 준비금·보유증권의 유의미한 변화',
        '',
        '<b>원천</b>',
        base.link('연준 FOMC 성명',STRUCTURAL_FED),
        base.link('연준 공식 시행지침',STRUCTURAL_IMPL),
        base.link('Reuters 태스크포스 보도',STRUCTURAL_URLS['balance']),
    ]
    if verified.get('korea'):
        lines.append(base.link('뉴스1 한국 공급망 보도',STRUCTURAL_URLS['korea']))
    msg='\n'.join(lines)
    if len(msg)>3900:
        raise RuntimeError('대차대조표 보충 알림 길이 초과')
    return msg


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except Exception:
        return {}


def current_meeting():
    fs=load_json(FOMC_STATE)
    stmt=fs.get('current_statement') or {}
    date=stmt.get('date')
    if not date:
        return None,None,stmt
    page='https://www.federalreserve.gov/monetarypolicy/fomcpresconf'+str(date).replace('-','')+'.htm'
    return str(date),page,stmt


def transcript_link(page):
    try:
        raw,_=base.fetch(page)
    except Exception:
        return None
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',raw,re.I|re.S):
        label=' '.join(html.unescape(re.sub(r'<[^>]+>',' ',m.group(2))).split()).strip().lower()
        href=urllib.parse.urljoin(page,m.group(1))
        if label in ('press conference transcript','transcript') and ('transcript' in href.lower() or href.lower().endswith('.pdf')):
            return href
    return None


def reuters_rows(date):
    q=urllib.parse.urlencode({'q':f'Kevin Warsh Fed {date} Reuters inflation economy rates','hl':'en-US','gl':'US','ceid':'US:en'})
    try:
        raw,_=base.fetch('https://news.google.com/rss/search?'+q)
        root=ET.fromstring(raw)
    except Exception:
        return []
    out=[]
    for item in root.findall('.//item')[:40]:
        title=(item.findtext('title') or '').strip()
        link=(item.findtext('link') or '').strip()
        src=item.find('source'); pub=(src.text or '').strip() if src is not None else ''
        if 'Reuters' not in pub and 'Reuters' not in title:
            continue
        out.append({'title':title,'url':link})
    return out[:8]


def classify(stmt_text,rows):
    text=(stmt_text or '')+' '+' '.join(x['title'] for x in rows)
    low=text.lower()
    return {
        'inflation_priority':bool(re.search(r'inflation remains elevated|price stability|focus.*inflation|inflation.*problem',low)),
        'economy_strong':bool(re.search(r'economic activity.*solid|domestic spending.*resilient|economy.*strength|capital investment.*robust',low)),
        'labor_soft':bool(re.search(r'labor.*soft|job gains.*slowed|unemployment.*ris',low)),
        'no_precommit':bool(re.search(r'data[- ]dependent|not precommit|no.*forward guidance|not.*predetermined',low)),
        'balance_sheet':bool(re.search(r'ample reserves|balance sheet|treasury bills|reinvest',low)),
    }


def message(date,page,stmt,rows,cls,tr):
    lines=[
        '<b>[Warsh 기자회견 · 반응함수 변화]</b>',
        f'기준: {date} FOMC',
        '',
        '<b>핵심 판정</b>',
        f"• 물가 우선: {'확인' if cls['inflation_priority'] else '새로운 강한 문구 자동 확인 안 됨'}",
        f"• 경기 견조: {'확인' if cls['economy_strong'] else '추가 확인 필요'}",
        f"• 노동시장 약화 신호: {'확인' if cls['labor_soft'] else '뚜렷한 약화 문구 자동 확인 안 됨'}",
        f"• 사전 금리경로 약속 회피: {'확인' if cls['no_precommit'] else '기자회견 전문·보도 추가 확인 필요'}",
        '',
        '<b>쉽게 말하면</b>',
        '• 기자회견은 성명서보다 “다음 회의에 무엇을 더 확인하려는지”를 읽는 용도로 봅니다.',
        '• 한 문장만으로 다음 인상·동결을 확정하지 않고 물가·고용·선물금리·2년물 반응과 같이 판정합니다.',
        '',
        '<b>검증 상태</b>',
    ]
    if tr:
        lines.append('• 연준 공식 기자회견 전문 링크 확인 완료')
    else:
        lines.append('• 공식 기자회견 전문 링크 공개 전/미확인 — 성명서와 신뢰보도를 보조적으로 사용')
    lines += [
        '',
        '<b>다음 확인</b>',
        '• 기자회견 뒤 2년물과 다음 FOMC 선물경로가 같은 방향으로 움직이는지',
        '• 근원 PCE·고용 3개월 추세가 워시의 설명을 실제로 뒷받침하는지',
        '• 대차대조표는 “충분한 준비금 유지”에서 실제 총량축소형 QT로 바뀌는지',
        '',
        '<b>원천</b>',
        base.link('연준 FOMC 기자회견 페이지',page),
    ]
    if tr:
        lines[-1]+=' · '+base.link('연준 공식 기자회견 전문',tr)
    # Reuters is only corroboration; labels stay Korean and raw English titles are not emitted.
    for i,row in enumerate(rows[:2],1):
        lines[-1]+=' · '+base.link(f'Reuters 보도 {i}',row['url'])
    return '\n'.join(lines)


def main():
    old=base.load()
    date,page,stmt=current_meeting()
    if not date:
        raise RuntimeError('현재 FOMC 회의일 확인 실패')
    tr=transcript_link(page)
    rows=reuters_rows(date)
    cls=classify(stmt.get('text') or '',rows)

    migrated=bool(old and not old.get('meeting_date'))
    meeting_changed=bool(old.get('meeting_date') and old.get('meeting_date')!=date)
    transcript_new=bool(tr and tr!=old.get('transcript'))
    # Rotating Reuters RSS headlines are not a fresh policy decision.
    # A new official transcript, not a transient headline, can reopen coverage.
    first=not bool(old)
    should=base.FORCE or meeting_changed or transcript_new
    if first or migrated:
        should=base.FORCE

    new=dict(old)
    if should:
        generic_key=date+'|press-conference'
        if old.get('generic_pending_key')==generic_key and old.get('generic_delivery_status')=='sending':
            raise RuntimeError('기자회견 알림 전송 결과 불명확 — 재전송 보류')
        new.update({'generic_pending_key':generic_key,'generic_delivery_status':'sending'})
        base.save(new)
        mid=base.send(message(date,page,stmt,rows,cls,tr))
        if not isinstance(mid,int):
            raise RuntimeError('기자회견 Telegram message_id 미확인')
        new.update({
            'generic_pending_key':None,'generic_delivery_status':'confirmed',
            'generic_sent_key':generic_key,'generic_message_id':mid,
            'generic_sent_at_utc':datetime.now(timezone.utc).isoformat(),
        })

    structural_sent=False
    structural_status='not_applicable'
    in_window=(datetime.now(timezone.utc).date()<=date_type(2026,11,5))
    if date==STRUCTURAL_DATE and in_window and old.get('structural_sent_key')!=STRUCTURAL_KEY:
        if old.get('structural_pending_key')==STRUCTURAL_KEY and old.get('structural_delivery_status')=='sending':
            structural_status='delivery_uncertain'
        else:
            verified=verified_structural_sources()
            if structural_eligible(verified):
                new.update({
                    'structural_pending_key':STRUCTURAL_KEY,
                    'structural_delivery_status':'sending'
                })
                base.save(new)
                mid=base.send(structural_message(verified))
                if not isinstance(mid,int):
                    raise RuntimeError('구조변화 보충 Telegram message_id 미확인')
                new.update({
                    'structural_pending_key':None,
                    'structural_delivery_status':'confirmed',
                    'structural_sent_key':STRUCTURAL_KEY,
                    'structural_message_id':mid,
                    'structural_sources':[STRUCTURAL_FED]+[
                        url for topic,url in STRUCTURAL_URLS.items() if verified.get(topic)
                    ],
                    'structural_verified_topics':[
                        topic for topic in STRUCTURAL_URLS if verified.get(topic)
                    ],
                    'structural_sent_at_utc':datetime.now(timezone.utc).isoformat(),
                })
                structural_sent=True
                structural_status='confirmed'
            else:
                if verified is None:
                    structural_status='official_source_verification_pending'
                else:
                    structural_status='article_verification_pending'
                    new['structural_candidate_topics']=[
                        topic for topic,ok in verified.items() if ok
                    ]
    elif old.get('structural_sent_key')==STRUCTURAL_KEY:
        structural_status='already_sent'

    balance_addendum_sent=False
    balance_addendum_status='not_applicable'
    old_topics=set(old.get('structural_verified_topics') or [])
    balance_needed=(
        date==STRUCTURAL_DATE and in_window
        and old.get('structural_sent_key')==STRUCTURAL_KEY
        and 'balance' not in old_topics
        and old.get('balance_addendum_sent_key')!=BALANCE_ADDENDUM_KEY
    )
    if balance_needed:
        if (old.get('balance_addendum_pending_key')==BALANCE_ADDENDUM_KEY
                and old.get('balance_addendum_delivery_status')=='sending'):
            balance_addendum_status='delivery_uncertain'
        else:
            balance_proof=verified_structural_sources()
            implementation=source_text(STRUCTURAL_IMPL)
            impl_verified=all(x in implementation for x in (
                'maintain an ample level of reserves',
                'roll over at auction all principal payments',
                'reinvest all principal payments'
            ))
            if balance_proof and balance_proof.get('balance') and impl_verified:
                new.update({
                    'balance_addendum_pending_key':BALANCE_ADDENDUM_KEY,
                    'balance_addendum_delivery_status':'sending'
                })
                base.save(new)
                mid=base.send(balance_addendum_message(balance_proof))
                if not isinstance(mid,int):
                    raise RuntimeError('대차대조표 보충 Telegram message_id 미확인')
                new.update({
                    'balance_addendum_pending_key':None,
                    'balance_addendum_delivery_status':'confirmed',
                    'balance_addendum_sent_key':BALANCE_ADDENDUM_KEY,
                    'balance_addendum_message_id':mid,
                    'balance_addendum_sources':[
                        STRUCTURAL_FED,STRUCTURAL_IMPL,STRUCTURAL_URLS['balance']
                    ]+([STRUCTURAL_URLS['korea']] if balance_proof.get('korea') else []),
                    'balance_addendum_sent_at_utc':datetime.now(timezone.utc).isoformat()
                })
                balance_addendum_sent=True
                balance_addendum_status='confirmed'
            else:
                balance_addendum_status='source_verification_pending'
    elif old.get('balance_addendum_sent_key')==BALANCE_ADDENDUM_KEY:
        balance_addendum_status='already_sent'

    # A new, narrower Korea Q&A event only after BOTH prior messages have
    # confirmed receipts. Existing #117/#118 cannot be resent.
    korea_addendum_sent=False
    korea_addendum_status='not_applicable'
    korea_needed=(
        date==STRUCTURAL_DATE and in_window
        and old.get('structural_sent_key')==STRUCTURAL_KEY
        and old.get('structural_delivery_status')=='confirmed'
        and isinstance(old.get('structural_message_id'),int)
        and old.get('balance_addendum_sent_key')==BALANCE_ADDENDUM_KEY
        and old.get('balance_addendum_delivery_status')=='confirmed'
        and isinstance(old.get('balance_addendum_message_id'),int)
        and isinstance(old.get('structural_verified_topics'),list)
        and 'korea' not in old.get('structural_verified_topics',[])
        and old.get('korea_addendum_sent_key')!=KOREA_ADDENDUM_KEY
    )
    if korea_needed:
        if (old.get('korea_addendum_pending_key')==KOREA_ADDENDUM_KEY
                and old.get('korea_addendum_delivery_status')=='sending'):
            korea_addendum_status='delivery_uncertain'
        else:
            evidence=verified_korea_addendum_sources()
            if evidence:
                new.update({'korea_addendum_pending_key':KOREA_ADDENDUM_KEY,
                            'korea_addendum_delivery_status':'sending'})
                base.save(new)
                mid=base.send(korea_addendum_message(evidence))
                if not isinstance(mid,int):
                    raise RuntimeError('한국 공급망 Telegram message_id 미확인')
                new.update({
                    'korea_addendum_pending_key':None,
                    'korea_addendum_delivery_status':'confirmed',
                    'korea_addendum_sent_key':KOREA_ADDENDUM_KEY,
                    'korea_addendum_message_id':mid,
                    'korea_addendum_sources':[STRUCTURAL_FED]+[x['url'] for x in evidence],
                    'korea_addendum_sent_at_utc':datetime.now(timezone.utc).isoformat(),
                })
                korea_addendum_sent=True
                korea_addendum_status='confirmed'
            else:
                korea_addendum_status='source_verification_pending'
    elif old.get('korea_addendum_sent_key')==KOREA_ADDENDUM_KEY:
        korea_addendum_status='already_sent'

    new.update({
        'meeting_date':date,'meeting_page':page,'classification':cls,'transcript':tr,
        'sent':should,'reuters_count':len(rows),
        'structural_source_status':structural_status,
        'balance_addendum_status':balance_addendum_status,
        'korea_addendum_status':korea_addendum_status
    })
    base.save(new)
    print(json.dumps({
        'meeting_date':date,'migrated':migrated,'meeting_changed':meeting_changed,
        'transcript_new':transcript_new,'sent':should,'classification':cls,
        'structural_sent':structural_sent,'structural_status':structural_status,
        'structural_message_id':new.get('structural_message_id'),
        'balance_addendum_sent':balance_addendum_sent,
        'balance_addendum_status':balance_addendum_status,
        'balance_addendum_message_id':new.get('balance_addendum_message_id'),
        'korea_addendum_sent':korea_addendum_sent,
        'korea_addendum_status':korea_addendum_status,
        'korea_addendum_message_id':new.get('korea_addendum_message_id'),
    },ensure_ascii=False))


if __name__=='__main__':
    main()
