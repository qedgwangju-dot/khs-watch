#!/usr/bin/env python3
"""Source-only materiality evidence, without issuer lists or confirmed-only gates."""

from __future__ import annotations

import re


VERSION = 4
EARLY_SIGNAL = re.compile(
    r"검토|추진|협상|논의|가능성|예정|계획|전망(?!치|을|보다)|예상(?!치|을|보다)|관측|소식통|제안|의견수렴|입법예고|"
    r"해야|권고|제언|우려|필요|consider|propos|draft|talks|negotiat|forecast|sources say|reportedly|\b(?:may|could|should)\b", re.I,
)
HEADLINE_EARLY = re.compile(
    r"검토|협상|논의|가능성|관측|소식통|제안|제언|권고|해야|바꿔야|줄여야|늘려야|우려|전망$|예상$|"
    r"consider|propos|draft|forecast|sources say", re.I,
)
BACKGROUND = re.compile(
    r"^\d{4}년\s+설립|^(?:한편\s*)?(?:지난해|작년|과거|기존에는|종전에는|previously|last year)\b|"
    r"설립된 회사|설립된 기업|설립 이후 누적|창립 이래|has historically", re.I,
)
QUANTITY = re.compile(r"\d[\d,.]*\s*(?:%|bp\b|조\s*원|억\s*원|만\s*원|달러|유로|억원|조원|억달러|billion|million)", re.I)
SOFT_HEADLINE = re.compile(
    r"협력|협약|회동|만났|만났다|맞손|방문|비전|극찬|낙관|신제품|출시|공개|"
    r"협력 강화|동반 성장|동반성장|partnership|meeting|visit|launch|unveil", re.I,
)
ROUTINE_HEADLINE = re.compile(
    r"봉사|기부|나눔|문화행사|체육대회|기념촬영|시상|(?:상|어워드|어워즈).{0,12}수상|수상$|브랜드상|"
    r"할인 행사|할인행사|사은품|경품|체험행사|비전 선포|응원|격려|"
    r"관광객\s*공략|기획전|팝업\s*스토어|\d+주년|volunteer|charity|brand award|giveaway|ceremonial", re.I,
)
REGIONAL_CPI = re.compile(
    r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주).{0,12}소비자물가|"
    r"지역(?:별|의)?\s*소비자물가|regional consumer prices", re.I,
)
RETAIL_PRODUCT_METRIC = re.compile(
    r"매장당\s*매출|(?:키즈|신발|커피|패션).{0,25}(?:매출|판매)|(?:매출|판매).{0,20}(?:매장당|신발|커피)|"
    r"sales per store|kids.{0,20}sales", re.I,
)
ENTERPRISE_CHANGE = re.compile(
    r"영업이익|순이익|가이던스|마진|현금흐름|수주|공급계약|납품계약|공장|양산|인수|합병|규제|관세|주주환원|"
    r"operating profit|net income|guidance|cash flow|supply contract|factory|acquisition", re.I,
)
HARD_HEADLINE = re.compile(
    r"매출|이익|실적|가이던스|판가|가격|수주|계약|발주|공장|양산|증설|가동|"
    r"상용화|상장|투자유치|투자 유치|출자|자금조달|자사주|주식 매수|주주환원|주식 기부|지분 이전|"
    r"관세|금리|환율|예탁금|순매수|순매도|수출통제|임상|허가|공급부족|코스피|코스닥|증시|"
    r"earnings|guidance|contract|factory|production|tariff|interest rate|buyback", re.I,
)

