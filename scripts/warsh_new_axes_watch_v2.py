#!/usr/bin/env python3
"""Official-BLS parser override for warsh_new_axes_watch.

Uses BLS Latest Numbers for the four headline quarterly measures and the current
Productivity and Costs release for labor share, year-over-year values and the
business-cycle productivity trend. FRED remains only the base script's emergency
fallback if BLS is temporarily unavailable.
"""
import re
import warsh_new_axes_watch as base

LATEST_URL='https://www.bls.gov/productivity/latest-numbers.htm'
RELEASE_URL='https://www.bls.gov/news.release/prod2.htm'


def num(text,pattern,flags=re.I):
    m=re.search(pattern,text,flags)
    return float(m.group(1)) if m else None


def robust_bls_prod_snapshot():
    latest_raw,latest_final=base.fetch(LATEST_URL); latest=base.clean_text(latest_raw)
    release_raw,release_final=base.fetch(RELEASE_URL); reltext=base.clean_text(release_raw)

    qmatch=re.search(r"Labor productivity \(output per hour\)\s+([+-]?[\d.]+)%\s+in\s+(\d)(?:st|nd|rd|th) Qtr of (20\d{2})",latest,re.I)
    if not qmatch: raise RuntimeError('BLS latest-numbers quarter/productivity not parsed')
    prod_q=float(qmatch.group(1)); q=int(qmatch.group(2)); year=int(qmatch.group(3))

    umatch=re.search(r"NONFARM BUSINESS SECTOR:.*?Unit labor costs\s+([+-]?[\d.]+)%",latest,re.I|re.S)
    if not umatch: raise RuntimeError('BLS latest-numbers nonfarm ULC not parsed')
    ulc_q=float(umatch.group(1))

    mblock=re.search(r"MANUFACTURING SECTOR:(.*?)(?:Total Factor Productivity|$)",latest,re.I|re.S)
    mtext=mblock.group(1) if mblock else latest
    mp=num(mtext,r"Labor productivity \(output per hour\)\s+([+-]?[\d.]+)%")
    mulc=num(mtext,r"Unit labor costs\s+([+-]?[\d.]+)%")

    ordinals={1:'first',2:'second',3:'third',4:'fourth'}
    qphrase=f"{ordinals[q]} quarter of {year}"
    py=num(reltext,rf"From the same quarter a year ago, nonfarm business sector labor productivity (?:increased|rose)\s+([\d.]+)\s+percent(?: in the {qphrase})?")
    uy=num(reltext,r"Unit labor costs increased\s+([\d.]+)\s+percent over the last four quarters")

    share=num(reltext,rf"labor share.*?was\s+([\d.]+)\s+percent in the {qphrase}",re.I|re.S)
    if share is None:
        share=num(reltext,r"labor share.*?was\s+([\d.]+)\s+percent",re.I|re.S)

    cycle=num(reltext,r"current business cycle.*?labor productivity has grown at an annualized rate of\s+([\d.]+)\s+percent",re.I|re.S)
    realcomp=None
    rm=re.search(rf"Real hourly compensation.*?\s+(increased|decreased)\s+([\d.]+)\s+percent in the {qphrase}",reltext,re.I|re.S)
    if rm:
        realcomp=(-1 if rm.group(1).lower().startswith('decreas') else 1)*float(rm.group(2))

    # Validate that official headline values are coherent before using them.
    if mp is None or mulc is None:
        raise RuntimeError('BLS latest-numbers manufacturing values not parsed')

    if prod_q>=1.3 and ulc_q<=2.0 and mulc<=1.0:
        regime='생산성 개선·비용 압력 완화 — AI 공급효과에 유리'
    elif prod_q<=1.0 and ulc_q>=3.0:
        regime='생산성 둔화·비용 압력 확대 — AI 수요·물가 위험'
    else:
        regime='혼합 — 생산성 효과 추가 확인'

    revised='(r)' in latest or 'revised' in reltext.lower()
    return {
        'source_kind':'BLS',
        'key':f'{year}년 {q}분기'+(' 수정치' if revised else ''),
        'date':base.release_date(reltext) or f'{year}-Q{q}',
        'productivity_qoq_saar':prod_q,'productivity_yoy':py,
        'ulc_qoq_saar':ulc_q,'ulc_yoy':uy,
        'labor_share':share,'manufacturing_productivity':mp,'manufacturing_ulc':mulc,
        'cycle_productivity_ann':cycle,'real_hourly_comp':realcomp,
        'regime':regime,'url':release_final,
        'latest_numbers_url':latest_final,
    }

base.bls_prod_snapshot=robust_bls_prod_snapshot

if __name__=='__main__':
    base.main()
