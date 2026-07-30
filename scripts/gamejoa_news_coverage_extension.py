"""Coverage extensions for decision-relevant Korean market news."""

PUBLISHER_DOMAINS = {
    "newsis.com": "뉴시스", "chosun.com": "조선일보", "biz.chosun.com": "조선비즈",
    "wowtv.co.kr": "한국경제TV", "kmib.co.kr": "국민일보", "zdnet.co.kr": "지디넷코리아",
    "techm.kr": "테크M", "investchosun.com": "인베스트조선", "inews24.com": "아이뉴스24",
    "metroseoul.co.kr": "메트로신문", "seoul.co.kr": "서울신문",
}

SEARCH_SOURCES = [
    ("국내 기업 실적·장기계약·자본조달", "(실적 OR 영업이익 OR 순이익 OR 컨콜 OR LTA OR 장기공급계약 OR 유상증자 OR 자사주 OR 소각) (반도체 OR HBM OR MLCC OR 데이터센터 OR AI OR 금융 OR 증권) (site:newsis.com OR site:etnews.com OR site:edaily.co.kr OR site:fnnews.com OR site:inews24.com OR site:investchosun.com OR site:biz.heraldcorp.com)"),
    ("국내 증시 중단·레버리지 위험", "(사이드카 OR 서킷브레이커 OR 신용융자 OR 레버리지ETF OR 레버리지 ETF OR 투자한도 OR 괴리율 OR 기본예탁금) (발동 OR 규제 OR 제한 OR 손실 OR 상향 OR 시행) (site:newsis.com OR site:fnnews.com OR site:mt.co.kr OR site:hankyung.com OR site:yonhapnewstv.co.kr OR site:kmib.co.kr)"),
    ("반도체 공급망·공장 중단·차세대 메모리", "(TSMC OR JASM OR 구마모토 OR 지진 OR 강진 OR 공장중단 OR 공장 중단 OR 액체냉각 OR MLCC OR LPDDR6 OR HBM5 OR HBM 5 OR iHBM OR CXMT) (중단 OR 대피 OR 인증 OR 계약 OR 공급 OR 양산 OR 개발 OR 증설 OR 가격) (site:edaily.co.kr OR site:etoday.co.kr OR site:fnnews.com OR site:inews24.com OR site:seoul.co.kr OR site:biz.heraldcorp.com OR site:wowtv.co.kr)"),
    ("금리·국채·환율 충격", "(미국채10년물 OR 미국채 10년물 OR FOMC OR 기준금리 OR 금리인상 OR 금리 인상 OR 원달러 OR 원·달러 OR 엔화) (최고 OR 최저 OR 인상 OR 동결 OR 급등 OR 급락 OR 확률) (site:yna.co.kr OR site:newsis.com OR site:news1.kr OR site:edaily.co.kr)"),
    ("미국 수입제한·수출통제·로봇 정책", "(FCC OR 미국 상무부 OR 백악관 OR 트럼프) (수입금지 OR 수입 금지 OR 수입제한 OR 수입 제한 OR 수출통제 OR 관세 OR 제재) (로봇 OR 휴머노이드 OR 반도체 OR 인버터 OR 통신장비 OR 핵심광물) (site:dt.co.kr OR site:yna.co.kr OR site:newsis.com OR site:etoday.co.kr)"),
    ("AI 순환금융·대형 금융지원", "(엔비디아 OR 오픈AI OR 마이크로소프트 OR 메타 OR 구글 OR 아마존) (순환금융 OR 순환투자 OR 금융지원 OR 금융보증 OR 보증 OR 장기구매) (AI OR 데이터센터 OR HBM OR 반도체) (site:asiae.co.kr OR site:mt.co.kr OR site:wowtv.co.kr OR site:techm.kr OR site:chosun.com OR site:hankyung.com)"),
]

TRUSTED_MARKERS = tuple(v for d, p in PUBLISHER_DOMAINS.items() for v in (d, p))
PRIORITY_TERMS = {
    "유상증자": 14, "자사주 소각": 14, "자기주식 소각": 14, "lta": 15,
    "장기공급계약": 15, "장기 공급계약": 15, "사이드카": 16, "서킷브레이커": 18,
    "신용융자": 12, "투자한도": 14, "괴리율": 11, "공장 중단": 16,
    "공장중단": 16, "강진": 15, "지진": 13, "미국채": 15, "금리 인상": 15,
    "액체냉각": 13, "mlcc": 13, "lpddr6": 14, "hbm5": 15, "hbm 5": 15,
    "ihbm": 15, "순환금융": 15, "순환투자": 15, "금융보증": 14,
    "수입 금지": 16, "수입금지": 16, "수입 제한": 16, "수입제한": 16,
}
MATERIAL_TERMS = tuple(PRIORITY_TERMS)
IMPACT_TERMS = {
    "돈 버는 능력": ("장기공급계약", "lta", "금융지원", "금융보증", "순환금융", "순환투자", "공장 중단", "공장중단", "강진", "지진", "액체냉각", "mlcc", "lpddr6", "hbm5", "hbm 5", "ihbm"),
    "할인율": ("미국채", "수입 금지", "수입금지", "수입 제한", "수입제한"),
    "수급": ("사이드카", "서킷브레이커", "신용융자", "투자한도", "괴리율"),
    "시간표": ("공장 중단", "공장중단", "대피", "복구", "lta", "장기공급계약"),
}


def extend_unique(target, values):
    for value in values:
        if value not in target:
            target.append(value)


def apply_source_extensions(domains, searches, trusted):
    domains.update(PUBLISHER_DOMAINS)
    extend_unique(searches, SEARCH_SOURCES)
    extend_unique(trusted, TRUSTED_MARKERS)


def apply_term_extensions(priority, material, impacts):
    priority.update(PRIORITY_TERMS)
    extend_unique(material, MATERIAL_TERMS)
    for label, terms in IMPACT_TERMS.items():
        impacts.setdefault(label, [])
        extend_unique(impacts[label], terms)


def semantic_theme(alert, text):
    event_date = str(alert.get("published") or "")[:10]
    companies = (("삼성전기", ("삼성전기",)), ("삼성전자", ("삼성전자",)), ("SK하이닉스", ("sk하이닉스", "하이닉스")), ("NAVER", ("naver", "네이버")), ("엔비디아", ("엔비디아", "nvidia")), ("TSMC", ("tsmc", "jasm")))
    events = (("mlcc_lta", ("mlcc", "장기공급계약", "장기계약", "lta")), ("memory_lta", ("hbm", "메모리", "장기공급계약", "장기계약", "lta")), ("earnings", ("실적", "영업이익", "영업익", "순이익")), ("capital_raise", ("유상증자", "제3자배정", "3자배정")), ("factory_disruption", ("공장 중단", "공장중단", "대피", "강진", "지진")))
    for company, aliases in companies:
        if not any(alias in text for alias in aliases):
            continue
        for event, terms in events:
            hits = sum(term in text for term in terms)
            if hits >= (2 if event in {"mlcc_lta", "memory_lta"} else 1):
                return f"korean_business:{company}:{event}:{event_date}"
    return ""