# Prefer the first event mentioned in the headline, not a sector assigned by
# the classifier. Reuse it for evidence ranking and compact-summary checks.
HEADLINE_FOCUS = tuple((name, re.compile(head, re.I), re.compile(source, re.I)) for name, head, source in (
    ("ownership", r"지분.{0,25}(?:인수|매각|취득)|인수.{0,25}지분|합병", r"지분|인수|매각|취득|합병|stake|acquir|merger"),
    ("shareholder", r"자사주|자기주식|주주환원|배당", r"자사주|자기주식|주주환원|배당|(?:주식|지분).{0,30}(?:매수|취득|매입|처분)|buyback|dividend"),
    ("capital_listing", r"기업공개|\bipo\b|(?:증시|코스피|코스닥|나스닥)\s*상장|상장\s*(?:추진|예정|연기|철회|신청|승인)|신규\s*상장", r"기업공개|\bipo\b|상장(?!지수)"),
    ("mortgage_rate", r"주담대|모기지|주택담보대출", r"주담대|모기지|주택담보대출|mortgage"),
    ("macro_release", r"\bcpi\b|\bpce\b|\bppi\b|\bgdp\b|고용|실업률|물가", r"cpi|pce|ppi|gdp|고용|실업|물가|인플레이션|inflation|payroll"),
    ("energy_supply", r"브렌트|유가|원유|천연가스|호르무즈|홍해|유조선|운임|\bbrent\b|\boil\b|hormuz|tanker", r"브렌트|유가|원유|천연가스|호르무즈|홍해|유조선|운임|항행|통항|brent|\boil\b|hormuz|tanker|shipping"),
    ("bond_yield", r"금리|국채.{0,8}(?:투매|수익률)|bond yields|treasury yields", r"금리|국채.{0,8}수익률|bond yields|treasury yields|interest rates"),
    ("fx", r"환율|약달러|강달러|달러화|원[·/]달러|달러[·/]원|\bndf\b|exchange rate", r"환율|달러화|달러[·/]원|원[·/]달러|\bndf\b|exchange rate|dollar"),
    ("breadth", r"(?:상승|하락)\s*종목|순환매|쏠림", r"(?:오른|내린|상승|하락)\s*종목|순환매|쏠림|순매수|순매도|자금.{0,12}이동"),
    ("research_spending", r"r&d|연구개발", r"r&d|연구개발"),
    ("industrial_architecture", r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model", r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model"),
    ("science_milestone", r"극저온|양자|효소|cryogenic|quantum|enzyme", r"극저온|양자|효소|cryogenic|quantum|enzyme"),
    ("space_execution", r"위성|궤도|발사한도|발사계약|환경심사|환경영향평가|주파수|satellite|orbital|launch contract|spectrum", r"위성|궤도|발사|환경심사|환경영향평가|주파수|satellite|orbital|launch|spectrum"),
    ("fund_result", r"펀드.{0,20}(?:손실|청산|만기|수익)|(?:손실|청산).{0,20}펀드", r"손실|청산|수익률|loss|liquidat|returns"),
    ("memory", r"hbm|hbf|메모리|낸드|dram", r"hbm|hbf|메모리|낸드|dram"),
    ("earnings", r"매출|영업이익|순이익|실적|가이던스|earnings|guidance", r"매출|영업이익|순이익|실적|가이던스|revenue|profit|earnings|guidance"),
))
MONTH = re.compile(r"(?<!\d)(1[0-2]|[1-9])월")
ASPIRATION = re.compile(r"관계자는|기대한다|기대된다|키워나|키워\s*나|키우고|성장축|비전을|최선을|응원|company spokesperson", re.I)
DENIAL_HEADLINE = re.compile(r"확정.{0,8}(?:아냐|아니|않)|미확정|부인|사실무근|denies|not final", re.I)
DENIAL_SOURCE = re.compile(r"확정[^.!?]{0,20}(?:아냐|아니|않|없)|미확정|부인|사실무근|denies|not final", re.I)
SOLICITATION_HEADLINE = re.compile(r"잡으려면|활용\s*가능한\s*기회|스탁론|주식자금.{0,20}(?:대출|상담|마련)|투자자금.{0,20}(?:상담|마련)", re.I)
SOLICITATION_BODY = re.compile(r"스탁론|고객상담|상담센터|주식자금\s*(?:상품|대출)|투자금을\s*준비|신용.{0,8}대환|loan consultation", re.I)
TACTICAL_HEADLINE = re.compile(r"(?:미사일|무기|드론).{0,25}(?:첫\s*실전|실전\s*투입|시험\s*발사)|(?:진지|전차).{0,15}(?:타격|격파)|격추", re.I)
ECONOMIC_GEOPOLITICS = re.compile(
    r"에너지\s*시설|정유|유전|송유관|원유|유가|가스|항만|물류|유조선|운임|호르무즈|홍해|통항|봉쇄|"
    r"수출|수입|제재|국방\s*예산|방위\s*예산|조달|수주|공급계약|휴전|협상|접촉|합의|"
    r"확전|전면전|전쟁\s*(?:선포|확대)|핵(?:무기)?\s*(?:사용|위협|공격)|핵전쟁|참전|"
    r"추가\s*(?:공격|공습)|공격\s*임박|항공\s*모함|항공모함|병력\s*증강|"
    r"energy|refiner|pipeline|oil|gas|port|shipping|tanker|hormuz|blockade|sanction|procurement|contract|ceasefire|talks|negotiat|escalat", re.I,
)


