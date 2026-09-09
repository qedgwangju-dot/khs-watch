#!/usr/bin/env python3
"""Official-BLS parser override for warsh_new_axes_watch."""
import re
import warsh_new_axes_watch as base

base.BLS_PROD_URL='https://www.bls.gov/news.release/prod2.htm'

QMAP={'First':1,'Second':2,'Third':3,'Fourth':4}


def num(text,pattern,flags=re.I):
    m=re.search(pattern,text,flags)
    return float(m.group(1)) if m else None


def signed(word,val):
    v=float(val)
    return -v if word.lower().startswith('decreas') else v


def robust_bls_prod_snapshot():
    raw,final=base.fetch(base.BLS_PROD_URL); text=base.clean_text(raw)
    hdr=re.search(r'(First|Second|Third|Fourth) Quarter\s+(20\d{2})(?:,\s*(Preliminary|Revised))?',text,re.I)
    if not hdr: raise RuntimeError('BLS productivity quarter header not parsed')
    qword=hdr.group(1).capitalize(); year=int(hdr.group(2)); q=QMAP[qword]
    qphrase=f"{qword.lower()} quarter of {year}"

    p=num(text,rf"Nonfarm business sector labor productivity (?:increased|rose)(?: at an? [\d.]+-percent annual rate)?\s*([\d.]+)?\s*percent in the {qphrase}")
    # Current releases use a plain 'increased X percent' sentence. Handle that explicitly.
    if p is None:
        p=num(text,rf"Nonfarm business sector labor productivity increased\s+([\d.]+)\s+percent in the {qphrase}")
    py=num(text,rf"From the same quarter a year ago, nonfarm business sector labor productivity increased\s+([\d.]+)\s+percent")

    m=re.search(rf"Unit labor costs in the nonfarm business sector\s+(increased|decreased)\s+([\d.]+)\s+percent in the {qphrase}",text,re.I)
    uq=signed(m.group(1),m.group(2)) if m else None
    uy=num(text,r"Unit labor costs increased\s+([\d.]+)\s+percent over the last four quarters")
    share=num(text,rf"labor share.*?was\s+([\d.]+)\s+percent in the {qphrase}",re.I|re.S)

    mp=num(text,rf"(?:Manufacturing sector|Total manufacturing sector) labor productivity increased\s+([\d.]+)\s+percent in the {qphrase}")
    mm=re.search(rf"Unit labor costs in the total manufacturing sector\s+(increased|decreased)\s+([\d.]+)\s+percent in the {qphrase}",text,re.I)
    mulc=signed(mm.group(1),mm.group(2)) if mm else None
    cycle=num(text,r"current business cycle.*?labor productivity has grown at an annualized rate of\s+([\d.]+)\s+percent",re.I|re.S)
    mr=re.search(rf"Real hourly compensation.*?\s+(increased|decreased)\s+([\d.]+)\s+percent in the {qphrase}",text,re.I|re.S)
    realcomp=signed(mr.group(1),mr.group(2)) if mr else None

    # Table A1 fallback. The cleaned HTML contains the table row in this order:
    # productivity, output, hours, hourly comp, real hourly comp, unit labor costs.
    if p is None or uq is None:
        row=re.search(r"Nonfarm business\s+Previous quarter\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)",text,re.I)
        if row:
            p=float(row.group(1)); realcomp=float(row.group(5)); uq=float(row.group(6))
    if py is None:
        row=re.search(r"Nonfarm business\s+A year ago\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)",text,re.I)
        if row: py=float(row.group(1)); uy=float(row.group(6))
    if mp is None or mulc is None:
        row=re.search(r"Manufacturing\s+Previous quarter\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)",text,re.I)
        if row: mp=float(row.group(1)); mulc=float(row.group(6))

    if p is None or uq is None: raise RuntimeError('BLS official productivity values not parsed')
    if p>=1.3 and uq<=2.0 and (mulc is None or mulc<=1.0):
        regime='생산성 개선·비용 압력 완화 — AI 공급효과에 유리'
    elif p<=1.0 and uq>=3.0:
        regime='생산성 둔화·비용 압력 확대 — AI 수요·물가 위험'
    else: regime='혼합 — 생산성 효과 추가 확인'
    revised=(hdr.group(3) or '').lower()=='revised'
    return {'source_kind':'BLS','key':f'{year}년 {q}분기'+(' 수정치' if revised else ''),
            'date':base.release_date(text) or f'{year}-Q{q}',
            'productivity_qoq_saar':p,'productivity_yoy':py,'ulc_qoq_saar':uq,'ulc_yoy':uy,
            'labor_share':share,'manufacturing_productivity':mp,'manufacturing_ulc':mulc,
            'cycle_productivity_ann':cycle,'real_hourly_comp':realcomp,'regime':regime,'url':final}

base.bls_prod_snapshot=robust_bls_prod_snapshot

if __name__=='__main__':
    base.main()
