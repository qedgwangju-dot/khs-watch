#!/usr/bin/env python3
import email.utils
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import warsh_press_conference_watch as base

FOMC_STATE=Path('data/warsh_fomc_event_watch_state.json')
FED_HOME='https://www.federalreserve.gov/'


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
    meaningful=bool(old.get('classification') and old.get('classification')!=cls)
    first=not bool(old)

    should=base.FORCE or meeting_changed or transcript_new or meaningful
    # Migration from the old hard-coded September watcher is silent.
    if first or migrated:
        should=base.FORCE

    if should:
        base.send(message(date,page,stmt,rows,cls,tr))
    base.save({
        'meeting_date':date,'meeting_page':page,'classification':cls,'transcript':tr,
        'sent':should,'reuters_count':len(rows)
    })
    print(json.dumps({
        'meeting_date':date,'migrated':migrated,'meeting_changed':meeting_changed,
        'transcript_new':transcript_new,'sent':should,'classification':cls
    },ensure_ascii=False))


if __name__=='__main__':
    main()