def focus_kind(title: str) -> str:
    matches = [(match.start(), index, kind) for index, (kind, headline, _source) in enumerate(HEADLINE_FOCUS)
               if (match := headline.search(title or "")) is not None]
    return min(matches)[2] if matches else ""


def focus_matches(title: str, sentence: str) -> bool:
    if DENIAL_HEADLINE.search(title) and not DENIAL_SOURCE.search(sentence):
        return False
    kind = focus_kind(title)
    if kind == "mortgage_rate":
        return bool(re.search(r"주담대|모기지|주택담보대출|mortgage", sentence, re.I)
                    and re.search(r"금리|rate", sentence, re.I))
    if kind == "fx" and re.search(r"\bndf\b", title, re.I):
        return bool(re.search(r"\bndf\b|차액결제선물환|역외환율", sentence, re.I))
    if kind == "energy_supply" and re.search(r"브렌트|\bbrent\b", title, re.I):
        return bool(re.search(r"브렌트|\bbrent\b", sentence, re.I))
    if kind == "fund_result":
        funds = [root for root in re.findall(r"([A-Za-z0-9가-힣]+)펀드", title) if len(root) >= 2]
        if funds and not any(root in sentence for root in funds):
            return False
    return not kind or next(source for name, _head, source in HEADLINE_FOCUS if name == kind).search(sentence or "") is not None


def period_matches(title: str, sentence: str) -> bool:
    months, source_months = set(MONTH.findall(title or "")), set(MONTH.findall(sentence or ""))
    return not (months and source_months and months.isdisjoint(source_months))


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

