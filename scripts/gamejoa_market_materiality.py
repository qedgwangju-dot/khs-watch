#!/usr/bin/env python3
"""Source-only materiality evidence, without issuer lists or confirmed-only gates."""

from __future__ import annotations

import re
import datetime as dt
import hashlib
import json
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


VERSION = 85
OIL_PRICE = r"(?<![가-힣])(?:국제|고|저)?유가(?!증권)"
ENERGY_SUBJECT = (
    rf"원유|비축유|{OIL_PRICE}|브렌트|천연가스|운임|호르무즈|홍해|중동|이란|이스라엘|우크라이나|러시아|구리|리튬|"
    r"\boil\b|brent|wti|\bgas\b|hormuz|iran|ukraine|russia|copper|lithium"
)
EARLY_SIGNAL = re.compile(
    r"검토|추진|협상|논의|가능성|예정|계획|컨센서스|전망치|추정치|consensus|전망(?!치|을|보다)|예상(?!치|을|보다)|관측|소식통|제안|의견수렴|입법예고|"
    r"건의|요청|요구|제시|모색|촉구|해야|권고|제언|우려|필요|목표|보인다|나서야|시급|밑돌\s*듯|합의\s*(?:안\s*(?:됐|되)|하지\s*않)|미합의|consider|propos|draft|talks|negotiat|forecast|sources say|reportedly|\b(?:may|could|should|target|aim|expected)\b", re.I,
)
HEADLINE_EARLY = re.compile(
    r"검토|협상|논의|가능성|관측|소식통|제안|제언|권고|해야|바꿔야|줄여야|늘려야|우려|전망$|예상$|"
    r"consider|propos|draft|forecast|sources say", re.I,
)
BACKGROUND = re.compile(
    r"^\d{4}년\s+설립|^(?:한편\s*)?(?:앞서\s|지난해|작년|과거|기존에는|종전에는|previously|last year)\b|"
    r"설립된 회사|설립된 기업|설립 이후 누적|창립 이래|\d+\s*여?\s*년간.{0,130}(?:공급|협력|제공)해\s*왔다|has historically", re.I,
)
PAST_ACTION = re.compile(r"지난\s*(?:\d{1,2}월|달|해)|과거\s*\d{4}년", re.I)
COMPANY_PROFILE = re.compile(
    r"(?:분야|부문|업계)의\s*(?:글로벌\s*)?(?:선도\s*)?기업으로|"
    r"(?:기업|회사|업체)(?:으로|로)\s*[^.!?]{0,180}(?:공급한다|제공한다|운영한다)|"
    r"^(?:회사는\s*)?\d{4}년\s*설립(?:돼|되어|됐|되었)|"
    r"전\s*세계\s*직원은.{0,20}(?:명|넘)|company profile|is a (?:global|leading) provider", re.I,
)
ACCOUNTING_NOTE = re.compile(r"환율\s*환산|매출\s*인식.{0,100}기말\s*조정|기간\s*귀속.{0,80}최종\s*수치", re.I)
QUANTITY = re.compile(r"\d[\d,.]*\s*(?:%|bp\b|조\s*원|억\s*원|만\s*원|달러|유로|억원|조원|억달러|billion|million)", re.I)
SOFT_HEADLINE = re.compile(
    r"협력|협약|회동|만났|만났다|맞손|방문|비전|극찬|낙관|신제품|출시|공개|"
    r"협력 강화|동반 성장|동반성장|혁신\s*전략|전략\s*발표|강연|conference|presentation|partnership|meeting|visit|launch|unveil", re.I,
)
ROUTINE_HEADLINE = re.compile(
    r"봉사|기부|나눔|문화행사|체육대회|기념촬영|시상|(?:상|어워드|어워즈).{0,12}수상|수상$|브랜드상|"
    r"할인 행사|할인행사|사은품|경품|체험행사|비전 선포|응원|격려|인스타툰|론칭\s*이벤트|"
    r"관광객\s*공략|기획전|팝업\s*스토어|공원|정원|보고회|\d+주년|volunteer|charity|brand award|giveaway|ceremonial", re.I,
)
REGIONAL_CPI = re.compile(
    r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주).{0,12}소비자물가|"
    r"지역(?:별|의)?\s*소비자물가|regional consumer prices", re.I,
)
RETAIL_PRODUCT_METRIC = re.compile(
    r"매장당\s*매출|(?:키즈|신발|커피|패션).{0,25}(?:매출|판매)|(?:매출|판매).{0,20}(?:매장당|신발|커피)|"
    r"쇼핑|플래그십\s*스토어|sales per store|kids.{0,20}sales", re.I,
)
ROUTINE_PERSONNEL = re.compile(r"사장단\s*인사|임원\s*인사|이사회\s*의장.{0,15}내정", re.I)
STAFF_APPOINTMENT = re.compile(r"(?:변호사|전문가|고문|자문위원|임원|대표|사장|CEO).{0,25}(?:영입|선임|합류)|(?:영입|선임).{0,25}(?:변호사|고문|자문위원|대표|사장|CEO)|(?:수장|이사장|원장)\s*후보.{0,20}적격|staff appointment|hires? counsel", re.I)
ROUTINE_FOREGROUND = re.compile(r"(?:상|어워드|어워즈).{0,12}수상|수상$|포상|표창|(?:선제|조기|정기|임원|사장단)\s*인사|(?:도서|서적).{0,20}(?:출간|인기|관심)|book promotion", re.I)
DIRECT_HEADLINE_CHANGE = re.compile(r"(?:매출|영업이익|순이익|가이던스).{0,20}(?:증가|감소|상향|하향|상회|하회)|(?:수주|계약).{0,20}(?:체결|확정|억|조)|(?:공장|생산능력).{0,20}(?:증설|착공|가동)|(?:지분|사업부).{0,20}(?:인수|매각|취득).{0,12}(?:결정|완료|확정)|earnings revision|contract signed", re.I)
PHOTO_DESCRIPTION = re.compile(r"(?:기념촬영|사진촬영|촬영|시공|시연|발언|연설|질문에\s*답)(?:을|를)?\s*하고\s*있다|사진\s*확대", re.I)
VIRAL_DEMONSTRATION = re.compile(r"이색적인\s*장면|패러디|이색\s*영상|바이럴\s*영상|parody|viral video", re.I)
SUPPORT_EVENT = re.compile(r"투자유치\s*(?:지원|가이드|프로그램)|기업설명회|투자자\s*미팅|투자\s*상담회|investment matchmaking|fundraising workshop", re.I)
SPORTS_OWNERSHIP = re.compile(r"구단주|축구\s*구단|야구\s*구단|프로\s*(?:축구|야구)|football club|soccer club|club owner", re.I)
LOCAL_CEREMONY = re.compile(r"나무\s*심기|식목|선포식|기념식|지역\s*축제|tree planting|proclamation ceremony", re.I)
OFFICE_PUBLICITY = re.compile(r"사옥|본사\s*이전|헤드쿼터|새\s*둥지|headquarters|new office", re.I)
OFFICE_ECONOMIC_CHANGE = re.compile(
    r"영업이익|순이익|가이던스|연결\s*실적|공급\s*계약|납품\s*계약|수주|발주|공장|양산|"
    r"임대료|이전\s*비용|현금흐름|자금조달|자사주|배당|(?:사옥|부동산).{0,20}(?:매각|취득|매입)|"
    r"operating profit|guidance|supply contract|factory|rent|relocation cost|cash flow|financing", re.I,
)
PUBLIC_MARKET_BUSINESS_LINK = re.compile(
    r"상장사|상장\s*기업|상장\s*구단|증시\s*상장|코스피|코스닥|나스닥|뉴욕증권거래소|"
    r"영업이익|순이익|가이던스|연결\s*실적|공급\s*계약|납품\s*계약|수주|발주|"
    r"listed company|public company|listed club|nasdaq|nyse|operating profit|guidance|supply contract", re.I,
)
CUMULATIVE_PRODUCT_PR = re.compile(r"누적\s*(?:매출|판매)|cumulative (?:sales|revenue)", re.I)
RETAIL_PRODUCT_CONTEXT = re.compile(r"세탁|화장품|스킨케어|신발|커피|패션|생활용품|laundry|cosmetics|skincare|footwear|coffee", re.I)
ENTERPRISE_CHANGE = re.compile(
    r"영업이익|순이익|가이던스|실적|분기|연결|마진|현금흐름|수주|공급계약|납품계약|공장|양산|인수|합병|규제|관세|주주환원|"
    r"상장|기업공개|자사주|배당|지분|주식\s*(?:매수|매각)|자금조달|유상증자|\bipo\b|"
    r"operating profit|net income|guidance|cash flow|supply contract|factory|acquisition", re.I,
)
PRIVATE_LIFE_FOREGROUND = re.compile(
    r"전남편|전아내|열애|결혼식|음주\s*회동|사적\s*만남|술자리|한잔했|"
    r"(?:배우|가수|아이돌).{0,35}(?:근황|친분|데이트|연애|사생활|인증\s*(?:샷|사진))|"
    r"celebrity romance|private meeting|drinking reunion", re.I,
)
ENTERTAINMENT_MARKET_EVENT = re.compile(
    r"매출|영업(?:이익|익|손실)|순(?:이익|익|손실)|가이던스|현금흐름|"
    r"자사주|주주환원|배당|유상증자|자금조달|기업공개|\bipo\b|"
    r"(?:코스피|코스닥|나스닥|증시)\s*상장|상장\s*(?:추진|신청|승인|철회)|"
    r"(?:주식|지분).{0,25}(?:매수|매도|매각|매입|취득|인수|이전)|"
    r"인수|합병|공급\s*계약|납품\s*계약|수주|발주|설비투자|"
    r"주가|순매수|순매도|거래대금|금리|관세|수출통제|"
    r"operating profit|net (?:income|loss)|revenue|guidance|cash flow|"
    r"buyback|dividend|financing|acquisition|merger|supply contract|stock price", re.I,
)
CUSTOMER_DISCUSSION_SUBJECT = (
    r"공급|고객|구매|생산|공동\s*개발|hbm|파운드리|자율주행|데이터센터|ai.{0,4}(?:반도체|인프라)|"
    r"supply|customer|procurement|co-develop|foundry|autonomous|data cent(?:er|re)"
)
SOCIAL_MEETING_PROOF = re.compile(
    r"음주|술자리|한잔했|인증\s*(?:샷|사진)|(?:회동|만남|친분|근황)[^.!?]{0,20}인증|"
    r"(?:SNS|인스타그램|사진|영상)[^.!?]{0,25}(?:친분|근황)|drinking reunion", re.I,
)
SCOPED_BUSINESS_DISCUSSION = re.compile(
    r"(?:공급|납품|구매|공동\s*개발|생산|투자)[^.!?]{0,40}(?:협상|논의|협력|합의|협약)|"
    r"(?:협상|논의|협력|합의|협약)[^.!?]{0,40}(?:공급|납품|구매|공동\s*개발|생산|투자)|"
    r"(?:supply|procurement|co-development|production|investment).{0,40}(?:talks|discuss|negotiat|agreement)|"
    r"(?:discuss|negotiat).{0,40}(?:supply|procurement|co-development|production|investment)", re.I,
)
HARD_HEADLINE = re.compile(
    r"매출|이익|실적|가이던스|판가|가격|수주|계약|발주|공장|양산|증설|가동|"
    r"상용화|상장|투자유치|투자 유치|출자|자금조달|자사주|주식 매수|주주환원|주식 기부|지분 이전|"
    r"관세|금리|환율|예탁금|순매수|순매도|수출통제|임상|허가|공급부족|코스피|코스닥|증시|"
    r"earnings|guidance|contract|factory|production|tariff|interest rate|buyback", re.I,
)
SPECULATIVE_CONTACT = re.compile(
    r"(?:논의|회동|만남|협의)(?:할|가질|을\s*가질)[^.!?]{0,45}(?:전망|예상|가능성|관측)|"
    r"(?:만날|만나게\s*될)[^.!?]{0,50}(?:전망|예상|가능성)|"
    r"(?:논의|회동|협력)[^.!?]{0,30}할지[^.!?]{0,20}주목|"
    r"(?:may|could|expected to).{0,35}(?:meet|discuss)", re.I,
)
EXPLANATORY_ONLY = re.compile(
    r"(?:의도|취지|배경)[^.!?]{0,50}해석된다|때문이다|"
    r"경험[^.!?]{0,60}이식하려는|원인[^.!?]{0,40}분석했다|"
    r"(?:방식|여부)에\s*따라[^.!?]{0,70}(?:의미|결과)[^.!?]{0,25}달라진다|"
    r"구체적인\s*안이\s*나오기도\s*전에",
)
NEW_EXECUTION = re.compile(
    r"(?:계약|협약)[^.!?]{0,25}(?:체결|서명|취소|확정)|수주했다|"
    r"(?:예산|투자액|설비투자|보조금)[^.!?]{0,55}(?:확정|배정|증액|삭감|공시)|"
    r"(?:법안|규정|고시)[^.!?]{0,30}(?:발의|제정|개정|시행|입법예고)|"
    r"(?:매출|영업이익|가이던스)[^.!?]{0,65}(?:발표했다|공시했다|상향|하향)|"
    r"(?:오늘|이날|최근|\d{1,2}일)[^.!?]{0,80}(?:착공했다|가동을\s*시작|투입했다고|채택했다고)|"
    r"announced.{0,50}(?:contract|guidance|investment)|signed|awarded|approved", re.I,
)


def nonmarket_entertainment_reason(title: str, body: str = "", source_url: str = "") -> str:
    """Use article genre/foreground, never a search-query sector label."""
    foreground = f"{title} {' '.join(source_sentences(body)[:3])}"
    market_event = bool(ENTERTAINMENT_MARKET_EVENT.search(title))
    if PRIVATE_LIFE_FOREGROUND.search(foreground) and not market_event:
        return "private_life_without_business_change"
    try:
        path = urlsplit(source_url).path.lower()
    except ValueError:
        path = ""
    entertainment_section = bool(re.search(r"/(?:entertainment|entertain|showbiz|celebrity)(?:/|$)", path))
    if entertainment_section and not market_event:
        return "entertainment_without_headline_market_event"
    return ""

# Prefer the first event mentioned in the headline, not a sector assigned by
# the classifier. Reuse it for evidence ranking and compact-summary checks.
HEADLINE_FOCUS = tuple((name, re.compile(head, re.I), re.compile(source, re.I)) for name, head, source in (
    ("tax_relief", r"비과세|과세.{0,12}제외|특례\s*(?:관세|방안)|FTA.{0,12}특례", r"비과세|과세.{0,25}제외|특례|특혜관세"),
    ("network_segmentation_policy", r"망분리.{0,20}(?:완화|예외|규제)|(?:완화|예외).{0,20}망분리", r"망분리|규제\s*완화|신청\s*가능\s*대상|선정\s*규모"),
    ("housing_supply_policy", r"대통령.{0,30}부동산.{0,70}(?:대량\s*공급|매수확약)|LH.{0,30}(?:미분양|매수확약)|주택.{0,30}(?:매수확약|매입임대)", r"LH|매수확약|주택|미분양|매입임대"),
    ("cyber_incident", r"해킹|(?:개인|고객)?\s*정보\s*유출|사이버\s*(?:공격|침해)|랜섬웨어|data breach|cyber.?attack|ransomware", r"해킹|정보|유출|침해|긴급\s*점검회의|data breach|cyber.?attack"),
    ("sanctions_exemption", r"제재.*(?:면제|예외)", r"(?:예외|면제|일반\s*허가|general licen[cs]e)"),
    ("monetary_guidance", r"(?:연준|ECB|한국은행).{0,15}(?:의장|총재)", r"(?:금리|통화|정책).{0,90}(?:밝혔|말했|강조|신중|시사|필요)"),
    ("nuclear_warning", r"핵\s*(?:대응|사용|공격|위협)|nuclear.{0,12}(?:threat|response)", r"(?:핵|특별한\s*수단|모든\s*무기).{0,80}(?:대응|사용|경고|위협|준비|불가피)"),
    ("military_reinforcement", r"(?:항모|항공모함|병력).{0,40}(?:추가\s*파견|증강)", r"추가\s*파견|병력.{0,20}증강"),
    ("trading_status", r"거래\s*재개|액면병합|주식병합", r"거래.{0,12}재개|재개.{0,12}거래|액면병합|주식병합"),
    ("trading_rule", r"단주|최소\s*(?:매매|거래)\s*(?:수량|단위)|시간외\s*종가매매", r"단주|매매수량단위|시간외\s*종가매매"),
    ("maritime_attack", r"^(?!.*(?:임박|가능성|경고|위협|우려)).*?(?:호르무즈|홍해).{0,35}(?:공격|피격)", r"공격|피격|발사체|화재"),
    ("production_target", r"생산\s*(?:목표|할당량).{0,25}(?:동결|유지|확대|축소)", r"생산\s*(?:목표|할당량)"),
    ("facility_approval", r"(?:FDA|당국).{0,45}생산\s*설비.{0,15}승인", r"승인|생산\s*설비"),
    ("nav_forecast", r"주당\s*NAV.{0,35}전망", r"주당\s*(?:순자산가치|NAV)"),
    ("management_change", r"(?:CFO|CEO|최고재무책임자|최고경영자).{0,30}(?:사임|해임|교체)", r"사임|해임|교체"),
    ("fund_performance", r"ETF.{0,15}(?:순풍|강세|상승|하락|수익률)", r"ETF|수익률"),
    ("sanctions_request", r"제재.{0,30}(?:요청|요구|해야)|sanctions?.{0,30}(?:request|call)", r"제재[^.!?]{0,35}(?:요청|요구|해달라|해야)|sanctions?.{0,35}(?:request|call)"),
    ("economic_response", r"경제\s*전쟁|제재.{0,25}대응", r"경제\s*전쟁|제재|환율|필수\s*물자"),
    ("national_exports", r"수출국|연간\s*수출", r"누적\s*수출|수출액|월간\s*수출"),
    ("authorized_capital", r"수권\s*(?:자본|주식)|authorized (?:capital|shares)", r"수권\s*(?:자본|주식)|authorized (?:capital|shares)"),
    ("asset_financing", r"(?:칩|GPU|데이터센터|설비).{0,25}(?:파는|매각|담보|재임차)|sale.leaseback", r"특수목적기구|\bSPV\b|매각|담보|재임차|sale.leaseback"),
    ("factory_tariff", r"공장.{0,20}(?:안|않|미건설).{0,25}관세", r"공장.{0,160}관세"),
    ("customer_implementation", r"1차\s*시공|초도\s*납품", r"1차\s*시공|초도\s*납품"),
    ("commercial_order", r"수주|공급\s*계약|제조\s*계약|납품\s*계약|발사\s*계약|건설\s*계약|\d+\s*년\s*계약(?!가)|장비\s*공급.{0,20}\d[\d,.]*\s*(?:억|조)", r"수주|발주|계약"),
    ("industrial_partnership", r"(?:SMR|원전|선박|반도체|데이터센터|휴머노이드|자율주행).{0,90}(?:공동\s*검토|공동\s*연구|업무협약|MOU|항로.{0,15}운항\s*검토)", r"업무협약|MOU|공동\s*개발\s*협약"),
    ("industrial_program", r"(?:SMR|원전|양자|반도체|로봇).{0,16}상용화", r"(?:상용화|사업화).{0,50}(?:출범|지원|시행|추진)|(?:출범|지원|시행|추진).{0,50}(?:상용화|사업화)"),
    ("environmental_approval", r"환경(?:영향)?평가.{0,15}(?:통과|완료|면제)", r"최종\s*환경평가|FONSI|환경영향평가서.{0,35}(?:없이|면제)"),
    ("ownership", r"지분.{0,25}(?:인수|매각|취득)|자산.{0,50}(?:인수|매각|취득)|(?:피?인수).{0,25}(?:지분|계약|합의|완료|협상|논의|검토|임박)|인수로|회사\s*인수|(?:결합|합병).{0,12}완료|합병(?!원)|주식.{0,8}(?:판다|매도|매각)", r"지분|인수|매각|매도|취득|거래계획|결합|합병(?!원)|stake|acquir|merger"),
    ("debt_repayment", r"부채.{0,15}상환|대출.{0,15}상환|debt repayment", r"부채|대출|상환|debt|repay"),
    ("equity_compensation", r"주식\s*보상|주식\s*인센티브|성과연동주식|양도제한조건부주식|stock.based compensation|equity compensation", r"주식\s*보상|성과연동주식|양도제한조건부주식|\bPSP\b|\bRSU\b|stock.based compensation|equity compensation"),
    ("labor_negotiation", r"임단협|임금.{0,12}(?:협상|합의)|단체협약", r"임단협|임금|단체협약|잠정합의안|교섭"),
    ("investor_flow", r"(?:외국인|기관|개인|연기금).{0,60}(?:순매수|순매도|팔아|사들|매수|매도|던졌)", r"외국인|기관|개인|연기금"),
    ("shareholder", r"자사주|자기주식|주주환원|배당", r"자사주|자기주식|주주환원|배당|(?:주식|지분).{0,30}(?:매수|취득|매입|처분)|buyback|dividend"),
    ("capital_listing", r"기업공개|\bipo\b|(?:증시|코스피|코스닥|나스닥)\s*상장|상장\s*(?:추진|예정|연기|철회|신청|승인)|신규\s*상장|ETF.{0,15}(?:출시|상장)", r"기업공개|\bipo\b|상장(?!지수)|ETF.{0,80}출시"),
    ("financing", r"자금.{0,12}(?:투입|조달|유입)|대출|전환사채|전환\s*(?:선순위)?\s*채권|회사채\s*발행|funding|financing|loan|convertible (?:bond|note|debt)", r"자금|외부\s*자본|대출|투자(?!자)|조달|전환사채|전환\s*(?:선순위)?\s*채권|출자|납입|증자|확정된\s*사항|funding|financing|loan|convertible (?:bond|note|debt)"),
    ("capital_spending", r"설비투자|capex|자본지출|capital expenditure|(?:AI|인공지능)\s*(?:인프라\s*)?투자", r"설비투자|capex|자본지출|capital expenditure|(?:컴퓨터|컴퓨팅|설비|장비|인프라).{0,35}투자"),
    ("industry_market_share", r"점유율|시장.{0,8}(?:\d위|순위)", r"점유율|market share"),
    ("trade_threat", r"관세.{0,35}(?:위협|경고|두\s*배|2\s*배)|(?:두\s*배|2\s*배).{0,15}(?:청구|관세)|알래스카.{0,55}(?:청구|부담|압박)|tariff.{0,30}(?:threat|doubl)|doubl.{0,15}tariff", r"관세|청구|tariff|charge"),
    ("project_response", r"(?:정부|산업부).{0,45}(?:팩트시트|합의.{0,15}없는|사업.{0,15}미정)", r"팩트시트|공동\s*합의|추진\s*여부"),
    ("stockpile_release", r"비축유|비축\s*원유|G7.{0,30}(?:원유|경유).{0,20}방출|oil reserves|stockpile", r"비축\s*(?:유|원유|경유)|석유\s*비축|oil reserves|stockpile"),
    ("mortgage_rate", r"주담대|모기지|주택담보대출", r"주담대|모기지|주택담보대출|mortgage"),
    ("macro_release", r"\bcpi\b|\bpce\b|\bppi\b|\bgdp\b|고용(?!량)|비농업\s*일자리|실업률|물가|건설지출", r"cpi|pce|ppi|gdp|고용(?!량)|비농업\s*일자리|실업|물가|건설지출|인플레이션|inflation|payroll"),
    ("market_macro_response", r"(?=.*(?:뉴욕마감|뉴욕증시|월가))(?=.*(?:고용|취업|실업|CPI|FOMC|연준))", r"고용|비농업|실업|CPI|FOMC|연준|나스닥|S&P\s*500|다우"),
    ("equity_index", r"(?:나스닥|S&P\s*500|다우|코스피|코스닥).{0,20}(?:사상\s*최고|역대\s*최고|신고가)", r"나스닥|S&P\s*500|다우|코스피|코스닥"),
    ("equity_index_outlook", r"(?:코스피|코스닥|나스닥|S&P\s*500)[^A-Za-z0-9가-힣]{0,6}\d[\d,]*(?:[~∼-]\d[\d,]*)?.{0,25}(?:전망|간다|목표)", r"코스피|코스닥|나스닥|S&P\s*500"),
    ("public_compute_allocation", r"(?:정부|공공).{0,20}GPU.{0,40}(?:신청|배정|지원)", r"GPU.{0,80}(?:신청|배정|지원)"),
    ("export_results", r"수출(?:액|실적|량)|수출.{0,20}(?:\d위|역대|최대|최저|증가|감소)", r"수출(?:액|실적|량)|수출.{0,45}(?:\d|최대|최저)"),
    ("project_cost", r"(?:LNG|원전|데이터센터|발전소|공장).{0,20}(?:사업비|건설비|사업\s*비용)", r"(?:LNG|원전|데이터센터|발전소|공장).{0,40}(?:사업비|건설비|비용)"),
    ("breadth", r"(?:상승|하락)\s*종목|순환매|쏠림|AI\s*(?:빼면|제외하면)|증시\s*내부|시장\s*내부|(?:S&P500|코스피|코스닥|나스닥).{0,30}종목.{0,20}%.{0,15}(?:하락|상승)", r"(?:오른|내린|상승|하락)\s*종목|종목.{0,20}%.{0,15}(?:하락|상승)|순환매|쏠림|순매수|순매도|자금.{0,12}이동"),
    ("retail_fuel", r"주유소.{0,30}(?:기름값|휘발유|경유)|(?:휘발유|경유).{0,15}(?:L당|리터당)", r"(?:휘발유|경유).{0,55}(?:L|리터)(?:\(L\))?\s*당\s*\d[\d,.]*원"),
    ("commodity_price_release", r"세계\s*식량\s*가격|식량가격지수|FAO.{0,20}(?:식량|지수)", r"(?:세계\s*)?식량\s*가격\s*지수.{0,45}\d"),
    ("product_sales_mix", r"판매.{0,35}(?:비중|중.{0,15}(?:친환경|전기차|하이브리드))|제품\s*믹스|판매\s*믹스", r"판매(?:량|대수|비중)?.{0,100}(?:차지|비중|%)"),
    ("product_volume", r"[1-4]분기\s*판매\s*\d|판매량.{0,25}(?:증가|감소)", r"판매량|출고"),
    ("energy_import_mix", r"원유\s*도입\s*비중", r"원유\s*도입\s*비중|(?:중동|미주|사우디|미국)산"),
    ("energy_supply", rf"브렌트|{OIL_PRICE}|원유|천연가스|호르무즈|홍해|유조선|운임|\bbrent\b|\boil\b|hormuz|tanker", rf"브렌트|{OIL_PRICE}|원유|천연가스|호르무즈|홍해|유조선|운임|항행|통항|brent|\boil\b|hormuz|tanker|shipping"),
    ("bond_yield", r"금리|국채.{0,8}(?:투매|수익률)|bond yields|treasury yields", r"금리|국채.{0,8}수익률|bond yields|treasury yields|interest rates"),
    ("fx", r"환율|약달러|강달러|달러화|원[·/]달러|달러[·/]원|\bndf\b|exchange rate", r"환율|달러화|달러[·/]원|원[·/]달러|\bndf\b|exchange rate|dollar"),
    ("production_capacity", r"증설|캐파|생산능력|착공|가동\s*(?:중단|시작)|생산\s*중단|production capacity|capacity expansion|production halt", r"증설|캐파|생산능력|착공|가동|생산|production capacity|capacity|construction|production"),
    ("project_buildout", r"데이터센터\s*(?:구축|건설)|data cent(?:er|re).{0,15}(?:build|construction)", r"데이터센터[^.!?]{0,80}(?:구축|건설)|(?:구축|건설).{0,30}데이터센터|data cent(?:er|re).{0,80}(?:build|construction)|(?:build|construction).{0,30}data cent(?:er|re)"),
    ("research_spending", r"r&d|연구개발", r"r&d|연구개발"),
    ("research_result", r"연구\s*성과|실험\s*결과|벤치마크", r"벤치마크|실험\s*결과|연구\s*결과"),
    ("model_efficiency", r"토큰\s*(?:처리량|량)|추론\s*(?:속도|비용).{0,15}\d", r"토큰\s*(?:처리량|량).{0,35}\d|추론\s*(?:속도|비용).{0,35}\d"),
    ("analyst_revision", r"목표주가|목표가|투자의견|\[美특징주\].{0,60}(?:전망|평가)", r"목표주가|목표가|투자의견"),
    ("industry_outlook", r"투자\s*호재에도|먼저\s*돈\s*되는|수혜[株주].{0,12}분석", r"수요|발주|수주|시장\s*규모|demand|orders|market size"),
    ("technical_standard", r"(?:표준|규격).{0,15}(?:발표|제정)|(?:발표|제정).{0,15}(?:표준|규격)", r"표준|규격"),
    ("industrial_architecture", r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model", r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model"),
    ("space_turnaround", r"열\s*차폐|재진입|재발사|재비행|heat[ -]shield|thermal protection|re.?entry|reflight|relaunch|turnaround", r"열\s*차폐|재진입|재발사|재비행|타일|정비|heat[ -]shield|thermal protection|re.?entry|reflight|relaunch|turnaround"),
    ("space_propellant_storage", r"추진제|\bzbo\b|무손실\s*저장|zero[ -]boil[ -]off|propellant", r"추진제|\bzbo\b|무손실\s*저장|zero[ -]boil[ -]off|propellant"),
    ("science_milestone", r"극저온|양자|효소|cryogenic|quantum|enzyme", r"극저온|양자|효소|cryogenic|quantum|enzyme"),
    ("space_execution", r"위성|궤도|발사한도|발사계약|환경심사|환경영향평가|주파수|우주로.{0,12}(?:쐈|발사)|우주.{0,15}(?:시험|실험)|satellite|orbital|launch contract|spectrum", r"위성|궤도|발사|교신|환경심사|환경영향평가|주파수|satellite|orbital|launch|spectrum"),
    ("fund_result", r"펀드.{0,20}(?:손실|청산|만기|수익)|(?:손실|청산).{0,20}펀드", r"손실|청산|수익률|loss|liquidat|returns"),
    ("memory", r"hbm|hbf|메모리|낸드|D램|dram", r"hbm|hbf|메모리|낸드|D램|dram"),
    ("earnings", r"매출|영업(?:이익|익|손실)|순(?:이익|익|손실)|실적|가이던스|earnings|guidance", r"매출|영업(?:이익|익|손실)|순(?:이익|익|손실)|실적|가이던스|revenue|profit|earnings|guidance"),
))
MONTH = re.compile(r"(?<!\d)(1[0-2]|[1-9])월")
ASPIRATION = re.compile(r"관계자는|기대한다|기대된다|키워나|키워\s*나|키우고|성장축|비전을|최선을|응원|company spokesperson", re.I)
DENIAL_HEADLINE = re.compile(r"확정.{0,8}(?:아냐|아니|않)|합의\s*(?:안\s*(?:됐|되)|하지\s*않|에\s*없는)|미합의|미확정|부인|사실무근|denies|not final", re.I)
DENIAL_SOURCE = re.compile(r"확정[^.!?]{0,20}(?:아냐|아니|않|없)|합의\s*(?:안\s*(?:됐|되)|하지\s*않|에\s*없는)|팩트시트[^.!?]{0,40}(?:없|포함[^.!?]{0,15}않)|미합의|미확정|부인|사실무근|denies|not final", re.I)
SOLICITATION_HEADLINE = re.compile(r"잡으려면|활용\s*가능한\s*기회|스탁론|주식자금.{0,20}(?:대출|상담|마련)|투자자금.{0,20}(?:상담|마련)", re.I)
SOLICITATION_BODY = re.compile(r"스탁론|고객상담|상담센터|주식자금\s*(?:상품|대출)|투자금을\s*준비|신용.{0,8}대환|loan consultation", re.I)
TACTICAL_HEADLINE = re.compile(r"(?:미사일|무기|드론).{0,25}(?:첫\s*실전|실전\s*투입|시험\s*발사)|(?:진지|전차).{0,15}(?:타격|격파)|격추", re.I)
ECONOMIC_GEOPOLITICS = re.compile(
    rf"에너지\s*시설|정유|유전|송유관|원유|{OIL_PRICE}|가스|항만|물류|유조선|운임|호르무즈|홍해|통항|봉쇄|"
    r"수출|수입|제재|국방\s*예산|방위\s*예산|조달|수주|공급계약|휴전|협상|접촉|"
    r"확전|전면전|전쟁\s*(?:선포|확대)|핵(?:무기)?\s*(?:사용|위협|공격)|핵전쟁|참전|"
    r"추가\s*(?:공격|공습)|공격\s*임박|항공\s*모함|항공모함|항모|병력\s*증강|"
    r"energy|refiner|pipeline|oil|gas|port|shipping|tanker|hormuz|blockade|sanction|procurement|contract|ceasefire|talks|negotiat|escalat", re.I,
)
LOCAL_AUTHORITY = re.compile(
    r"도지사|도의원|시의원|군의원|구의원|시의회|군의회|구의회|지방정부|지자체|지방자치단체|"
    r"(?:경기|강원|경북|경남|충북|충남|전북|전남|제주)(?:특별자치)?도|"
    r"(?<![가-힣])[가-힣]{2,8}(?:시|군|구)(?:청)?(?:은|는|이|가|[,\s])", re.I,
)
LOCAL_ADMINISTRATIVE_TOPIC = re.compile(
    r"(?:평화경제|관광)특구|관광\s*(?:거점|개발)|주민|편입지역|생계지원|주거|주택공급\s*(?:전략|구상)|"
    r"도시계획|지역특화|지역경제|규제\s*개선|규제개선|지역\s*생산\s*전력|"
    r"현안|건의|요청|제안|전략.{0,8}제시|돌파구|모색|지정\s*신청", re.I,
)
POLICY_ADVOCACY = re.compile(r"건의|요청|요구|촉구|과제로\s*제시|의견이\s*나왔다|논의해\s*나가겠다|해소될\s*수\s*있도록")
FORMAL_POLICY_EXECUTION = re.compile(
    r"입법예고(?:했다|한다)|법안.{0,12}(?:발의했다|제출했다|통과했다)|"
    r"(?:고시|조례|규제|규정).{0,20}(?:개정했다|개정한다|제정했다|시행한다|의결했다|완화했다)|"
    r"시행일.{0,15}확정|행정명령.{0,15}서명|(?:인허가|허가|승인).{0,10}(?:완료|획득|결정)|"
    r"(?:허가|승인)했다|enacted|permit approved", re.I,
)
INDUSTRIAL_ASSET = re.compile(
    r"공장|생산|설비|반도체|데이터센터|전력|발전소|송전|배전|항만|물류|산업단지|"
    r"factory|production|data center|power|port|industrial park", re.I,
)


