"""Coverage extensions for decision-relevant Korean market news."""

PUBLISHER_DOMAINS = {
    "newsis.com": "뉴시스",
    "chosun.com": "조선일보",
    "biz.chosun.com": "조선비즈",
    "wowtv.co.kr": "한국경제TV",
    "kmib.co.kr": "국민일보",
    "zdnet.co.kr": "지디넷코리아",
    "techm.kr": "테크M",
    "investchosun.com": "인베스트조선",
    "inews24.com": "아이뉴스24",
    "metroseoul.co.kr": "메트로신문",
    "seoul.co.kr": "서울신문",
    "scmp.com": "South China Morning Post",
    "isplus.com": "일간스포츠",
}

DIRECT_ARTICLES = [
    {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "국민일보",
        "title": "레버리지 규제 첫날 거래 ‘뚝’…12조원대서 3조원대로 급감",
        "url": "https://www.kmib.co.kr/article/view.asp?arcid=9000000424&cp=nv",
        "published_kst": "2026-07-31T17:00:00+0900",
    },
    {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "아시아경제",
        "title": "단일레버리지 예탁금 상향 첫날…거래량 감소, 개미는 매도",
        "url": "https://view.asiae.co.kr/article/2026073116442893935",
        "published_kst": "2026-07-31T16:44:00+0900",
    },
    {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "매일경제",
        "title": "AI 패권 경쟁 ‘쩐의 전쟁’…빅테크 투자 1조달러 넘었다",
        "url": "https://www.mk.co.kr/article/12113486",
        "published_kst": "2026-07-31T16:30:00+0900",
    },
    {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "연합뉴스",
        "title": '유안타증권 "단일종목 레버리지 ETF 규제, 코스닥 반등 계기될 것"',
        "url": "https://www.yna.co.kr/view/AKR20260730034600008",
        "published_kst": "2026-07-30T08:41:00+0900",
    },
    {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "조선비즈",
        "title": "삼성전자, 반도체 스타트업 투자·기술 확보에 8000억 출자",
        "url": "https://biz.chosun.com/it-science/ict/2026/07/30/E5GYIUCGO5HNPGVB6P7ZT3IBWA/",
        "fetch_url": "https://biz.chosun.com/it-science/ict/2026/07/30/E5GYIUCGO5HNPGVB6P7ZT3IBWA/?outputType=amp",
        "published_kst": "2026-07-30T18:37:00+0900",
    },
]

