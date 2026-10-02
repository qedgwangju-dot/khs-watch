#!/usr/bin/env python3
"""Source-only materiality evidence, without issuer lists or confirmed-only gates."""

from __future__ import annotations

import re


VERSION = 32
OIL_PRICE = r"(?<![가-힣])(?:국제|고|저)?유가(?!증권)"
ENERGY_SUBJECT = (
    rf"원유|{OIL_PRICE}|브렌트|천연가스|운임|호르무즈|홍해|이란|이스라엘|우크라이나|러시아|구리|리튬|"
    r"\boil\b|brent|wti|\bgas\b|hormuz|iran|ukraine|russia|copper|lithium"
)
EARLY_SIGNAL = re.compile(
    r"검토|추진|협상|논의|가능성|예정|계획|전망(?!치|을|보다)|예상(?!치|을|보다)|관측|소식통|제안|의견수렴|입법예고|"
    r"건의|요청|요구|제시|모색|촉구|해야|권고|제언|우려|필요|목표|보인다|나서야|시급|밑돌\s*듯|합의\s*(?:안\s*(?:됐|되)|하지\s*않)|미합의|consider|propos|draft|talks|negotiat|forecast|sources say|reportedly|\b(?:may|could|should|target|aim|expected)\b", re.I,
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
    r"협력 강화|동반 성장|동반성장|혁신\s*전략|전략\s*발표|강연|conference|presentation|partnership|meeting|visit|launch|unveil", re.I,
)
ROUTINE_HEADLINE = re.compile(
    r"봉사|기부|나눔|문화행사|체육대회|기념촬영|시상|(?:상|어워드|어워즈).{0,12}수상|수상$|브랜드상|"
    r"할인 행사|할인행사|사은품|경품|체험행사|비전 선포|응원|격려|"
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
STAFF_APPOINTMENT = re.compile(r"(?:변호사|전문가|고문|자문위원|임원).{0,25}(?:영입|선임|합류)|(?:영입|선임).{0,25}(?:변호사|고문|자문위원)|(?:수장|이사장|원장)\s*후보.{0,20}적격|staff appointment|hires? counsel", re.I)
ROUTINE_FOREGROUND = re.compile(r"(?:상|어워드|어워즈).{0,12}수상|수상$|포상|표창|(?:선제|조기|정기|임원|사장단)\s*인사|(?:도서|서적).{0,20}(?:출간|인기|관심)|book promotion", re.I)
DIRECT_HEADLINE_CHANGE = re.compile(r"(?:매출|영업이익|순이익|가이던스).{0,20}(?:증가|감소|상향|하향|상회|하회)|(?:수주|계약).{0,20}(?:체결|확정|억|조)|(?:공장|생산능력).{0,20}(?:증설|착공|가동)|(?:지분|사업부).{0,20}(?:인수|매각|취득).{0,12}(?:결정|완료|확정)|earnings revision|contract signed", re.I)
PHOTO_DESCRIPTION = re.compile(r"(?:기념촬영|사진촬영|촬영|시공|시연|발언|연설|질문에\s*답)(?:을|를)?\s*하고\s*있다", re.I)
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
HARD_HEADLINE = re.compile(
    r"매출|이익|실적|가이던스|판가|가격|수주|계약|발주|공장|양산|증설|가동|"
    r"상용화|상장|투자유치|투자 유치|출자|자금조달|자사주|주식 매수|주주환원|주식 기부|지분 이전|"
    r"관세|금리|환율|예탁금|순매수|순매도|수출통제|임상|허가|공급부족|코스피|코스닥|증시|"
    r"earnings|guidance|contract|factory|production|tariff|interest rate|buyback", re.I,
)

# Prefer the first event mentioned in the headline, not a sector assigned by
# the classifier. Reuse it for evidence ranking and compact-summary checks.
HEADLINE_FOCUS = tuple((name, re.compile(head, re.I), re.compile(source, re.I)) for name, head, source in (
    ("tax_relief", r"비과세|과세.{0,12}제외|특례\s*(?:관세|방안)|FTA.{0,12}특례", r"비과세|과세.{0,25}제외|특례|특혜관세"),
    ("sanctions_exemption", r"제재.*(?:면제|예외)", r"(?:예외|면제|일반\s*허가|general licen[cs]e)"),
    ("monetary_guidance", r"(?:연준|ECB|한국은행).{0,15}(?:의장|총재)", r"(?:금리|통화|정책).{0,90}(?:밝혔|말했|강조|신중|시사|필요)"),
    ("nuclear_warning", r"핵\s*(?:대응|사용|공격|위협)|nuclear.{0,12}(?:threat|response)", r"(?:핵|특별한\s*수단|모든\s*무기).{0,80}(?:대응|사용|경고|위협|준비|불가피)"),
    ("trading_status", r"거래\s*재개|액면병합|주식병합", r"거래.{0,12}재개|재개.{0,12}거래|액면병합|주식병합"),
    ("customer_implementation", r"1차\s*시공|초도\s*납품", r"1차\s*시공|초도\s*납품"),
    ("industrial_program", r"(?:SMR|원전|양자|반도체|로봇).{0,16}상용화", r"(?:상용화|사업화).{0,50}(?:출범|지원|시행|추진)|(?:출범|지원|시행|추진).{0,50}(?:상용화|사업화)"),
    ("environmental_approval", r"환경(?:영향)?평가.{0,15}(?:통과|완료|면제)", r"최종\s*환경평가|FONSI|환경영향평가서.{0,35}(?:없이|면제)"),
    ("ownership", r"지분.{0,25}(?:인수|매각|취득)|인수.{0,25}지분|합병(?!원)|주식.{0,8}(?:판다|매도|매각)", r"지분|인수|매각|매도|취득|거래계획|합병(?!원)|stake|acquir|merger"),
    ("labor_negotiation", r"임단협|임금.{0,12}(?:협상|합의)|단체협약", r"임단협|임금|단체협약|잠정합의안|교섭"),
    ("shareholder", r"자사주|자기주식|주주환원|배당", r"자사주|자기주식|주주환원|배당|(?:주식|지분).{0,30}(?:매수|취득|매입|처분)|buyback|dividend"),
    ("capital_listing", r"기업공개|\bipo\b|(?:증시|코스피|코스닥|나스닥)\s*상장|상장\s*(?:추진|예정|연기|철회|신청|승인)|신규\s*상장|ETF.{0,15}(?:출시|상장)", r"기업공개|\bipo\b|상장(?!지수)|ETF.{0,80}출시"),
    ("financing", r"자금.{0,12}(?:투입|조달|유입)|대출|funding|financing|loan", r"자금|대출|투자(?!자)|조달|전환사채|출자|납입|증자|확정된\s*사항|funding|financing|loan|convertible debt"),
    ("mortgage_rate", r"주담대|모기지|주택담보대출", r"주담대|모기지|주택담보대출|mortgage"),
    ("macro_release", r"\bcpi\b|\bpce\b|\bppi\b|\bgdp\b|고용|실업률|물가|건설지출", r"cpi|pce|ppi|gdp|고용|실업|물가|건설지출|인플레이션|inflation|payroll"),
    ("export_results", r"수출(?:액|실적|량)|수출.{0,20}(?:\d위|역대|최대|최저|증가|감소)", r"수출(?:액|실적|량)|수출.{0,45}(?:\d|최대|최저)"),
    ("energy_supply", rf"브렌트|{OIL_PRICE}|원유|천연가스|호르무즈|홍해|유조선|운임|\bbrent\b|\boil\b|hormuz|tanker", rf"브렌트|{OIL_PRICE}|원유|천연가스|호르무즈|홍해|유조선|운임|항행|통항|brent|\boil\b|hormuz|tanker|shipping"),
    ("bond_yield", r"금리|국채.{0,8}(?:투매|수익률)|bond yields|treasury yields", r"금리|국채.{0,8}수익률|bond yields|treasury yields|interest rates"),
    ("fx", r"환율|약달러|강달러|달러화|원[·/]달러|달러[·/]원|\bndf\b|exchange rate", r"환율|달러화|달러[·/]원|원[·/]달러|\bndf\b|exchange rate|dollar"),
    ("breadth", r"(?:상승|하락)\s*종목|순환매|쏠림", r"(?:오른|내린|상승|하락)\s*종목|순환매|쏠림|순매수|순매도|자금.{0,12}이동"),
    ("production_capacity", r"증설|캐파|생산능력|착공|가동\s*(?:중단|시작)|생산\s*중단|production capacity|capacity expansion|production halt", r"증설|캐파|생산능력|착공|가동|생산|production capacity|capacity|construction|production"),
    ("project_buildout", r"데이터센터\s*(?:구축|건설)|data cent(?:er|re).{0,15}(?:build|construction)", r"데이터센터[^.!?]{0,80}(?:구축|건설)|(?:구축|건설).{0,30}데이터센터|data cent(?:er|re).{0,80}(?:build|construction)|(?:build|construction).{0,30}data cent(?:er|re)"),
    ("research_spending", r"r&d|연구개발", r"r&d|연구개발"),
    ("research_result", r"연구\s*성과|실험\s*결과|벤치마크", r"벤치마크|실험\s*결과|연구\s*결과"),
    ("model_efficiency", r"토큰\s*(?:처리량|량)|추론\s*(?:속도|비용).{0,15}\d", r"토큰\s*(?:처리량|량).{0,35}\d|추론\s*(?:속도|비용).{0,35}\d"),
    ("analyst_revision", r"목표주가|목표가|투자의견|\[美특징주\].{0,60}(?:전망|평가)", r"목표주가|목표가|투자의견"),
    ("industrial_architecture", r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model", r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model"),
    ("space_turnaround", r"열\s*차폐|재진입|재발사|재비행|heat[ -]shield|thermal protection|re.?entry|reflight|relaunch|turnaround", r"열\s*차폐|재진입|재발사|재비행|타일|정비|heat[ -]shield|thermal protection|re.?entry|reflight|relaunch|turnaround"),
    ("space_propellant_storage", r"추진제|\bzbo\b|무손실\s*저장|zero[ -]boil[ -]off|propellant", r"추진제|\bzbo\b|무손실\s*저장|zero[ -]boil[ -]off|propellant"),
    ("science_milestone", r"극저온|양자|효소|cryogenic|quantum|enzyme", r"극저온|양자|효소|cryogenic|quantum|enzyme"),
    ("space_execution", r"위성|궤도|발사한도|발사계약|환경심사|환경영향평가|주파수|satellite|orbital|launch contract|spectrum", r"위성|궤도|발사|환경심사|환경영향평가|주파수|satellite|orbital|launch|spectrum"),
    ("fund_result", r"펀드.{0,20}(?:손실|청산|만기|수익)|(?:손실|청산).{0,20}펀드", r"손실|청산|수익률|loss|liquidat|returns"),
    ("memory", r"hbm|hbf|메모리|낸드|dram", r"hbm|hbf|메모리|낸드|dram"),
    ("earnings", r"매출|영업(?:이익|익)|순(?:이익|익)|실적|가이던스|earnings|guidance", r"매출|영업(?:이익|익)|순(?:이익|익)|실적|가이던스|revenue|profit|earnings|guidance"),
))
MONTH = re.compile(r"(?<!\d)(1[0-2]|[1-9])월")
ASPIRATION = re.compile(r"관계자는|기대한다|기대된다|키워나|키워\s*나|키우고|성장축|비전을|최선을|응원|company spokesperson", re.I)
DENIAL_HEADLINE = re.compile(r"확정.{0,8}(?:아냐|아니|않)|합의\s*(?:안\s*(?:됐|되)|하지\s*않)|미합의|미확정|부인|사실무근|denies|not final", re.I)
DENIAL_SOURCE = re.compile(r"확정[^.!?]{0,20}(?:아냐|아니|않|없)|합의\s*(?:안\s*(?:됐|되)|하지\s*않)|미합의|미확정|부인|사실무근|denies|not final", re.I)
SOLICITATION_HEADLINE = re.compile(r"잡으려면|활용\s*가능한\s*기회|스탁론|주식자금.{0,20}(?:대출|상담|마련)|투자자금.{0,20}(?:상담|마련)", re.I)
SOLICITATION_BODY = re.compile(r"스탁론|고객상담|상담센터|주식자금\s*(?:상품|대출)|투자금을\s*준비|신용.{0,8}대환|loan consultation", re.I)
TACTICAL_HEADLINE = re.compile(r"(?:미사일|무기|드론).{0,25}(?:첫\s*실전|실전\s*투입|시험\s*발사)|(?:진지|전차).{0,15}(?:타격|격파)|격추", re.I)
ECONOMIC_GEOPOLITICS = re.compile(
    rf"에너지\s*시설|정유|유전|송유관|원유|{OIL_PRICE}|가스|항만|물류|유조선|운임|호르무즈|홍해|통항|봉쇄|"
    r"수출|수입|제재|국방\s*예산|방위\s*예산|조달|수주|공급계약|휴전|협상|접촉|"
    r"확전|전면전|전쟁\s*(?:선포|확대)|핵(?:무기)?\s*(?:사용|위협|공격)|핵전쟁|참전|"
    r"추가\s*(?:공격|공습)|공격\s*임박|항공\s*모함|항공모함|병력\s*증강|"
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


def focus_kind(title: str) -> str:
    # A scoped tax treatment is the event; oil is only its subject.
    if HEADLINE_FOCUS[0][1].search(title or ""):
        return "tax_relief"
    if re.search(r"ETF.{0,15}(?:출시|상장)", title or "", re.I):
        return "capital_listing"
    matches = [(match.start(), index, kind) for index, (kind, headline, _source) in enumerate(HEADLINE_FOCUS)
               if (match := headline.search(title or "")) is not None]
    return min(matches)[2] if matches else ""


def focus_matches(title: str, sentence: str) -> bool:
    if DENIAL_HEADLINE.search(title) and not DENIAL_SOURCE.search(sentence):
        return False
    kind = focus_kind(title)
    if kind == "labor_negotiation" and "부결" in title and not re.search(r"부결|타결.{0,12}(?:못|않)|추가\s*교섭", sentence):
        return False
    if kind == "nuclear_warning":
        condition = re.search(r"([가-힣A-Za-z]{2,20})\s*(?:피격|공격)(?:시|받)", title)
        if condition and condition.group(1) not in sentence:
            return False
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
    ("trading_status_change", ("flows", "timeline"),
     r"거래\s*재개|매매\s*재개|액면병합|주식병합|거래정지|매매정지",
     r"재개|결정|발표|완료|정지"),
    ("capital_listing_stage", ("flows", "timeline"),
     r"기업공개|\bipo\b|(?:증시|코스피|코스닥|나스닥)\s*상장|상장\s*(?:추진|예정|연기|철회|신청|승인)|ETF",
     r"추진|예정|목표|신청|승인|상장(?:했다|한다고|한다|할)|연기|철회|마케팅|등록|출시|plan|aim|file|approv|delay|withdraw|market"),
    ("commercial_order", ("earnings", "timeline"),
     r"수주|발주|공급계약|공급\s*계약|납품\s*계약|발사\s*계약|purchase order|supply contract|procurement contract|launch (?:contract|agreement)",
     r"체결|확정|수주|발주|갱신|취소|파기|해지|협상|추진|서명|sign|secure|award|agree|cancel|negotiat"),
    ("order_backlog_level", ("earnings", "timeline"),
     r"수주잔고|수주\s*잔고|잔여수주|order backlog|remaining orders", r"확보|기록|집계|발표|증가|감소|secur|report|increas|decreas"),
    ("customer_supply_start", ("earnings", "timeline"),
     r"고객|공급|납품|시공|customer|supply|deliver", r"첫\s*(?:공급|납품)|공급(?:했다|한다|하기로)|납품(?:했다|한다)|(?:1차\s*시공|초도\s*납품).{0,15}완료|first delivery|began supplying"),
    ("procurement_execution_stage", ("earnings", "timeline"),
     r"입찰|시공사|우선협상|procurement|bid|preferred bidder",
     r"제출|선정|선택|낙찰|철회|탈락|확보|submit|select|award|withdraw"),
    ("selling_price_or_cost", ("earnings",),
     r"판매가격|판매\s*가격|판가|단가|원가|평균판매가격|\basp\b|selling price|unit price|input cost",
     r"인상|인하|상승|하락|급등|급락|증가|감소|전가|협상|상향|하향|rais|cut|rise|fall|increas|decreas|negotiat"),
    ("earnings_or_guidance", ("earnings",),
     r"매출|영업이익|순이익|마진|실적|가이던스|출하|판매(?:량|실적|는|가)|시장점유율|revenue|earnings|profit|guidance|shipments",
     r"증가|감소|상승|하락|상회|하회|상향|하향|달성|기록|집계|발표|전망|예상|rise|fall|grow|cut|rais|report|forecast|beat|miss"),
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
     r"투자(?=\s*(?:\d|를|한다|한다고|하는|하고|해|했다|할|하겠|금|액|규모|계획|협약|계약|자금|라운드)|.{0,12}유치)|전략투자|capex|자본지출|(?<!대)출자|자금\s*조달|자본\s*조달|회사채|주주환원|배당|자사주|자기주식|지분|funding|financing|buyback|dividend|bond issuance|stake",
     r"체결|유치|출자|발행|증액|삭감|확대|축소|매입|매수|취득|소각|매각|인수|검토|추진|결정|발표|승인|투입|금융\s*종결|납입|집행|투자\s*라운드.{0,10}참여|raise|issu|buy|repurchas|sell|acquir|announc|consider|approv|financing closed|funding disbursed"),
    ("financing_infrastructure", ("earnings", "timeline"),
     r"금융플랫폼|금융\s*플랫폼|투자\s*자금\s*조달|financing platform|investment financing",
     r"구축|설립|출범|조성|지원|build|establish|launch|support"),
    ("convertible_ownership_rights", ("flows", "timeline"),
     r"전환사채|\bcb\b|convertible bond|의결권|voting rights", r"전환|승인|확보|convert|approv|secur"),
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
    ("operating_asset_transaction", ("earnings", "timeline"),
     r"(?:사옥|부동산|사업부|영업자산).{0,20}(?:매각|취득|매입)|operating asset|headquarters sale",
     r"결정|확정|검토|추진|계약|매각했다|매입했다|decid|consider|contract|sold|acquir"),
    ("institutional_capital_access", ("earnings", "timeline"),
     r"국민연금|연기금|벤처캐피털|\bvc\b|pension fund|venture capital",
     r"투자\s*기회.{0,8}(?:확대|넓)|출자|투자협력|투자.{0,20}(?:협력|논의)|funding|investment opportunities|commitment"),
    ("market_infrastructure", ("timeline",),
     r"증권계좌|거래시스템|결제망|증권거래소|오픈뱅킹|증권 거래|brokerage account|trading system|payment network",
     r"연결|도입|출시|가동|개편|허용|launch|deploy|connect|reform"),
    ("model_operating_specification", ("earnings", "timeline"),
     r"모델|llm|ai model|language model|솔라 미니|gpu|npu",
     r"(?:gpu|npu|가속기)\s*(?:\d+|한|두|세)\s*(?:장|개)|\d+\s*(?:장|개)의?\s*(?:gpu|npu)|(?:메모리|전력|지연시간|추론비용|운용비용|토큰량|토큰\s*처리량).{0,25}\d+(?:\.\d+)?\s*(?:%|gb|w|배)|\d+(?:\.\d+)?\s*(?:배|%)\s*(?:빠르|절감|줄|감소)"),
    ("industrial_architecture_adoption", ("earnings", "timeline"),
     r"hvdc|\bvdc\b|\bcpo\b|광트랜시버|광\s*인터커넥트|파운데이션\s*모델|foundation model|co.packaged optics",
     r"규격|채택|통합|전환|도입|standard|specification|adopt|integrat|deploy"),
    ("industrial_partnership_execution", ("earnings", "timeline"),
     r"풍력|태양광|발전소|반도체|데이터센터|휴머노이드|자율주행|무인기|항공우주|wind power|solar|power plant|semiconductor|data center|humanoid|autonomous driving|drone|aerospace",
     r"(?:업무협약|공동개발\s*협약|MOU).{0,20}(?:체결|맺|서명)|(?:체결|맺|서명).{0,20}(?:업무협약|공동개발\s*협약|MOU)|signed.{0,30}(?:mou|joint development)"),
    ("rates_fx_or_macro", ("discount_rate",),
     r"금리|국고채|모기지|주담대|주택담보대출|물가|인플레이션|고용|건설지출|환율|달러화|유동성|차입|구매관리자|\bpmi\b|cpi|pce|payroll|mortgage|interest rate|treasury|inflation|exchange rate|borrowing",
     r"인상|(?<!할)인하|동결|상승|하락|오른|내린|올랐|내렸|둔화|급등|급락|상회|하회|밑돌|웃돌|발표|기록|증가|감소|결정|약세|강세|최고|치솟|cut|hike|hold|rise|fall|miss|beat|announc|estimat|record"),
    ("policy_scope_or_stage", ("timeline",),
     r"관세|법인세|세율|세금|수출통제|수출.{0,12}(?:금지|제한)|수입금지|수입 금지|수입 제한|수입제한|과잉생산.{0,20}(?:대응|조치)|제재|보조금|지원금|예탁금|긴급조치권|규제|인허가|허가\s*절차|고시|조례|환경심사|환경영향평가|주파수|tariff|tax rate|corporate tax|export control|import ban|sanction|subsid|licens|environmental review|spectrum|\bban(?:s|ned)?\b",
     r"제안|검토|추진|인상|인하|올리|올렸|상향|하향|완화|강화|시행|발효|금지|제한|허가|승인|제정|개정|철회|의견수렴|입법예고|면제|배정|의결|착수|발표|propos|draft|\bban(?:s|ned)?\b|prohibit|restrict|approv|enact|implement|consider|exempt|allocat|adopt"),
    ("environmental_approval", ("timeline",),
     r"최종\s*환경평가|FONSI|환경영향평가서", r"완료|결정을\s*내렸|작성\s*없이|면제"),
    ("export_control_scope", ("earnings", "timeline"),
     r"country group|trade authorization|export administration|수출관리규정|수출허가",
     r"remov|add|available|amend|change|변경|제외|허용"),
    ("public_program_cost_study", ("timeline",),
     r"방위사업|국방예산|방위예산|조달예산|missile defense|defense budget|procurement budget",
     r"추산|심의|추정|예산안|cost estimate|cost study|budget proposal"),
    ("market_price_or_flow", (),
     r"주가|증시|코스피|코스닥|etf|etn|순매수|순매도|거래대금|유입|유출|수익률|주식|shares|stocks|equities|inflows|outflows",
     r"급등|급락|상승|하락|순매수|순매도|유입|유출|이동|상장|편입|편출|증가|감소|surge|slump|rise|fall|inflows|outflows|list|rebalance"),
    ("physical_supply_or_capacity", ("earnings", "timeline"),
     r"공장|생산(?!자)|설비|공급|수요|재고|수율|리드타임|부족|품귀|항만|물류|운송|데이터센터|AI\s*팩토리|factory|production|supply|demand|inventory|lead time|port|freight|data cent(?:er|re)",
     r"증설|착공|가동|증가|감소|중단|차질|부족|품귀|지연|연장|매각|검토|확대|축소|상용화|구축|건설\s*(?:하|할|을|에|계획|계약|추진)|신설|짓고|짓는다|도입|생산할|늘고|늘었|expand|start|halt|disrupt|shortage|delay|consider|launch|build|deploy"),
    ("sector_demand_outlook", ("earnings",),
     r"반도체|메모리|데이터센터|출하량|semiconductor|memory|data center|shipments", r"호황|불황|수요.{0,20}(?:전망|늘|줄)|boom|bust|demand outlook"),
    ("market_outlook", (),
     r"코스피|코스닥|증시|주식시장|kospi|kosdaq|stock market", r"오를|내릴|상승할|하락할|상승\s*전망|하락\s*전망|forecast|outlook"),
    ("fund_assets_level", (),
     r"펀드.{0,40}순자산|순자산.{0,30}펀드|fund.{0,30}(?:net assets|aum)", r"돌파|증가|감소|exceed|increas|decreas"),
    ("technology_or_clinical_stage", ("earnings", "timeline"),
     r"메모리|반도체|hbm|hbf|cxl|칩|공정|로봇|신약|임상|fda|의약품|기술|양자|극저온|memory|semiconductor|chip|clinical|drug|technology|quantum|cryogenic",
     r"양산|상용화|인증|승인|허가|임상\s*[1-3]상.{0,15}결과|임상 결과|임상결과|공급|도입|검증|성능|대역폭|수율|전력효율|결과 발표|생산|production|commercial|certif|approv|deploy|validat|performance|bandwidth|yield"),
    ("space_execution_stage", ("timeline",),
     r"위성|궤도|satellite|orbital", r"시험|검증|발사.{0,15}(?:완료|성공)|prototype|orbital test|launch.{0,20}(?:complet|success)"),
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
     r"공격|공습|피격|발사체|화재|휴전|협상|통항|봉쇄|제재|상승|하락|오른|내린|급등|급락|차질|감산|증산|합의|경고|명령|배치|발표|attack|strike|ceasefire|talks|blockade|sanction|rise|fall|disrupt|output|warn|deploy|announc"),
    ("climate_operational_damage", ("earnings", "timeline"),
     r"폭염|폭우|홍수|태풍|정전|가뭄|산불|heatwave|flood|outage|drought|wildfire",
     r"전력|변압기|과부하|폐사|양식|농작물|생산|공급|항만|물류|공장|피해|사망|power|transformer|crop|production|supply|port|factory|damage|death"),
    ("labor_cost_or_execution", ("earnings", "timeline"),
     r"파업|노조|성과급|임단협|(?<!금)감원|(?:인력|인원|일자리).{0,20}감축|임금|strike|union|layoff|wage",
     r"생산|공장|운송|항만|비용|인상|교섭|협상|부결|타결|주식|지급|중단|감축|production|factory|port|cost|talks|shares|halt|cut"),
    ("customer_discussions", ("earnings", "timeline"),
     r"공급|고객|구매|생산|공동개발|공동 개발|인증|hbm|파운드리|자율주행|데이터센터|ai.{0,4}(?:반도체|인프라)|supply|customer|procurement|co-develop|foundry|autonomous|data center",
     r"협상|논의|검토|회동|협력(?!사)|합의|협약|negotiat|discuss|consider|meeting|collaborat|agreement"),
)
COMPILED_RULES = tuple(
    (kind, axes, re.compile(subject, re.I), re.compile(action, re.I))
    for kind, axes, subject, action in RULES
)