def local_administration_without_execution(title: str, lead: str, evidence: list[dict]) -> bool:
    """A local proposal or notional project budget is not a business commitment."""
    foreground = f"{title} {lead}"
    if not LOCAL_AUTHORITY.search(foreground) or not LOCAL_ADMINISTRATIVE_TOPIC.search(foreground):
        return False
    direct_kinds = {
        "commercial_order", "customer_supply_start", "procurement_execution_stage", "earnings_or_guidance",
        "licensing_cashflow", "corporate_ownership_execution", "climate_operational_damage",
    }
    for item in evidence:
        sentence, kind = item["source_excerpt"], item["kind"]
        if kind in direct_kinds:
            return False
        if POLICY_ADVOCACY.search(sentence) or not INDUSTRIAL_ASSET.search(sentence):
            continue
        if kind == "policy_scope_or_stage" and FORMAL_POLICY_EXECUTION.search(sentence):
            return False
        if kind == "physical_supply_or_capacity" and re.search(
            r"착공했다|착공한다|착공식을|가동을\s*시작|가동했다|생산을\s*중단|건설\s*계약.{0,10}체결|"
            r"(?:공장|데이터센터|발전소|산업단지).{0,40}(?:허가했다|승인했다|승인받|허가받)|"
            r"construction started|production halted", sentence, re.I,
        ):
            return False
        if kind == "capital_or_shareholder_action" and re.search(
            r"출자계약.{0,12}체결|금융\s*종결|자금.{0,12}납입|대출.{0,12}승인|"
            r"투자.{0,12}집행했다|financing closed|funding disbursed", sentence, re.I,
        ):
            return False
    return True


@lru_cache(maxsize=2048)
def focus_kind(title: str) -> str:
    # A scoped tax treatment is the event; oil is only its subject.
    if HEADLINE_FOCUS[0][1].search(title or ""):
        return "tax_relief"
    revision = re.search(r"목표(?:주가|가).{0,18}(?:[↑↓]|상향|하향|높여|낮춰|올려|내려)", title or "")
    if revision:
        primary = title[:revision.start()]
        if (re.search(r"(?:상반기|하반기|[1-4]분기).{0,25}(?:매출|영업(?:이익|익|손실)|순(?:이익|익|손실)).{0,12}\d", primary)
                and not re.search(r"전망|추정|예상|컨센서스", primary)):
            return "earnings"
        return "analyst_revision"
    if re.search(r"\[(?:美)?특징주\]|(?:주가|주식).{0,25}(?:급등|급락|강세|약세)|장\s*초반|장중", title or "") and re.search(
        r"급등|급락|강세|약세|상승|하락", title or "",
    ):
        return "intraday_equity"
    if re.search(r"청약\s*경쟁률", title or ""):
        return "housing_demand"
    if re.search(r"수주.{0,30}비중", title or "") and not re.search(r"추가\s*수주|신규\s*계약|수주액\s*변경", title or ""):
        return "backlog_mix"
    if (re.search(r"국책과제.{0,15}(?:수주|선정)", title or "")
            and not re.search(r"매출|영업이익|실적|목표주가", title or "")):
        return "research_award"
    if (re.search(r"MLCC|AOI|자동광학|검사장비", title or "", re.I)
            and re.search(r"채택|공정\s*진입|초도\s*납품", title or "")
            and not re.search(r"영업이익|실적|목표주가|수주액|공급\s*계약", title or "")):
        return "industrial_customer_adoption"
    if re.search(r"장기\s*마케팅\s*계약|장기\s*오프테이크\s*계약", title or ""):
        return "marketing_offtake"
    if (re.search(r"항공", title or "")
            and re.search(r"운수권|취항\s*기반|(?:노선|취항).{0,20}확대|증편", title or "")
            and not re.search(r"매출|영업(?:이익|익)|순(?:이익|익)|실적|목표(?:주가|가)|자금조달|수주|공급\s*계약", title or "")):
        return "aviation_network"
    if re.search(r"(?:군사력|병력|항모|항공모함).{0,30}(?:배치|파견|증강)", title or ""):
        return "military_reinforcement"
    if next(head for name, head, _source in HEADLINE_FOCUS if name == "industrial_partnership").search(title or ""):
        return "industrial_partnership"
    for kind in ("network_segmentation_policy", "housing_supply_policy", "maritime_attack", "production_target", "facility_approval", "nav_forecast"):
        if kind == "network_segmentation_policy" and re.search(r"유출|침해\s*사고|피해", title or ""):
            continue
        if next(head for name, head, _source in HEADLINE_FOCUS if name == kind).search(title or ""):
            return kind
    if re.search(r"ETF.{0,15}(?:출시|상장)", title or "", re.I):
        return "capital_listing"
    if re.search(r"국고채\s*발행.{0,15}(?:축소|확대|증가|감소)", title or ""):
        return "sovereign_issuance"
    if re.search(r"자금\s*조달|외부\s*자본|funding|financing", title or "", re.I):
        return "financing"
    if re.search(r"성과급|보상\s*비용", title or "") and re.search(r"매출|이익|마진|수익성|실적", title or ""):
        return "earnings"
    if next(head for name, head, _source in HEADLINE_FOCUS if name == "investor_flow").search(title or ""):
        return "investor_flow"
    # The changed measure/action outranks a company or commodity mentioned
    # earlier in a headline (e.g. DRAM share, not generic memory demand).
    for kind in ("project_response", "capital_spending", "industry_market_share", "trade_threat", "stockpile_release", "equity_compensation", "commercial_order", "breadth", "sanctions_request", "market_macro_response", "equity_index"):
        if next(head for name, head, _source in HEADLINE_FOCUS if name == kind).search(title or ""):
            return kind
    matches = [(match.start(), index, kind) for index, (kind, headline, _source) in enumerate(HEADLINE_FOCUS)
               if (match := headline.search(title or "")) is not None]
    return min(matches)[2] if matches else ""


def focus_matches(title: str, sentence: str) -> bool:
    if COMPANY_PROFILE.search(sentence or "") or ACCOUNTING_NOTE.search(sentence or ""):
        return False
    if DENIAL_HEADLINE.search(title) and not DENIAL_SOURCE.search(sentence):
        return False
    kind = focus_kind(title)
    if kind == "intraday_equity":
        return bool(intraday_equity_observations(title, sentence))
    if kind == "housing_demand":
        return bool(re.search(r"전국\s*1순위\s*평균\s*청약\s*경쟁률", sentence)
                    and re.search(r"\d+(?:\.\d+)?\s*대\s*1", sentence))
    if kind == "backlog_mix":
        return bool(re.search(r"수주\s*잔고", sentence) and re.search(SOURCE_MONEY, sentence)
                    and re.search(r"비중.{0,15}\d+(?:\.\d+)?%", sentence)
                    and re.search(r"분석했다|밝혔다|발표했다", sentence))
    if kind == "research_award":
        return bool(re.search(r"국책과제", sentence) and re.search(r"수주|선정", sentence)
                    and re.search(r"\d{1,2}일\s*밝혔다", sentence))
    if kind == "industrial_customer_adoption":
        return bool(re.search(r"검사|AOI", sentence, re.I) and re.search(r"장비", sentence)
                    and re.search(r"채택", sentence) and re.search(r"\d{1,2}일\s*밝혔다", sentence))
    if kind == "marketing_offtake":
        return bool(re.search(r"마케팅\s*계약|오프테이크\s*계약", sentence)
                    and re.search(r"체결|서명", sentence))
    if kind == "aviation_network":
        return bool(re.search(r"운수권.{0,30}확보|취항.{0,20}(?:가능|확대)|증편", sentence)
                    and not re.search(r"준비하고|관계자는|기대|방침", sentence))
    if kind == "military_reinforcement":
        return bool(re.search(r"병력|군사력|항모|항공모함", sentence)
                    and re.search(r"배치|파견|증강|지원\s*계획", sentence)
                    and re.search(r"합의|발표|결정|명령|파견했|배치했", sentence)
                    and not re.search(r"피하겠|입장으로\s*보|중재자\s*역할", sentence))
    if kind == "analyst_revision":
        return bool(re.search(r"목표(?:주가|가)|적정\s*주가", sentence)
                    and re.search(r"상향|하향|높였|낮췄|올렸|내렸", sentence)
                    and re.search(SOURCE_MONEY, sentence))
    if kind == "industrial_partnership":
        return bool(re.search(r"SMR|소형모듈원자로|원전|선박|반도체|데이터센터|휴머노이드|자율주행", sentence, re.I)
                    and re.search(r"(?:업무협약|MOU|공동개발\s*협약).{0,25}(?:체결했|서명했|맺었)|(?:체결했|서명했|맺었).{0,25}(?:업무협약|MOU)", sentence, re.I)
                    and not SPECULATIVE_CONTACT.search(sentence))
    if kind == "maritime_attack":
        return bool(re.search(r"선박|유조선|해협", sentence)
                    and re.search(r"공격|피격|회항|발사체|화재", sentence)
                    and re.search(r"보고했|밝혔|전했|재개됐|회항했", sentence)
                    and not re.search(r"될\s*경우|가능성|전망|우려가\s*반영", sentence))
    if kind == "production_target":
        return bool(re.search(r"생산\s*(?:목표|할당량)", sentence)
                    and re.search(r"동결|유지|확대|축소", sentence)
                    and re.search(r"합의|결정|발표|동결하기로", sentence))
    if kind == "facility_approval":
        return bool(re.search(r"승인|미국\s*시장에\s*공급|미국\s*공급", sentence)
                    and re.search(r"생산\s*(?:설비|능력)|원료의약품", sentence)
                    and not re.search(r"컨센서스|예상\s*매출|매출액", sentence))
    if kind == "nav_forecast":
        return bool(re.search(r"주당\s*(?:순자산가치|NAV)", sentence)
                    and re.search(r"대비|기준|증가|예상", sentence))
    if kind == "ownership" and re.search(r"인수|합병", title):
        return bool(re.search(r"인수|합병|완전자회사", sentence))
    if kind == "management_change":
        return bool(re.search(r"CFO|CEO|최고재무책임자|최고경영자", sentence, re.I)
                    and re.search(r"사임|해임|교체", sentence))
    if kind == "fund_performance":
        if re.search(r"美|미국", title) and re.search(r"국내|한국", sentence) and not re.search(r"미국|美", sentence):
            return False
        return bool(re.search(r"ETF|수익률", sentence) and re.search(r"\d+(?:\.\d+)?%|상승|하락|강세", sentence))
    if kind == "trading_rule":
        return bool(re.search(r"단주|매매수량단위|시간외\s*종가매매", sentence)
                    and re.search(r"허용|검토|확대|처분|변경|시행|발표", sentence))
    if kind == "product_volume":
        return bool(re.search(r"판매량|출고", sentence) and (
            re.search(r"\d[\d,.]*(?:만\d[\d,.]*)?대", sentence)
            or re.search(r"\d[\d,.]*%\s*(?:증가|감소|늘|줄)", sentence)
        ))
    if kind == "technical_standard":
        return bool(re.search(r"표준|규격", sentence) and re.search(r"발표|제정|채택", sentence)
                    and re.search(r"JESD\d+[A-Z0-9.-]*|IEEE\s*\d+[A-Z0-9.-]*|ISO\s*\d+[A-Z0-9.-]*", sentence, re.I))
    if kind == "investor_flow":
        actors = [actor for actor in ("외국인", "기관", "개인", "연기금") if actor in title]
        direction = r"순매도|팔아|매도|던졌|쏟아" if re.search(r"순매도|팔아|매도|던졌", title) else r"순매수|사들|매수"
        return bool(any(actor in sentence for actor in actors) and re.search(direction, sentence))
    if kind == "energy_import_mix":
        return bool(re.search(r"원유\s*도입\s*비중", sentence) and QUANTITY.search(sentence))
    if kind == "sovereign_issuance":
        return bool(re.search(r"국고채.{0,20}발행|발행.{0,20}국고채", sentence)
                    and re.search(r"축소|확대|증가|감소|계획|발표|결정", sentence)
                    and QUANTITY.search(sentence))
    if kind == "earnings":
        metric = next((term for term, pattern in (
            (r"영업(?:이익|익|손실)", r"영업(?:이익|익|손실)"),
            (r"순(?:이익|익|손실)", r"순(?:이익|익|손실)"),
            (r"매출(?:액)?", r"매출(?:액)?"),
        ) if re.search(pattern, title)), "")
        if metric and not re.search(metric, sentence):
            return False
    if kind == "bond_yield" and re.search(r"닛케이|항셍|아시아증시", title):
        return bool(re.search(r"닛케이|항셍|아시아증시|페드워치|FedWatch", sentence, re.I))
    if kind == "network_segmentation_policy":
        return bool(
            re.search(r"망분리|규제\s*완화|신청\s*가능\s*대상|선정\s*규모", sentence)
            and re.search(r"선정된다|선정한다|선정할|확대|늘릴|예외.{0,20}허용|완화.{0,15}(?:추진|시행|확대)", sentence)
        )
    if kind == "housing_supply_policy":
        return bool(re.search(r"LH|미분양|매입임대|매수확약", sentence)
                    and re.search(r"매수확약|매수\s*확약|매입.{0,20}(?:지시|결정|확정)", sentence)
                    and re.search(r"지시|결정|확정|시행|발표|밝혔다", sentence))
    if kind == "national_exports":
        return bool(national_export_observation(sentence))
    if kind == "cyber_incident":
        if re.search(r"예방|모의\s*훈련|모의\s*해킹|가상\s*공격|시연|가정|유출될|유출되지|유출로\s*이어지지|피해가\s*없", sentence):
            return False
        incident = bool(
            re.search(r"해킹|사이버|랜섬웨어|침해|(?:개인|고객|임직원)\s*정보|data breach|ransomware", sentence, re.I)
            and re.search(r"유출(?:됐|되었|됐다|되었다)|유출.{0,55}(?:밝혔다|확인했다|확인됐|파악했다|추정했다)|"
                          r"(?:서비스|운영|생산|거래).{0,20}(?:중단됐|중단했다)|피해.{0,20}(?:발생했|봤다)|"
                          r"data breach.{0,35}(?:reported|confirmed)|ransomware.{0,35}(?:halted|disrupted)", sentence, re.I)
        )
        response = bool(
            re.search(r"금융(?:당국|위원장|위원회|감독원장)|금감원장|금융위|금감원", sentence)
            and re.search(r"CEO|최고경영자|금융사\s*대표", sentence, re.I)
            and re.search(r"긴급\s*(?:점검|대응)?\s*회의|긴급\s*소집", sentence)
            and re.search(r"연다|열었다|열\s*예정|개최한다|개최했다|개최할\s*예정|소집해", sentence)
        )
        return incident or response
    if kind == "trading_status":
        return bool(re.search(r"거래.{0,15}재개|재개.{0,15}거래|액면병합|주식병합|보통주.{0,45}범위로\s*병합", sentence)
                    and re.search(r"발표|상정|결정|승인|추진|시행|예정|재개(?:된|됐|한다|일|\s*기준가)|\d+\s*(?:대|:|주를)\s*\d+|announc|approv|plan", sentence, re.I)
                    and not re.search(r"(?:사례|전례)가|일부\s*(?:투자자|애널리스트)|보장할\s*수\s*없", sentence))
    if kind == "authorized_capital":
        return bool(re.search(r"수권\s*(?:자본|주식)|authorized (?:capital|shares)", sentence, re.I)
                    and re.search(r"증액|늘리는|늘리겠|확대|increase|expand", sentence, re.I)
                    and re.search(r"안건|상정|제안|표결|proposal|vote", sentence, re.I)
                    and re.search(r"\d", sentence))
    if kind == "industry_outlook":
        return bool(re.search(r"증권|연구원|리서치|애널리스트|분석가|analyst|research", sentence, re.I)
                    and re.search(r"수요|발주|수주|시장\s*규모|demand|orders|market size", sentence, re.I)
                    and re.search(r"추산|추정|전망|예상|estimate|forecast|expect", sentence, re.I)
                    and QUANTITY.search(sentence))
    if kind == "project_response":
        return bool(re.search(r"팩트시트|공동\s*합의|추진\s*여부", sentence)
                    and re.search(r"없|포함[^.!?]{0,15}않|말하기\s*어렵|밝히기\s*어렵", sentence))
    if kind == "economic_response":
        return bool(re.search(r"대통령|총리|정부|중앙은행", sentence)
                    and re.search(r"경제\s*전쟁|제재", sentence)
                    and re.search(r"새로운\s*조치|대응\s*조치|환율\s*(?:관리|통제)|필수\s*물자", sentence)
                    and re.search(r"도입|발표|시행|검토|결정|밝혔", sentence))
    if kind == "ownership" and "자산" in title:
        return bool("자산" in sentence and re.search(r"인수|매입|취득|매각", sentence))
    if kind == "debt_repayment":
        return bool(re.search(r"부채|대출|debt|loan", sentence, re.I)
                    and re.search(r"상환|repay", sentence, re.I))
    if kind == "industry_market_share":
        return bool(re.search(r"점유율|market share", sentence, re.I)
                    and re.search(r"\d+(?:\.\d+)?\s*%|\d위|\d+(?:\.\d+)?\s*%포인트", sentence))
    if kind == "capital_spending":
        if business_investment_observation(re.sub(r"\((?:약[^)]*|원화\s*환산\s*확인\s*불가)\)", "", sentence)):
            return True
        return bool(re.search(r"설비투자|증설투자|capex|자본지출|capital expenditure|(?:AI|인공지능)\s*(?:인프라\s*)?투자", sentence, re.I)
                    and re.search(r"계획|예상|전망|늘|증가|확대|상향|투입|지출|실시|이르|확정|집행|공시|plan|expect|increas|raise", sentence, re.I))
    if kind == "equity_index":
        return bool(re.search(r"나스닥|S&P\s*500|다우|코스피|코스닥", sentence, re.I)
                    and re.search(r"\d+(?:\.\d+)?%", sentence)
                    and re.search(r"올랐|내렸|상승|하락|마감|기록", sentence)
                    and not re.search(r"전망|예상|가능성|목표|기대", sentence))
    if kind == "equity_index_outlook":
        return bool(re.search(r"증권|리서치|연구원", sentence)
                    and re.search(r"코스피|코스닥|나스닥|S&P\s*500", sentence, re.I)
                    and re.search(r"\d[\d,]*\s*[~∼-]\s*\d[\d,]*", sentence)
                    and re.search(r"전망|예상|목표", sentence))
    if kind == "public_compute_allocation":
        return bool(re.search(r"GPU", sentence, re.I) and re.search(r"신청|배정|지원", sentence)
                    and re.search(r"\d[\d,만]*\s*장", sentence))
    if kind == "trade_threat":
        return bool(re.search(r"관세|청구|tariff|charge", sentence, re.I)
                    and re.search(r"위협|경고|두\s*배|2\s*배|인상|올리|threat|warn|doubl|raise", sentence, re.I))
    if kind == "factory_tariff":
        rates = {re.sub(r"\s+", "", value) for value in re.findall(r"\d+(?:\.\d+)?\s*%", title)}
        source_rates = {re.sub(r"\s+", "", value) for value in re.findall(r"\d+(?:\.\d+)?\s*%", sentence)}
        return bool(
            "공장" in sentence and "관세" in sentence
            and rates.issubset(source_rates)
            and re.search(r"안\s*짓|짓지\s*않|건설하지\s*않|미건설|그렇게\s*하지\s*않으면", sentence)
            and re.search(r"부과|청구|매기", sentence)
        )
    if kind == "stockpile_release" and re.search(r"채운|재비축|refill", title, re.I):
        return bool(re.search(r"비축|reserve|stockpile", sentence, re.I)
                    and re.search(r"채우|채운|채울|재비축|refill", sentence, re.I))
    if kind == "stockpile_release":
        return bool(re.search(r"비축\s*(?:유|원유|경유)|석유\s*비축|oil reserves|stockpile", sentence, re.I)
                    or re.search(r"\d+(?:\.\d+)?\s*(?:억|만)?\s*배럴.{0,25}방출", sentence))
    if kind == "labor_negotiation" and "부결" in title and not re.search(r"부결|타결.{0,12}(?:못|않)|추가\s*교섭", sentence):
        return False
    if kind == "nuclear_warning":
        condition = re.search(r"([가-힣A-Za-z]{2,20})\s*(?:피격|공격)(?:시|받)", title)
        if condition and condition.group(1) not in sentence:
            return False
    if kind == "mortgage_rate":
        return bool(re.search(r"주담대|모기지|주택담보대출|mortgage", sentence, re.I)
                    and re.search(r"금리|rate", sentence, re.I))
    if kind == "retail_fuel":
        product = "휘발유" if "휘발유" in title else "경유" if "경유" in title else ""
        return bool((not product or product in sentence)
                    and re.search(r"(?:휘발유|경유).{0,55}(?:L|리터)(?:\(L\))?\s*당\s*\d[\d,.]*원", sentence))
    if kind == "product_sales_mix":
        product = next((term for term in ("친환경", "전기차", "하이브리드") if term in title), "")
        return bool((not product or product in sentence or (product == "친환경" and "하이브리드" in sentence and "전기차" in sentence))
                    and re.search(r"판매(?:량|대수|비중)?.{0,100}(?:차지|비중|%)", sentence))
    if kind == "fx" and re.search(r"\bndf\b", title, re.I):
        return bool(re.search(r"\bndf\b|차액결제선물환|역외환율", sentence, re.I))
    if kind == "energy_supply" and re.search(r"브렌트|\bbrent\b", title, re.I):
        return bool(re.search(r"브렌트|\bbrent\b", sentence, re.I))
    if kind == "fund_result":
        funds = [root for root in re.findall(r"([A-Za-z0-9가-힣]+)펀드", title) if len(root) >= 2]
        if funds and not any(root in sentence for root in funds):
            return False
    if kind == "project_buildout":
        capacity = re.compile(r"(\d+(?:\.\d+)?(?:\s*[~∼-]\s*\d+(?:\.\d+)?)?)\s*(GW|MW|기가와트|메가와트)", re.I)
        target = capacity.search(title)
        if target:
            def capacity_key(match):
                number = re.sub(r"\s+", "", match.group(1)).replace("∼", "~").replace("-", "~")
                unit = match.group(2).lower().replace("기가와트", "gw").replace("메가와트", "mw")
                return number, unit
            if not any(capacity_key(value) == capacity_key(target) for value in capacity.finditer(sentence)):
                return False
    return not kind or next(source for name, _head, source in HEADLINE_FOCUS if name == kind).search(sentence or "") is not None