SEARCH_SOURCES = [
    (
        "단일종목 레버리지 규제 시행효과·거래급감",
        "(단일종목레버리지 OR 단일종목 레버리지 OR 단일레버리지 OR 기본예탁금) "
        "(거래대금 OR 거래량 OR 개인매도 OR 개인 매도 OR 거래급감 OR 거래 급감) "
        "(첫날 OR 시행 OR 상향 OR 3000만원) "
        "(site:kmib.co.kr OR site:asiae.co.kr OR site:mk.co.kr OR site:yna.co.kr "
        "OR site:newsis.com OR site:edaily.co.kr OR site:mt.co.kr)",
    ),
    (
        "빅테크 AI 투자·반도체·전력 인프라 CAPEX",
        "(빅테크 OR 하이퍼스케일러 OR 마이크로소프트 OR 구글 OR 아마존 OR 메타) "
        "(AI투자 OR AI 투자 OR CAPEX OR 설비투자 OR 설비 투자 OR 투자계획 OR 투자 계획) "
        "(1조달러 OR 1조 달러 OR 반도체 OR 데이터센터 OR 전력인프라 OR 전력 인프라) "
        "(site:mk.co.kr OR site:hankyung.com OR site:yna.co.kr OR site:newsis.com "
        "OR site:edaily.co.kr OR site:mt.co.kr OR site:biz.chosun.com)",
    ),
    (
        "국내 경영진·최대주주 직접매수",
        "(회장 OR 대표이사 OR 대표 OR 사장 OR 임원 OR 최대주주 OR 창업자) "
        "(장내매수 OR 장내 매수 OR 주식매수 OR 주식 매수 OR 지분매수 OR 지분 매수 "
        "OR 자사주식 매입 OR 자사 주식 매입) "
        "(site:newsis.com OR site:yna.co.kr OR site:etnews.com OR site:edaily.co.kr "
        "OR site:fnnews.com OR site:mk.co.kr OR site:hankyung.com OR site:isplus.com)",
    ),
    (
        "국내 기업 실적·장기계약·자본조달",
        "(실적 OR 영업이익 OR 순이익 OR 컨콜 OR LTA OR 장기공급계약 OR 유상증자 "
        "OR 자사주 OR 소각 OR 장내매수 OR 지분매수 OR 주식매수 OR 내부자매수) "
        "(반도체 OR HBM OR MLCC OR 데이터센터 OR AI OR 금융 OR 증권 OR 엔터 OR 콘텐츠) "
        "(site:newsis.com OR site:etnews.com OR site:edaily.co.kr OR site:fnnews.com OR "
        "site:inews24.com OR site:investchosun.com OR site:biz.heraldcorp.com OR "
        "site:isplus.com)",
    ),
    (
        "국내 대기업 전략기술 출자·스타트업 투자",
        "(출자 OR 투자조합 OR 벤처펀드 OR 스타트업투자 OR 스타트업 투자 OR 전략적투자 OR 전략적 투자) "
        "(반도체 OR AI OR 로봇 OR 배터리 OR 바이오 OR 데이터센터 OR 첨단기술 OR 신기술) "
        "(삼성전자 OR SK OR SK하이닉스 OR LG OR 현대차 OR 한화 OR NAVER OR 카카오) "
        "(site:biz.chosun.com OR site:yna.co.kr OR site:newsis.com OR site:etnews.com "
        "OR site:edaily.co.kr OR site:mk.co.kr OR site:hankyung.com OR site:investchosun.com)",
    ),
    (
        "국내 증시 중단·레버리지 위험",
        "(사이드카 OR 서킷브레이커 OR 신용융자 OR 레버리지ETF OR 레버리지 ETF "
        "OR 투자한도 OR 괴리율 OR 기본예탁금) (발동 OR 규제 OR 제한 OR 손실 OR 상향 OR 시행) "
        "(site:newsis.com OR site:fnnews.com OR site:mt.co.kr OR site:hankyung.com OR "
        "site:yonhapnewstv.co.kr OR site:kmib.co.kr)",
    ),
    (
        "단일종목 레버리지 규제·코스닥 수급",
        "(단일종목 레버리지 OR 단일종목 ETF OR 단일종목 ETN) "
        "(규제 OR 기본예탁금 OR 시행 OR 자금효율 OR 접근성) "
        "(코스닥 OR 중소형주 OR 성장주 OR 삼성전자 OR SK하이닉스) "
        "(site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:mt.co.kr "
        "OR site:edaily.co.kr OR site:hankyung.com)",
    ),
    (
        "반도체 공급망·공장 중단·차세대 메모리",
        "(TSMC OR JASM OR 구마모토 OR 지진 OR 강진 OR 공장중단 OR 공장 중단 "
        "OR 액체냉각 OR MLCC OR LPDDR6 OR HBM5 OR HBM 5 OR iHBM OR CXMT) "
        "(중단 OR 대피 OR 인증 OR 계약 OR 공급 OR 양산 OR 개발 OR 증설 OR 가격) "
        "(site:edaily.co.kr OR site:etoday.co.kr OR site:fnnews.com OR site:inews24.com OR "
        "site:seoul.co.kr OR site:biz.heraldcorp.com OR site:wowtv.co.kr)",
    ),
    (
        "금리·국채·환율 충격",
        "(미국채10년물 OR 미국채 10년물 OR FOMC OR 기준금리 OR 금리인상 OR 금리 인상 "
        "OR 원달러 OR 원·달러 OR 엔화) (최고 OR 최저 OR 인상 OR 동결 OR 급등 OR 급락 OR 확률) "
        "(site:yna.co.kr OR site:newsis.com OR site:news1.kr OR site:edaily.co.kr)",
    ),
    (
        "미국 수입제한·수출통제·로봇 정책",
        "(FCC OR 미국 상무부 OR 백악관 OR 트럼프) "
        "(수입금지 OR 수입 금지 OR 수입제한 OR 수입 제한 OR 수출통제 OR 관세 OR 제재) "
        "(로봇 OR 휴머노이드 OR 반도체 OR 인버터 OR 통신장비 OR 핵심광물) "
        "(site:dt.co.kr OR site:yna.co.kr OR site:newsis.com OR site:etoday.co.kr)",
    ),
    (
        "AI 순환금융·대형 금융지원",
        "(엔비디아 OR 오픈AI OR 마이크로소프트 OR 메타 OR 구글 OR 아마존) "
        "(순환금융 OR 순환투자 OR 금융지원 OR 금융보증 OR 보증 OR 장기구매) "
        "(AI OR 데이터센터 OR HBM OR 반도체) "
        "(site:asiae.co.kr OR site:mt.co.kr OR site:wowtv.co.kr OR site:techm.kr OR "
        "site:chosun.com OR site:hankyung.com)",
    ),
    (
        "미국 AI 반도체 정부지원·광통신",
        "(글로벌파운드리스 OR GlobalFoundries OR 광반도체 OR 실리콘포토닉스 "
        "OR 실리콘 포토닉스 OR 광통신 OR 광패키징) "
        "(정부지원 OR 정부 지원 OR 보조금 OR 개발비 OR CHIPS OR 저리대출 OR 저리 대출) "
        "(AI OR 데이터센터 OR 반도체 OR 첨단패키징) "
        "(site:biz.chosun.com OR site:reuters.com OR site:etnews.com OR site:yna.co.kr "
        "OR site:newsis.com)",
    ),
    (
        "중국 정치국 경기부양·정책 일정",
        "(중국 정치국 OR Politburo OR 전체회의 OR 3중전회 OR 중앙위원회) "
        "(정책지원 OR 정책 지원 OR 경기부양 OR 경기 부양 OR 재정지출 OR 재정 지출 "
        "OR 성장둔화 OR 성장 둔화 OR 10월 OR 개최) "
        "(site:scmp.com OR site:reuters.com OR site:yna.co.kr OR site:newsis.com "
        "OR site:hankyung.com)",
    ),
    (
        "국민연금·연기금 성과와 자산배분",
        "(국민연금 OR 연기금 OR NPS) "
        "(수익률 OR 국내주식 OR 국내 주식 OR 자산배분 OR 투자비중 OR 투자 비중 "
        "OR 순매수 OR 순매도) "
        "(site:hankyung.com OR site:yna.co.kr OR site:newsis.com OR site:etoday.co.kr)",
    ),
    (
        "국내 국고채·금리 충격",
        "(국고채 OR 국채 3년물 OR 국채 10년물 OR 채권금리 OR 채권 금리) "
        "(상승 OR 하락 OR 급등 OR 급락 OR FOMC OR 미국금리 OR 미국 금리 OR bp) "
        "(site:yna.co.kr OR site:newsis.com OR site:news1.kr OR site:edaily.co.kr "
        "OR site:hankyung.com)",
    ),
    (
        "정책펀드·저리대출·기업 설비투자",
        "(국민성장펀드 OR 정책금융 OR 정책 금융 OR 저리대출 OR 저리 대출 OR 정부투자 "
        "OR 정부 투자) "
        "(LG디스플레이 OR 테크윙 OR HBM OR 디스플레이 OR 반도체 OR 생산시설 "
        "OR 증설 OR 투자유치 OR 투자 유치) "
        "(site:hankyung.com OR site:yna.co.kr OR site:newsis.com OR site:etnews.com "
        "OR site:edaily.co.kr)",
    ),
]

