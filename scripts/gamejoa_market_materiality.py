#!/usr/bin/env python3
"""Source-only materiality evidence, without issuer lists or confirmed-only gates."""

from __future__ import annotations

import re


VERSION = 1
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
    r"volunteer|charity|brand award|giveaway|ceremonial", re.I,
)
HARD_HEADLINE = re.compile(
    r"매출|이익|실적|가이던스|판가|가격|수주|계약|발주|공장|양산|증설|가동|"
    r"상용화|상장|투자유치|투자 유치|출자|자금조달|자사주|주식 매수|주주환원|주식 기부|지분 이전|"
    r"관세|금리|환율|예탁금|순매수|순매도|수출통제|임상|허가|공급부족|코스피|코스닥|증시|"
    r"earnings|guidance|contract|factory|production|tariff|interest rate|buyback", re.I,
)

# Each rule needs a subject and a change in the same source-authored sentence.
# Quantities, counterparties and stages are evidence, not estimates of price impact.
RULES = (
    ("earnings_or_guidance", ("earnings",),
     r"매출|영업이익|순이익|마진|실적|가이던스|출하|판매량|시장점유율|revenue|earnings|profit|guidance|shipments",
     r"증가|감소|상승|하락|상회|하회|상향|하향|달성|기록|집계|발표|전망|예상|rise|fall|grow|cut|rais|report|forecast|beat|miss"),
    ("capital_or_shareholder_action", ("earnings", "timeline"),
     r"투자.{0,12}유치|출자|자금조달|자본조달|회사채|주주환원|배당|자사주|자기주식|지분|funding|financing|buyback|dividend|bond issuance|stake",
     r"체결|유치|출자|발행|증액|삭감|확대|축소|매입|매수|취득|소각|매각|인수|검토|추진|결정|발표|raise|issu|buy|repurchas|sell|acquir|announc|consider"),
    ("insider_disclosed_trade", ("flows",),
     r"(?:회장|대표|사장|임원|ceo|executive).{0,80}(?:주식|지분|shares|stake)",
     r"매수|매입|취득|매도|처분|buy|purchas|sell|disclos"),
    ("ownership_transfer", ("flows", "timeline"),
     r"주식|지분|shares|stake", r"기부|이전|증여|donat|transfer"),
    ("institutional_capital_access", ("earnings", "timeline"),
     r"국민연금|연기금|벤처캐피털|\bvc\b|pension fund|venture capital",
     r"투자\s*기회.{0,8}(?:확대|넓)|출자|투자협력|투자 협력|funding|investment opportunities|commitment"),
    ("market_infrastructure", ("timeline",),
     r"증권계좌|거래시스템|결제망|증권거래소|오픈뱅킹|증권 거래|brokerage account|trading system|payment network",
     r"연결|도입|출시|가동|개편|허용|launch|deploy|connect|reform"),
    ("model_operating_specification", ("earnings", "timeline"),
     r"모델|llm|ai model|language model|솔라 미니|gpu|npu",
     r"(?:gpu|npu|가속기)\s*(?:\d+|한|두|세)\s*(?:장|개)|\d+\s*(?:장|개)의?\s*(?:gpu|npu)|(?:메모리|전력|지연시간|추론비용|운용비용).{0,15}\d+(?:\.\d+)?\s*(?:%|gb|w|배)|\d+(?:\.\d+)?\s*(?:배|%)\s*(?:빠르|절감|줄|감소)"),
    ("rates_fx_or_macro", ("discount_rate",),
     r"기준금리|국채금리|국고채|물가|인플레이션|고용|환율|달러화|유동성|차입|cpi|pce|payroll|interest rate|treasury|inflation|exchange rate|borrowing",
     r"인상|인하|동결|상승|하락|둔화|급등|급락|상회|하회|발표|증가|감소|결정|약세|강세|cut|hike|hold|rise|fall|miss|beat|announc|estimat"),
    ("policy_scope_or_stage", ("timeline",),
     r"관세|수출통제|수출금지|수입금지|수입 금지|수입 제한|수입제한|제재|보조금|지원금|예탁금|규제|인허가|조례|tariff|export control|import ban|sanction|subsid|licens|\bban(?:s|ned)?\b",
     r"제안|검토|추진|인상|인하|완화|강화|시행|발효|금지|제한|허가|승인|제정|철회|의견수렴|입법예고|propos|draft|\bban(?:s|ned)?\b|prohibit|restrict|approv|enact|implement|consider"),
    ("market_price_or_flow", (),
     r"주가|증시|코스피|코스닥|etf|etn|순매수|순매도|거래대금|유입|유출|수익률|주식|shares|stocks|equities|inflows|outflows",
     r"급등|급락|상승|하락|순매수|순매도|유입|유출|이동|상장|편입|편출|증가|감소|surge|slump|rise|fall|inflows|outflows|list|rebalance"),
    ("physical_supply_or_capacity", ("earnings", "timeline"),
     r"공장|생산|설비|공급|수요|재고|수율|리드타임|부족|품귀|항만|물류|운송|factory|production|supply|demand|inventory|lead time|port|freight",
     r"증설|착공|가동|증가|감소|중단|차질|부족|품귀|지연|연장|매각|검토|확대|축소|상용화|expand|start|halt|disrupt|shortage|delay|consider|launch"),
    ("technology_or_clinical_stage", ("earnings", "timeline"),
     r"메모리|반도체|hbm|hbf|cxl|칩|공정|로봇|신약|임상|fda|의약품|기술|memory|semiconductor|chip|clinical|drug|technology",
     r"양산|상용화|인증|승인|허가|임상 결과|임상결과|공급|도입|검증|성능|대역폭|수율|전력효율|결과 발표|생산|production|commercial|certif|approv|deploy|validat|performance|bandwidth|yield"),
    ("energy_geopolitics_or_supply_risk", ("earnings", "discount_rate"),
     r"원유|유가|천연가스|운임|호르무즈|홍해|이란|이스라엘|우크라이나|러시아|구리|리튬|\boil\b|brent|wti|\bgas\b|hormuz|iran|ukraine|russia|copper|lithium",
     r"공격|공습|휴전|협상|통항|봉쇄|제재|상승|하락|급등|급락|차질|감산|증산|합의|attack|strike|ceasefire|talks|blockade|sanction|rise|fall|disrupt|output"),
    ("climate_operational_damage", ("earnings", "timeline"),
     r"폭염|폭우|홍수|태풍|정전|가뭄|산불|heatwave|flood|outage|drought|wildfire",
     r"전력|변압기|과부하|폐사|양식|농작물|생산|공급|항만|물류|공장|피해|사망|power|transformer|crop|production|supply|port|factory|damage|death"),
    ("labor_cost_or_execution", ("earnings", "timeline"),
     r"파업|노조|성과급|임단협|감원|감축|임금|strike|union|layoff|wage",
     r"생산|공장|운송|항만|비용|인상|교섭|협상|주식|지급|중단|감축|production|factory|port|cost|talks|shares|halt|cut"),
    ("customer_discussions", ("earnings", "timeline"),
     r"공급|고객|구매|생산|공동개발|공동 개발|인증|hbm|파운드리|자율주행|데이터센터|ai.{0,4}(?:반도체|인프라)|supply|customer|procurement|co-develop|foundry|autonomous|data center",
     r"협상|논의|검토|회동|협력|합의|negotiat|discuss|consider|meeting|collaborat|agreement"),
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
    sentences = [part.strip() for part in re.split(r"(?<!\d)[.!?。](?!\d)\s*|[\r\n]+", body) if part.strip()]
    generic_tokens = {"기업", "대표", "회장", "공개", "협력", "강화", "발표", "미래", "신제품", "출시", "회동", "계획"}
    tokens = [word for word in re.findall(r"[A-Za-z0-9가-힣]+", title.lower()) if len(word) >= 2 and word not in generic_tokens]
    routine = bool(ROUTINE_HEADLINE.search(title) and not HARD_HEADLINE.search(title))
    soft = bool(SOFT_HEADLINE.search(title) and not HARD_HEADLINE.search(title))
    for index, sentence in enumerate(sentences):
        if BACKGROUND.search(sentence):
            continue
        # A numeric company profile or another topic later in the article must
        # not turn today's ceremonial/promotion headline into a market event.
        anchored = any(token in sentence.lower() for token in tokens)
        adjacent = index > 0 and any(token in sentences[index - 1].lower() for token in tokens)
        if (routine or soft) and not anchored and not adjacent:
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
            if kind == "technology_or_clinical_stage" and not re.search(
                r"양산|상용화|인증|승인|허가|임상|공급|도입|검증|성능|대역폭|수율|전력효율|production|commercial|approv|deploy|performance|bandwidth|yield", sentence, re.I,
            ):
                continue
            if kind == "model_operating_specification" and not re.search(
                r"구동|동작|실행|추론|운용|가동|배포|메모리|전력|지연시간|추론비용|운용비용|running|inference|deploy|memory|power|latency|cost", sentence, re.I,
            ):
                continue
            early = bool(EARLY_SIGNAL.search(sentence)) or kind in {"customer_discussions", "institutional_capital_access"}
            priority = 2 if early or kind in {"technology_or_clinical_stage", "market_infrastructure", "model_operating_specification"} else 3
            if kind in {"earnings_or_guidance", "market_price_or_flow"} and not QUANTITY.search(sentence):
                priority = 2
            result["priority"] = max(result["priority"], priority)
            evidence_axes = list(axes)
            if kind in {"capital_or_shareholder_action", "market_price_or_flow"} and re.search(
                r"자사주|자기주식|배당|순매수|순매도|유입|유출|거래대금|편입|편출|매수|매도|buyback|dividend|inflows|outflows|rebalance", sentence, re.I,
            ):
                evidence_axes.append("flows")
            if kind == "policy_scope_or_stage" and re.search(
                r"관세|수출|수입|보조금|지원금|비용|생산|공급|tariff|export|import|subsid|cost|production|supply", sentence, re.I,
            ):
                evidence_axes.append("earnings")
            result["axes"] = list(dict.fromkeys(result["axes"] + evidence_axes))
            if len(result["evidence"]) < 4 and not any(item["kind"] == kind for item in result["evidence"]):
                result["evidence"].append({"kind": kind, "stage": "early_signal" if early else "reported_change", "source_excerpt": sentence})
    if result["evidence"]:
        result.update(disposition="keep", reason="source_change_evidence")
        if HEADLINE_EARLY.search(title):
            result["priority"] = min(result["priority"], 2)
            result["headline_stage"] = "early_signal"
    elif routine or soft:
        result.update(disposition="exclude", priority=0, reason="routine_or_vague_without_market_change")
    else:
        # This is a refinement of the existing broad market gate, not a new
        # universal whitelist. Unrecognised events still face that gate.
        result["reason"] = "existing_market_gate_required"
    return result