def period_matches(title: str, sentence: str) -> bool:
    if focus_kind(title) == "national_exports":
        # A milestone's prospective date is not the observation's reference month.
        return True
    months, source_months = set(MONTH.findall(title or "")), set(MONTH.findall(sentence or ""))
    if months and source_months and months.isdisjoint(source_months):
        return False
    quarter = re.compile(r"(?<!\d)([1-4])\s*(?:분기|Q\b)|\bQ([1-4])\b", re.I)
    periods = {a or b for a, b in quarter.findall(title or "")}
    source_periods = {a or b for a, b in quarter.findall(sentence or "")}
    quarter_range = re.compile(r"(?<!\d)[1-4]\s*[~∼-]\s*[1-4]\s*분기")
    if periods and quarter_range.search(sentence or "") and not quarter_range.search(title or ""):
        distinct_periods = {a or b for a, b in quarter.findall(quarter_range.sub("", sentence or ""))}
        if not periods.intersection(distinct_periods):
            return False
    return not (periods and source_periods and periods.isdisjoint(source_periods))


def focus_score(title: str, sentence: str) -> int:
    score = (40 if focus_matches(title, sentence) else -40) if focus_kind(title) else 0
    if DENIAL_HEADLINE.search(title):
        score += 45 if DENIAL_SOURCE.search(sentence) else -60
    months, source_months = set(MONTH.findall(title or "")), set(MONTH.findall(sentence or ""))
    if months and source_months:
        score += 16 if months & source_months else -60
    if BACKGROUND.search(sentence):
        score -= 25
    if re.match(r"^\d{4}년\s*(?:출시|설립)", sentence):
        score -= 35
    if ASPIRATION.search(sentence):
        score -= 25
    if re.search(r"할\s*경우|한다면", sentence) and not re.search(r"검토\s*중|협상\s*중|계약을\s*체결", sentence):
        score -= 25
    if re.match(r"^(?:또|그리고|한편|이러한|이를|이\s*같은)\s", sentence):
        score -= 15
    if focus_kind(title) and QUANTITY.search(sentence):
        score += 15
    if focus_matches(title, sentence) and any(
        re.sub(r"\s+", "", amount.group(0)) in re.sub(r"\s+", "", sentence)
        for amount in QUANTITY.finditer(title)
    ):
        score += 25
    if focus_kind(title) == "ownership" and re.search(r"지분.{0,20}\d+(?:\.\d+)?%", sentence):
        score += 20
    if focus_kind(title) == "shareholder" and re.search(r"종료|사라|마무리|막바지", title) and re.search(r"종료|마무리|마지막\s*주문", sentence):
        score += 25
    return score


def core_focus_aligned(title: str, core: str) -> bool:
    return focus_matches(title, core) and period_matches(title, core)


def business_investment_observation(sentence: str) -> dict[str, str]:
    """Retain the measured population instead of relabelling it as total AI CAPEX."""
    sentence = re.sub(r"\((?:약[^)]*|원화\s*환산\s*확인\s*불가)\)", "", sentence)
    match = re.search(
        r"([가-힣A-Za-z]{2,20})\s*기업들의\s*(컴퓨터\s*및\s*관련\s*장비)\s*투자는\s*"
        r"(올해|20\d{2}년)\s*([1-4])분기\s*(\d[\d,.]*\s*(?:억|조|만)?\s*달러)를?\s*(?:넘어|넘었고,?)\s*"
        r"전년\s*동기\s*대비\s*(\d+(?:\.\d+)?)%\s*(증가했다|감소했다|늘었다|줄었다)", sentence,
    )
    if not match:
        return {}
    country, population, year, quarter, amount, change, direction = match.groups()
    return {"country": country, "population": population, "year": year, "quarter": quarter,
            "amount": re.sub(r"\s+", "", amount), "change": change,
            "direction": "증가" if direction in {"증가했다", "늘었다"} else "감소"}


def intraday_equity_observations(title: str, body: str) -> dict[str, object]:
    """Bind large quoted issuer moves to one explicit time and comparison basis."""
    if not re.search(r"장\s*초반|장중|급등|급락|강세|약세", title) or not re.search(r"한국거래소|유가증권시장|코스닥시장", body):
        return {}
    source = source_reported_body(body)
    market = "한국거래소"
    issuer_pattern = r"[A-Za-z0-9가-힣&·.-]{2,30}"
    price_pattern = r"\d[\d,만천백십]*원"
    first = re.search(
        r"(?<!\d)(\d{1,2})일\s*한국거래소에\s*따르면\s*([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는)\s*"
        r"이날\s*(오전|오후)\s*(\d{1,2})시\s*(\d{1,2})분\s*기준\s*전\s*거래일\s*대비\s*"
        r"(\d+(?:\.\d+)?)%\s*(오른|내린)\s*(\d[\d,만천백십]*원)[^.!?]{0,25}(?:거래되고\s*있다|거래됐다|기록했다)\.", source,
    )
    values = first.groups() if first else None
    excerpt = first.group(0) if first else ""
    if not first:
        first = re.search(
            rf"(?<!\d)(\d{{1,2}})일\s*한국거래소에\s*따르면\s*(오전|오후)\s*(\d{{1,2}})시\s*(\d{{1,2}})분\s*(?:기준|현재)\s*"
            rf"({issuer_pattern})(?:은|는)\s*전\s*거래일\s*대비\s*(\d+(?:\.\d+)?)%\s*(오른|내린)\s*"
            rf"({price_pattern})[^.!?]{{0,25}}(?:거래되고\s*있다|거래됐다|기록했다)\.", source,
        )
        if first:
            day, half, hour, minute, issuer, rate, direction, price = first.groups()
            values = (day, issuer, half, hour, minute, rate, direction, price)
            excerpt = first.group(0)
    if not first:
        # A quote with an omitted subject is bound only to an explicit issuer,
        # stock code and trading day in the immediately preceding source lead.
        subject = re.search(rf"({issuer_pattern})\[\d{{6}}\]\s*주가가\s*(\d{{1,2}})일[^\n]{{0,90}}\n", source)
        quoted = re.search(
            rf"이날\s*(유가증권시장|코스닥시장)에서\s*(오전|오후)\s*(\d{{1,2}})시\s*(\d{{1,2}})분\s*현재\s*"
            rf"전장보다\s*(\d+(?:\.\d+)?)%\s*(오른|내린)\s*({price_pattern})에\s*거래되고\s*있다\.", source,
        )
        if subject and quoted and 0 <= quoted.start() - subject.end() < 30:
            market, half, hour, minute, rate, direction, price = quoted.groups()
            values = (subject.group(2), subject.group(1), half, hour, minute, rate, direction, price)
            first = quoted
            excerpt = subject.group(0).strip() + " " + quoted.group(0)
    if not first:
        core = re.search(
            r"(한국거래소|유가증권시장|코스닥시장)\s*기준\s*(\d{1,2})일\s*(오전|오후)\s*(\d{1,2})시(\d{1,2})분\s*"
            r"([^\n]+?)에\s*거래됐다\.\s*등락률은\s*전\s*거래일\s*대비다\.", source,
        )
        if not core:
            return {}
        market, day, half, hour, minute, observed = core.groups()
        quotes = []
        for row in observed.split(", "):
            value = re.fullmatch(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는)\s*(\d+(?:\.\d+)?)%\s*(오른|내린)\s*(\d[\d,만천백십]*원)", row)
            if not value or value.group(1).casefold() not in title.casefold():
                return {}
            issuer, rate, direction, price = value.groups()
            quotes.append({"issuer": issuer, "rate": rate, "direction": direction,
                           "price": price, "source_excerpt": core.group(0)})
        if not quotes or max(abs(float(row['rate'])) for row in quotes) < 5:
            return {}
        return {"market": market, "day": day, "half": half, "hour": hour, "minute": minute, "quotes": quotes}
    day, issuer, half, hour, minute, rate, direction, price = values
    if issuer.casefold() not in title.casefold() or abs(float(rate)) < 5:
        return {}
    quotes = [{"issuer": issuer, "rate": rate, "direction": direction, "price": price,
               "source_excerpt": excerpt}]
    following = re.match(
        r"\s*같은\s*시각\s*([A-Za-z0-9가-힣&·.-]{2,30})\s*역시\s*"
        r"전\s*거래일\s*대비\s*(\d+(?:\.\d+)?)%\s*(상승|하락)한\s*"
        r"(\d[\d,만천백십]*원)[^.!?]{0,30}(?:기록|거래)[^.!?]{0,70}\.", source[first.end():],
    )
    if following and following.group(1).casefold() in title.casefold():
        other, other_rate, other_direction, other_price = following.groups()
        quotes.append({"issuer": other, "rate": other_rate,
                       "direction": "오른" if other_direction == "상승" else "내린",
                       "price": other_price, "source_excerpt": following.group(0).lstrip(". ")})
    return {"market": market, "day": day, "half": half, "hour": hour, "minute": minute, "quotes": quotes}


def intraday_equity_event_terms(alert: dict) -> dict[str, object]:
    """Suppress modest quote ticks, not new issuer actions or material reversals."""
    title = str(alert.get("source_title") or alert.get("news") or "")
    if focus_kind(title) != "intraday_equity" or not alert.get("body_verified"):
        return {}
    observation = intraday_equity_observations(title, str(alert.get("source_body") or ""))
    try:
        published = dt.datetime.fromisoformat(str(alert.get("published") or "").replace("Z", "+00:00"))
        if not observation or not published.tzinfo:
            return {}
        session = published.astimezone(dt.timezone(dt.timedelta(hours=9))).date()
        if session.day != int(observation['day']):
            return {}
        return {"session": session.isoformat(), "quotes": sorted(
            [[row['issuer'], row['direction'], int(Decimal(row['rate']) // 5) * 5]
             for row in observation['quotes']])}
    except (TypeError, ValueError, InvalidOperation):
        return {}


def us_equity_close_identity(alert: dict) -> str:
    """Identify an observed US session close across publishers, not an intraday quote."""
    title = str(alert.get("source_title") or alert.get("news") or "")
    body = str(alert.get("source_body") or "") if alert.get("body_verified") else ""
    if not re.search(r"뉴욕마감|뉴욕증시|월가", title) or not body:
        return ""
    session = re.search(
        r"뉴욕(?:증시|주식시장)[^.!?]{0,40}?(?:(\d{1,2})월\s*)?(\d{1,2})일\s*\(현지(?:시간)?\)", body,
    )
    close = re.search(
        r"나스닥(?:종합)?지수(?:는|가|이)?[^!?]{0,80}?\(([+-]?\d+(?:\.\d+)?)%\)\s*"
        r"(오른|뛴|상승한|내린|하락한|떨어진)\s*(\d[\d,]*(?:만[\d,]+)?(?:\.\d+)?)\s*"
        r"(?:에|로)?\s*(?:마감했다|거래를\s*끝냈다)", body,
    )
    try:
        published = dt.datetime.fromisoformat(str(alert.get("published") or "").replace("Z", "+00:00"))
        if not session or not close or not published.tzinfo:
            return ""
        published = published.astimezone(dt.timezone(dt.timedelta(hours=9))).date()
        month = int(session.group(1)) if session.group(1) else published.month
        year = published.year
        if not session.group(1) and int(session.group(2)) > published.day:
            previous_month = published.replace(day=1) - dt.timedelta(days=1)
            year, month = previous_month.year, previous_month.month
        elif month > published.month:
            year -= 1
        day = dt.date(year, month, int(session.group(2)))
        if not dt.timedelta() <= published - day <= dt.timedelta(days=7):
            return ""
        value = close.group(3).replace(',', '')
        level = float(value.split('만')[0]) * 10000 + float(value.split('만')[1]) if '만' in value else float(value)
        rate = abs(float(close.group(1)))
        if close.group(2) in {"내린", "하락한", "떨어진"}:
            rate = -rate
        elif float(close.group(1)) < 0:
            return ""
        return f"source_event:v1:us:equity_close:{day.isoformat()}:nasdaq={level:.12g}:change={rate:.12g}"
    except (TypeError, ValueError):
        return ""


def market_breadth_identity(alert: dict) -> str:
    """Use the measured index population, month and breadth, not AI sector tags."""
    title = str(alert.get("source_title") or alert.get("news") or "")
    body = str(alert.get("source_body") or "") if alert.get("body_verified") else ""
    if focus_kind(title) != "breadth" or not body:
        return ""
    measures = re.finditer(
        r"(S&P\s*500|코스피|코스닥|나스닥(?:100)?)(?:\s*(?:지수|구성|전체))?\s*"
        r"(?:구성\s*)?종목(?:의|\s*중)?\s*(?:약\s*)?(\d+(?:\.\d+)?)%\s*(?:는|가|이|은)?\s*(하락|상승)", body,
    )
    try:
        published = dt.datetime.fromisoformat(str(alert.get("published") or "").replace("Z", "+00:00"))
        if not published.tzinfo:
            return ""
        published = published.astimezone(dt.timezone(dt.timedelta(hours=9)))
        identities = set()
        for measure in measures:
            if not 0 <= float(measure.group(2)) <= 100:
                continue
            context = body[max(0, measure.start() - 220):measure.end()]
            periods = list(re.finditer(r"(?:(\d{4})년\s*)?(\d{1,2})월", context))
            if not periods:
                continue
            period = periods[-1]
            month = int(period.group(2))
            year = int(period.group(1)) if period.group(1) else published.year - (month > published.month)
            dt.date(year, month, 1)
            index = re.sub(r"\s+", "", measure.group(1)).lower()
            direction = "down" if measure.group(3) == "하락" else "up"
            identities.add(f"source_event:v1:market_breadth:{index}:{year}-{month:02d}:{direction}_share={float(measure.group(2)):.12g}")
        return identities.pop() if len(identities) == 1 else ""
    except (TypeError, ValueError):
        return ""


def retail_fuel_observation(title: str, body: str) -> dict:
    """Extract the headline product's observed weekly price and comparison."""
    if focus_kind(title) != "retail_fuel":
        return {}
    for sentence in source_sentences(body):
        if not focus_matches(title, sentence):
            continue
        price = re.search(r"(휘발유|경유)\s*(?:평균\s*)?(?:판매)?가격은?\s*(?:리터(?:\(L\))?|L)\s*당\s*(\d[\d,.]*)원", sentence)
        change = re.search(r"전주\s*(?:보다|대비)\s*(?:L\s*당\s*)?(\d[\d,.]*)원\s*(내렸|올랐|하락|상승)", sentence)
        period = re.search(r"(\d{1,2}월\s*(?:첫째|둘째|셋째|넷째|다섯째|[1-5])\s*주)", sentence)
        if price and change and period:
            return {"product": price.group(1), "price": price.group(2), "change": change.group(1),
                    "direction": "하락" if change.group(2) in {"내렸", "하락"} else "상승",
                    "period": period.group(1), "source_excerpt": sentence}
    return {}


def national_export_observation(sentence: str) -> dict | None:
    """Bind an observed current-period total, not historical or target figures."""
    sentence = re.sub(r"\((?:약\s*\d[\d,.]*\s*(?:조|억|만)?\s*원|원화\s*환산\s*확인\s*불가)\)", "", sentence)
    if re.search(r"당시|과거|추정치|전망치|예상치|수출하면|수출할\s*경우", sentence):
        return None
    match = re.search(
        r"(?P<year>올해|금년)\s*(?P<period>(?:\d{1,2}\s*[~∼-]\s*)?\d{1,2}월|연간)?\s*"
        r"(?P<metric>누적\s*수출액|월간\s*수출액|수출액)(?:은|이|가)\s*"
        r"(?P<amount>\d[\d,.]*\s*(?:조|억|만)?\s*달러)\s*"
        r"(?:에\s*달(?:했|하|해)|(?:로|으로)\s*(?:집계됐|집계되었|늘었|증가했|감소했|기록됐)|입니다|이다|였다|이었다)",
        sentence,
    )
    if not match:
        return None
    return {key: re.sub(r"\s+", "", match.group(key) or "")
            for key in ("year", "period", "metric", "amount")}


def factory_tariff_observation(title: str, body: str) -> dict | None:
    """Bind a direct conditional quote even when its headline is generic."""
    kind = focus_kind(title)
    headline_bound = kind == "factory_tariff" and bool(re.search(r"미국|美", title))
    lead_bound = (
        not kind and "트럼프" in title
        and bool(re.search(r"격전지|유세|선거|연설|발언", title))
        and not re.search(ENERGY_SUBJECT, title, re.I)
        and bool(re.search(r"미국\s*(?:내\s*(?:공장|투자)|공장)|미국에\s*공장", body[:800]))
    )
    if not headline_bound and not lead_bound:
        return None
    focus_title = title if headline_bound else "미국 공장 미건설 관세"
    for index, sentence in enumerate(source_sentences(body)):
        if not headline_bound and (
            index > 2 or BACKGROUND.search(sentence) or re.search(r"전날|지난주|지난달|과거", sentence)
        ):
            continue
        if "트럼프" not in sentence or "말했다" not in sentence or not focus_matches(focus_title, sentence):
            continue
        duration = re.search(r"약\s*((\d+(?:\.\d+)?)\s*(년\s*반|년|개월))", sentence)
        rate = re.search(r"(\d+(?:\.\d+)?)%\s*(?:의\s*)?관세", sentence)
        if not duration or not rate:
            continue
        number = float(duration.group(2))
        unit = re.sub(r"\s", "", duration.group(3))
        months = number if unit == "개월" else number * 12 + (6 if unit == "년반" else 0)
        return {
            "sentence": sentence, "grace": duration.group(1), "rate": rate.group(1),
            "months": format(months, ".12g"),
        }
    return None


def canonical_source_fact(text: str) -> str:
    """Normalize typography and redundant wording, never actors or event terms."""
    text = re.sub(r"\((?:약\s*\d[\d,.]*\s*(?:조|억|만)?\s*원|원화\s*환산\s*확인\s*불가)\)", "", text)
    text = re.sub(r"인공지능\s*\(AI\)|인공지능", "ai", text, flags=re.I)
    text = re.sub(r"최고경영자\s*\(CEO\)|최고경영자", "ceo", text, flags=re.I)
    text = re.sub(r"(?<![가-힣])이번\s+", "", text)
    return re.sub(r"[^a-z0-9가-힣.%+\-]", "", text.casefold()).rstrip(".")


def verified_source_fact_identity(alert: dict) -> str:
    """Exact source-fact equivalence for otherwise unmodelled market events.

    New secondary evidence, amounts, periods, parties or execution stages keep
    their own identity. A company/topic match or fuzzy similarity is insufficient.
    """
    keys = verified_source_fact_keys(alert)
    if not keys:
        return ""
    digest = hashlib.sha256(json.dumps(keys).encode("utf-8")).hexdigest()
    return f"source_facts:v1:{digest}"


def verified_source_fact_keys(alert: dict) -> list[str]:
    """Keep source-action aliases so shorter wire copies cannot republish a fact.

    All facts in a candidate must already be seen before it is suppressed.
    New quantities, counterparties or stages therefore survive as new evidence.
    """
    if not alert.get("body_verified"):
        return []
    title = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "")
    body = str(alert.get("source_body") or "")
    return list(_verified_source_fact_keys(title, body, str(alert.get("link") or "")))


def source_article_body(body: str) -> str:
    """Match the display boundary, excluding rotating recommendation cards."""
    paragraphs = []
    for line in body.splitlines():
        line = line.strip()
        if re.fullmatch(r"관련\s*뉴스|주요\s*뉴스|.+기자의\s*주요\s*뉴스", line):
            break
        if re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", line) or re.match(
            r"^(?:제보는\s*카카오톡|[◎☞]\s*공감언론|<저작권자)", line,
        ):
            break
        if re.fullmatch(r"\[email protected\](?:\s+[가-힣]{2,6}\s*기자)?", line):
            break
        paragraphs.append(line)
    return "\n".join(paragraphs)


def verified_source_body_digest(alert: dict) -> str:
    """An unchanged-body receipt independent of classification rule versions."""
    if not alert.get("body_verified"):
        return ""
    body = canonical_source_fact(source_article_body(str(alert.get("source_body") or "")))
    return hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""


def source_reported_body(body: str) -> str:
    """Keep the report, not a separately labelled leading AI commentary card."""
    lines = source_article_body(body).splitlines()
    nonempty = [index for index, line in enumerate(lines) if line.strip()]
    if nonempty and re.fullmatch(r"(?:💡\s*)?AI\s*분석", lines[nonempty[0]].strip(), re.I):
        # This publisher layout has one summary paragraph followed by the report.
        start = nonempty[2] if len(nonempty) > 2 else len(lines)
        return "\n".join(lines[start:])
    return "\n".join(lines)


@lru_cache(maxsize=256)
def _verified_source_fact_keys(title: str, body: str, source_url: str) -> tuple[str, ...]:
    # Cache computation only within this process, keyed by the entire fresh body.
    # Do not persist source bodies or reuse a previous run's retrieval evidence.
    body = source_reported_body(body)
    assessment = assess(title, body, source_url=source_url)
    if assessment["disposition"] != "keep" or assessment["priority"] < 2:
        return ()
    evidence = assessment["evidence"]
    if not evidence or len(evidence[0]["source_excerpt"]) < 50:
        return ()
    if re.match(r"^(?:양측|회사|기업|업체|그는|이는|이들은)(?:은|는|이|가)?\s", evidence[0]["source_excerpt"]):
        return ()
    facts = {(item["kind"], item["stage"], canonical_source_fact(item["source_excerpt"]))
             for item in evidence}
    # The display audit keeps one excerpt per kind. The identity must also
    # retain later numeric terms of that same kind (e.g. 15 vs 20 participants).
    kinds = {item["kind"] for item in evidence}
    for sentence in source_sentences(body):
        if (BACKGROUND.search(sentence) or PAST_ACTION.search(sentence) or PHOTO_DESCRIPTION.search(sentence)
                or COMPANY_PROFILE.search(sentence) or ACCOUNTING_NOTE.search(sentence)
                or canonical_source_fact(sentence) == canonical_source_fact(title)
                or not focus_matches(title, sentence) or not period_matches(title, sentence)):
            continue
        for kind, _axes, subject, action in COMPILED_RULES:
            if kind in kinds and subject.search(sentence) and action.search(sentence) and evidence_is_new_event(kind, sentence):
                stage = "early_signal" if EARLY_SIGNAL.search(sentence) or kind == "customer_discussions" else "reported_change"
                facts.add((kind, stage, canonical_source_fact(sentence)))
    return tuple(sorted(
        "source_fact:v1:" + hashlib.sha256(json.dumps(fact, ensure_ascii=False).encode("utf-8")).hexdigest()
        for fact in facts
    ))


SOURCE_MONEY = r"(\d[\d,.\s조억만천백십]*?)\s*(달러|유로|위안|원)"


def korean_amount_value(raw: str) -> str:
    """Parse numeric Korean unit groups; never infer a missing number/unit."""
    raw = re.sub(r"[\s,]", "", raw)
    if not raw:
        return ""

    def small(group: str) -> Decimal | None:
        if not group:
            return Decimal(0)
        total = Decimal(0)
        previous = 10000
        while group:
            token = re.match(r"(\d+(?:\.\d+)?)([천백십]?)", group)
            if not token:
                return None
            unit = {"천": 1000, "백": 100, "십": 10, "": 1}[token.group(2)]
            if unit >= previous:
                return None
            total += Decimal(token.group(1)) * unit
            previous = unit
            group = group[token.end():]
        return total

    try:
        total = Decimal(0)
        for label, multiplier in (("조", 10**12), ("억", 10**8), ("만", 10**4)):
            if label in raw:
                coefficient, raw = raw.split(label, 1)
                value = small(coefficient)
                if value is None or value <= 0:
                    return ""
                total += value * multiplier
        value = small(raw)
        if value is None:
            return ""
        formatted = format(total + value, "f")
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
    except InvalidOperation:
        return ""


def licensing_event_terms(title: str, body: str) -> dict[str, object]:
    """Match a named asset's exclusive license, not all news about its issuer."""
    if not re.search(r"기술이전|라이선스", title):
        return {}
    source = source_reported_body(body)
    issuer = re.match(r"^([^,，]{2,35})[,，]\s*([A-Za-z가-힣·&-]{2,30})에\s", title)
    asset = re.search(r"\b[A-Z]{1,5}\d{2,6}\b", title)
    if not issuer or not asset or issuer.group(2) not in source or asset.group(0) not in source:
        return {}
    lead = " ".join(source_sentences(source)[:3])
    if not re.search(r"독점\s*라이선스", lead) or not re.search(r"체결|부여", lead):
        return {}
    if re.search(r"검토|협상|논의|해지|취소|철회", title + " " + lead):
        return {}
    upfront = re.search(rf"선급금\s*{SOURCE_MONEY}", lead)
    milestone = re.search(rf"(최대\s*)?{SOURCE_MONEY}\s*(?:규모의|의)?\s*(?:단계별\s*)?마일스톤", lead)
    if not upfront or not milestone:
        return {}
    upfront_value, milestone_value = korean_amount_value(upfront.group(1)), korean_amount_value(milestone.group(2))
    if not upfront_value or not milestone_value:
        return {}
    royalty_rates = sorted({value for sentence in source_sentences(source) if "로열티" in sentence
                            for value in re.findall(r"\d+(?:\.\d+)?%", sentence)})
    # Numeric runway/royalty revisions are new evidence, even for the same asset.
    runway = sorted(set(re.findall(r"현금\s*가용\s*기간[^.!?]{0,60}?(\d{4})년", source)))
    excluded = sorted(set(re.findall(r"([A-Za-z가-힣]{2,20})(?:을|를)\s*제외한", lead)))
    license_sentence = next((sentence for sentence in source_sentences(source)
                             if asset.group(0) in sentence and re.search(r"독점\s*라이선스", sentence)), "")
    scope = ("us" if re.search(r"미국\s*내\s*독점", license_sentence) else
             "global" if re.search(r"(?:글로벌|전\s*세계)\s*독점", license_sentence) else "unspecified")
    return {"issuer": issuer.group(1).strip(), "counterparty": issuer.group(2), "asset": asset.group(0),
            "stage": "exclusive_license_signed", "scope": scope,
            "excluded": excluded, "upfront": [upfront.group(2), upfront_value],
            "milestone": [milestone.group(3), milestone_value, bool(milestone.group(1))],
            "royalty_rates": royalty_rates, "runway_years": runway}


def odd_lot_rule_terms(title: str, body: str) -> dict[str, object]:
    """Normalize shares/units only for the sourced single-stock ETF lot rule."""
    source = source_reported_body(body)
    compact = re.sub(r"\s+", "", source)
    if not all(re.search(pattern, compact) for pattern in (
        r"금융위(?:원회)?", r"단일종목레버리지", r"단주", r"시간외종가매매",
    )):
        return {}
    lot = re.search(r"매매수량단위.{0,35}?(\d+)(?:주|좌)(?:씩)?(?:으로|로).{0,15}확대", compact)
    if not lot:
        return {}
    disposal = [sentence for sentence in source_sentences(source)
                if re.search(r"시간\s*외\s*종가\s*매매", sentence) and "단주" in sentence
                and re.search(r"허용|처분|처리|검토", sentence)]
    if not disposal:
        return {}
    proposal = " ".join(disposal)
    if re.search(r"검토|논의|거론|구상", proposal):
        stage = "review"
    elif re.search(r"시행했다|허용했다|시행한다고|허용한다고|확정|시행한다", proposal):
        stage = "implemented_or_confirmed"
    else:
        return {}
    # Do not use the date of another action (the lot-size announcement) here.
    timing = sorted(set(re.findall(r"\d{4}년\s*\d{1,2}월(?:\s*\d{1,2}일)?|\d{1,2}월\s*\d{1,2}일|\d+개월|\d+일간", proposal)))
    return {"authority": "korea_fsc", "instrument": "single_stock_leveraged_products",
            "min_lot": int(lot.group(1)), "disposal": "after_hours_closing_price", "stage": stage,
            "disposal_timing": [re.sub(r"\s+", "", value) for value in timing]}