def evidence_is_new_event(kind: str, sentence: str) -> bool:
    """Do not promote service descriptions or event support into transactions."""
    if re.search(r"체험해\s*보고|미리\s*체험|솔루션.{0,30}(?:탐색|찾아볼|검색)|카탈로그.{0,30}(?:분류|제공)", sentence) and not re.search(
        r"(?:공급|납품)\s*계약.{0,20}체결|수주했다|(?:성능|전력|비용).{0,20}\d+(?:\.\d+)?%", sentence,
    ):
        return False
    if kind == "capital_listing_stage" and "ETF" in sentence.upper() and not re.search(r"기업공개|\bipo\b", sentence, re.I):
        return bool(re.search(r"(?:ETF.{0,80}(?:출시|상장)|(?:출시|상장).{0,80}ETF)", sentence, re.I))
    if re.search(r"논의해\s*나가겠다|해소될\s*수\s*있도록|최선을\s*다하겠다", sentence) and not re.search(
        r"고시.{0,12}개정|법안.{0,12}(?:발의|제출)|계약.{0,12}체결|시행일.{0,15}확정", sentence,
    ):
        return False
    if kind == "commercial_order":
        return bool(re.search(
            r"체결|확정|수주(?:했다|했다고|한|하며|했으며|에\s*성공)|발주(?:했다|하기로)|갱신|취소|파기|해지|협상|서명|"
            r"(?:수주|발주).{0,20}(?:금액|규모|억\s*원|조\s*원)|sign|secur|award|agree|cancel|negotiat", sentence, re.I,
        ))
    if kind == "corporate_transaction":
        return bool(re.search(
            r"(?:인수|합병)(?:했다|한다고|한다|하기로|한|를\s*(?:검토|추진|협상|결정))|"
            r"(?:인수|합병).{0,30}(?:계약|대금|금액|협상|검토\s*중|합의|발표|완료)|"
            r"(?:acquir|merg).{0,35}(?:announc|agree|complete|consider|negotiat)|acquired|acquisition of", sentence, re.I,
        ))
    if kind == "capital_or_shareholder_action":
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
    if kind == "market_infrastructure" and re.search(r"연결돼\s*있|연결되어\s*있|기반으로\s*작동", sentence):
        return bool(re.search(r"새로|처음|신규|도입했다|가동했다|출시했다", sentence))
    if kind == "technology_or_clinical_stage" and re.search(r"기대한다|기대된다|역량을|전문성을|소개하는\s*계기|학회.{0,20}(?:선정|채택)", sentence):
        return bool(re.search(r"임상\s*[1-3]상|\d+(?:\.\d+)?\s*(?:%|배|mK|dB)|인증\s*(?:획득|취득)|허가\s*(?:신청|승인)", sentence, re.I))
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
    if kind == "market_price_or_flow" and re.search(r"투자할\s*수|투자가\s*가능|추종하는", sentence) and not re.search(
        r"순매수|순매도|유입|유출|거래대금|수익률|주가.{0,20}\d", sentence,
    ):
        return False
    if kind == "market_price_or_flow" and re.search(r"유의할|주의할|유의해야|주의해야|변동성.{0,15}(?:지적|유의)", sentence):
        return False
    if kind == "energy_geopolitics_or_supply_risk":
        without_quotes = re.sub(r"(?:S-?Oil|SK이노베이션)\s*\([^)]*\)", "", sentence, flags=re.I)
        if not re.search(ENERGY_SUBJECT, without_quotes, re.I):
            return False
    return True


