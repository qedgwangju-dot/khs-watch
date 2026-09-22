#!/usr/bin/env python3
import html
import re
import urllib.parse
import warsh_press_conference_watch as base

FED_HOME='https://www.federalreserve.gov/'

def transcript_link_v2():
    # 1) meeting page exact label
    try:
        raw,_=base.fetch(base.MEETING)
        for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',raw,re.I|re.S):
            label=' '.join(html.unescape(re.sub(r'<[^>]+>',' ',m.group(2))).split()).strip().lower()
            if label in ('press conference transcript','transcript'):
                href=urllib.parse.urljoin(base.MEETING,m.group(1))
                if 'transcript' in href.lower() or href.lower().endswith('.pdf'):
                    return href
    except Exception:
        pass
    # 2) Fed homepage fallback: current press conference transcript PDF
    try:
        raw,_=base.fetch(FED_HOME)
        for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',raw,re.I|re.S):
            label=' '.join(html.unescape(re.sub(r'<[^>]+>',' ',m.group(2))).split()).strip().lower()
            href=urllib.parse.urljoin(FED_HOME,m.group(1))
            if label=='transcript' and ('20260916' in href or '2026' in href):
                return href
    except Exception:
        pass
    return None

def message_v2(rows,cls,transcript,correction=False):
    lines=[
        '<b>[Warsh 기자회견 · 반응함수]</b>',
        '기준: 2026년 9월 FOMC',
        '',
        '<b>한눈에 보기</b>',
        '• <b>물가 우선</b>: 인플레이션이 아직 높아 추가긴축 선택지를 유지',
        '• <b>경기·고용</b>: 경제와 고용이 금리인상을 막을 정도로 약하지 않음',
        '• <b>정책경로</b>: 추가 인상을 미리 약속하지 않고 여러 달의 추세를 보고 결정',
        '• <b>장기금리</b>: 경제 강도·설비투자·지정학·국채공급 등 복수 요인을 분리해서 봄',
        '',
        '<b>쉽게 말하면</b>',
        '• “경기가 무너져 금리를 못 올리는 상황은 아니다. 물가가 충분히 식지 않았으니 지금은 물가를 먼저 본다.”가 핵심입니다.',
        '• 다만 한 번의 CPI나 시장가격 하나만으로 다음 인상을 확정하지 않습니다.',
        '',
        '<b>다음 판정이 바뀌는 조건</b>',
        '• 근원 PCE 3·6개월 연율이 2%대 중반 이하로 지속 둔화',
        '• 실업률 상승과 비농업 고용 3개월 평균 급락이 함께 확인',
        '• 연준이 성장·고용 하방위험을 물가보다 우선한다고 공식 전환',
        '',
        '<b>검증 상태</b>',
    ]
    if transcript:
        lines.append(f"• 연준 공식 기자회견 전문 확인: {base.link('공식 전문',transcript)}")
    else:
        lines.append('• 공식 기자회견 전문 링크를 아직 확인하지 못해 연준 성명·점도표와 신뢰 보도를 교차 사용합니다.')
    lines += ['', '<b>원천</b>', base.link('연준 9월 FOMC 회의 페이지',base.MEETING)]
    for label,url in base.REUTERS_SOURCES:
        lines[-1]+=' · '+base.link('Reuters '+label,url)
    return '\n'.join(lines)

base.transcript_link=transcript_link_v2
base.message=message_v2
if __name__=='__main__':
    base.main()