def merger_agreement_terms(title: str, body: str) -> dict[str, object]:
    """Match the announced deal across synopsis/full-report copies."""
    if not re.search(r"인수\s*합의", title) or re.search(r"협상|논의|검토|가능성|추진", title):
        return {}
    parties = re.match(r"^([^,，]{2,40})[,，]\s*([A-Za-z0-9가-힣&·-]{2,30})\s", title)
    target_view = re.match(r"^([A-Za-z0-9가-힣&·-]{2,30})[,，]\s*([^,，]{2,40}?)의\s+\d", title)
    source = source_reported_body(body)
    lead = " ".join(source_sentences(source)[:2])
    if not re.search(r"인수(?:하기로\s*합의|하는\s*합병계약을\s*체결)", lead):
        return {}
    if target_view:
        buyer, target = target_view.group(2), target_view.group(1)
        if re.sub(r"\s+", "", buyer) not in re.sub(r"\s+", "", lead):
            return {}
    elif parties and parties.group(2) in lead:
        buyer, target = parties.groups()
    else:
        return {}
    if re.search(r"합의(?:하지|한\s*것은)\s*않|체결(?:하지|한\s*것은)\s*않", lead):
        return {}
    title_amount = re.search(SOURCE_MONEY, title)
    if not title_amount:
        return {}
    value = korean_amount_value(title_amount.group(1))
    amount = next((item for item in re.finditer(SOURCE_MONEY, lead)
                   if item.group(2) == title_amount.group(2) and korean_amount_value(item.group(1)) == value), None)
    if not amount or not value:
        return {}
    actor = re.sub(r"\s+", "", buyer).casefold()
    stage = "completed" if re.search(r"인수\s*완료|인수\s*종결", title) else "signed"
    revision = bool(re.search(r"조건\s*(?:변경|수정)|인수가\s*(?:변경|상향|하향)", title + " " + lead))
    terms = {"buyer": actor, "target": target, "amount": [amount.group(2), value],
             "stage": stage, "revised_terms": revision}
    if revision:
        terms["revision_excerpt"] = canonical_source_fact(lead)
    return terms


def broker_earnings_report_terms(title: str, body: str, published: str = "") -> dict[str, object]:
    """Bind copies of an attributed earnings report to its numerical terms."""
    if not re.search(r"證|증권", title) or not re.search(r"[1-4]분기", title):
        return {}
    source = source_reported_body(body)
    actor = re.search(r"([A-Za-z가-힣]{2,20}증권)(?:은|는)(?:\s+\d{1,2}일)?\s+([A-Za-z0-9가-힣&·.-]{2,30})에\s*대해", source)
    if not actor or actor.group(1) not in title.replace("證", "증권"):
        return {}
    money = r"(\d[\d,.\s조억만천백십]*?)\s*원"
    quarterly = re.compile(r"([1-4])분기\s*매출(?:액)?(?:은|는|이)?[^!?\n]{0,50}?" + money
                           + r"[^!?\n]{0,40}?영업이익(?:은|는|이)?[^!?\n]{0,50}?" + money)
    forecast = next((match for sentence in source_sentences(source)
                     if re.search(r"예상|전망|추정|기록할", sentence)
                     if (match := quarterly.search(sentence))), None)
    if not forecast:
        return {}
    quarter, revenue, profit = forecast.groups()
    if f"{quarter}분기" not in title:
        return {}
    targets = []
    for sentence in source_sentences(source):
        if "목표주가" in sentence:
            amounts = re.findall(money, sentence)
            if amounts:
                targets.append(korean_amount_value(amounts[-1]))
    annual = re.search(
        r"(?:올해|20\d{2}년)\s*연간\s*매출액과\s*영업이익은\s*각각\s*"
        r"(?:전년\s*대비\s*[\d.]+%\s*(?:증가|감소)한\s*)?" + money
        + r"\s*,\s*(?:[\d.]+%\s*(?:증가|감소)한\s*)?" + money, source,
    )
    year = re.search(r"(20\d{2})(?:년\s*|\s*회계연도\s*)(?:연간|[1-4]분기)", source)
    report_date = published[:10] if re.match(r"20\d{2}-\d{2}-\d{2}", published) else ""
    return {"broker": actor.group(1), "issuer": actor.group(2), "quarter": int(quarter),
            "year": year.group(1) if year else report_date[:4] if "올해" in source else "", "report_date": report_date,
            "revenue_won": korean_amount_value(revenue), "profit_won": korean_amount_value(profit),
            "annual_forecast_won": [korean_amount_value(value) for value in annual.groups()] if annual else [],
            "current_target_won": sorted(set(targets)),
            "explicit_correction": bool(re.search(r"정정|수정\s*보고서|전망치\s*재조정", title + " " + source)),
            "revenue_display": revenue.strip(), "profit_display": profit.strip()}


def analyst_target_revision_terms(title: str, body: str, published: str = "") -> dict[str, object]:
    """Keep the broker's revised target distinct from issuer earnings guidance."""
    if focus_kind(title) != "analyst_revision":
        return {}
    source = source_reported_body(body)
    money = r"(\d[\d,.\s조억만천백십]*?)\s*원"
    actor = re.search(
        r"([A-Za-z가-힣]{2,20}증권)(?:은|는|이|가)(?:\s+\d{1,2}일)?\s+"
        r"([A-Za-z0-9가-힣&·.-]{2,30})(?:\([^)]*\)|\[[^]]*\])?"
        r"(?:의|에\s*대해)\s+목표(?:주가|가)(?:를|는|을|은)?\s*(?:기존\s*)?"
        + money + r"에서\s*" + money + r"(?:으로|로)\s*(상향|하향|높였|낮췄|올렸|내렸)", source,
    )
    if not actor:
        return {}
    broker, issuer, previous, current, direction = actor.groups()
    previous_value, current_value = korean_amount_value(previous), korean_amount_value(current)
    if not previous_value or not current_value or previous_value == current_value:
        return {}
    return {"broker": broker, "issuer": issuer, "previous_won": previous_value,
            "current_won": current_value, "direction": "down" if direction in {"하향", "낮췄", "내렸"} else "up",
            "report_date": published[:10] if re.match(r"20\d{2}-\d{2}-\d{2}", published) else "",
            "previous_display": previous.strip(), "current_display": current.strip()}


def freight_cost_observation(title: str, body: str) -> dict[str, str]:
    """Keep a voyage cost and daily charter rate on their own stated bases."""
    if focus_kind(title) != "energy_supply" or not re.search(r"셔틀\s*운항", title):
        return {}
    source = re.sub(r"\((?:약[^)]*|원화\s*환산\s*확인\s*불가)\)", "", source_reported_body(body))
    source = re.sub(r"\s+", " ", source)
    provenance = re.search(r"(월스트리트저널|로이터|블룸버그|WSJ)(?:\(([A-Z]+)\))?(?:은|는|의)\s*(\d{1,2})일(?:\(현지시간\)|\s*현지\s*보도)", source)
    cost = re.search(r"셔틀\s*운항(?:에는\s*왕복\s*항해\s*(\d+)회당|의\s*왕복\s*(\d+)회\s*비용은)\s*최대\s*(\d[\d,.\s만억조]*달러)(?:\s*가\s*드는|다\.)", source)
    if not (provenance and cost and re.search(r"초대형\s*원유운반선|VLCC", source)):
        return {}
    terms = {"source": provenance.group(2) or provenance.group(1), "day": provenance.group(3),
             "voyages": cost.group(1) or cost.group(2), "max_cost": re.sub(r"\s+", "", cost.group(3))}
    charter = re.search(r"(지난달\s*말)\s*([^.!?]{2,45}?)까지\s*운항하는\s*초대형\s*유조선의\s*용선료는\s*"
                        r"전쟁\s*발발\s*전\s*하루\s*약\s*(\d[\d,.\s만억조]*달러)\s*수준에서\s*"
                        r"하루\s*(\d[\d,.\s만억조]*달러)로\s*급등했다", source)
    if charter:
        terms.update(period=charter.group(1), route=charter.group(2),
                     previous_daily=re.sub(r"\s+", "", charter.group(3)),
                     current_daily=re.sub(r"\s+", "", charter.group(4)))
    return terms


def public_compute_allocation(title: str, body: str) -> dict[str, str]:
    """Use the disclosed application round, not an advocate's proposed CAPEX."""
    if focus_kind(title) != "public_compute_allocation":
        return {}
    source = source_reported_body(body)
    provider = re.search(r"정보통신산업진흥원\(NIPA\)|^NIPA 자료에 따르면", source)
    applications = re.search(r"(20\d{2}년\s*\d{1,2}월부터\s*(?:올해|20\d{2}년)\s*\d{1,2}월)까지\s*"
                             r"진행된\s*공모에\s*\d[\d,]*개\s*기관이\s*\d[\d,]*개\s*과제로\s*GPU\s*(\d[\d,만]*)장을\s*신청했다", source)
    allocations = re.search(r"최종\s*배정\s*대상은\s*\d[\d,]*개\s*기관,\s*\d[\d,]*개\s*과제로\s*GPU\s*(\d[\d,만]*)장이\s*지원됐다\.\s*전체\s*신청량의\s*(\d+(?:\.\d+)?)%", source)
    if not (provider and applications and allocations):
        normalized = re.search(r"^NIPA 자료에 따르면 (20\d{2}년\s*\d{1,2}월부터\s*(?:올해|20\d{2}년)\s*\d{1,2}월)까지 공모에서 "
                               r"GPU (\d[\d,만]*)장을 신청했고 (\d[\d,만]*)장이 배정됐다\. 배정량은 신청량의 (\d+(?:\.\d+)?)%다\.", source)
        if not normalized:
            return {}
        return dict(zip(("period", "requested", "allocated", "allocation_rate"), normalized.groups()), provider="NIPA")
    return {"provider": "NIPA", "period": applications.group(1), "requested": applications.group(2),
            "allocated": allocations.group(1), "allocation_rate": allocations.group(2)}


def housing_demand_observation(title: str, body: str) -> dict[str, str]:
    """Keep the national population and matched observation window together."""
    if focus_kind(title) != "housing_demand":
        return {}
    source = re.sub(r"\s+", " ", source_reported_body(body))
    release = re.search(
        r"(?<!\d)(\d{1,2})일\s*(?:부동산\s*플랫폼\s*)?([A-Za-z가-힣]{2,20})(?:이|가)\s*"
        r"(올해|20\d{2}년)\((\d{1,2}월\s*\d{1,2}일[~∼-]\d{1,2}월\s*\d{1,2}일)\s*"
        r"입주자모집공고\s*기준\)[^.!?]{0,40}전국\s*1순위\s*평균\s*청약경쟁률은\s*"
        r"(\d+(?:\.\d+)?)대\s*1로\s*집계됐다\.\s*이는\s*지난해\s*같은\s*기간\((\d+(?:\.\d+)?)대\s*1\)", source,
    )
    if release:
        day, provider, year, period, current, previous = release.groups()
        return {"day": day, "provider": provider, "year": year, "period": period,
                "current": current, "previous": previous}
    normalized = re.search(
        r"^([A-Za-z가-힣]{2,20})(?:은|는)\s*(\d{1,2})일\s*(올해|20\d{2}년)\s*"
        r"(\d{1,2}월\s*\d{1,2}일[~∼-]\d{1,2}월\s*\d{1,2}일)\s*입주자모집공고\s*기준\s*"
        r"전국\s*1순위\s*평균\s*청약경쟁률이\s*(\d+(?:\.\d+)?)대\s*1이라고\s*발표했다\.\s*"
        r"지난해\s*같은\s*기간은\s*(\d+(?:\.\d+)?)대\s*1이었다\.", source,
    )
    if not normalized:
        return {}
    provider, day, year, period, current, previous = normalized.groups()
    return {"day": day, "provider": provider, "year": year, "period": period,
            "current": current, "previous": previous}


def conditional_index_outlook(title: str, body: str, published: str = "") -> dict[str, str]:
    """A broker's conditional index target is not an observed index or profit."""
    if focus_kind(title) != "equity_index_outlook":
        return {}
    source = re.sub(r"\s+", " ", source_reported_body(body))
    broker = re.search(r"([A-Za-z가-힣]{2,20}증권)(?:은|는)\s*(\d{1,2})일\s*보고서에서", source)
    targets = re.search(r"(코스피|코스닥|나스닥|S&P\s*500)(?:가|이)\s*(?:\d[\d,]*선을\s*회복한\s*가운데\s*)?"
                        r"(\d[\d,]*)선을\s*(?:돌파해\s*안착하면|돌파·안착하면)\s*(\d[\d,]*[~∼-]\d[\d,]*)선까지\s*"
                        r"(?:추가\s*)?상승할\s*수\s*있(?:다는\s*전망|다고\s*전망했다)", source)
    condition = re.search(r"(유가,\s*금리의\s*추가적인\s*급등세만\s*없다면|유가·금리의 추가 급등이 없고)", source)
    if not (broker and targets and condition):
        return {}
    return {"broker": broker.group(1), "day": broker.group(2), "index": targets.group(1),
            "threshold": targets.group(2), "target_range": targets.group(3).replace("∼", "~").replace("-", "~"),
            "condition": condition.group(1),
            "report_date": published[:8] + broker.group(2).zfill(2) if re.match(r"20\d{2}-\d{2}-\d{2}", published) else ""}


def marketing_contract_observation(title: str, body: str) -> dict[str, str]:
    if focus_kind(title) != "marketing_offtake":
        return {}
    sentences = source_sentences(source_reported_body(body))
    statement = next((row for row in sentences if focus_matches(title, row)
                      and re.search(r"\d{1,2}일\s*밝혔다", row) and not PAST_ACTION.search(row)), "")
    issuer = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:이|가|은|는)\s", statement)
    customer = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:\([^)]*\))?(?:와|과)\s*", statement)
    product = re.search(r"([A-Za-z0-9가-힣]{2,25})\s*장기\s*(?:마케팅|오프테이크)\s*계약", statement)
    day = re.search(r"(?<!\d)(\d{1,2})일\s*밝혔다", statement)
    scope = next((row for row in sentences if product and product.group(1) in row
                  and re.search(r"20\d{2}년까지", row) and re.search(r"최대\s*\d", row)), "")
    year = re.search(r"(20\d{2})년까지", scope)
    volume = re.search(r"최대\s*(\d[\d,.]*\s*만?\s*톤)", scope)
    if not (issuer and customer and product and day and year and volume and issuer.group(1) in title):
        return {}
    return {"issuer": issuer.group(1), "customer": customer.group(1), "product": product.group(1),
            "day": day.group(1), "until_year": year.group(1), "maximum_volume": volume.group(1),
            "volume_stage": "expected" if re.search(r"전망|예상", scope) else "contracted"}


def research_program_award_observation(title: str, body: str) -> dict[str, str]:
    """Keep consortium project costs and public support separate from issuer sales."""
    if focus_kind(title) != "research_award":
        return {}
    rows = source_sentences(source_reported_body(body))
    statement = next((row for row in rows if focus_matches(title, row) and not PAST_ACTION.search(row)), "")
    issuer = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:\([^)]*\))?(?:은|는)\s", statement)
    count = re.search(r"국책과제\s*(\d+)건", statement)
    day = re.search(r"(?<!\d)(\d{1,2})일\s*밝혔다", statement)
    tasks = next((match for row in rows if (match := re.search(
        r"각각\s*제안한\s*([^.!?]{2,40}?)\s*과제와\s*([^.!?]{2,40}?)\s*과제가", row))), None)
    budget = next((row for row in rows if re.search(r"(?:두|전체|총)\s*과제의\s*총\s*연구개발비", row)), "")
    total = re.search(rf"총\s*연구개발비는\s*(?:약\s*)?(?P<amount>{SOURCE_MONEY})", budget)
    grant = re.search(rf"정부\s*지원금은\s*(?:약\s*)?(?P<amount>{SOURCE_MONEY})", budget)
    if not (issuer and count and day and tasks and total and grant and issuer.group(1) in title):
        return {}
    return {"issuer": issuer.group(1), "count": count.group(1), "day": day.group(1),
            "tasks": tasks.group(1) + "·" + tasks.group(2), "total_budget": total.group("amount"),
            "government_support": grant.group("amount"), "source_excerpt": statement}


def order_expansion_target_observation(title: str, body: str) -> dict[str, str]:
    """An awarded order and the hoped-for expansion amount are different stages."""
    if not re.search(r"공급|수주|계약", title):
        return {}
    rows = source_sentences(source_reported_body(body))
    statement = next((row for row in rows if not PAST_ACTION.search(row)
                      and re.search(r"공급\s*계약을\s*수주했다고\s*\d{1,2}일\s*밝혔다", row)), "")
    issuer = re.match(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는)\s", statement)
    target = next((row for row in rows if "이번 계약을 시작으로" in row
                   and "관련 수주 규모" in row and "목표" in row), "")
    amount = re.search(rf"관련\s*수주\s*규모를\s*(?:약\s*)?(?P<amount>{SOURCE_MONEY})까지", target)
    if not (issuer and amount and issuer.group(1) in title):
        return {}
    return {"issuer": issuer.group(1), "statement": statement, "expansion_target": amount.group("amount")}


def industrial_customer_adoption_observation(title: str, body: str) -> dict[str, str]:
    """Bind actual equipment adoption to its disclosed product and production site."""
    if focus_kind(title) != "industrial_customer_adoption":
        return {}
    rows = source_sentences(source_reported_body(body))
    statement = next((row for row in rows if focus_matches(title, row) and not PAST_ACTION.search(row)), "")
    issuer = next((match for match in re.finditer(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는)\s", statement)
                   if match.group(1) in title), None)
    equipment = re.search(r"자동광학검사\(AOI\)\s*장비", statement, re.I)
    customer = re.search(r"(?:적층세라믹콘덴서\(MLCC\)|MLCC)\s*제조사(?:향|용)", statement, re.I)
    product = re.search(r"솔루션\s*['‘\"]?([A-Za-z0-9가-힣·.-]{2,30})(?:\([^)]*\))?['’\"]?(?:이|가)\s*채택", statement)
    day = re.search(r"(?<!\d)(\d{1,2})일\s*밝혔다", statement)
    site = next((match for row in rows if (match := re.search(r"([가-힣]{2,15})\s*생산거점", row))), None)
    if not (issuer and equipment and customer and product and day and site):
        return {}
    return {"issuer": issuer.group(1), "product": product.group(1), "site": site.group(1),
            "day": day.group(1), "stage": "initial_delivery_completed" if re.search(
                r"초도\s*물량\s*납품을\s*완료", statement) else "adopted", "source_excerpt": statement}


def broker_backlog_mix_observation(title: str, body: str) -> dict[str, str]:
    if focus_kind(title) != "backlog_mix":
        return {}
    statement = next((row for row in source_sentences(source_reported_body(body)) if focus_matches(title, row)), "")
    match = re.search(
        rf"([A-Za-z0-9가-힣]{{2,25}}증권)(?:은|는)\s*(\d{{1,2}})일\s*"
        rf"([A-Za-z0-9가-힣&·.-]{{2,30}})에\s*대해\s*(올해\s*(?:상반기|하반기)|20\d{{2}}년\s*(?:상반기|하반기)|[1-4]분기)\s*"
        rf"기준\s*([^.!?]{{2,25}}?부문)\s*수주\s*잔고\s*(?P<amount>{SOURCE_MONEY})\s*중\s*"
        rf"([가-힣]{{2,15}})\s*비중이\s*(\d+(?:\.\d+)?)%에\s*육박", statement,
    )
    if not match or match.group(3) not in title:
        return {}
    return {"broker": match.group(1), "day": match.group(2), "issuer": match.group(3),
            "period": match.group(4), "business": match.group(5), "amount": match.group('amount'),
            "region": match.group(9), "share": match.group(10), "source_excerpt": statement}