DIRECT_RSS_SOURCES = [
    ("뉴시스 속보", "https://www.newsis.com/RSS/sokbo.xml", "trusted"),
    ("뉴시스 경제", "https://www.newsis.com/RSS/economy.xml", "trusted"),
    ("뉴시스 금융", "https://www.newsis.com/RSS/bank.xml", "trusted"),
    ("뉴시스 산업", "https://www.newsis.com/RSS/industry.xml", "trusted"),
    ("뉴시스 연예", "https://www.newsis.com/RSS/entertain.xml", "trusted"),
]

TRUSTED_MARKERS = tuple(
    value
    for domain, publisher in PUBLISHER_DOMAINS.items()
    for value in (domain, publisher)
)

PRIORITY_TERMS = {
    "거래대금": 14, "거래량 감소": 15, "거래 급감": 17, "거래급감": 17,
    "개인 매도": 16, "개인매도": 16, "예탁금 상향": 16, "규제 첫날": 15,
    "ai 투자": 17, "ai투자": 17, "1조달러": 18, "1조 달러": 18,
    "설비 투자": 15, "설비투자": 15, "전력 인프라": 15, "전력인프라": 15,
    "첨단 반도체": 13, "투자 계획": 14, "투자계획": 14,
    "유상증자": 14, "자사주 매입": 16, "자사주 소각": 14, "자기주식 소각": 14,
    "lta": 15, "장기공급계약": 15, "장기 공급계약": 15,
    "사이드카": 16, "서킷브레이커": 18, "신용융자": 12,
    "투자한도": 14, "괴리율": 11, "공장 중단": 16, "공장중단": 16,
    "강진": 15, "지진": 13, "미국채": 15, "금리 인상": 15,
    "액체냉각": 13, "mlcc": 13, "lpddr6": 14, "hbm5": 15,
    "hbm 5": 15, "ihbm": 15, "순환금융": 15, "순환투자": 15,
    "금융보증": 14, "수입 금지": 16, "수입금지": 16,
    "수입 제한": 16, "수입제한": 16,
    "정부 지원": 15, "정부지원": 15, "보조금": 16, "개발비": 13,
    "정책 지원": 14, "정책지원": 14, "경기 부양": 15, "경기부양": 15,
    "재정 지출": 14, "재정지출": 14, "정치국": 14, "전체회의": 12,
    "국민연금": 15, "연기금": 13, "국고채": 15, "채권금리": 14,
    "국민성장펀드": 17, "정책금융": 15, "정책 금융": 15,
    "저리 대출": 15, "저리대출": 15, "광반도체": 15,
    "실리콘 포토닉스": 15, "실리콘포토닉스": 15, "생산시설 증설": 15,
    "회장": 12, "대표이사": 12, "대표": 8, "사장": 10, "임원": 10,
    "장내매수": 18, "장내 매수": 18, "지분매수": 17, "지분 매수": 17,
    "내부자 직접매수": 18, "지분율": 12,
    "출자": 16, "투자조합": 16, "벤처펀드": 15, "스타트업 투자": 16,
    "스타트업투자": 16, "전략적 투자": 16, "전략적투자": 16,
    "기술 확보": 15, "오픈 이노베이션": 14,
    "단일종목 레버리지": 18, "코스닥 반등": 15,
    "연기금 벤치마크": 14, "코스닥 펀드": 14, "코스닥 프리미엄 지수": 14,
}