# Each rule needs a subject and a change in the same source-authored sentence.
# Quantities, counterparties and stages are evidence, not estimates of price impact.
RULES = (
    ("capital_listing_stage", ("flows", "timeline"),
     r"기업공개|\bipo\b|(?:증시|코스피|코스닥|나스닥)\s*상장|상장\s*(?:추진|예정|연기|철회|신청|승인)",
     r"추진|예정|목표|신청|승인|상장했다|연기|철회|마케팅|등록|plan|aim|file|approv|delay|withdraw|market"),
    ("commercial_order", ("earnings", "timeline"),
     r"수주|발주|공급계약|공급\s*계약|납품\s*계약|발사\s*계약|purchase order|supply contract|procurement contract|launch (?:contract|agreement)",
     r"체결|확정|수주|발주|갱신|취소|파기|해지|협상|추진|서명|sign|secure|award|agree|cancel|negotiat"),
    ("selling_price_or_cost", ("earnings",),
     r"판매가격|판매\s*가격|판가|단가|원가|평균판매가격|\basp\b|selling price|unit price|input cost",
     r"인상|인하|상승|하락|급등|급락|증가|감소|전가|협상|상향|하향|rais|cut|rise|fall|increas|decreas|negotiat"),
    ("earnings_or_guidance", ("earnings",),
     r"매출|영업이익|순이익|마진|실적|가이던스|출하|판매량|시장점유율|revenue|earnings|profit|guidance|shipments",
     r"증가|감소|상승|하락|상회|하회|상향|하향|달성|기록|집계|발표|전망|예상|rise|fall|grow|cut|rais|report|forecast|beat|miss"),
    ("research_spending_change", ("earnings", "timeline"),
     r"r&d|연구개발", r"증가|감소|늘|줄|투자|지출|비용|rise|fall|spend|invest"),
    ("licensing_cashflow", ("earnings", "timeline"),
     r"로열티|선급금|마일스톤|기술이전|royalty|upfront|milestone|licens",
     r"체결|계약|수령|수취|받|합의|서명|sign|agreement|receiv"),
    ("capital_or_shareholder_action", ("earnings", "timeline"),
     r"투자(?=\s*(?:\d|를|한다|한다고|할|하겠|금|액|규모|계획|협약|계약|자금)|.{0,12}유치)|capex|출자|자금조달|자본조달|회사채|주주환원|배당|자사주|자기주식|지분|funding|financing|buyback|dividend|bond issuance|stake",
     r"체결|유치|출자|발행|증액|삭감|확대|축소|매입|매수|취득|소각|매각|인수|검토|추진|결정|발표|raise|issu|buy|repurchas|sell|acquir|announc|consider"),
    ("insider_disclosed_trade", ("flows",),
     r"(?:회장|대표|사장|임원|ceo|executive).{0,80}(?:주식|지분|shares|stake)",
     r"매수|매입|취득|매도|처분|buy|purchas|sell|disclos"),
    ("ownership_transfer", ("flows", "timeline"),
     r"주식|지분|shares|stake", r"기부|이전|증여|donat|transfer"),
    ("corporate_transaction", ("earnings", "timeline"),
     r"회사|기업|사업|법인|지분|company|business|subsidiar|stake", r"인수|합병|acquir|merger"),
    ("institutional_capital_access", ("earnings", "timeline"),
     r"국민연금|연기금|벤처캐피털|\bvc\b|pension fund|venture capital",
     r"투자\s*기회.{0,8}(?:확대|넓)|출자|투자협력|투자 협력|funding|investment opportunities|commitment"),
    ("market_infrastructure", ("timeline",),
     r"증권계좌|거래시스템|결제망|증권거래소|오픈뱅킹|증권 거래|brokerage account|trading system|payment network",
     r"연결|도입|출시|가동|개편|허용|launch|deploy|connect|reform"),
    ("model_operating_specification", ("earnings", "timeline"),
     r"모델|llm|ai model|language model|솔라 미니|gpu|npu",
     r"(?:gpu|npu|가속기)\s*(?:\d+|한|두|세)\s*(?:장|개)|\d+\s*(?:장|개)의?\s*(?:gpu|npu)|(?:메모리|전력|지연시간|추론비용|운용비용).{0,15}\d+(?:\.\d+)?\s*(?:%|gb|w|배)|\d+(?:\.\d+)?\s*(?:배|%)\s*(?:빠르|절감|줄|감소)"),
    ("industrial_architecture_adoption", ("earnings", "timeline"),
     r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model|co.packaged optics",
     r"규격|채택|통합|전환|도입|standard|specification|adopt|integrat|deploy"),
    ("rates_fx_or_macro", ("discount_rate",),
     r"기준\s*금리|국채\s*금리|국고채|모기지|주담대|주택담보대출|물가|인플레이션|고용|환율|달러화|유동성|차입|cpi|pce|payroll|mortgage|interest rate|treasury|inflation|exchange rate|borrowing",
     r"인상|(?<!할)인하|동결|상승|하락|둔화|급등|급락|상회|하회|발표|증가|감소|결정|약세|강세|최고|치솟|cut|hike|hold|rise|fall|miss|beat|announc|estimat"),
    ("policy_scope_or_stage", ("timeline",),
     r"관세|수출통제|수출금지|수입금지|수입 금지|수입 제한|수입제한|제재|보조금|지원금|예탁금|규제|인허가|조례|환경심사|환경영향평가|주파수|tariff|export control|import ban|sanction|subsid|licens|environmental review|spectrum|\bban(?:s|ned)?\b",
     r"제안|검토|추진|인상|인하|완화|강화|시행|발효|금지|제한|허가|승인|제정|철회|의견수렴|입법예고|면제|배정|의결|착수|propos|draft|\bban(?:s|ned)?\b|prohibit|restrict|approv|enact|implement|consider|exempt|allocat|adopt"),
    ("public_program_cost_study", ("timeline",),
     r"방위사업|국방예산|방위예산|조달예산|missile defense|defense budget|procurement budget",
     r"추산|심의|추정|예산안|cost estimate|cost study|budget proposal"),
    ("market_price_or_flow", (),
     r"주가|증시|코스피|코스닥|etf|etn|순매수|순매도|거래대금|유입|유출|수익률|주식|shares|stocks|equities|inflows|outflows",
     r"급등|급락|상승|하락|순매수|순매도|유입|유출|이동|상장|편입|편출|증가|감소|surge|slump|rise|fall|inflows|outflows|list|rebalance"),
    ("physical_supply_or_capacity", ("earnings", "timeline"),
     r"공장|생산|설비|공급|수요|재고|수율|리드타임|부족|품귀|항만|물류|운송|factory|production|supply|demand|inventory|lead time|port|freight",
     r"증설|착공|가동|증가|감소|중단|차질|부족|품귀|지연|연장|매각|검토|확대|축소|상용화|expand|start|halt|disrupt|shortage|delay|consider|launch"),
    ("technology_or_clinical_stage", ("earnings", "timeline"),
     r"메모리|반도체|hbm|hbf|cxl|칩|공정|로봇|신약|임상|fda|의약품|기술|양자|극저온|memory|semiconductor|chip|clinical|drug|technology|quantum|cryogenic",
     r"양산|상용화|인증|승인|허가|임상 결과|임상결과|공급|도입|검증|성능|대역폭|수율|전력효율|결과 발표|생산|production|commercial|certif|approv|deploy|validat|performance|bandwidth|yield"),
    ("space_execution_stage", ("timeline",),
     r"위성|궤도|satellite|orbital", r"시험|검증|발사.{0,15}(?:완료|성공)|prototype|orbital test|launch.{0,20}(?:complet|success)"),
    ("biology_research_discovery", ("timeline",),
     r"효소|단백질|enzyme|protein", r"발견|규명|discover|characteriz"),
    ("energy_geopolitics_or_supply_risk", ("earnings", "discount_rate"),
     r"원유|유가|브렌트|천연가스|운임|호르무즈|홍해|이란|이스라엘|우크라이나|러시아|구리|리튬|\boil\b|brent|wti|\bgas\b|hormuz|iran|ukraine|russia|copper|lithium",
     r"공격|공습|피격|발사체|화재|휴전|협상|통항|봉쇄|제재|상승|하락|급등|급락|차질|감산|증산|합의|경고|명령|배치|발표|attack|strike|ceasefire|talks|blockade|sanction|rise|fall|disrupt|output|warn|deploy|announc"),
    ("climate_operational_damage", ("earnings", "timeline"),
     r"폭염|폭우|홍수|태풍|정전|가뭄|산불|heatwave|flood|outage|drought|wildfire",
     r"전력|변압기|과부하|폐사|양식|농작물|생산|공급|항만|물류|공장|피해|사망|power|transformer|crop|production|supply|port|factory|damage|death"),
    ("labor_cost_or_execution", ("earnings", "timeline"),
     r"파업|노조|성과급|임단협|(?<!금)감원|감축|임금|strike|union|layoff|wage",
     r"생산|공장|운송|항만|비용|인상|교섭|협상|주식|지급|중단|감축|production|factory|port|cost|talks|shares|halt|cut"),
    ("customer_discussions", ("earnings", "timeline"),
     r"공급|고객|구매|생산|공동개발|공동 개발|인증|hbm|파운드리|자율주행|데이터센터|ai.{0,4}(?:반도체|인프라)|supply|customer|procurement|co-develop|foundry|autonomous|data center",
     r"협상|논의|검토|회동|협력(?!사)|합의|협약|negotiat|discuss|consider|meeting|collaborat|agreement"),
)
COMPILED_RULES = tuple(
    (kind, axes, re.compile(subject, re.I), re.compile(action, re.I))
    for kind, axes, subject, action in RULES
)