def commercial_delivery_terms(title: str, body: str, published: str = "") -> dict[str, object]:
    """Bind a model-specific delivery to its supplier, customer and announcement."""
    if not re.search(r"공급|납품", title) or not re.match(r"20\d{2}-\d{2}-\d{2}", published):
        return {}
    lead = next((row for row in source_sentences(source_reported_body(body))
                 if not BACKGROUND.search(row) and not PAST_ACTION.search(row)
                 and re.search(r"(?:공급|납품)한다고\s*\d{1,2}일\s*밝혔다", row)), "")
    supplier = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는|가)\s+", lead)
    delivery = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})의\s*[^'‘.!?]{0,40}?['‘]([^'’]{2,60})['’](?:[^'‘’.!?]{0,12})?에\s*"
                         r"([^'‘’\".!?]{2,60}?)\s*(?:공급|납품)한다고", lead)
    day = re.search(r"(?<!\d)(\d{1,2})일\s*밝혔다", lead)
    if not (supplier and delivery and day and supplier.group(1) in title):
        return {}
    customer = re.sub(r"의$", "", delivery.group(1))
    product = re.sub(r"^(?:차세대\s*|소프트웨어\s*중심\s*차량\(SDV\)\s*맞춤형\s*)", "", delivery.group(3))
    return {"issuer": supplier.group(1), "customer": customer,
            "model": canonical_source_fact(delivery.group(2)),
            "product": canonical_source_fact(product),
            "disclosure_date": published[:8] + day.group(1).zfill(2), "stage": "delivery_announced",
            "amounts": [[row.group(2), korean_amount_value(row.group(1))] for row in re.finditer(SOURCE_MONEY, lead)],
            "explicit_revision": bool(re.search(r"공급\s*(?:변경|정정|철회)|추가\s*공급|납품\s*(?:변경|정정)", title + " " + lead))}


def commercial_order_terms(title: str, body: str, published: str = "") -> dict[str, object]:
    """Use disclosed counterparties, product and exact amount, never rounded proximity."""
    if focus_kind(title) != "commercial_order":
        return {}
    source = source_reported_body(body)
    lead = next((sentence for sentence in source_sentences(source)
                 if not PAST_ACTION.search(sentence) and re.search(r"공시했다|공시했다고|수주했다고\s*\d{1,2}일\s*밝혔다", sentence)
                 and re.search(r"수주했|계약.{0,20}체결했", sentence)), "")
    parties = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:\(\d{6}\))?(?:은|는)\s*(?:\d{1,2}일\s*)?([A-Za-z0-9가-힣&·.-]{2,30})(?:\(\d{6}\))?(?:와|과|로부터)\s+", lead)
    amount = re.search(SOURCE_MONEY, lead)
    if not amount:
        amount_statement = next((sentence for sentence in source_sentences(source)
                                 if re.match(r"계약금액은\s*", sentence)), "")
        amount = re.search(SOURCE_MONEY, amount_statement)
    product = re.search(r"\((?:[^()]*?이하\s+)?([A-Z][A-Z0-9-]{1,15})\)[’'\"]?\s*(?:장비|제품|설비)", lead)
    day = re.search(r"(?<!\d)(\d{1,2})일(?=\s)", lead)
    if not (parties and amount and product and day and re.match(r"20\d{2}-\d{2}-\d{2}", published)):
        return {}
    issuer, customer = parties.groups()
    value = korean_amount_value(amount.group(1))
    if issuer not in title or not value:
        return {}
    revision = bool(re.search(r"계약\s*(?:정정|변경|수정)|수주액\s*(?:상향|하향)|추가\s*수주", title + " " + lead))
    period = re.search(r"계약\s*기간은\s*([^.!?\n]{1,45}?까지)", source)
    terms = {"issuer": issuer, "customer": customer, "product": product.group(1),
             "amount": [amount.group(2), value],
             "disclosure_date": published[:8] + day.group(1).zfill(2), "stage": "signed",
             "contract_period": canonical_source_fact(period.group(1)) if period else "",
             "explicit_revision": revision}
    if revision:
        terms["revision_excerpt"] = canonical_source_fact(lead)
    return terms


def industrial_route_study_terms(title: str, body: str, published: str = "") -> dict[str, object]:
    """Identify a signed SMR route-study MOU, not approval or a vessel order."""
    if focus_kind(title) != "industrial_partnership" or not re.match(r"20\d{2}-\d{2}-\d{2}", published):
        return {}
    source = source_reported_body(body)
    lead = next((row for row in source_sentences(source)
                 if focus_matches(title, row) and not PAST_ACTION.search(row)), "")
    issuer = re.match(r"^([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는)\s+", lead)
    partner = re.search(r"\(([A-Z][A-Z0-9.-]{1,15})\)(?:와|과)\s|\s([A-Z][A-Z0-9.-]{1,15})(?:와|과)\s", lead)
    day = re.search(r"(?<!\d)(\d{1,2})일(?=\s)", lead)
    if not (issuer and partner and day and issuer.group(1) in title
            and re.search(r"SMR|소형모듈원자로", lead, re.I)
            and re.search(r"자동차운반선|PCTC", lead, re.I)
            and re.search(r"한국과\s*미국|한미\s*항로", lead)
            and re.search(r"공동\s*검토|공동\s*연구", lead)):
        return {}
    return {"issuer": issuer.group(1), "partner": partner.group(1) or partner.group(2),
            "technology": "SMR", "vessel": "PCTC", "route": "KR-US", "stage": "joint_route_study",
            "announcement_date": published[:8] + day.group(1).zfill(2),
            "amounts": [[item.group(2), korean_amount_value(item.group(1))] for item in re.finditer(SOURCE_MONEY, lead)],
            "explicit_revision": bool(re.search(r"협약\s*(?:정정|변경|철회)|추가\s*협약", title + " " + lead))}


def source_event_identity(alert: dict) -> str:
    """Identify a sourced action and its terms, not a company-wide theme.

    Unrecognised or incomplete facts retain the existing link/title keys.
    Stored title-only receipts may supply an identity only when self-contained.
    """
    audited = audited_source_event_identity(alert)
    if audited:
        return audited
    close = us_equity_close_identity(alert)
    if close:
        return close
    breadth = market_breadth_identity(alert)
    if breadth:
        return breadth
    title = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "")
    body = str(alert.get("source_body") or "") if alert.get("body_verified") else ""
    for event, terms in (("commercial_order", commercial_order_terms(title, body, str(alert.get("published") or ""))),
                         ("commercial_delivery", commercial_delivery_terms(title, body, str(alert.get("published") or ""))),
                         ("intraday_equity", intraday_equity_event_terms(alert)),
                         ("conditional_index_outlook", conditional_index_outlook(title, body, str(alert.get("published") or ""))),
                         ("analyst_target", analyst_target_revision_terms(title, body, str(alert.get("published") or "")))):
        if terms and (terms.get("disclosure_date", terms.get("report_date")) or event == "intraday_equity"):
            terms = {key: value for key, value in terms.items() if not key.endswith("_display")}
            digest = hashlib.sha256(json.dumps(terms, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            return f"source_event:v2:{event}:{digest}"
    route_study = industrial_route_study_terms(title, body, str(alert.get("published") or ""))
    if route_study:
        digest = hashlib.sha256(json.dumps(route_study, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"source_event:v2:industrial_route_study:{digest}"
    research = broker_earnings_report_terms(title, body, str(alert.get("published") or ""))
    if research and research["report_date"] and research["year"]:
        terms = {key: value for key, value in research.items() if not key.endswith("_display")}
        digest = hashlib.sha256(json.dumps(terms, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"source_event:v2:broker_earnings:{digest}"
    for event, terms in (("license", licensing_event_terms(title, body)),
                         ("odd_lot_rule", odd_lot_rule_terms(title, body)),
                         ("merger_agreement", merger_agreement_terms(title, body))):
        if terms:
            digest = hashlib.sha256(json.dumps(terms, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            return f"source_event:v2:{event}:{digest}"
    kind = focus_kind(title)
    factory = factory_tariff_observation(title, body) if body else None
    if factory:
        return (f"source_event:v1:trump:us_factory_not_built:statement:"
                f"max_rate={float(factory['rate']):.12g}:grace_approx_months={factory['months']}")
    facts = [sentence for sentence in source_sentences(body)
             if not BACKGROUND.search(sentence) and focus_matches(title, sentence)]
    foreground = title + " " + " ".join(facts[:3])
    alaska_quote = next((sentence for sentence in source_sentences(body)
                         if not BACKGROUND.search(sentence)
                         and re.search(r"합의[^.!?]{0,30}(?:않|안\s*하)|서명[^.!?]{0,20}(?:않|안\s*하)", sentence)
                         and re.search(r"(?:청구|부담)[^.!?]{0,30}(?:두|2)\s*배|(?:두|2)\s*배[^.!?]{0,30}(?:청구|부담)", sentence)), "")
    if re.search(r"트럼프|Trump", title, re.I) and re.search(r"알래스카|Alaska", title, re.I):
        if re.search(r"한국|Korea|韓", title + " " + body[:800], re.I) and (kind == "trade_threat" or alaska_quote):
            foreground = title + " " + (alaska_quote or " ".join(facts[:3]))
            multiple = re.search(r"(두|\d+(?:\.\d+)?)\s*배|doubl", foreground, re.I)
            if multiple:
                number = "2" if multiple.group(1) in (None, "두") else format(float(multiple.group(1)), ".12g")
                # Charging a project twice is not a doubled tariff rate.
                subject = "project_charge" if alaska_quote else "tariff" if re.search(r"관세|tariff", title, re.I) else "project_charge"
                stage = "implemented" if re.search(r"시행|발효|부과\s*결정|signed|implemented", title, re.I) else "threat"
                rates = sorted(set(re.findall(r"\d+(?:\.\d+)?\s*%", foreground))) if subject == "tariff" else []
                terms = ":rates=" + "+".join(re.sub(r"\s", "", rate) for rate in rates) if rates else ""
                return f"source_event:v1:trump:korea:alaska:{subject}:{stage}:multiple={number}{terms}"
    if kind == "stockpile_release" and re.search(r"G7|주요\s*7개국", foreground, re.I):
        volume = re.search(r"(\d+(?:\.\d+)?)\s*(억|만)?\s*배럴", foreground)
        duration = re.search(r"(\d+)\s*(?:개월|달)|(?:four|4)[ -]months?", foreground, re.I)
        if volume and duration:
            count = float(volume.group(1)) * {None: 1, "만": 10000, "억": 100000000}[volume.group(2)]
            months = duration.group(1) or "4"
            stage = "executed" if re.search(r"방출\s*완료|방출했다|released", title, re.I) else "plan"
            return f"source_event:v1:g7:oil_reserves:{stage}:barrels={count:.12g}:months={int(months)}"
    if re.search(r"트럼프|Trump", title, re.I) and re.search(r"한국|Korea|韓|한미\s*(?:양국|공동|합의)", title + " " + body[:800], re.I) and re.search(r"석유|원유|oil", title, re.I):
        statement = next((sentence for sentence in source_sentences(body or title)
                          if not BACKGROUND.search(sentence) and re.search(r"트럼프|Trump", sentence, re.I)
                          and re.search(r"석유|원유|oil", sentence, re.I)
                          and re.search(r"투자|프로젝트|invest|project", sentence, re.I)), "")
        amount = re.search(r"(\d+(?:\.\d+)?)\s*억\s*달러|\$?\s*(\d+(?:\.\d+)?)\s*billion", statement, re.I)
        if amount:
            dollars = float(amount.group(1)) * 100000000 if amount.group(1) else float(amount.group(2)) * 1000000000
            response = focus_kind(title) == "project_response" and DENIAL_SOURCE.search(body)
            stage = "denial" if DENIAL_HEADLINE.search(title) or response else "signed" if re.search(r"서명|계약\s*체결|signed", title, re.I) else "statement"
            return f"source_event:v1:trump:korea:us_oil_investment:{stage}:usd={dollars:.12g}"
    return ""


@lru_cache(maxsize=1)
def verified_event_aliases() -> tuple[dict, ...]:
    path = Path(__file__).resolve().parent.parent / "data/gamejoa_verified_event_aliases.json"
    return tuple(json.loads(path.read_text(encoding="utf-8"))["entries"])


def audited_source_event_identity(alert: dict) -> str:
    """Only individually reviewed bodies may reconcile rounded order reports."""
    if not alert.get("body_verified") or not alert.get("source_body"):
        return ""
    title = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "")
    digest = hashlib.sha256(str(alert["source_body"]).encode("utf-8")).hexdigest()
    for proof in verified_event_aliases():
        if (proof.get("source_title") == title and proof.get("link") == alert.get("link")
                and proof.get("source_body_sha256") == digest
                and proof.get("source_published_kst") == str(alert.get("published") or "")
                and proof.get("run_id") and proof.get("message_id")):
            return str(proof["source_event_identity"])
    return ""

# Each rule needs a subject and a change in the same source-authored sentence.
# Quantities, counterparties and stages are evidence, not estimates of price impact.
RULES = (
    ("public_compute_allocation", ("earnings", "timeline"),
     r"GPU.{0,100}신청|GPU.{0,60}배정", r"지원됐다|배정됐다|배정했다"),
    ("business_investment_observation", ("earnings", "discount_rate"),
     r"기업들의\s*컴퓨터\s*및\s*관련\s*장비\s*투자", r"전년\s*동기\s*대비.{0,30}(?:증가했다|감소했다|늘었다|줄었다)"),
    ("management_change", ("earnings", "timeline"), r"CFO|CEO|최고재무책임자|최고경영자", r"사임|해임|교체"),
    ("network_segmentation_policy", ("earnings", "timeline"),
     r"망분리|규제\s*완화|신청\s*가능\s*대상|선정\s*규모",
     r"선정된다|선정한다|선정할|확대|늘릴|완화.{0,15}(?:추진|시행|확대)"),
    ("housing_supply_policy", ("earnings", "timeline"),
     r"LH|미분양|매수확약|매입임대", r"지시|결정|확정|시행|발표|밝혔다"),
    ("debt_repayment_change", ("earnings", "timeline"),
     r"부채|대출|debt|loan", r"(?:전액\s*)?상환(?:해|했|완료)|repaid|repayment completed"),
    ("trading_status_change", ("flows", "timeline"),
     r"거래\s*재개|매매\s*재개|액면병합|주식병합|거래정지|매매정지|보통주.{0,45}범위로\s*병합",
     r"재개|결정|발표|완료|정지"),
    ("capital_listing_stage", ("flows", "timeline"),
     r"기업공개|\bipo\b|(?:증시|코스피|코스닥|나스닥)\s*상장|상장\s*(?:추진|예정|연기|철회|신청|승인)|(?:나스닥|코스피|코스닥).{0,35}첫\s*거래|ETF",
     r"추진|예정|목표|신청|승인|상장(?:했다|한다고|한다|할|돼)|첫\s*거래를\s*시작(?:한다|한다고|하는)|연기|철회|마케팅|등록|출시|plan|aim|file|approv|delay|withdraw|market"),
    ("commercial_order", ("earnings", "timeline"),
     r"수주|발주|공급계약|공급(?:하는)?\s*계약|제조\s*(?:서비스\s*)?계약|납품\s*계약|발사\s*계약|건설\s*계약|purchase order|supply contract|manufacturing (?:contract|agreement)|procurement contract|launch (?:contract|agreement)",
     r"체결|맺었다|맺었다고|확정|수주|발주|갱신|취소|파기|해지|협상|추진|서명|sign|secure|award|agree|cancel|negotiat"),
    ("order_backlog_level", ("earnings", "timeline"),
     r"수주잔고|수주\s*잔고|잔여수주|order backlog|remaining orders", r"확보|기록|집계|발표|증가|감소|secur|report|increas|decreas"),
    ("customer_supply_start", ("earnings", "timeline"),
     r"고객|공급|납품|시공|customer|supply|deliver", r"첫\s*(?:공급|납품)|공급(?:했다|한다|하기로)|납품(?:했다|한다)|(?:공급|납품)과\s*설치.{0,10}완료|(?:1차\s*시공|초도\s*납품).{0,15}완료|first delivery|began supplying"),
    ("procurement_execution_stage", ("earnings", "timeline"),
     r"입찰|시공사|우선협상|procurement|bid|preferred bidder",
     r"제출|선정|선택|낙찰|철회|탈락|확보|submit|select|award|withdraw"),
    ("selling_price_or_cost", ("earnings",),
     r"판매가격|판매\s*가격|판가|단가|원가|평균판매가격|(?:세계\s*)?식량\s*가격\s*지수|(?:메모리|HBM|D램|DRAM|낸드|NAND)\s*(?:공급\s*)?가격|\basp\b|selling price|unit price|input cost",
     r"인상|인하|상승|하락|오르|내리|올랐|내렸|급등|급락|증가|감소|전가|협상|상향|하향|rais|cut|rise|fall|increas|decreas|negotiat"),
    ("project_cost_evaluation", ("earnings",),
     r"(?:LNG|원전|데이터센터|발전소|공장).{0,40}(?:사업비|건설비|사업.{0,15}비용)",
     r"추산|추정|비교|두\s*배|\d+(?:\.\d+)?\s*배|cost estimate|estimated cost"),
    ("conditional_project_charge", ("earnings", "timeline"),
     r"청구(?:금|액)?|부담(?:금|액)?",
     r"(?:합의|서명)[^.!?]{0,40}(?:않|안\s*하)[^.!?]{0,60}(?:두|2|\d+(?:\.\d+)?)\s*배"),
    ("energy_stockpile_action", ("earnings", "discount_rate", "timeline"),
     r"비축\s*(?:유|원유|경유)|석유\s*비축|oil reserves|oil stockpile",
     r"방출|매입|재비축|채우|채운|채울|release|refill|purchase"),
    ("earnings_or_guidance", ("earnings",),
     r"매출|영업이익|순이익|영업손실|순손실|마진|실적|가이던스|주당\s*(?:NAV|순자산가치)|(?<!제)출하|판매(?:량|실적|는|가)|시장점유율|revenue|earnings|profit|guidance|shipments",
     r"증가|감소|상승|하락|상회|하회|상향|하향|달성|기록|집계|발표|공시|전망|예상|컨센서스|추정치|적자\s*전환|적자로\s*전환|rise|fall|grow|cut|rais|report|forecast|consensus|beat|miss"),
    ("national_export_release", ("earnings", "discount_rate"),
     r"누적\s*수출|월간\s*수출|수출액", r"달(?:했|하|해)|늘었|증가|감소|기록|집계|넘어섰|달성|달러\s*(?:입니다|이다|였다|이었다)"),
    ("product_sales_mix", ("earnings",),
     r"판매(?:량|대수|비중)?", r"\d+(?:\.\d+)?%\s*(?:를|을)?\s*차지|비중.{0,20}(?:높아|올라|낮아|줄어)"),
    ("industry_market_share", ("earnings",),
     r"(?:D램|DRAM|낸드|NAND|HBM|반도체).{0,80}점유율|매출\s*점유율|시장점유율|market share",
     r"\d+(?:\.\d+)?\s*%|기록|집계|report"),
    ("analyst_revision", ("discount_rate",),
     r"목표주가|목표가|투자의견", r"상향|하향|높였|낮췄|올렸|내렸"),
    ("export_results", ("earnings",),
     r"수출(?:액|실적|량)|수출.{0,45}(?:\d|최대|최저)",
     r"증가|감소|상승|하락|최대|최저|기록|집계|발표"),
    ("research_spending_change", ("earnings", "timeline"),
     r"r&d|연구개발", r"증가|감소|늘|줄|투자|지출|비용|rise|fall|spend|invest"),
    ("research_validation_result", ("earnings", "timeline"),
     r"벤치마크|benchmark", r"\d+(?:\.\d+)?\s*(?:%|배).{0,15}(?:향상|개선|증가|감소|절감)"),
    ("licensing_cashflow", ("earnings", "timeline"),
     r"로열티|선급금|마일스톤|기술이전|royalty|upfront|milestone|licens",
     r"체결|계약|수령|수취|받|합의|서명|sign|agreement|receiv"),
    ("customer_financing_commitment", ("earnings", "timeline"),
     r"대출|전환사채|loan|convertible debt",
     r"받기로\s*합의|대출\s*(?:계약|약정).{0,15}(?:체결|서명)|대출.{0,20}(?:집행했다|승인했다)|agreed to (?:lend|borrow)|loan agreement.{0,20}(?:signed|executed)"),
    ("capital_or_shareholder_action", ("earnings", "timeline"),
     r"투자(?=\s*(?:\d|를|한다|한다고|하는|하고|해|했다|할|하겠|금|액|규모|계획|협약|계약|자금|라운드)|.{0,12}유치)|전략투자|설비투자|capex|자본지출|(?<!대)출자|자금\s*조달|자본\s*조달|회사채|전환사채|전환\s*(?:선순위)?\s*채권|주주환원|배당|자사주|자기주식|지분|funding|financing|buyback|dividend|bond issuance|stake",
     r"체결|유치|출자|발행|증액|삭감|확대|축소|매입|매수|취득|소각|매각|인수|검토|협상|추진|계획|증가|감소|늘리|결정|확정|공시|발표|승인|투입|금융\s*종결|납입|집행|투자\s*라운드.{0,10}참여|raise|issu|buy|repurchas|sell|acquir|announc|consider|negotiat|approv|financing closed|funding disbursed"),
    ("authorized_capital_proposal", ("flows", "timeline"),
     r"수권\s*(?:자본|주식)|authorized (?:capital|shares)", r"안건|상정|제안|표결|proposal|vote"),
    ("financing_infrastructure", ("earnings", "timeline"),
     r"금융플랫폼|금융\s*플랫폼|투자\s*자금\s*조달|financing platform|investment financing",
     r"구축|설립|출범|조성|지원|build|establish|launch|support"),
    ("convertible_ownership_rights", ("flows", "timeline"),
     r"전환사채|\bcb\b|convertible bond|의결권|voting rights", r"전환|승인|확보|convert|approv|secur"),
    ("equity_compensation_change", ("earnings", "flows", "timeline"),
     r"주식\s*보상|성과연동주식|양도제한조건부주식|stock.based compensation|equity compensation",
     r"신규\s*도입|도입.{0,20}(?:결의|결정|발표)|부여.{0,20}(?:결의|결정|발표)|도입했다|도입하기로|introduc|adopt|approve"),
    ("insider_disclosed_trade", ("flows",),
     r"(?:회장|대표|사장|임원|ceo|executive).{0,80}(?:주식|지분|shares|stake)",
     r"매수|매입|취득|매도|매각|처분|buy|purchas|sell|disclos"),
    ("ownership_transfer", ("flows", "timeline"),
     r"주식|지분|shares|stake", r"기부|이전|증여|donat|transfer"),
    ("corporate_transaction", ("earnings", "timeline"),
     r"회사|기업|사업|법인|지분|인수|합병(?!원)|company|business|subsidiar|stake|acquir|merger", r"인수|합병(?!원)|acquir|merger"),
    ("corporate_ownership_execution", ("earnings", "timeline"),
     r"잔여\s*지분|완전자회사|100%\s*자회사|주식교환|지분.{0,20}\d+(?:\.\d+)?%|remaining stake|wholly.owned|share exchange",
     r"확보|편입|취득|교환|acquir|convert|exchange"),
    ("corporate_action_clarification", ("earnings", "timeline"),
     r"자금조달|인수|합병(?!원)|공급\s*계약|투자\s*(?:계획|자체)|투자액|financing|acquisition|merger|supply contract|investment plan",
     r"(?:확정|결정)된\s*사항(?:은|이)?\s*없|합의\s*(?:안\s*(?:됐|되)|하지\s*않)|미합의|부인|사실무근|denies|not final"),
    ("policy_agreement_clarification", ("earnings", "timeline"),
     r"팩트시트|공동\s*합의|(?:사업|프로젝트)의?\s*추진\s*여부",
     r"포함[^.!?]{0,20}않|팩트시트[^.!?]{0,20}없|말하기\s*어렵|밝히기\s*어렵"),
    ("operating_asset_transaction", ("earnings", "timeline"),
     r"(?:사옥|부동산|사업부|영업자산).{0,20}(?:매각|취득|매입)|(?:칩|GPU|데이터센터|설비).{0,100}(?:특수목적기구|\bSPV\b|담보|재임차)|operating asset|headquarters sale|sale.leaseback",
     r"결정|확정|검토|추진|논의|계약|매각했다|매입했다|이전하는|decid|consider|discuss|contract|sold|acquir"),
    ("institutional_capital_access", ("earnings", "timeline"),
     r"국민연금|연기금|벤처캐피털|\bvc\b|pension fund|venture capital",
     r"투자\s*기회.{0,8}(?:확대|넓)|출자|투자협력|투자.{0,20}(?:협력|논의)|funding|investment opportunities|commitment"),
    ("market_infrastructure", ("timeline",),
     r"증권계좌|거래시스템|결제망|증권거래소|오픈뱅킹|증권 거래|brokerage account|trading system|payment network",
     r"연결|도입|출시|가동|개편|허용|launch|deploy|connect|reform"),
    ("cyber_operational_incident", ("earnings", "timeline"),
     r"해킹|사이버|랜섬웨어|침해|(?:개인|고객|임직원)\s*정보|data breach|ransomware",
     r"유출|서비스.{0,20}중단|운영.{0,20}중단|생산.{0,20}중단|피해|reported|confirmed|halted|disrupted"),
    ("cyber_regulatory_response", ("timeline",),
     r"금융(?:당국|위원장|위원회|감독원장)|금감원장|금융위|금감원",
     r"긴급\s*(?:점검|대응)?\s*회의|긴급\s*소집"),
    ("model_operating_specification", ("earnings", "timeline"),
     r"모델|llm|ai model|language model|솔라 미니|gpu|npu",
     r"(?:gpu|npu|가속기)\s*(?:\d+|한|두|세)\s*(?:장|개)|\d+\s*(?:장|개)의?\s*(?:gpu|npu)|(?:메모리|전력|지연시간|추론비용|운용비용|토큰량|토큰\s*처리량).{0,25}\d+(?:\.\d+)?\s*(?:%|gb|w|배)|\d+(?:\.\d+)?\s*(?:배|%)\s*(?:빠르|절감|줄|감소)"),
    ("industrial_architecture_adoption", ("earnings", "timeline"),
     r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model|co.packaged optics",
     r"규격|채택|통합|전환|도입|standard|specification|adopt|integrat|deploy"),
    ("industrial_partnership_execution", ("earnings", "timeline"),
     r"SMR|소형모듈원자로|원전|선박|풍력|태양광|발전소|반도체|데이터센터|휴머노이드|자율주행|무인기|항공우주|wind power|solar|power plant|semiconductor|data center|humanoid|autonomous driving|drone|aerospace",
     r"(?:업무협약|공동개발\s*협약|MOU).{0,20}(?:체결|맺|서명)|(?:체결|맺|서명).{0,20}(?:업무협약|공동개발\s*협약|MOU)|signed.{0,30}(?:mou|joint development)"),
    ("rates_fx_or_macro", ("discount_rate",),
     r"금리|국고채|모기지|주담대|주택담보대출|물가|인플레이션|고용(?!량)|비농업\s*일자리|실업률|건설지출|환율|달러화|유동성|차입|구매관리자|\bpmi\b|cpi|pce|payroll|mortgage|interest rate|treasury (?:yield|bond|note|bill|securit|borrow)|(?:u\.?s\.?\s+|united states )treasury|inflation|exchange rate|borrowing",
     r"인상|(?<!할)인하|동결|상승|하락|오른|내린|올랐|내렸|둔화|급등|급락|상회|하회|밑돌|웃돌|발표|기록|증가|감소|결정|약세|강세|최고|치솟|cut|hike|hold|rise|fall|miss|beat|announc|estimat|record"),
    ("attributed_fx_forecast", ("discount_rate",),
     r"원[·/]달러|달러[·/]원|환율", r"전망|예상"),
    ("policy_scope_or_stage", ("timeline",),
     r"관세|법인세|세율|세금|수출통제|수출.{0,12}(?:금지|제한)|수입금지|수입 금지|수입 제한|수입제한|과잉생산.{0,20}(?:대응|조치)|제재|보조금|지원금|예탁금|긴급조치권|규제|인허가|허가\s*절차|고시|조례|환경심사|환경영향평가|주파수|tariff|tax rate|corporate tax|export control|import ban|sanction|subsid|licens|environmental review|spectrum|\bban(?:s|ned)?\b",
     r"제안|검토|추진|인상|인하|부과|올리|올렸|낮추|낮췄|상향|하향|완화|강화|시행|발효|금지|제한|(?<!인)허가(?:했|한다|를\s*(?:내|받|취득))|승인(?:했|한다|을\s*(?:받|획득|취득))|제정|개정|철회|의견수렴|입법예고|면제|배정|의결|착수|발표|propos|draft|\bban(?:s|ned)?\b|prohibit|restrict|approv|enact|implement|consider|exempt|allocat|adopt"),
    ("economic_restriction_response", ("discount_rate", "timeline"),
     r"경제\s*전쟁|제재", r"새로운\s*조치.{0,30}(?:도입|발표)|대응\s*조치.{0,30}(?:도입|발표|시행)"),
    ("environmental_approval", ("timeline",),
     r"최종\s*환경평가|FONSI|환경영향평가서", r"완료|결정을\s*내렸|작성\s*없이|면제"),
    ("export_control_scope", ("earnings", "timeline"),
     r"country group|trade authorization|export administration|수출관리규정|수출허가",
     r"remov|add|available|amend|change|변경|제외|허용"),
    ("public_program_cost_study", ("timeline",),
     r"방위사업|국방예산|방위예산|조달예산|missile defense|defense budget|procurement budget",
     r"추산|심의|추정|예산안|cost estimate|cost study|budget proposal"),
    ("market_price_or_flow", (),
     r"주가|증시|코스피|코스닥|나스닥|S&P\s*500|러셀\s*2000|etf|etn|순매수|순매도|거래대금|유입|유출|수익률|주식|shares|stocks|equities|inflows|outflows",
     r"급등|급락|상승|하락|올랐|내렸|순매수|순매도|유입|유출|이동|상장|편입|편출|증가|감소|surge|slump|rise|fall|inflows|outflows|list|rebalance"),
    ("energy_import_mix", ("earnings", "timeline"), r"원유\s*도입\s*비중", r"\d+(?:\.\d+)?%"),
    ("technical_standard", ("timeline",), r"JESD\d+[A-Z0-9.-]*|IEEE\s*\d+[A-Z0-9.-]*|ISO\s*\d+[A-Z0-9.-]*", r"표준|규격"),
    ("trading_rule", ("flows", "timeline"), r"단주|최소\s*(?:매매|거래)\s*(?:수량|단위)|매매수량단위|시간외\s*종가매매", r"검토|허용|확대|변경|시행|발표"),
    ("physical_supply_or_capacity", ("earnings", "timeline"),
     r"공장|(?<!재)생산(?!자|성|유발)|설비|공급|수요|재고|수율|리드타임|부족|품귀|항만|물류|운송|데이터센터|AI\s*팩토리|factory|production|supply|demand|inventory|lead time|port|freight|data cent(?:er|re)",
     r"증설|착공|가동|증가|감소|중단|차질|부족|품귀|지연|연장|매각|검토|확대|축소|상용화|구축|건설\s*(?:하|할|을|에|계획|계약|추진)|신설|짓고|짓는다|도입|생산할|늘고|늘었|expand|start|halt|disrupt|shortage|delay|consider|launch|build|deploy"),
    ("sector_demand_outlook", ("earnings",),
     r"반도체|메모리|데이터센터|출하량|semiconductor|memory|data center|shipments", r"호황|불황|수요.{0,20}(?:전망|늘|줄)|(?:발주|수주|시장\s*규모).{0,80}(?:추산|추정|전망|예상)|boom|bust|demand outlook"),
    ("market_outlook", (),
     r"코스피|코스닥|증시|주식시장|kospi|kosdaq|stock market", r"오를|내릴|상승할|하락할|상승\s*전망|하락\s*전망|forecast|outlook"),
    ("fund_assets_level", (),
     r"펀드.{0,40}순자산|순자산.{0,30}펀드|fund.{0,30}(?:net assets|aum)", r"돌파|증가|감소|exceed|increas|decreas"),
    ("technology_or_clinical_stage", ("earnings", "timeline"),
     r"메모리|반도체|hbm|hbf|cxl|칩|공정|로봇|신약|임상|fda|의약품|기술|양자|극저온|데이터센터.{0,50}냉각|냉각.{0,50}데이터센터|memory|semiconductor|chip|clinical|drug|technology|quantum|cryogenic",
     r"양산|상용화|인증|승인|허가|임상\s*[1-3]상.{0,15}결과|임상 결과|임상결과|공급|도입|검증|성능|대역폭|수율|전력효율|결과 발표|생산|production|commercial|certif|approv|deploy|validat|performance|bandwidth|yield"),
    ("space_execution_stage", ("timeline",),
     r"위성|궤도|satellite|orbital", r"시험|검증|발사.{0,15}(?:완료|성공)|교신.{0,20}성공|prototype|orbital test|launch.{0,20}(?:complet|success)"),
    ("launch_turnaround_bottleneck", ("earnings", "timeline"),
     r"로켓|발사체|우주선|rocket|launch vehicle|spacecraft",
     r"(?:재발사|재비행|발사\s*일정|정비\s*기간|교체\s*비용).{0,35}(?:지연|연장|증가|감소|단축|제한)|"
     r"(?:turnaround|reflight|relaunch|launch schedule|maintenance (?:time|cost)).{0,35}(?:delay|increas|decreas|reduc|limit|extend)"),
    ("space_thermal_validation", ("timeline",),
     r"열\s*차폐|heat[ -]shield|thermal protection|재생\s*냉각|regenerative cooling",
     r"시험|검증|실증|인증|채택|도입|검토|test|validat|demonstrat|certif|adopt|deploy|consider"),
    ("cryogenic_propellant_storage", ("timeline",),
     r"추진제|\bzbo\b|무손실\s*저장|zero[ -]boil[ -]off|cryogenic.{0,25}(?:storage|propellant)",
     r"시험|검증|실증|인증|도입|검토|test|validat|demonstrat|certif|deploy|consider"),
    ("biology_research_discovery", ("timeline",),
     r"효소|단백질|enzyme|protein", r"발견|규명|discover|characteriz"),
    ("energy_geopolitics_or_supply_risk", ("earnings", "discount_rate"),
     ENERGY_SUBJECT,
     r"공격|공습|피격|발사체|화재|휴전|협상|통항|봉쇄|제재|상승|하락|오른|내린|급등|급락|차질|감산|증산|합의|경고|명령|배치|추가\s*파견|파견했다|발표|attack|strike|ceasefire|talks|blockade|sanction|rise|fall|disrupt|output|warn|deploy|announc"),
    ("climate_operational_damage", ("earnings", "timeline"),
     r"폭염|폭우|홍수|태풍|정전|가뭄|산불|heatwave|flood|outage|drought|wildfire",
     r"전력|변압기|과부하|폐사|양식|농작물|생산|공급|항만|물류|공장|피해|사망|power|transformer|crop|production|supply|port|factory|damage|death"),
    ("labor_cost_or_execution", ("earnings", "timeline"),
     r"파업|노조|성과급|임단협|(?<!금)감원|해고|(?:인력|인원|일자리).{0,20}감축|임금|strike|union|layoff|laid off|wage",
     r"생산|공장|운송|항만|비용|인상|교섭|협상|부결|타결|주식|지급|중단|감축|production|factory|plant|port|cost|talks|shares|halt|cut"),
    ("customer_discussions", ("earnings", "timeline"),
     CUSTOMER_DISCUSSION_SUBJECT,
     r"협상|논의|검토|회동|협력(?!사)|합의|협약|negotiat|discuss|consider|meeting|collaborat|agreement"),
)
COMPILED_RULES = tuple(
    (kind, axes, re.compile(subject, re.I), re.compile(action, re.I))
    for kind, axes, subject, action in RULES
)


def evidence_is_new_event(kind: str, sentence: str) -> bool:
    """Do not promote service descriptions or event support into transactions."""
    if COMPANY_PROFILE.search(sentence) or ACCOUNTING_NOTE.search(sentence):
        return False
    if kind == "business_investment_observation":
        return bool(business_investment_observation(sentence))
    if kind == "technical_standard":
        return bool(re.search(r"발표|제정|채택", sentence))
    if kind in {"customer_discussions", "commercial_order", "physical_supply_or_capacity",
                "technology_or_clinical_stage", "industrial_partnership_execution",
                "capital_or_shareholder_action"} and SPECULATIVE_CONTACT.search(sentence):
        return False
    if kind in {"physical_supply_or_capacity", "technology_or_clinical_stage", "selling_price_or_cost",
                "rates_fx_or_macro", "capital_or_shareholder_action", "market_price_or_flow"}:
        if EXPLANATORY_ONLY.search(sentence) and not NEW_EXECUTION.search(sentence) and not re.search(
            r"\d[\d,.]*\s*(?:%|bp|조원|억원|달러|톤|대).{0,35}(?:기록|집계|발표|공시|상향|하향)", sentence,
        ):
            return False
        if re.search(r"20\d{2}년에[^.!?]{0,80}(?:이미|도입된\s*바|출시된)", sentence):
            return False
    if kind in {"physical_supply_or_capacity", "technology_or_clinical_stage"} and re.search(
        r"상용화하며\s*축적|축적한.{0,70}바탕으로.{0,90}개발했다", sentence,
    ) and not re.search(r"새로.{0,40}(?:인증|양산|납품)|시험\s*결과|실증\s*결과|공급\s*계약", sentence):
        return False
    if kind in {"physical_supply_or_capacity", "technology_or_clinical_stage"} and re.search(
        r"상용화\s*가능성이\s*높|기술\s*선점에\s*나서고", sentence,
    ) and not QUANTITY.search(sentence) and not NEW_EXECUTION.search(sentence):
        return False
    if kind in {"network_segmentation_policy", "housing_supply_policy"}:
        focus_title = "망분리 규제 완화" if kind == "network_segmentation_policy" else "LH 미분양 매수확약"
        return focus_matches(focus_title, sentence)
    if kind == "national_export_release":
        return bool(national_export_observation(sentence))
    if kind in {"cyber_operational_incident", "cyber_regulatory_response"}:
        return focus_matches("금융권 해킹", sentence)
    if kind in {"technology_or_clinical_stage", "physical_supply_or_capacity", "industrial_architecture_adoption"} and re.search(
        r"(?:움직임|추세|흐름|사례).{0,16}(?:이어지|이어지고|늘고|늘어나|확산)|"
        r"(?:활용|적용)\s*범위.{0,16}(?:넓어지고|확대되고)", sentence,
    ) and not (
        QUANTITY.search(sentence)
        or re.search(r"(?:계약|발주).{0,20}(?:체결|확정)|(?:시험|검증|인증).{0,20}(?:완료|획득)|착공했다|가동을\s*시작", sentence)
    ):
        return False
    if kind == "customer_discussions" and SOCIAL_MEETING_PROOF.search(sentence) and not SCOPED_BUSINESS_DISCUSSION.search(sentence):
        return False
    if re.search(r"(?:주요|법률)\s*이슈를\s*짚고|(?:핵심\s*)?정보를\s*전달하고자|기사(?:에서는|에서)[^.!?]{0,35}소개합니다", sentence):
        return False
    if kind == "customer_discussions" and re.search(
        r"(?:검토|평가|심사)하는\s*(?:프로그램|제도)|(?:고객|구축|서비스)\s*사례[^.!?]{0,40}(?:제출|인정)|"
        r"program[^.!?]{0,50}(?:reviews|evaluates)[^.!?]{0,40}customer", sentence, re.I,
    ):
        return False
    if kind in {"capital_or_shareholder_action", "convertible_ownership_rights"} and re.search(
        r"증액\s*승인만으로|즉각적인\s*희석\s*효과는\s*없|신주가\s*발행되지는\s*않|"
        r"(?:검토|의결권을\s*행사)할\s*충분한\s*시간", sentence,
    ):
        return False
    if kind == "capital_or_shareholder_action" and re.search(r"비전을\s*달성하기\s*위해|패스트트랙을\s*택했다", sentence):
        return False
    if kind == "authorized_capital_proposal":
        return focus_matches("수권자본 증액", sentence)
    if kind == "trading_status_change":
        if re.search(r"(?:기준인지|반영됐는지).{0,25}(?:확인되지|불명확)|회사가 발표한 값이 아니라", sentence):
            return False
        return bool(re.search(
            r"(?:거래|매매).{0,25}(?:재개|정지)|"
            r"(?:액면|주식)병합.{0,60}(?:추진|상정|결정|승인|시행|완료|발표)|"
            r"\d+주를\s*\d+주로\s*합치는\s*액면병합|"
            r"\d+대\d+(?:에서\s*\d+대\d+)?[^.!?]{0,30}병합.{0,55}(?:상정|결정|승인|발표)", sentence,
        ))
    if kind in {"commercial_order", "corporate_transaction", "customer_supply_start", "customer_discussions", "industrial_partnership_execution", "capital_or_shareholder_action", "insider_disclosed_trade", "ownership_transfer", "technology_or_clinical_stage"} and PAST_ACTION.search(sentence):
        return False
    if kind == "rates_fx_or_macro" and re.search(r"환율\s*환산|매출\s*인식|기간\s*귀속|기말\s*조정", sentence):
        return False
    if kind == "rates_fx_or_macro" and re.search(r"가정하면|오르는\s*정도|상승하는\s*정도", sentence):
        return False
    if kind == "attributed_fx_forecast":
        return bool(
            re.search(r"[A-Za-z가-힣]{2,20}증권", sentence)
            and re.search(r"올해\s*연말|내년\s*연말", sentence)
            and re.search(r"\d[\d,]*\s*원\s*(?:전후|안팎)", sentence)
            and re.search(r"전망했다|예상했다", sentence)
        )
    if re.match(r"^[■#]\s*", sentence) and not re.search(r"(?:다|요)[.!?]?$", sentence):
        return False
    if re.search(r"해당\s*수치|이번\s*공시는\s*실적\s*발표가\s*아니", sentence) and re.search(r"반영되지|실적\s*발표가\s*아니", sentence):
        return False
    if kind == "convertible_ownership_rights" and re.search(r"전환사채|convertible bond", sentence, re.I):
        return bool(re.search(
            r"발행|전환\s*(?:권|율|가액|가격|비율|청구).{0,30}(?:변경|조정|확정|승인|행사)|"
            r"전환사채.{0,25}전환.{0,15}(?:승인|결정|청구)|issu|conversion.{0,25}(?:approv|change|exercise)", sentence, re.I,
        ))
    if kind == "policy_scope_or_stage" and re.search(
        r"(?:찬성|반대|지지)[^.!?]{0,25}\d+(?:\.\d+)?%|여론조사|지지율", sentence,
    ) and not FORMAL_POLICY_EXECUTION.search(sentence) and not re.search(
        r"국민투표[^.!?]{0,35}(?:가결|부결|확정)|referendum[^.!?]{0,35}(?:passed|rejected)", sentence, re.I,
    ):
        return False
    if kind in {"physical_supply_or_capacity", "energy_geopolitics_or_supply_risk"} and re.search(
        r"(?:수\s*있|가능성)[^.!?]{0,35}(?:분석|추측)|(?:의도|심리(?:적)?\s*압박|목적)[^.!?]{0,80}(?:수\s*있|가능성)", sentence,
    ) and not re.search(
        r"(?:공급|생산|운송|통항|물류)[^.!?]{0,25}(?:중단됐|중단되었|차질이\s*발생|폐쇄됐)|"
        r"(?:정유|유전|송유관|에너지\s*시설)[^.!?]{0,30}(?:피격|파손|중단)", sentence,
    ):
        return False
    if re.search(r"체험해\s*보고|미리\s*체험|솔루션.{0,30}(?:탐색|찾아볼|검색)|카탈로그.{0,30}(?:분류|제공)", sentence) and not re.search(
        r"(?:공급|납품)\s*계약.{0,20}체결|수주했다|(?:성능|전력|비용).{0,20}\d+(?:\.\d+)?%", sentence,
    ):
        return False
    if kind == "capital_listing_stage" and "ETF" in sentence.upper() and not re.search(r"기업공개|\bipo\b", sentence, re.I):
        return bool(re.search(r"(?:출시|상장)(?:했다|했다고|한다|한다고|할|될|한\s*것|될\s*예정)|신규\s*상장", sentence, re.I))
    if re.search(r"논의해\s*나가겠다|해소될\s*수\s*있도록|최선을\s*다하겠다", sentence) and not re.search(
        r"고시.{0,12}개정|법안.{0,12}(?:발의|제출)|계약.{0,12}체결|시행일.{0,15}확정", sentence,
    ):
        return False
    if kind == "commercial_order":
        if re.search(r"증권|연구원|애널리스트|analyst", sentence, re.I) and re.search(
            r"추산|추정|예상|전망|estimate|forecast|expect", sentence, re.I,
        ) and not re.search(r"계약.{0,20}체결|수주했다|수주에\s*성공|계약을\s*확정", sentence):
            return False
        return bool(re.search(
            r"체결|맺었다|맺었다고|확정|수주(?:했다|했다고|한|하며|했으며|에\s*성공)|발주(?:했다|하기로)|갱신|취소|파기|해지|협상|서명|"
            r"(?:수주|발주).{0,20}(?:금액|규모|억\s*원|조\s*원)|sign|secur|award|agree|cancel|negotiat", sentence, re.I,
        ))
    if kind == "corporate_transaction":
        if re.search(r"인수\s*계약이라|거래가\s*마무리되면|통합\s*과정의\s*불확실성", sentence):
            return False
        return bool(re.search(
            r"(?:인수|합병)(?:했다|한다고|한다|하기로|한|를\s*(?:검토|추진|협상|결정))|"
            r"(?:인수|합병|결합).{0,30}(?:계약.{0,15}체결|협상\s*중|검토\s*중|합의했|발표했|완료|마무리)|"
            r"인수(?:하는)?\s*방안.{0,15}(?:논의|검토|협상)|"
            r"인수\s*계약에\s*따라[^.!?]{0,70}주당|"
            r"(?:acquir|merg).{0,35}(?:announc|agree|complete|consider|negotiat)|acquired|acquisition of", sentence, re.I,
        ))
    if kind == "capital_or_shareholder_action":
        if re.search(r"포함될\s*수\s*있|사용할\s*수\s*있|일반\s*운영자금에는", sentence) and not re.search(
            r"발행.{0,20}(?:계획|추진|발표)|유치했다|계약을\s*체결|집행했다|출자하기로\s*결정", sentence,
        ):
            return False
        if SUPPORT_EVENT.search(sentence) and not re.search(
            r"(?:투자|출자|지원금|보조금).{0,25}\d[\d,.]*\s*(?:조|억|만|billion|million)|"
            r"(?:투자|출자).{0,20}(?:계약\s*체결|유치했다|집행했다)|funding (?:secured|committed)", sentence, re.I,
        ):
            return False
    if kind == "policy_scope_or_stage" and POLICY_ADVOCACY.search(sentence):
        trade_threat = re.search(r"(?:수출|수입).{0,30}(?:금지|제한).{0,35}(?:경고|위협)|(?:관세|제재).{0,25}(?:부과|강화).{0,25}(?:경고|위협)", sentence)
        return bool(FORMAL_POLICY_EXECUTION.search(sentence) or trade_threat)
    if kind == "policy_scope_or_stage" and re.search(r"규제\s*명확성|규제.{0,15}명확해질|출발선", sentence):
        return bool(re.search(r"입법예고|시행일|제정|개정|발효|행정명령|규제안|법안", sentence))
    if kind == "policy_scope_or_stage" and re.search(r"규제\s*명확화\s*후|규제가\s*통과된다면", sentence):
        return bool(FORMAL_POLICY_EXECUTION.search(sentence))
    if kind == "market_infrastructure" and re.search(r"연결돼\s*있|연결되어\s*있|기반으로\s*작동", sentence):
        return bool(re.search(r"새로|처음|신규|도입했다|가동했다|출시했다", sentence))
    if kind == "technology_or_clinical_stage" and re.search(r"기대한다|기대된다|역량을|전문성을|소개하는\s*계기|학회.{0,20}(?:선정|채택)", sentence):
        return bool(re.search(r"임상\s*[1-3]상|\d+(?:\.\d+)?\s*(?:%|배|mK|dB)|인증\s*(?:획득|취득)|허가\s*(?:신청|승인)", sentence, re.I))
    if kind == "technology_or_clinical_stage" and not re.search(
        r"(?<!해)양산(?!업)|상용화|인증|승인|허가|임상\s*[1-3][ab]?상.{0,15}결과|임상\s*결과|공급|도입|검증|성능|대역폭|수율|전력효율|생산|production|commercial|certif|approv|deploy|validat|performance|bandwidth|yield", sentence, re.I,
    ):
        return False
    if kind == "physical_supply_or_capacity" and re.search(
        r"(?:공급|할인행사)[^.!?]{0,100}(?:진행한\s*점|실시한\s*점|도움이\s*(?:됐|되었))", sentence,
    ):
        return False
    if kind == "physical_supply_or_capacity" and re.search(
        r"기대감|테마성|수혜\s*기대|주가를\s*뒷받침|가능성이\s*주가|"
        r"(?:고도화|확충|확대)(?:해야|할\s*필요)|해야\s*한다는\s*시장의\s*요구", sentence,
    ):
        return bool(re.search(r"\d[\d,.]*\s*(?:GW|MW|조\s*원|억\s*원|톤|대)|계약\s*체결|착공했다|가동을\s*시작", sentence, re.I))
    if kind == "market_price_or_flow" and re.search(r"법률\s*(?:솔루션|자문)|투자유치\s*가이드|회수\s*전략", sentence):
        return False
    if kind == "market_price_or_flow" and re.search(r"상장\s*의미|상장기업으로\s*등극|상장사인|상장기업인", sentence) and not re.search(
        r"주가|거래대금|순매수|순매도|(?:자금|투자금).{0,20}(?:유입|유출)|\d+(?:\.\d+)?%", sentence,
    ):
        return False
    if kind == "market_price_or_flow" and re.search(r"투자할\s*수|투자가\s*가능|추종하는", sentence) and not re.search(
        r"순매수|순매도|유입|유출|거래대금|수익률|주가.{0,20}\d", sentence,
    ):
        return False
    if kind == "market_price_or_flow" and re.search(r"유의할|주의할|유의해야|주의해야|변동성.{0,15}(?:지적|유의)", sentence):
        return False
    if kind == "project_cost_evaluation" and not (
        QUANTITY.search(sentence) or re.search(r"(?:두|\d+(?:\.\d+)?)\s*배", sentence)
    ):
        return False
    if kind == "energy_geopolitics_or_supply_risk":
        without_quotes = re.sub(r"(?:S-?Oil|SK이노베이션)\s*\([^)]*\)", "", sentence, flags=re.I)
        if not re.search(ENERGY_SUBJECT, without_quotes, re.I):
            return False
    if kind == "climate_operational_damage":
        if re.search(r"구호대|구조대|구호\s*(?:활동|물품)|봉사|기부|성금|감사|노고|짧은\s*정전|정전\s*시간.{0,25}(?:짧|최저|\d위)", sentence):
            return False
        if re.search(r"(?:피해|정전|차질).{0,15}(?:방지|예방)|예방.{0,15}(?:피해|정전)|prevent.{0,25}(?:outage|damage)", sentence, re.I):
            return False
    return True


def news_value_rank(evidence: list[dict]) -> int:
    """Economic mechanism outranks textual focus and announcement certainty."""
    kinds = {item["kind"] for item in evidence}
    if kinds & {"business_investment_observation", "trading_rule", "energy_import_mix", "network_segmentation_policy", "housing_supply_policy", "commercial_order", "order_backlog_level", "customer_supply_start", "procurement_execution_stage", "selling_price_or_cost",
                "earnings_or_guidance", "industry_market_share", "export_results", "national_export_release", "licensing_cashflow", "corporate_transaction", "corporate_ownership_execution", "export_control_scope",
                "policy_scope_or_stage", "environmental_approval", "industrial_architecture_adoption", "physical_supply_or_capacity",
                "launch_turnaround_bottleneck", "sector_demand_outlook"}:
        return 4
    if kinds & {"technical_standard", "technology_or_clinical_stage", "space_execution_stage", "space_thermal_validation",
                "cryogenic_propellant_storage", "biology_research_discovery", "research_validation_result", "model_operating_specification",
                "customer_discussions", "industrial_partnership_execution", "corporate_action_clarification", "capital_or_shareholder_action", "capital_listing_stage",
                "authorized_capital_proposal", "policy_agreement_clarification", "economic_restriction_response", "customer_financing_commitment", "public_program_cost_study", "project_cost_evaluation", "conditional_project_charge", "energy_stockpile_action", "energy_geopolitics_or_supply_risk"}:
        return 3
    return 2


def transmission_scope(title: str, evidence: list[dict]) -> tuple[int, str]:
    """Prioritize sourced market/industry changes, not merely dense issuer facts."""
    kinds = {item['kind'] for item in evidence}
    excerpts = ' '.join(item['source_excerpt'] for item in evidence)
    if 'business_investment_observation' in kinds:
        return 3, 'dated_business_equipment_investment_observation'
    if "energy_import_mix" in kinds:
        return 3, 'national_energy_import_mix'
    if "technical_standard" in kinds and re.search(r"반도체|실리콘\s*포토닉스|광통신|전력망|데이터센터", title):
        return 2, 'industry_technical_standard'
    if kinds & {"trading_rule", "network_segmentation_policy", "housing_supply_policy"}:
        return 3, 'scoped_national_regulatory_or_supply_action'
    if 'national_export_release' in kinds:
        return 3, 'national_export_release'
    if 'economic_restriction_response' in kinds:
        return 2, 'announced_economic_response_without_specified_policy_terms'
    if focus_kind(title) == 'breadth' and 'market_price_or_flow' in kinds and QUANTITY.search(excerpts) and re.search(
        r"S&P\s*500|나스닥|러셀\s*2000|코스피|코스닥", excerpts, re.I,
    ):
        return 3, 'market_wide_breadth_change'
    if 'policy_agreement_clarification' in kinds and re.search(r"한미|한국|양국|Korea", excerpts, re.I):
        return 3, 'bilateral_policy_agreement_clarification'
    if kinds & {'policy_scope_or_stage', 'export_control_scope', 'environmental_approval'} and re.search(
        r"관세|수출통제|수입.{0,20}(?:금지|제한)|금리|예탁금|FCC|BIS|NEPA|tariff|export control|import ban|interest rate", title, re.I,
    ):
        return 3, 'market_wide_policy_terms'
    if focus_kind(title) in {'macro_release', 'market_macro_response'} and kinds & {'rates_fx_or_macro'} and QUANTITY.search(excerpts) and not REGIONAL_CPI.search(title):
        return 3, 'national_macro_release'
    if kinds & {'energy_stockpile_action', 'energy_geopolitics_or_supply_risk'} and re.search(
        rf"{OIL_PRICE}|원유|비축|경유|천연가스|호르무즈|이란|우크라이나|oil|stockpile|hormuz|iran|ukraine", f"{title} {excerpts}", re.I,
    ):
        return 3, 'energy_or_geopolitical_transmission'
    if kinds & {'market_price_or_flow'} and re.search(r"외국인|기관|연기금|ETF|ETN", title, re.I) and re.search(
        r"순매수|순매도|유입|유출|규제|예탁금", title,
    ):
        return 3, 'market_capital_flow'
    if kinds & {'industry_market_share', 'selling_price_or_cost', 'physical_supply_or_capacity', 'order_backlog_level', 'sector_demand_outlook',
                'commercial_order', 'capital_or_shareholder_action', 'industrial_architecture_adoption'} and re.search(
        r"설비투자|CAPEX|데이터센터|HBM|D램|DRAM|낸드|NAND|파운드리|광통신|HVDC|CPO|"
        r"전력망|원전|SMR|양산|공급부족|공급\s*부족|메모리|반도체|memory|semiconductor|data cent(?:er|re)", title, re.I,
    ):
        return 2, 'industry_supply_or_investment_chain'
    return 1, 'issuer_specific_event'


def equity_publication_assessment(title: str, evidence: list[dict], *, body: str = "", source_url: str = "") -> dict:
    """Separate a true economic fact from a foreground stock-market catalyst."""
    kinds = {item['kind'] for item in evidence}
    if not kinds:
        return {'eligible': False, 'reason': 'no_verified_economic_change'}
    execution = any(NEW_EXECUTION.search(item['source_excerpt']) for item in evidence)
    lead = " ".join(source_sentences(source_reported_body(body))[:5])
    economic_execution = any(
        not PAST_ACTION.search(item['source_excerpt']) and item['kind'] in {
            'commercial_order', 'customer_supply_start', 'procurement_execution_stage',
            'earnings_or_guidance', 'licensing_cashflow', 'corporate_ownership_execution',
            'export_control_scope', 'policy_scope_or_stage', 'capital_or_shareholder_action',
        } and (NEW_EXECUTION.search(item['source_excerpt']) or FORMAL_POLICY_EXECUTION.search(item['source_excerpt']))
        for item in evidence
    )
    crypto_history = bool(
        re.search(r"가상자산|비트코인|암호화폐|crypto", title, re.I)
        and re.search(r"경제\s*(?:규모|\d)|도입\s*보고서|adoption report", title + " " + lead, re.I)
        and re.search(r"지난해\s*\d{1,2}월부터\s*지난\s*\d{1,2}월|전년\s*(?:같은\s*기간|동기)|연간", body)
    )
    if crypto_history and not re.search(
        r"ETF.{0,20}(?:순유입|순유출|승인)|규제.{0,15}(?:발표|시행|변경)|"
        r"(?:상장사|주식|매출|영업이익|실적|주주환원|관세|수출통제)", title, re.I,
    ):
        return {'eligible': False, 'reason': 'annual_crypto_adoption_survey_without_equity_catalyst'}
    source_rows = source_sentences(source_reported_body(body))
    new_policy_terms = any(
        not PAST_ACTION.search(row) and not re.search(r"\d{1,2}월\s*발표(?:된|한)|기존\s*계획|종전\s*계획", row)
        and (FORMAL_POLICY_EXECUTION.search(row)
             or (QUANTITY.search(row) and re.search(r"예산|지원금|기금|세율|관세율|공급량", row)
                 and re.search(r"발표했다|확정했다|결정했다|증액했다|인상했다|인하했다|변경했다", row)))
        for row in source_rows
    )
    if (re.search(r"공론화|시민참여단|시민\s*회의", title + " " + " ".join(source_rows[:12]))
            and re.search(r"인식조사|숙의토론|시민제안서|온라인\s*투표", body)
            and not new_policy_terms and not economic_execution):
        return {'eligible': False, 'reason': 'public_deliberation_survey_not_macro_release_or_policy_execution'}
    if (re.search(r"국감|국정감사", title + " " + lead)
            and re.search(r"정책\s*방향|정책.{0,10}제시", lead)
            and re.search(r"발표한\s*데\s*이어|기존\s*계획|종전\s*계획", body)
            and not new_policy_terms):
        return {'eligible': False, 'reason': 'national_policy_roadmap_without_new_committed_terms'}
    if (re.search(r"스마트오피스|사무환경|무선\s*업무\s*환경", title + " " + lead)
            and re.search(r"업무협약|\bMOU\b", lead, re.I)
            and not any(item['kind'] in {'commercial_order', 'earnings_or_guidance', 'licensing_cashflow',
                                       'capital_or_shareholder_action', 'procurement_execution_stage'} for item in evidence)
            and not re.search(r"(?:신규\s*고객|초도\s*납품|첫\s*납품|고객\s*검증).{0,35}(?:완료|시작|확정)|"
                              r"공급\s*계약.{0,25}체결", lead)):
        return {'eligible': False, 'reason': 'office_technology_mou_roles_not_actual_customer_delivery'}
    if (re.search(r"\d+년간|연간", title) and re.search(r"정전|사고|피해", title)
            and re.search(r"제출받은\s*자료|자료를\s*분석|예방.{0,20}투입", lead)
            and not re.search(r"(?:오늘|이날|\d{1,2}일).{0,50}(?:정전.{0,15}발생|생산.{0,15}중단|피해.{0,15}발생)", lead)):
        return {'eligible': False, 'reason': 'historical_operational_audit_not_current_supply_disruption'}
    if (re.search(r"국감|국정감사|청문회", title + " " + lead)
            and re.search(r"총력|최우선|안정|완화|강조", title)
            and re.search(r"\d{1,2}월\s*발표(?:된|한)|기존\s*계획|종전\s*계획", body)
            and not new_policy_terms):
        return {'eligible': False, 'reason': 'policy_hearing_reiteration_without_changed_instrument'}
    if (LOCAL_AUTHORITY.search(title + " " + lead)
            and re.search(r"농업|농산물|쌀\s*생산|영농", title)
            and re.search(r"영농조합|공동영농|농가소득|농업기반\s*구축사업", body)
            and not kinds & {'commercial_order', 'customer_supply_start', 'earnings_or_guidance',
                             'climate_operational_damage', 'export_control_scope'}
            and not re.search(r"전국|수출\s*(?:금지|제한)|식량\s*위기|곡물\s*가격", title)):
        return {'eligible': False, 'reason': 'local_farming_support_without_equity_or_supply_shock'}
    if (re.search(r"신메뉴|메뉴\s*라인업|라떼|신제품.{0,15}(?:라인업|선보|강화)", title)
            and not any(not PAST_ACTION.search(item['source_excerpt']) and item['kind'] in {
                'commercial_order', 'licensing_cashflow', 'corporate_ownership_execution',
                'capital_or_shareholder_action', 'selling_price_or_cost',
            } for item in evidence)
            and not re.search(r"(?:연결|분기|반기|연간|전체|회사).{0,20}매출|영업이익|순이익|가이던스|설비투자", lead)):
        return {'eligible': False, 'reason': 'retail_menu_publicity_without_company_financial_change'}
    if (re.search(r"국회\s*분석|국회입법조사처|기존\s*(?:규정|협정|법률).{0,20}(?:분석|영향)", lead)
            and re.search(r"시험대|문제\s*아니다|영향|쟁점|해설", title)
            and not any(not PAST_ACTION.search(sentence) and re.search(
                r"(?:협정|합의|계약).{0,25}(?:서명했다|체결했다)|(?:법안|규칙|고시|시행령).{0,25}(?:발의했다|공포했다|개정했다|입법예고했다)|"
                r"(?:관세율|세율|예산|지원금).{0,25}(?:변경했다|확정했다|증액했다|인상했다|인하했다)", sentence,
            ) for sentence in source_sentences(source_reported_body(body)))):
        return {'eligible': False, 'reason': 'existing_policy_rule_analysis_without_new_instrument'}
    if (re.search(r"비트코인|이더리움|가상자산|코인\s*시세", title)
            and re.search(r"강보합|약보합|거래|\d[\d,]*(?:만|억|달러|원).{0,8}(?:대|선)", title)
            and focus_kind(title) != 'equity_index'
            and not re.search(r"ETF.{0,20}(?:순유입|순유출|승인)|규칙\s*제안|규정\s*제정|규제\s*(?:발표|시행)|"
                              r"공급\s*계약|주식|매출|영업이익|투자\s*공시|매수\s*발표|\d+(?:\.\d+)?%.{0,12}(?:폭락|폭등|급락|급등)", title, re.I)):
        return {'eligible': False, 'reason': 'crypto_spot_recap_without_foreground_equity_catalyst'}
    if (LOCAL_AUTHORITY.search(title + ' ' + lead)
            and re.search(r"고도화|기능\s*추가|화면\s*개선|사용\s*편의|만족도|홍보관|활용\s*사례", title + ' ' + lead)
            and kinds <= {'technology_or_clinical_stage', 'physical_supply_or_capacity', 'customer_discussions', 'market_price_or_flow'}
            and not economic_execution):
        return {'eligible': False, 'reason': 'local_service_feature_demo_without_economic_execution'}
    if (re.search(r"자체\s*(?:테스트|시험|검증)|self.test|internal test", lead, re.I)
            and not economic_execution
            and not re.search(r"(?:독립|외부|고객).{0,20}(?:검증|시험).{0,50}(?:성능|정확도|대역폭|처리량|수율|전력효율).{0,25}\d+(?:\.\d+)?\s*(?:%|배|dB)", lead, re.I)):
        return {'eligible': False, 'reason': 'vendor_self_test_without_measured_external_or_business_milestone'}
    if (re.search(r"정품인증\s*스티커|위조방지\s*라벨|MOQ|최소주문수량", title, re.I)
            and re.search(r"폐지|무료|무상|제작|마케팅", title)
            and kinds <= {'physical_supply_or_capacity', 'technology_or_clinical_stage', 'selling_price_or_cost'}):
        return {'eligible': False, 'reason': 'service_promotion_without_market_execution'}
    if re.search(r"\[서학픽\]|서학개미\s*탑픽|서학개미.{0,25}순매수\s*1위", title) and not execution:
        return {'eligible': False, 'reason': 'routine_retail_foreign_stock_ranking_not_market_catalyst'}
    if focus_kind(title) == "mortgage_rate" and re.search(r"오르나|더\s*뛰나|\[[^]]*쇼크", title):
        current_rate_action = re.search(
            r"(?:은행|금융사).{0,35}(?:대출|주담대|모기지)\s*금리.{0,45}"
            r"(?:인상했다|인하했다|조정했다|변경했다|인상한다고|인하한다고)", body,
        )
        if not current_rate_action:
            return {'eligible': False, 'reason': 'rate_risk_explainer_without_new_institutional_action'}
    if re.search(r"기자24시|칼럼|사설|오피니언|/journalist/|/opinion/", f"{title} {source_url}", re.I) and not execution:
        return {'eligible': False, 'reason': 'opinion_rehash_without_new_source_action'}
    if re.search(r"교육센터|인력양성|인력\s*양성|교육\s*프로그램", title) and not execution:
        return {'eligible': False, 'reason': 'training_plan_without_committed_market_execution'}
    if re.search(r"아이폰|스마트폰|아이패드|가정용|생활용", title) and re.search(
        r"틈새시장|외장\s*메모리|신제품|제품\s*소개|제품\s*출시", title,
    ) and not execution:
        return {'eligible': False, 'reason': 'consumer_product_without_new_earnings_or_supply_terms'}
    if re.search(r"전략[^.!?]{0,20}이식|공장은[^.!?]{0,20}실험장|기술을?\s*택한|택한[^.!?]{0,10}기술", title) and not execution:
        return {'eligible': False, 'reason': 'business_case_overview_without_incremental_event'}
    if (
        re.search(r"대통령|정부|총리|장관|당국|금융위|금감원", title)
        and re.search(r"철저|대책\s*마련|대응\s*강화|점검.{0,8}지시", title)
        and kinds <= {'cyber_operational_incident'}
    ):
        return {'eligible': False, 'reason': 'generic_response_without_new_market_terms'}
    if (
        re.search(r"인터뷰|interview", title, re.I)
        and not re.search(r"상장|기업공개|\bIPO\b|스팩\s*합병|첫\s*거래|listing|first trade", title, re.I)
        and kinds <= {'capital_listing_stage'}
    ):
        return {'eligible': False, 'reason': 'secondary_listing_fact_in_business_vision_interview'}
    overview = re.search(r"초격차|\[기획|체질|비전|성장\s*전략|반등\s*채비", title)
    roadmap_kinds = {
        'research_spending_change', 'earnings_or_guidance',
        'physical_supply_or_capacity', 'industrial_architecture_adoption',
    }
    incremental_execution = re.compile(
        r"상향|하향|증액|감액|취소|철회|착공|납입|집행|체결|"
        r"(?:투자|예산|목표|생산|설비|가동|규격|규제|공급|수요|매출|영업이익).{0,60}"
        r"(?:발표했다|발표했다고|공시했다|공시했다고|확정했다|결정했다|증가했다|감소했다|시작했다)|"
        r"announced|signed|approved|revised|increased|decreased|started",
        re.I,
    )
    if overview and kinds <= roadmap_kinds and all(
        re.search(r"20\d{2}년까지|목표|구상|전략", item['source_excerpt'])
        and not incremental_execution.search(item['source_excerpt'])
        for item in evidence
    ):
        return {'eligible': False, 'reason': 'roadmap_overview_without_incremental_execution'}
    return {
        'eligible': True,
        'reason': 'foreground_source_market_change',
        'evidence_kinds': sorted(kinds),
    }


def source_sentences(text: str) -> list[str]:
    """Keep punctuation inside a quoted statement with its speaker."""
    sentences = []
    for paragraph in str(text or "").splitlines():
        quoted, start = False, 0
        for boundary in re.finditer(r'[“”"]|(?<=[.!?。])\s+', paragraph):
            marker = boundary.group(0)
            if marker == "“":
                quoted = True
            elif marker == "”":
                quoted = False
            elif marker == '"':
                quoted = not quoted
            elif not quoted:
                if re.search(r"\b[A-Z]\.$", paragraph[:boundary.start()]) and re.match(r"[A-Z가-힣]", paragraph[boundary.end():]):
                    continue
                if value := paragraph[start:boundary.start()].strip():
                    sentences.append(value)
                start = boundary.end()
        if value := paragraph[start:].strip():
            sentences.append(value)
    return sentences


def assess(title: str, body: str, *, source_url: str = "") -> dict:
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    body = source_reported_body(str(body or "")).strip()
    result = {"version": VERSION, "disposition": "review", "priority": 1, "axes": [], "evidence": []}
    if not title or not body:
        result["reason"] = "source_evidence_unavailable"
        return result
    if (re.fullmatch(r"[A-Za-z0-9가-힣&.·]{2,20}", title.strip())
            and not HARD_HEADLINE.search(title) and not focus_kind(title)):
        result.update(disposition="exclude", priority=0, reason="source_headline_without_event")
        return result
    if re.search(r"따라\s*투자하면|투자하면\s*돈\s*벌까|경제\s*용어|투자\s*방법|자산\s*(?:키우는|늘리는)\s*법|재테크\s*(?:방법|비법)|장기\s*투자\s*요령", title) and not DIRECT_HEADLINE_CHANGE.search(title):
        result.update(disposition="exclude", priority=0, reason="investment_method_explainer_not_new_market_event")
        return result
    exhibition_lead = " ".join(source_sentences(body)[:3])
    if (LOCAL_AUTHORITY.search(title + " " + exhibition_lead)
            and re.search(r"대학생|학생|학부모", title)
            and re.search(r"장학금|생활비|생활지원금|교육복지", title + " " + exhibition_lead)
            and not re.search(r"전국|국가\s*예산|정부\s*예산|세율|법인세", title)):
        result.update(disposition="exclude", priority=0, reason="local_education_welfare_notice_not_equity_event")
        return result
    consumer_fashion = re.search(r"패션|스니커즈|티셔츠|스타일링|컬렉션", title)
    foreground_financial_change = any(
        QUANTITY.search(sentence) and re.search(r"매출|영업이익|순이익|가이던스|설비투자|공급\s*계약", sentence)
        and re.search(r"발표|공시|상향|하향|증가|감소|확정|체결", sentence)
        for sentence in source_sentences(body)[:3]
    )
    if (re.search(r"기숙사형|대학생|대학교|대학.{0,10}기숙사", title + " " + exhibition_lead)
            and re.search(r"전세임대|기숙사형|주거비\s*지원|생활비\s*지원", title + " " + exhibition_lead)
            and not foreground_financial_change
            and not re.search(r"국가\s*예산|정부\s*예산|세율|법인세|건설\s*계약|착공|미분양\s*매수확약", title)):
        result.update(disposition="exclude", priority=0, reason="student_housing_service_not_equity_supply_catalyst")
        return result
    if consumer_fashion and re.search(r"상품|디자인|협업|출시", title + " " + exhibition_lead) and not (
        DIRECT_HEADLINE_CHANGE.search(title) or foreground_financial_change
    ):
        result.update(disposition="exclude", priority=0, reason="consumer_fashion_publicity_without_new_financial_change")
        return result
    startup_profile = re.search(r"창업존.{0,40}인터뷰|입주기업\s*인터뷰|입주기업\s*대표를\s*만나", body[:800])
    profile_execution = any(
        not PAST_ACTION.search(sentence) and not BACKGROUND.search(sentence)
        and (re.search(r"(?:공급|납품|기술이전)\s*계약.{0,30}체결|신규\s*고객.{0,30}(?:확보|납품)", sentence)
             or (QUANTITY.search(sentence) and re.search(r"시험\s*결과|실증\s*결과|독립\s*검증|고객\s*검증", sentence)))
        for sentence in source_sentences(body)[:5]
    )
    if startup_profile and not profile_execution and not DIRECT_HEADLINE_CHANGE.search(title):
        result.update(disposition="exclude", priority=0, reason="startup_profile_without_new_verified_execution")
        return result
    if (re.search(r"실태\s*조사|누적\s*매출", exhibition_lead) and re.search(r"마련해야|정비해야|제언|권고", title)
            and re.search(r"\d{4}년부터\s*\d{4}년까지|\d{4}\s*[~∼-]\s*\d{4}", exhibition_lead)
            and not re.search(r"예산.{0,30}확정|출자\s*계약.{0,20}체결|공급\s*계약.{0,20}체결|시행하기로\s*결정", body)):
        result.update(disposition="exclude", priority=0, reason="historical_survey_and_policy_advice_without_new_execution")
        return result
    if re.search(r"(?:축제|박람회|전시회).{0,20}(?:참가|참여)|포토존|체험\s*행사", title + " " + exhibition_lead) and not (
        DIRECT_HEADLINE_CHANGE.search(title)
        or re.search(r"(?:공급|납품|기술이전)\s*계약을\s*체결했다|공장.{0,25}착공했다|양산을\s*시작했다", exhibition_lead)
    ):
        result.update(disposition="exclude", priority=0, reason="exhibition_foreground_not_new_investment")
        return result
    routine_certificate = bool(re.search(r"보안인증|보안\s*인증|CSAP|ISMS|컴피턴시|competency", title, re.I)
                               and re.search(r"획득|취득|인정|certified|obtained", title, re.I))
    certificate_business_change = routine_certificate and any(
        not BACKGROUND.search(sentence) and not PAST_ACTION.search(sentence)
        and not re.search(r"사례[^.!?]{0,40}(?:제출|인정)|서비스를\s*제공할\s*수|프로그램이다", sentence)
        and re.search(
            r"(?:신규\s*고객|공급\s*계약|납품\s*계약|수주).{0,25}(?:체결|확정|확보|획득)|"
            r"(?:매출|영업이익|순이익|자금조달).{0,25}(?:증가|상향|확정|유치)|supply contract signed", sentence, re.I,
        )
        for sentence in source_sentences(body)
    )
    if routine_certificate and not certificate_business_change:
        result.update(disposition="exclude", priority=0, reason="routine_security_certificate_without_business_commitment")
        return result
    if re.search(r"투자\s*이민|EB-?5", title, re.I) and re.search(r"상담|설명회|세미나", title):
        result.update(disposition="exclude", priority=0, reason="consumer_immigration_consultation_not_equity_news")
        return result
    if re.search(r"민자적격성조사|(?:경기도|지방정부|지자체).{0,50}(?:기후위성|관측위성)", title) and not re.search(
        r"수주|발주|공급\s*계약|우선협상|시공사\s*선정|금융\s*종결|민간\s*투자\s*확정|상장사.{0,25}매출", body,
    ):
        result.update(disposition="exclude", priority=0, reason="local_public_project_without_business_execution")
        return result
    if SOLICITATION_HEADLINE.search(title) and SOLICITATION_BODY.search(body) and (
        re.search(r"잡으려면|활용\s*가능한\s*기회", title)
        or not re.search(r"규제|제재|반대매매|손실|예탁금|금리\s*(?:인상|인하)", title)
    ):
        result.update(disposition="exclude", priority=0, reason="investment_loan_solicitation_not_market_news")
        return result
    sentences = source_sentences(body)
    lead = " ".join(sentences[:3])
    headline_lead = f"{title} {lead}"
    fuel = retail_fuel_observation(title, body)
    if fuel and "주유소" in title and not re.search(r"규제|유류세|가격상한|최고가격|가격\s*통제", title):
        price = float(fuel["price"].replace(",", ""))
        change = float(fuel["change"].replace(",", ""))
        if price > 0 and change / price < 0.01:
            result.update(disposition="exclude", priority=0, reason="routine_weekly_retail_fuel_move_below_one_percent")
            return result
    if focus_kind(title) == "mortgage_rate" and re.search(
        r"(?:\d+(?:\.\d+)?%|금리)[^.!?]{0,15}(?:되면|오르면|빌렸다면|빌리면)|가정", title,
    ) and re.search(r"가정하면|오를\s*경우|오르면|분석이\s*나왔다", lead):
        result.update(disposition="exclude", priority=0, reason="hypothetical_household_interest_calculation_not_new_rate")
        return result
    agency_overview = bool(
        re.search(r"업무를[^.!?]{0,45}살펴보는\s*기획\s*기사|기관의\s*(?:역할|업무)[^.!?]{0,25}소개하는\s*기획", body[:800])
        or re.search(r"\[[^\]]{2,25}(?:가\s*바꾼다|역할\s*소개|업무\s*소개)\]", title)
    )
    new_instrument = any(
        not BACKGROUND.search(sentence) and not PAST_ACTION.search(sentence)
        and re.search(
            r"(?:고시|법률|법안|규칙|시행령).{0,30}(?:개정했다|제정했다|시행한다|공포했다)|"
            r"(?:조달|공급|구매)\s*계약.{0,30}(?:체결|확정)|"
            r"(?:예산|지원금|계약금액).{0,30}\d[\d,.]*\s*(?:억|조)\s*원.{0,20}(?:확정|증액|투입)|"
            r"(?:새|신규)\s*(?:허가|규제|제도).{0,30}(?:시행일|시행|발효)", sentence,
        )
        for sentence in sentences
    ) if agency_overview else False
    if agency_overview and not new_instrument and not DIRECT_HEADLINE_CHANGE.search(title):
        result.update(disposition="exclude", priority=0, reason="agency_role_overview_not_new_industry_event")
        return result
    if re.search(r"화제의\s*바이오人|인물\s*탐구|CEO\s*프로필|경영자\s*약력|executive profile", title, re.I) and not (
        DIRECT_HEADLINE_CHANGE.search(title) or re.search(r"임상\s*[1-3][ab]?상.{0,25}(?:결과|유효성|실패|성공)|임상\s*결과", title, re.I)
    ):
        result.update(disposition="exclude", priority=0, reason="person_profile_without_direct_new_business_event")
        return result
    entertainment_reason = nonmarket_entertainment_reason(title, body, source_url)
    if entertainment_reason:
        result.update(disposition="exclude", priority=0, reason=entertainment_reason)
        return result
    if re.search(r"배당.{0,45}(?:유지|동결)|dividend.{0,30}unchanged", title, re.I) and not re.search(
        r"(?:특별|추가)\s*배당.{0,20}(?:신설|도입|증액)|자사주.{0,20}(?:신규|확대|매입|소각)|"
        r"배당.{0,20}(?:인상|인하|삭감|중단|재개)|dividend.{0,20}(?:rais|cut|suspend|resum)", headline_lead, re.I,
    ):
        result.update(reason="unchanged_routine_dividend_without_new_shareholder_terms")
        return result
    if re.search(r"서비스\s*비교|비교해보니|사용기|체험기", title) and not DIRECT_HEADLINE_CHANGE.search(title):
        result.update(reason="retrospective_service_comparison_without_new_event")
        return result
    if re.search(r"국무부|대변인|spokesperson", title, re.I) and re.search(r"윈윈|win.win|이룬\s*게\s*중요|이룬게\s*중요", title, re.I) and not re.search(r"청구|위협|경고|threat|warn", title, re.I) and not DIRECT_HEADLINE_CHANGE.search(title):
        result.update(reason="spokesperson_reassurance_without_new_agreement_terms")
        return result
    if re.search(r"(?:관여|대화|소통).{0,15}(?:지속|계속)|(?:지속|계속).{0,15}(?:관여|대화|소통)|continued.{0,30}engagement|keep.{0,15}dialogue", title, re.I) and re.search(r"촉구|권고|urges?|calls? for", title, re.I) and not re.search(r"시행|발효|새\s*(?:수출|수입)|새로운\s*(?:수출|수입)|\d+(?:\.\d+)?%|new (?:ban|restriction)|effective", title, re.I):
        result.update(reason="continued_dialogue_without_new_policy_or_supply_terms")
        return result
    foreground_genres = (
        (r"인스타툰|론칭\s*이벤트|경품|사은품", "consumer_promotion_not_business_commitment"),
        (r"구호대|구호\s*활동|성금|봉사", "humanitarian_response_not_operating_damage"),
        (r"생산유발|경제적\s*파급효과|경제\s*기여\s*효과", "regional_multiplier_study_not_current_output"),
        (r"마타도어|성매매\s*의혹|허위\s*의혹|홍익인간|개천절.{0,20}(?:경축|기념)|(?:총리|대통령).{0,20}연대.{0,10}통합", "political_or_ceremonial_not_market_event"),
    )
    for pattern, reason in foreground_genres:
        if re.search(pattern, title) and not DIRECT_HEADLINE_CHANGE.search(title):
            result.update(disposition="exclude", priority=0, reason=reason)
            return result
    if re.search(r"금지.{0,20}(?:사실\s*아니|사실\s*아님)|(?:식탁|테이블).{0,15}간장", title) and not re.search(r"행정명령|시행일|규칙안\s*철회|규제\s*철회", lead):
        result.update(disposition="exclude", priority=0, reason="consumer_fact_check_not_new_policy")
        return result
    if re.search(r"최고의\s*친구|우호\s*과시|우정\s*과시|best friend", title, re.I) and not re.search(r"관세|수출통제|휴전\s*합의|제재\s*(?:시행|해제)|공급\s*계약", title):
        result.update(disposition="exclude", priority=0, reason="diplomatic_praise_not_new_policy")
        return result
    if re.search(r"\[리뷰\]|써보니|찍는\s*맛|사용기|체험기|hands.on review", headline_lead, re.I) and not re.search(r"매출|영업이익|순이익|가이던스|공급\s*계약|판매량|출하량|수주", headline_lead):
        result.update(disposition="exclude", priority=0, reason="consumer_review_not_industry_change")
        return result
    if re.search(r"모기\s*(?:저격|퇴치)|모기.{0,40}레이저|레이저.{0,40}모기", title) and not PUBLIC_MARKET_BUSINESS_LINK.search(headline_lead):
        result.update(disposition="exclude", priority=0, reason="consumer_curiosity_without_market_business_link")
        return result
    company_result_or_execution = bool(re.search(
        r"(?:연결|분기|반기|연간|전체|회사).{0,20}매출|영업이익|순이익|가이던스|설비투자|"
        r"공급\s*계약.{0,20}체결|공장.{0,20}(?:착공|증설)|규제.{0,20}(?:시행|발효)", headline_lead,
    ))
    consumer_sku = bool(re.search(r"라면|칼국수|과자|음료|화장품|스킨케어|신발|생활용품", title)
                        and re.search(r"['‘][^'’]{2,45}['’]|(?:신제품|단일\s*제품|개별\s*제품|특정\s*매장)", headline_lead)
                        and re.search(r"판매\s*호조|(?:매장|마트).{0,25}(?:점|1위)|제품.{0,30}매출|판매량", headline_lead))
    if consumer_sku and not company_result_or_execution:
        result.update(disposition="exclude", priority=0, reason="single_consumer_sku_or_store_sales_publicity")
        return result
    quantified_delivery = bool(re.search(
        r"(?:계약\s*금액|수주액|매출|발주량|공급\s*물량|납품\s*물량).{0,35}\d[\d,.]*\s*(?:억|조|대|개|만)|"
        r"\d[\d,.]*\s*(?:억|조)\s*원.{0,25}(?:공급|납품|계약)", headline_lead,
    ))
    if (re.search(r"(?:대학교|대학|[가-힣]{2,10}대)에", headline_lead)
            and re.search(r"웹\s*보안|보안\s*솔루션", title)
            and re.search(r"공급|납품", title) and not quantified_delivery):
        result.update(disposition="exclude", priority=0, reason="single_campus_software_without_material_delivery_scope")
        return result
    if (re.search(r"(?:중고|리마스터).{0,25}(?:굴착기|건설장비)", title)
            and re.search(r"시장\s*공략|업무\s*협력|유통망|쇼케이스", headline_lead)
            and not quantified_delivery):
        result.update(disposition="exclude", priority=0, reason="used_equipment_distribution_without_order_scope")
        return result
    if (re.search(r"ETF", title, re.I) and re.search(r"한\s*주|주간|지난주", title + " " + lead)
            and re.search(r"수익률|수익률.{0,15}1위|ETF.{0,10}\d+(?:\.\d+)?%", title + " " + lead)
            and not re.search(r"(?:순유입|순유출|순매수|순매도|설정액).{0,35}\d[\d,.]*\s*(?:억|조)\s*원", body)
            and not DIRECT_HEADLINE_CHANGE.search(title)):
        result.update(disposition="exclude", priority=0, reason="weekly_etf_return_table_without_new_flow_or_execution")
        return result
    historical_survey = bool(re.search(r"프랜차이즈|가맹점", title)
                             and re.search(r"20\d{2}\s*[~∼-]\s*20\d{2}년", lead)
                             and re.search(r"브랜드.{0,25}분석|분석한\s*결과|조사\s*결과", lead))
    historical_project_inventory = bool(re.search(r"공공주택|공공\s*사업", title)
                                        and re.search(r"작년|지난해", body[:2000])
                                        and re.search(r"자료에\s*따르면|제출받은\s*자료", body[:2000])
                                        and re.search(r"착공하지\s*못|미착공", body[:2000]))
    if (historical_survey or historical_project_inventory) and not re.search(
        r"(?:오늘|이날|\d{1,2}일).{0,100}(?:공시했다|시행한다|발효한다|착공을\s*취소했다|계약을\s*해지했다)|"
        r"(?:새로운|신규)\s*(?:규제|공급계약|예산).{0,30}(?:확정|체결|시행)", lead,
    ):
        result.update(disposition="exclude", priority=0, reason="historical_sector_or_project_inventory_not_new_execution")
        return result
    if (re.search(r"(?:10|\d{1,2})대\s*거래|거래.{0,20}(?:순위|랭킹)|우수\s*거래.{0,15}선정", title)
            and re.search(r"선정|평가|순위", lead)
            and not re.search(r"(?:오늘|이날|\d{1,2}일).{0,40}(?:새\s*계약|추가\s*계약|계약\s*변경|계약을\s*체결)", lead)):
        result.update(disposition="exclude", priority=0, reason="retrospective_deal_ranking_not_new_transaction")
        return result
    if (re.search(r"펀드.{0,20}출시|['‘][^'’]*펀드['’].{0,10}출시", title)
            and not re.search(r"ETF|상장지수|순유입|순유출|설정액|환매|청산|기관.{0,20}출자|규제", title, re.I)):
        result.update(disposition="exclude", priority=0, reason="retail_fund_product_launch_not_capital_flow")
        return result
    if (re.search(r"52주\s*신고가", title) and re.search(r"연속\s*순매수", title)
            and re.search(r"기사\s*자동생성\s*알고리즘|자동생성\s*알고리즘", body)
            and not DIRECT_HEADLINE_CHANGE.search(title)):
        result.update(disposition="exclude", priority=0, reason="automated_stock_streak_without_new_business_catalyst")
        return result
    if re.search(r"외부.{0,15}(?:요청|개입).{0,12}(?:없|않)|(?:요청|개입)\s*없었", title) and not re.search(r"신규\s*투자|투자\s*(?:철회|중단)|환수|감액|증액|지분\s*매각", headline_lead):
        result.update(disposition="exclude", priority=0, reason="political_investment_process_denial_not_new_terms")
        return result
    if re.search(r"(?:공화당|민주당|민주).{0,12}(?:승리|이기)|대공황", title) and re.search(r"유세|지지\s*호소", body[:1500]) and not re.search(r"법안\s*발의|행정명령\s*서명|지급\s*대상|지급\s*일정|시행일", lead):
        result.update(disposition="exclude", priority=0, reason="campaign_benefit_claim_without_payment_policy")
        return result
    electoral = bool(re.search(r"유세|선거운동|지지\s*(?:호소|결집)|campaign rally|election campaign", headline_lead, re.I))
    if ROUTINE_FOREGROUND.search(title) and not DIRECT_HEADLINE_CHANGE.search(title):
        result.update(disposition="exclude", priority=0, reason="routine_foreground_not_new_economic_event")
        return result
    if re.search(r"[가-힣]{2,10}(?:시|군|구)[,\s].{0,40}(?:재생에너지|탄소중립|온실가스|에너지\s*계획)", title) and not re.search(
        r"(?:수주|공급\s*계약|예산|출자|투입).{0,30}(?:\d[\d,.]*\s*(?:억|조)\s*원|체결|확정)|(?:발전소|설비).{0,25}(?:착공|가동|허가|승인)", headline_lead,
    ):
        result.update(disposition="exclude", priority=0, reason="municipal_energy_target_without_market_execution")
        return result
    if STAFF_APPOINTMENT.search(title) and not re.search(r"공급\s*계약|수주|고객\s*계약|인수\s*(?:계약|완료)|영업이익|순이익|가이던스|supply contract|guidance", headline_lead, re.I):
        result.update(disposition="exclude", priority=0, reason="staff_appointment_without_market_change")
        return result
    if VIRAL_DEMONSTRATION.search(headline_lead) and not re.search(
        r"공급\s*계약|납품\s*계약|수주|임상\s*[1-3]상|검증\s*결과|실증\s*결과|"
        r"(?:대역폭|수율|전력효율|추론비용).{0,20}\d+(?:\.\d+)?\s*(?:%|배)|supply contract|validation results", headline_lead, re.I,
    ):
        result.update(disposition="exclude", priority=0, reason="entertainment_demonstration_without_industry_evidence")
        return result
    if OFFICE_PUBLICITY.search(headline_lead) and not OFFICE_ECONOMIC_CHANGE.search(f"{title} {body}"):
        result.update(disposition="exclude", priority=0, reason="office_publicity_without_business_economics")
        return result
    if SPORTS_OWNERSHIP.search(headline_lead) and not PUBLIC_MARKET_BUSINESS_LINK.search(headline_lead):
        result.update(disposition="exclude", priority=0, reason="sports_ownership_without_market_business_link")
        return result
    if LOCAL_CEREMONY.search(title) and re.search(
        r"(?:[가-힣]{2,8}(?:시|구|군)\s*[ ('’]|구청|지자체|지방자치단체)|municipality|city council", headline_lead, re.I,
    ) and not PUBLIC_MARKET_BUSINESS_LINK.search(headline_lead):
        result.update(disposition="exclude", priority=0, reason="local_ceremony_without_market_business_change")
        return result
    if CUMULATIVE_PRODUCT_PR.search(title) and RETAIL_PRODUCT_CONTEXT.search(headline_lead) and not PUBLIC_MARKET_BUSINESS_LINK.search(headline_lead):
        result.update(disposition="exclude", priority=0, reason="cumulative_consumer_product_publicity")
        return result
    if TACTICAL_HEADLINE.search(title) and not ECONOMIC_GEOPOLITICS.search(f"{title} {lead}"):
        result.update(disposition="exclude", priority=0, reason="tactical_military_without_economic_transmission")
        return result
    generic_tokens = {"기업", "대표", "회장", "공개", "협력", "강화", "발표", "미래", "신제품", "출시", "회동", "계획"}
    tokens = [word for word in re.findall(r"[A-Za-z0-9가-힣]+", title.lower()) if len(word) >= 2 and word not in generic_tokens]
    routine = bool(ROUTINE_HEADLINE.search(title) and not HARD_HEADLINE.search(title))
    soft = bool(SOFT_HEADLINE.search(title) and not HARD_HEADLINE.search(title))
    matches = []
    if focus_kind(title) == 'backlog_mix':
        for sentence in sentences:
            if focus_matches(title, sentence):
                matches.append((2, 60, 0, ['earnings', 'timeline'], {
                    'kind': 'order_backlog_level', 'stage': 'reported_statistic', 'source_excerpt': sentence,
                }))
    research = research_program_award_observation(title, body)
    if research or focus_kind(title) == 'research_award':
        statement = research.get('source_excerpt') or next((row for row in sentences if focus_matches(title, row)), '')
        if statement:
            matches.append((2, 60, 0, ['earnings', 'timeline'], {
                'kind': 'public_research_award', 'stage': 'selected_project', 'source_excerpt': statement,
            }))
    adoption = industrial_customer_adoption_observation(title, body)
    if adoption:
        matches.append((2, 60, 0, ['earnings', 'timeline'], {
            'kind': 'customer_supply_start', 'stage': adoption['stage'], 'source_excerpt': adoption['source_excerpt'],
        }))
    elif focus_kind(title) == 'industrial_customer_adoption':
        for sentence in sentences:
            if focus_matches(title, sentence):
                matches.append((2, 60, 0, ['earnings', 'timeline'], {
                    'kind': 'customer_supply_start', 'stage': 'adopted', 'source_excerpt': sentence,
                }))
    marketing = marketing_contract_observation(title, body)
    marketing_statement = next((row for row in sentences if focus_kind(title) == 'marketing_offtake'
                                and focus_matches(title, row) and re.search(r"\d{1,2}일\s*밝혔다", row)), "")
    if marketing or marketing_statement:
        excerpt = marketing_statement
        matches.append((2, 60, 0, ['earnings', 'timeline'], {
            'kind': 'commercial_order', 'stage': 'reported_change', 'source_excerpt': excerpt,
        }))
    if focus_kind(title) == 'aviation_network':
        for sentence in sentences:
            if focus_matches(title, sentence) and re.search(r"일부터|주\s*\d+회|\d+개\s*.*도시", sentence):
                matches.append((2, 60, 0, ['earnings', 'timeline'], {
                    'kind': 'physical_supply_or_capacity', 'stage': 'early_signal', 'source_excerpt': sentence,
                }))
    freight = freight_cost_observation(title, body)
    if freight:
        excerpt = next((sentence for sentence in sentences if re.search(r"왕복.{0,30}최대.{0,20}달러", sentence)), "")
        matches.append((3, 60, 0, ['earnings', 'discount_rate'], {
            'kind': 'shipping_cost_observation', 'stage': 'reported_statistic', 'source_excerpt': excerpt,
        }))
    allocation = public_compute_allocation(title, body)
    if allocation:
        excerpt = " ".join(sentence for sentence in sentences if re.search(r"진행된\s*공모에|최종\s*배정\s*대상은|^NIPA 자료", sentence))
        matches.append((2, 60, 0, ['earnings', 'timeline'], {
            'kind': 'public_compute_allocation', 'stage': 'reported_statistic', 'source_excerpt': excerpt,
        }))
    index_outlook = conditional_index_outlook(title, body)
    if index_outlook:
        excerpt = " ".join(sentence for sentence in sentences if re.search(r"보고서에서|선을\s*돌파해\s*안착하면", sentence))
        matches.append((2, 60, 0, ['discount_rate'], {
            'kind': 'market_outlook', 'stage': 'early_signal', 'source_excerpt': excerpt,
        }))
    quotes = intraday_equity_observations(title, body)
    if quotes:
        for quote in quotes['quotes']:
            matches.append((2, 60, 0, ['flows'], {
                'kind': 'market_price_or_flow', 'stage': 'reported_change',
                'source_excerpt': quote['source_excerpt'],
            }))
    if focus_kind(title) == 'military_reinforcement' and ECONOMIC_GEOPOLITICS.search(body):
        for sentence in sentences:
            if focus_matches(title, sentence) and not BACKGROUND.search(sentence) and re.search(r"다[.!?]$", sentence):
                matches.append((2, 60, 0, ['discount_rate', 'timeline'], {
                    'kind': 'military_deployment_plan',
                    'stage': 'early_signal' if re.search(r'계획|합의|배치하기로', sentence) else 'reported_change',
                    'source_excerpt': sentence,
                }))
    housing = housing_demand_observation(title, body)
    if housing:
        excerpt = next((sentence for sentence in sentences if "입주자모집공고 기준" in sentence and "전국" in sentence), "")
        matches.append((2, 60, 0, ['earnings', 'discount_rate'], {
            'kind': 'housing_demand_observation', 'stage': 'reported_statistic', 'source_excerpt': excerpt,
        }))
    headline_text = re.sub(r"[\W_]+", "", title).casefold()
    for index, sentence in enumerate(sentences):
        if re.sub(r"[\W_]+", "", sentence).casefold() == headline_text:
            continue
        if title and sentence.startswith(title + " "):
            continue
        if PHOTO_DESCRIPTION.search(sentence):
            continue
        if BACKGROUND.search(sentence) or COMPANY_PROFILE.search(sentence) or re.match(r"^한편[,\s]", sentence) or not period_matches(title, sentence):
            continue
        if re.search(r"\d+\s*년간.{0,20}(?:이어온|추진해\s*온|투자유치\s*노력)|(?:이어온|쌓아온).{0,12}투자유치\s*노력", sentence) and not QUANTITY.search(sentence):
            continue
        if re.search(r"추가매수를\s*고려하고\s*있었다면|투자자라면|투자금을\s*준비하는\s*방법|기회를\s*잡으려", sentence):
            continue
        # A numeric company profile or another topic later in the article must
        # not turn today's ceremonial/promotion headline into a market event.
        anchors = {token for token in tokens if not token.isdigit() and token in sentence.lower()}
        anchored = bool(anchors)
        adjacent = (index > 0
                    and re.sub(r"[\W_]+", "", sentences[index - 1]).casefold() != headline_text
                    and any(token in sentences[index - 1].lower() for token in tokens))
        if (focus_kind(title) or DENIAL_HEADLINE.search(title)) and not focus_matches(title, sentence):
            continue
        for kind, axes, subject, action in COMPILED_RULES:
            if not subject.search(sentence) or not action.search(sentence):
                continue
            policy_focus = focus_kind(title)
            if policy_focus in {"network_segmentation_policy", "housing_supply_policy"} and kind != policy_focus:
                continue
            if kind in {"network_segmentation_policy", "housing_supply_policy"} and kind != policy_focus:
                continue
            if kind in {"cyber_operational_incident", "cyber_regulatory_response"} and focus_kind(title) != "cyber_incident":
                continue
            if focus_kind(title) == "cyber_incident" and kind not in {"cyber_operational_incident", "cyber_regulatory_response"}:
                continue
            if focus_kind(title) == "industry_outlook" and kind != "sector_demand_outlook":
                continue
            if focus_kind(title) == "project_response" and kind != "policy_agreement_clarification":
                continue
            if focus_kind(title) == "economic_response" and kind != "economic_restriction_response":
                continue
            if focus_kind(title) == "national_exports" and kind != "national_export_release":
                continue
            if kind == "national_export_release" and focus_kind(title) != "national_exports":
                continue
            if (focus_kind(title) == "financing"
                    and re.search(r"자금\s*조달|자본\s*조달|외부\s*자본|대출|전환사채|전환\s*(?:선순위)?\s*채권|funding|financing|loan", title, re.I)
                    and kind not in {
                "capital_or_shareholder_action", "customer_financing_commitment", "capital_listing_stage",
                "corporate_action_clarification", "financing_infrastructure", "operating_asset_transaction",
            }):
                continue
            if focus_kind(title) == "earnings" and kind != "earnings_or_guidance":
                continue
            if focus_kind(title) == "analyst_revision" and kind != "analyst_revision":
                continue
            if focus_kind(title) == "industrial_partnership" and kind != "industrial_partnership_execution":
                continue
            if focus_kind(title) == "equity_index" and kind != "market_price_or_flow":
                continue
            if focus_kind(title) in {"intraday_equity", "housing_demand", "marketing_offtake", "aviation_network", "research_award", "industrial_customer_adoption", "backlog_mix"}:
                continue
            if not evidence_is_new_event(kind, sentence):
                continue
            # A late company-only forecast cannot replace an unrecognised
            # headline event; an actual new contract/action remains eligible.
            if not focus_kind(title) and index >= 3 and len(anchors) < 2 and not (
                anchored and kind in {"commercial_order", "corporate_transaction", "capital_or_shareholder_action", "customer_supply_start"}
                and re.search(r"체결했다|체결했다고|수주했다|수주했다고|인수했다|유치했다|납입했다|집행했다|signed|acquired", sentence, re.I)
            ):
                continue
            if kind == "export_results" and not QUANTITY.search(sentence):
                continue
            # Campaign rhetoric and retrospective blame are not new macro data.
            # A concrete policy proposal or current escalation remains eligible.
            factory_layoff = bool(
                kind == "labor_cost_or_execution"
                and re.search(r"공장|생산|factory|plant", title, re.I)
                and re.search(r"해고|감원|감축|layoff|laid off", title, re.I)
                and re.search(r"\d[\d,]*\s*(?:명|people|workers|jobs)", sentence, re.I)
                and re.search(r"해고(?:됐|했|한다|하기로)|감원(?:했|한다|하기로)|감축(?:했|한다|하기로)|were laid off|laid off|cut\s+\d", sentence, re.I)
            )
            if electoral and not factory_layoff and kind not in {"policy_scope_or_stage", "export_control_scope", "energy_geopolitics_or_supply_risk", "energy_stockpile_action", "conditional_project_charge"}:
                continue
            if not anchored and not adjacent and not focus_kind(title) and not subject.search(title):
                continue
            if routine and kind not in {"policy_scope_or_stage", "physical_supply_or_capacity", "capital_or_shareholder_action"}:
                continue
            if soft and kind in {"earnings_or_guidance", "rates_fx_or_macro", "market_price_or_flow"} and not SOFT_HEADLINE.search(sentence):
                continue
            if soft and kind == "customer_discussions" and not re.search(
                CUSTOMER_DISCUSSION_SUBJECT, sentence, re.I,
            ):
                continue
            if kind == "rates_fx_or_macro" and re.search(
                r"환율\s*(?:우대|혜택)|우대\s*환율|즉시\s*할인|할인\s*쿠폰|사은품|경품", sentence,
            ):
                continue
            if kind == "market_price_or_flow" and not re.search(
                r"주가|증시|코스피|코스닥|나스닥|S&P\s*500|러셀\s*2000|etf|etn|순매수|순매도|거래대금|수익률|주식|자금|자본|투자금|shares|stocks|equities|capital|fund flows", sentence, re.I,
            ):
                continue
            if kind == "market_price_or_flow" and re.search(r"(?:나스닥|코스피|코스닥).{0,35}첫\s*거래", sentence) and not re.search(
                r"주가|거래대금|순매수|순매도|유입|유출|급등|급락", sentence,
            ):
                continue
            if kind == "market_price_or_flow" and re.search(r"ETF.{0,80}(?:상장|출시)", sentence, re.I) and not re.search(
                r"순매수|순매도|유입|유출|거래대금|주가|수익률|올랐|내렸|상승|하락", sentence,
            ):
                continue
            if kind == "earnings_or_guidance" and not re.search(
                r"매출|영업(?:이익|익|손실)|순(?:이익|익|손실)|마진|가이던스|주당\s*(?:NAV|순자산가치)|(?<![제연])출하|판매(?:량|실적|는|가)|시장점유율|주당순이익|"
                r"실적.{0,20}(?:어닝|상회|하회|흑자|적자)|\beps\b|revenue|earnings|profit|guidance|shipments", sentence, re.I,
            ):
                continue
            if kind == "labor_cost_or_execution" and not re.search(
                r"파업|임단협|단체협약|임금.{0,25}(?:인상|인하|교섭|협상|부결|타결)|성과급.{0,25}(?:주식|지급|변경)|"
                r"(?<!금)감원|해고|(?:인력|인원|일자리).{0,20}감축|(?:생산|공장|운송|항만).{0,25}(?:중단|차질)|"
                r"strike|layoff|laid off|wage.{0,20}(?:talk|rais|cut)|(?:worker|job|labor|labour).{0,20}(?:cut|reduc)", sentence, re.I,
            ):
                continue
            if kind == "physical_supply_or_capacity":
                if re.search(r"공공서비스.{0,12}확대|(?:쉼터|라운지).{0,20}(?:개방|개관|확대)", sentence):
                    continue
                if re.search(r"(?:가동|공급|생산).{0,8}중단을?\s*(?:방지|막|예방)|prevent.{0,25}(?:outage|shutdown)", sentence, re.I):
                    continue
                if not re.search(
                    r"공장|생산(?!성)|설비|공급|리드타임|품귀|항만|물류|운송|반도체|메모리|기판|전력|원유|원자재|데이터센터|AI\s*팩토리|광통신|광인터커넥트|네트워크|"
                    r"factory|production|supply|lead time|shortage|port|freight|semiconductor|memory|substrate|power|oil|raw material|optical|network|data cent(?:er|re)", sentence, re.I,
                ):
                    continue
            if kind == "policy_scope_or_stage" and re.search(r"조례", sentence) and not re.search(
                r"관세|수출|수입|제재|보조금|지원금|예탁금|규제|인허가|환경심사|환경영향평가|주파수|"
                r"전력|공장|데이터센터|생산|금융|세금|세율|요금", sentence, re.I,
            ):
                continue
            if kind == "technology_or_clinical_stage" and not re.search(
                r"양산|상용화|인증|승인|허가|임상|공급|도입|검증|성능|대역폭|수율|전력효율|production|commercial|approv|deploy|validat|performance|bandwidth|yield", sentence, re.I,
            ):
                continue
            if kind == "technology_or_clinical_stage" and not re.search(
                r"메모리|반도체|hbm|hbf|cxl|칩|공정|로봇|신약|임상|fda|의약품|양자|극저온|"
                r"데이터센터|고객|공급|생산|양산|상용화|전력|냉각|자동화|자율주행|통신|위성|우주|"
                r"memory|semiconductor|chip|robot|clinical|drug|quantum|cryogenic|data center|customer|supply|production|power|cooling|automation|satellite|spacecraft", sentence, re.I,
            ):
                continue
            if kind == "industrial_architecture_adoption" and not re.search(
                r"데이터센터|AI\s*클러스터|전력\s*(?:분배|변환)|휴머노이드|로봇|data center|AI cluster|power (?:distribution|conversion)|humanoid|robot", sentence, re.I,
            ):
                continue
            if kind == "biology_research_discovery" and not re.search(
                r"실험|검증|연구\s*결과|논문|laboratory|experiment|validat|research results|paper", sentence, re.I,
            ):
                continue
            if kind in {"space_thermal_validation", "cryogenic_propellant_storage"} and not re.search(
                r"로켓|발사체|우주선|궤도|우주|rocket|launch vehicle|spacecraft|orbital|in.space", sentence, re.I,
            ):
                continue
            if kind == "model_operating_specification" and not re.search(
                r"구동|동작|실행|추론|운용|가동|배포|메모리|전력|토큰|지연시간|추론비용|운용비용|running|inference|deploy|memory|power|latency|cost", sentence, re.I,
            ):
                continue
            if kind == "energy_geopolitics_or_supply_risk" and not ECONOMIC_GEOPOLITICS.search(sentence) and not re.search(r"브렌트|\bbrent\b|\bwti\b", sentence, re.I):
                continue
            if kind == "economic_restriction_response" and not re.search(r"환율|필수\s*물자|수출|수입|결제|외환", body):
                continue
            if kind == "climate_operational_damage" and not re.search(
                r"정전|과부하|폐사|사망|침수|소실|피해|차질|중단|손실|outage|overload|death|damage|disrupt|halt|loss", sentence, re.I,
            ):
                continue
            if kind == "research_spending_change" and not QUANTITY.search(sentence):
                continue
            early = bool(EARLY_SIGNAL.search(sentence)) or kind in {"customer_discussions", "institutional_capital_access", "authorized_capital_proposal", "sector_demand_outlook", "policy_agreement_clarification", "economic_restriction_response"}
            if focus_kind(title) == "factory_tariff" and re.search(r"트럼프", sentence) and re.search(r"말했다|경고했다", sentence):
                early = True
            if kind == "national_export_release" and re.search(r"가시권|달성할\s*수|달성\s*가능", sentence):
                early = True
            if re.search(r"(?:할|하는|하는\s*)\s*경우|한다면|하면.{0,30}(?:달성|가능)|if\s+", sentence, re.I):
                early = True
            if (kind == "earnings_or_guidance" and index > 0
                    and EARLY_SIGNAL.search(sentences[index - 1])
                    and re.match(r"^(?:이는|이\s*수치는|이\s*전망치는|전년\s*동기\s*대비)\s", sentence)
                    and not re.search(r"발표했다|공시했다|잠정\s*실적|확정\s*실적", sentence)):
                early = True
            if kind == "capital_listing_stage" and re.search(r"오는\s*\d{1,2}일|조만간|출시한다고|출시할|상장할", sentence):
                early = True
            priority = 2 if early or kind in {"technology_or_clinical_stage", "research_validation_result", "market_infrastructure", "model_operating_specification", "industrial_architecture_adoption", "space_execution_stage", "space_thermal_validation", "cryogenic_propellant_storage", "biology_research_discovery", "public_program_cost_study", "project_cost_evaluation", "sector_demand_outlook", "market_outlook", "fund_assets_level", "financing_infrastructure", "equity_compensation_change"} else 3
            if kind == "capital_listing_stage":
                priority = 3
            if kind in {"earnings_or_guidance", "industry_market_share", "market_price_or_flow"} and not QUANTITY.search(sentence):
                priority = 2
            if kind == "research_spending_change":
                priority = 2
            if focus_kind(title) == "industry_outlook":
                priority = min(priority, 2)
            # Certainty and economic materiality are separate. A scoped import
            # ban or financing negotiation can outrank a routine index recap.
            if early and kind in {"policy_scope_or_stage", "capital_or_shareholder_action", "physical_supply_or_capacity", "energy_geopolitics_or_supply_risk"} and re.search(
                rf"수입|수출|관세|보조금|자금조달|대출|공장|생산|공급|호르무즈|유조선|{OIL_PRICE}|import|export|tariff|loan|funding|factory|supply|hormuz|tanker|oil", sentence, re.I,
            ):
                priority = 3
            evidence_axes = list(axes)
            if kind in {"capital_or_shareholder_action", "market_price_or_flow"} and re.search(
                r"자사주|자기주식|배당|순매수|순매도|유입|유출|거래대금|편입|편출|매수|매도|buyback|dividend|inflows|outflows|rebalance", sentence, re.I,
            ):
                evidence_axes.append("flows")
            if kind == "market_price_or_flow" and "flows" not in evidence_axes:
                listing = bool(re.search(r"etf|etn", sentence, re.I) and re.search(
                    r"상장(?:했다|한다고|한다|할|\s*예정)|(?:newly\s*listed|will\s*list)", sentence, re.I,
                ))
                priority = 2 if focus_kind(title) in {"breadth", "equity_index"} or listing else 1
                if listing:
                    evidence_axes.append("timeline")
            if kind == "policy_scope_or_stage" and re.search(
                r"관세|법인세|세율|세금|수출|수입|보조금|지원금|비용|생산|공급|tariff|tax rate|corporate tax|export|import|subsid|cost|production|supply", sentence, re.I,
            ):
                evidence_axes.append("earnings")
            focus = focus_score(title, sentence)
            if kind == "policy_scope_or_stage" and re.search(r"고시.{0,15}개정|법안.{0,15}(?:발의|통과)|시행일|발효일", sentence):
                focus += 20
            matches.append((priority, focus, -index, evidence_axes,
                            {"kind": kind, "stage": "early_signal" if early else "reported_change", "source_excerpt": sentence}))
    if matches:
        matches.sort(key=lambda item: item[:3], reverse=True)
        result["priority"] = matches[0][0]
        result["focus"] = matches[0][1]
        for _priority, _focus, _index, axes, evidence in matches:
            result["axes"] = list(dict.fromkeys(result["axes"] + axes))
            if len(result["evidence"]) < 4 and not any(item["kind"] == evidence["kind"] for item in result["evidence"]):
                result["evidence"].append(evidence)
        result.update(disposition="keep", reason="source_change_evidence")
        result["news_value_rank"] = news_value_rank(result["evidence"])
        kinds = {item["kind"] for item in result["evidence"]}
        support_mou = (re.search(r"은행|bank", headline_lead, re.I)
                       and re.search(r"금융지원|금융\s*지원|제조.{0,10}자금|생산자금", headline_lead)
                       and re.search(r"업무협약|지원\s*협약", headline_lead))
        scoped_support = any(
            not BACKGROUND.search(sentence) and not PAST_ACTION.search(sentence)
            and QUANTITY.search(sentence)
            and re.search(r"지원|대출|보증|금리|출자|납입|집행", sentence)
            for sentence in sentences
        )
        if support_mou and not scoped_support and kinds <= {
            "customer_discussions", "financing_infrastructure", "capital_or_shareholder_action",
            "industrial_partnership_execution",
        }:
            result["priority"] = 1
            result["scope_note"] = "support_mou_without_size_terms_or_committed_execution"
        if kinds == {"authorized_capital_proposal"}:
            result["priority"] = 1
            result["scope_note"] = "authorized_capacity_without_committed_financing_or_issuance"
        if re.search(r"대선|선거|정치\s*지형|유세|출마|지지율", title) and kinds <= {"rates_fx_or_macro", "market_outlook"}:
            result["priority"] = 1
            result["scope_note"] = "political_profile_not_new_macro_release_or_policy_change"
        if local_administration_without_execution(title, lead, result["evidence"]):
            result["priority"] = 1
            result["scope_note"] = "local_administrative_proposal_without_business_execution"
        if (
            focus_kind(title) == "macro_release"
            and re.search(r"농축산물|농산물|축산물|외식|식품|채소|과일", title)
            and re.search(r"물가", title)
            and not re.search(r"소비자물가|\bcpi\b|\bpce\b|\bppi\b", title, re.I)
            and kinds <= {"rates_fx_or_macro", "physical_supply_or_capacity"}
        ):
            result["priority"] = 1
            result["scope_note"] = "consumer_price_component_commentary_without_new_market_event"
        if re.search(r"총력|독려|당부", title) and kinds <= {"policy_scope_or_stage", "physical_supply_or_capacity", "customer_discussions"} and not re.search(
            r"고시.{0,15}개정|법안.{0,15}(?:발의|통과)|시행일.{0,15}확정|계약.{0,15}체결|예산.{0,20}(?:확정|증액)|발주.{0,15}(?:했다|확정)", body,
        ):
            result["priority"] = 1
            result["scope_note"] = "target_reiteration_without_new_instrument_or_execution"
        forum_agenda = re.search(r"포럼|패널토론|토론회|기조\s*발제|forum|panel discussion", headline_lead + " " + body[:400], re.I)
        forum_change = any(
            not BACKGROUND.search(sentence) and not PAST_ACTION.search(sentence)
            and (
                re.search(r"(?:정부|금융위|국세청|국회|장관|부처|서울시).{0,80}(?:입법예고했다|발의했다|개정한다|시행한다|시행하기로\s*결정|공포했다)", sentence)
                or (QUANTITY.search(sentence) and re.search(r"(?:공급|예산|보조금|지원금|조달|발주).{0,50}(?:확정했다|결정했다|증액했다|착공했다|집행했다|발주했다)", sentence))
            )
            for sentence in sentences
        )
        if forum_agenda and kinds <= {"policy_scope_or_stage", "customer_discussions", "financing_infrastructure", "market_infrastructure", "physical_supply_or_capacity"} and not forum_change:
            result["priority"] = 1
            result["scope_note"] = "forum_policy_opinion_without_announced_instrument_change"
        if SUPPORT_EVENT.search(title) and kinds <= {"capital_or_shareholder_action", "corporate_transaction", "institutional_capital_access", "financing_infrastructure"}:
            result["priority"] = 1
            result["scope_note"] = "support_event_without_committed_capital"
        if re.search(r"학회|초록|conference abstract", title, re.I) and not re.search(
            r"임상\s*[1-3]상|유효성|안전성|\d+(?:\.\d+)?\s*(?:%|배|mK|dB)|기술이전\s*계약|허가\s*신청", body, re.I,
        ) and kinds <= {"technology_or_clinical_stage", "market_price_or_flow"}:
            result["priority"] = 1
            result["scope_note"] = "abstract_acceptance_without_new_test_results"
        if re.search(r"기술지주|시드\s*투자|엔젤\s*투자|seed funding|angel investment", headline_lead, re.I) and kinds <= {"capital_or_shareholder_action", "technology_or_clinical_stage", "market_price_or_flow"} and not re.search(
            r"공급\s*계약|납품\s*계약|본계약\s*체결|임상\s*[1-3]상|대역폭.{0,10}\d|추론비용.{0,10}\d|전력효율.{0,10}\d|코스피|코스닥|상장사|listed company", body, re.I,
        ):
            result["priority"] = 1
            result["scope_note"] = "isolated_seed_funding_without_market_transmission"
        if re.search(r"계란|달걀|한우|돼지고기|egg prices", title, re.I) and kinds <= {"physical_supply_or_capacity", "rates_fx_or_macro", "sector_demand_outlook"}:
            result["priority"] = 1
            result["scope_note"] = "single_consumer_price_without_industry_change"
        if re.search(r"전시회|단독\s*부스|공동\s*부스|박람회|exhibition booth", headline_lead, re.I) and kinds <= {
            "physical_supply_or_capacity", "technology_or_clinical_stage", "customer_discussions", "market_price_or_flow",
        } and not re.search(r"임상\s*[1-3]상.{0,20}결과|(?:대역폭|수율|전력효율|반응률).{0,20}\d+(?:\.\d+)?\s*(?:%|배)", body, re.I):
            result["priority"] = 1
            result["scope_note"] = "exhibition_attendance_without_new_business_event"
        if re.search(r"심의회|위원회", title) and re.search(r"격상|구성|참여\s*확대", title) and kinds <= {
            "physical_supply_or_capacity", "customer_discussions", "market_price_or_flow",
        }:
            result["priority"] = 1
            result["scope_note"] = "administrative_membership_not_economic_policy_change"
        if re.search(r"르포|인터뷰", title) and re.search(r"집값|주택|공원|개발", title) and kinds <= {
            "physical_supply_or_capacity", "rates_fx_or_macro", "policy_scope_or_stage", "customer_discussions", "market_price_or_flow",
        }:
            result["priority"] = 1
            result["scope_note"] = "local_housing_commentary_without_business_execution"
        if HEADLINE_EARLY.search(title):
            result["headline_stage"] = "early_signal"
            if re.search(r"제언|권고|해야|바꿔야|줄여야|늘려야", title):
                result["priority"] = min(result["priority"], 2)
        if focus_kind(title) == "fund_result" or re.search(r"(?:상반기|하반기|연간).{0,25}(?:결산|비교|가장)|R&D|연구개발", title, re.I):
            result["priority"] = min(result["priority"], 2)
        # Local indicators and product-level sales PR can be true without
        # displacing changes to industry architecture, financing or execution.
        if REGIONAL_CPI.search(title):
            result["priority"] = min(result["priority"], 1)
            result["scope_note"] = "regional_indicator_not_national_macro"
        elif RETAIL_PRODUCT_METRIC.search(title) and not ENTERPRISE_CHANGE.search(title):
            result["priority"] = min(result["priority"], 1)
            result["scope_note"] = "retail_product_or_store_metric"
        elif ROUTINE_PERSONNEL.search(title) and not ENTERPRISE_CHANGE.search(title):
            result["priority"] = min(result["priority"], 1)
            result["scope_note"] = "personnel_announcement_without_business_change"
        if re.search(r"증시|코스피|코스닥|나스닥|뉴욕마감|대만.*가권", title) and re.search(r"마감|출발|강보합|약보합|소폭|0\.\d+%", title) and not focus_kind(title) and not re.search(
            r"순매수|순매도|유입|유출|서킷브레이커|사이드카|실적|관세|연준|fomc|금리|유가", title, re.I,
        ):
            result["priority"] = min(result["priority"], 2)
    elif routine or soft:
        result.update(disposition="exclude", priority=0, reason="routine_or_vague_without_market_change")
    else:
        # Discovery can keep unfamiliar candidates, but publication needs
        # source evidence rather than a broad sector label.
        result["reason"] = "existing_market_gate_required"
    if result['evidence']:
        result['transmission_scope_rank'], result['transmission_scope_reason'] = transmission_scope(title, result['evidence'])
        result['equity_publication'] = equity_publication_assessment(title, result['evidence'], body=body, source_url=source_url)
        if not result['equity_publication']['eligible']:
            result['priority'] = min(result['priority'], 1)
            result['scope_note'] = result['equity_publication']['reason']
    return result