MATERIAL_TERMS = tuple(PRIORITY_TERMS)

IMPACT_TERMS = {
    "돈 버는 능력": (
        "ai 투자", "ai투자", "1조달러", "1조 달러", "설비 투자", "설비투자",
        "전력 인프라", "전력인프라", "첨단 반도체", "투자 계획", "투자계획",
        "장기공급계약", "lta", "금융지원", "금융보증", "순환금융", "순환투자",
        "공장 중단", "공장중단", "강진", "지진", "액체냉각", "mlcc",
        "lpddr6", "hbm5", "hbm 5", "ihbm",
        "정부 지원", "정부지원", "보조금", "개발비", "국민성장펀드",
        "정책금융", "정책 금융", "저리 대출", "저리대출", "광반도체",
        "출자", "투자조합", "벤처펀드", "스타트업 투자", "스타트업투자",
        "전략적 투자", "전략적투자", "기술 확보", "오픈 이노베이션",
        "실리콘 포토닉스", "실리콘포토닉스", "생산시설 증설",
    ),
    "할인율": (
        "미국채", "수입 금지", "수입금지", "수입 제한", "수입제한",
        "정책 지원", "정책지원", "경기 부양", "경기부양", "재정 지출",
        "재정지출", "국고채", "채권금리",
    ),
    "수급": (
        "사이드카", "서킷브레이커", "신용융자", "투자한도", "괴리율",
        "국민연금", "연기금", "국민성장펀드",
        "장내매수", "장내 매수", "지분매수", "지분 매수",
        "내부자 직접매수", "지분율",
        "거래대금", "거래량 감소", "거래 급감", "거래급감",
        "개인 매도", "개인매도", "예탁금 상향", "규제 첫날",
        "단일종목 레버리지", "코스닥 반등", "연기금 벤치마크",
        "코스닥 펀드", "코스닥 프리미엄 지수",
    ),
    "시간표": (
        "공장 중단", "공장중단", "대피", "복구", "lta", "장기공급계약",
        "정치국", "전체회의", "10월", "정책 지원", "정책지원",
        "국민성장펀드", "저리 대출", "저리대출", "생산시설 증설",
        "ai 투자", "ai투자", "설비 투자", "설비투자", "투자 계획", "투자계획",
        "출자", "투자조합", "벤처펀드", "스타트업 투자", "스타트업투자",
    ),
}