def news_value_rank(evidence: list[dict]) -> int:
    """Economic mechanism outranks textual focus and announcement certainty."""
    kinds = {item["kind"] for item in evidence}
    if kinds & {"commercial_order", "order_backlog_level", "customer_supply_start", "procurement_execution_stage", "selling_price_or_cost",
                "earnings_or_guidance", "export_results", "licensing_cashflow", "corporate_transaction", "corporate_ownership_execution", "export_control_scope",
                "policy_scope_or_stage", "environmental_approval", "industrial_architecture_adoption", "physical_supply_or_capacity",
                "launch_turnaround_bottleneck", "sector_demand_outlook"}:
        return 4
    if kinds & {"technology_or_clinical_stage", "space_execution_stage", "space_thermal_validation",
                "cryogenic_propellant_storage", "biology_research_discovery", "research_validation_result", "model_operating_specification",
                "customer_discussions", "industrial_partnership_execution", "corporate_action_clarification", "capital_or_shareholder_action", "capital_listing_stage",
                "customer_financing_commitment", "public_program_cost_study", "energy_geopolitics_or_supply_risk"}:
        return 3
    return 2


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
                if value := paragraph[start:boundary.start()].strip():
                    sentences.append(value)
                start = boundary.end()
        if value := paragraph[start:].strip():
            sentences.append(value)
    return sentences