def assess(title: str, body: str) -> dict:
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    body = str(body or "").strip()
    result = {"version": VERSION, "disposition": "review", "priority": 1, "axes": [], "evidence": []}
    if not title or not body:
        result["reason"] = "source_evidence_unavailable"
        return result
    if SOLICITATION_HEADLINE.search(title) and SOLICITATION_BODY.search(body) and (
        re.search(r"잡으려면|활용\s*가능한\s*기회", title)
        or not re.search(r"규제|제재|반대매매|손실|예탁금|금리\s*(?:인상|인하)", title)
    ):
        result.update(disposition="exclude", priority=0, reason="investment_loan_solicitation_not_market_news")
        return result
    sentences = [part.strip() for part in re.split(r"(?<!\d)[.!?。](?!\d)\s*|[\r\n]+", body) if part.strip()]
    lead = " ".join(sentences[:3])
    if TACTICAL_HEADLINE.search(title) and not ECONOMIC_GEOPOLITICS.search(f"{title} {lead}"):
        result.update(disposition="exclude", priority=0, reason="tactical_military_without_economic_transmission")
        return result
    generic_tokens = {"기업", "대표", "회장", "공개", "협력", "강화", "발표", "미래", "신제품", "출시", "회동", "계획"}
    tokens = [word for word in re.findall(r"[A-Za-z0-9가-힣]+", title.lower()) if len(word) >= 2 and word not in generic_tokens]
    routine = bool(ROUTINE_HEADLINE.search(title) and not HARD_HEADLINE.search(title))
    soft = bool(SOFT_HEADLINE.search(title) and not HARD_HEADLINE.search(title))
    matches = []
    for index, sentence in enumerate(sentences):
        if BACKGROUND.search(sentence) or not period_matches(title, sentence):
            continue
        if re.search(r"추가매수를\s*고려하고\s*있었다면|투자자라면|투자금을\s*준비하는\s*방법|기회를\s*잡으려", sentence):
            continue
        # A numeric company profile or another topic later in the article must
        # not turn today's ceremonial/promotion headline into a market event.
        anchored = any(token in sentence.lower() for token in tokens)
        adjacent = index > 0 and any(token in sentences[index - 1].lower() for token in tokens)
        if (routine or soft) and not anchored and not adjacent:
            continue
        if (focus_kind(title) or DENIAL_HEADLINE.search(title)) and not focus_matches(title, sentence):
            continue
        for kind, axes, subject, action in COMPILED_RULES:
            if not subject.search(sentence) or not action.search(sentence):
                continue
            if routine and kind not in {"policy_scope_or_stage", "physical_supply_or_capacity", "capital_or_shareholder_action"}:
                continue
            if soft and kind in {"earnings_or_guidance", "rates_fx_or_macro", "market_price_or_flow"} and not SOFT_HEADLINE.search(sentence):
                continue
            if soft and kind == "customer_discussions" and not re.search(
                r"공급|고객|구매|생산|공동\s*개발|인증|hbm|파운드리|자율주행|데이터센터|ai.{0,4}(?:반도체|인프라)|supply|customer|procurement|co-develop|foundry|autonomous|data center", sentence, re.I,
            ):
                continue
            if kind == "rates_fx_or_macro" and re.search(
                r"환율\s*(?:우대|혜택)|우대\s*환율|즉시\s*할인|할인\s*쿠폰|사은품|경품", sentence,
            ):
                continue
            if kind == "technology_or_clinical_stage" and not re.search(
                r"양산|상용화|인증|승인|허가|임상|공급|도입|검증|성능|대역폭|수율|전력효율|production|commercial|approv|deploy|validat|performance|bandwidth|yield", sentence, re.I,
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
            if kind == "model_operating_specification" and not re.search(
                r"구동|동작|실행|추론|운용|가동|배포|메모리|전력|지연시간|추론비용|운용비용|running|inference|deploy|memory|power|latency|cost", sentence, re.I,
            ):
                continue
            if kind == "energy_geopolitics_or_supply_risk" and not ECONOMIC_GEOPOLITICS.search(sentence) and not re.search(r"브렌트|\bbrent\b|\bwti\b", sentence, re.I):
                continue
            if kind == "research_spending_change" and not QUANTITY.search(sentence):
                continue
            early = bool(EARLY_SIGNAL.search(sentence)) or kind in {"customer_discussions", "institutional_capital_access"}
            priority = 2 if early or kind in {"technology_or_clinical_stage", "market_infrastructure", "model_operating_specification", "industrial_architecture_adoption", "space_execution_stage", "biology_research_discovery", "public_program_cost_study"} else 3
            if kind == "capital_listing_stage":
                priority = 3
            if kind in {"earnings_or_guidance", "market_price_or_flow"} and not QUANTITY.search(sentence):
                priority = 2
            if kind == "research_spending_change":
                priority = 2
            # Certainty and economic materiality are separate. A scoped import
            # ban or financing negotiation can outrank a routine index recap.
            if early and kind in {"policy_scope_or_stage", "capital_or_shareholder_action", "physical_supply_or_capacity", "energy_geopolitics_or_supply_risk"} and re.search(
                r"수입|수출|관세|보조금|자금조달|대출|공장|생산|공급|호르무즈|유조선|유가|import|export|tariff|loan|funding|factory|supply|hormuz|tanker|oil", sentence, re.I,
            ):
                priority = 3
            evidence_axes = list(axes)
            if kind in {"capital_or_shareholder_action", "market_price_or_flow"} and re.search(
                r"자사주|자기주식|배당|순매수|순매도|유입|유출|거래대금|편입|편출|매수|매도|buyback|dividend|inflows|outflows|rebalance", sentence, re.I,
            ):
                evidence_axes.append("flows")
            if kind == "market_price_or_flow" and "flows" not in evidence_axes:
                priority = 2 if focus_kind(title) == "breadth" else 1
            if kind == "policy_scope_or_stage" and re.search(
                r"관세|수출|수입|보조금|지원금|비용|생산|공급|tariff|export|import|subsid|cost|production|supply", sentence, re.I,
            ):
                evidence_axes.append("earnings")
            matches.append((priority, focus_score(title, sentence), -index, evidence_axes,
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
        if re.search(r"증시|코스피|코스닥|나스닥|뉴욕마감|대만.*가권", title) and re.search(r"마감|출발|강보합|약보합|소폭|0\.\d+%", title) and not focus_kind(title) and not re.search(
            r"순매수|순매도|유입|유출|서킷브레이커|사이드카|실적|관세|연준|fomc|금리|유가", title, re.I,
        ):
            result["priority"] = min(result["priority"], 2)
    elif routine or soft:
        result.update(disposition="exclude", priority=0, reason="routine_or_vague_without_market_change")
    else:
        # This is a refinement of the existing broad market gate, not a new
        # universal whitelist. Unrecognised events still face that gate.
        result["reason"] = "existing_market_gate_required"
    return result