def extend_unique(target: list, values) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def apply_source_extensions(domains: dict, searches: list, trusted: list) -> None:
    domains.update(PUBLISHER_DOMAINS)
    extend_unique(searches, SEARCH_SOURCES)
    extend_unique(trusted, TRUSTED_MARKERS)


def apply_term_extensions(priority: dict, material: list, impacts: dict) -> None:
    priority.update(PRIORITY_TERMS)
    extend_unique(material, MATERIAL_TERMS)
    for label, terms in IMPACT_TERMS.items():
        impacts.setdefault(label, [])
        extend_unique(impacts[label], terms)


def semantic_theme(alert: dict, normalized_text: str) -> str:
    text = normalized_text
    event_date = str(alert.get("published") or "")[:10]
    if (
        ("단일종목" in text or "단일레버리지" in text)
        and "레버리지" in text
        and ("예탁금" in text or "규제" in text)
        and any(term in text for term in ("거래대금", "거래량", "거래 급감", "거래급감", "개인 매도", "개인매도"))
    ):
        return f"korean_market:single_stock_leverage_rule_effect:{event_date}"
    company_aliases = (
        ("삼성전기", ("삼성전기",)),
        ("삼성전자", ("삼성전자",)),
        ("SK하이닉스", ("sk하이닉스", "하이닉스")),
        ("NAVER", ("naver", "네이버")),
        ("엔비디아", ("엔비디아", "nvidia")),
        ("TSMC", ("tsmc", "jasm")),
    )
    event_aliases = (
        ("mlcc_lta", ("mlcc", "장기공급계약", "장기계약", "lta")),
        ("memory_lta", ("hbm", "메모리", "장기공급계약", "장기계약", "lta")),
        ("earnings", ("실적", "영업이익", "영업익", "순이익")),
        ("capital_raise", ("유상증자", "제3자배정", "3자배정")),
        ("factory_disruption", ("공장 중단", "공장중단", "대피", "강진", "지진")),
    )
    for company, aliases in company_aliases:
        if not any(alias in text for alias in aliases):
            continue
        for event, terms in event_aliases:
            hits = sum(term in text for term in terms)
            minimum_hits = 2 if event in {"mlcc_lta", "memory_lta"} else 1
            if hits >= minimum_hits:
                return f"korean_business:{company}:{event}:{event_date}"
    return ""