def assess(title: str, body: str) -> dict:
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    body = str(body or "").strip()
    result = {"version": VERSION, "disposition": "review", "priority": 1, "axes": [], "evidence": []}
    if not title or not body:
        result["reason"] = "source_evidence_unavailable"
        return result
    if re.search(r"따라\s*투자하면|투자하면\s*돈\s*벌까|경제\s*용어|투자\s*방법", title) and not DIRECT_HEADLINE_CHANGE.search(title):
        result.update(disposition="exclude", priority=0, reason="investment_method_explainer_not_new_market_event")
        return result
    if re.search(r"보안인증|보안\s*인증|CSAP|ISMS", title, re.I) and re.search(r"획득|취득", title) and not re.search(
        r"(?:신규\s*고객|공급\s*계약|납품\s*계약|수주).{0,25}(?:체결|확정|확보|획득)|"
        r"(?:매출|영업이익|순이익|자금조달).{0,25}(?:증가|상향|확정|유치)|supply contract signed", body, re.I,
    ):
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
    electoral = bool(re.search(r"유세|선거운동|지지\s*(?:호소|결집)|campaign rally|election campaign", title, re.I))
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
    if OFFICE_PUBLICITY.search(headline_lead) and not OFFICE_ECONOMIC_CHANGE.search(headline_lead):
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
    for index, sentence in enumerate(sentences):
        if PHOTO_DESCRIPTION.search(sentence):
            continue
        if BACKGROUND.search(sentence) or re.match(r"^한편[,\s]", sentence) or not period_matches(title, sentence):
            continue
        if re.search(r"\d+\s*년간.{0,20}(?:이어온|추진해\s*온|투자유치\s*노력)|(?:이어온|쌓아온).{0,12}투자유치\s*노력", sentence) and not QUANTITY.search(sentence):
            continue
        if re.search(r"추가매수를\s*고려하고\s*있었다면|투자자라면|투자금을\s*준비하는\s*방법|기회를\s*잡으려", sentence):
            continue
        # A numeric company profile or another topic later in the article must
        # not turn today's ceremonial/promotion headline into a market event.
        anchored = any(token in sentence.lower() for token in tokens)
        adjacent = index > 0 and any(token in sentences[index - 1].lower() for token in tokens)
        if (focus_kind(title) or DENIAL_HEADLINE.search(title)) and not focus_matches(title, sentence):
            continue
        for kind, axes, subject, action in COMPILED_RULES:
            if not subject.search(sentence) or not action.search(sentence):
                continue
            if not evidence_is_new_event(kind, sentence):
                continue
            if kind == "export_results" and not QUANTITY.search(sentence):
                continue
            # Campaign rhetoric and retrospective blame are not new macro data.
            # A concrete policy proposal or current escalation remains eligible.
            if electoral and kind not in {"policy_scope_or_stage", "export_control_scope", "energy_geopolitics_or_supply_risk"}:
                continue
            if not anchored and not adjacent and not focus_kind(title) and not subject.search(title):
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
            if kind == "market_price_or_flow" and not re.search(
                r"주가|증시|코스피|코스닥|etf|etn|순매수|순매도|거래대금|수익률|주식|자금|자본|투자금|shares|stocks|equities|capital|fund flows", sentence, re.I,
            ):
                continue
            if kind == "market_price_or_flow" and re.search(r"ETF.{0,80}(?:상장|출시)", sentence, re.I) and not re.search(
                r"순매수|순매도|유입|유출|거래대금|주가|수익률|올랐|내렸|상승|하락", sentence,
            ):
                continue
            if kind == "earnings_or_guidance" and not re.search(
                r"매출|영업(?:이익|익)|순(?:이익|익)|마진|가이던스|출하|판매(?:량|실적|는|가)|시장점유율|주당순이익|"
                r"실적.{0,20}(?:어닝|상회|하회|흑자|적자)|\beps\b|revenue|earnings|profit|guidance|shipments", sentence, re.I,
            ):
                continue
            if kind == "labor_cost_or_execution" and not re.search(
                r"파업|임단협|단체협약|임금.{0,25}(?:인상|인하|교섭|협상|부결|타결)|성과급.{0,25}(?:주식|지급|변경)|"
                r"(?<!금)감원|(?:인력|인원|일자리).{0,20}감축|(?:생산|공장|운송|항만).{0,25}(?:중단|차질)|"
                r"strike|layoff|wage.{0,20}(?:talk|rais|cut)|(?:worker|job|labor|labour).{0,20}(?:cut|reduc)", sentence, re.I,
            ):
                continue
            if kind == "physical_supply_or_capacity":
                if re.search(r"공공서비스.{0,12}확대|(?:쉼터|라운지).{0,20}(?:개방|개관|확대)", sentence):
                    continue
                if re.search(r"(?:가동|공급|생산).{0,8}중단을?\s*(?:방지|막|예방)|prevent.{0,25}(?:outage|shutdown)", sentence, re.I):
                    continue
                if not re.search(
                    r"공장|생산|설비|공급|리드타임|품귀|항만|물류|운송|반도체|메모리|기판|전력|원유|원자재|데이터센터|AI\s*팩토리|광통신|광인터커넥트|네트워크|"
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
            if kind == "climate_operational_damage" and not re.search(
                r"정전|과부하|폐사|사망|침수|소실|피해|차질|중단|손실|outage|overload|death|damage|disrupt|halt|loss", sentence, re.I,
            ):
                continue
            if kind == "research_spending_change" and not QUANTITY.search(sentence):
                continue
            early = bool(EARLY_SIGNAL.search(sentence)) or kind in {"customer_discussions", "institutional_capital_access"}
            if kind == "capital_listing_stage" and re.search(r"오는\s*\d{1,2}일|출시한다고|출시할|상장할", sentence):
                early = True
            priority = 2 if early or kind in {"technology_or_clinical_stage", "research_validation_result", "market_infrastructure", "model_operating_specification", "industrial_architecture_adoption", "space_execution_stage", "space_thermal_validation", "cryogenic_propellant_storage", "biology_research_discovery", "public_program_cost_study", "sector_demand_outlook", "market_outlook", "fund_assets_level", "financing_infrastructure"} else 3
            if kind == "capital_listing_stage":
                priority = 3
            if kind in {"earnings_or_guidance", "market_price_or_flow"} and not QUANTITY.search(sentence):
                priority = 2
            if kind == "research_spending_change":
                priority = 2
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
                listing = bool(re.search(r"etf|etn", sentence, re.I) and re.search(r"상장|list", sentence, re.I))
                priority = 2 if focus_kind(title) == "breadth" or listing else 1
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
        if re.search(r"포럼|패널토론|forum|panel discussion", headline_lead, re.I) and kinds <= {"policy_scope_or_stage", "customer_discussions", "financing_infrastructure", "market_infrastructure"} and not re.search(
            r"(?:정부|금융위|국세청|국회|장관|부처).{0,80}(?:입법예고했다|발의했다|개정한다|시행한다|시행하기로\s*결정|공포했다)", body,
        ):
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
    return result
