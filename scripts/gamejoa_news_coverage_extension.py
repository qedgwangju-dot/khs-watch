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
        "국내 폭염·전력피크·아파트 정전",
        "(폭염 OR 극한폭염 OR 극한 폭염 OR 열대야 OR 전력피크 OR 전력 피크) "
        "(아파트정전 OR 아파트 정전 OR 정전사고 OR 정전 사고 OR 대규모정전 OR 대규모 정전) "
        "(변압기 OR 과부하 OR 노후설비 OR 노후 설비 OR 배전설비 OR 배전 설비 OR 전력사용량) "
        "(site:yna.co.kr OR site:newsis.com OR site:news1.kr OR site:kmib.co.kr "
        "OR site:edaily.co.kr OR site:hankyung.com OR site:seoul.co.kr OR site:imbc.com "
        "OR site:news.sbs.co.kr)",
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
    (
        "한국 월간 수출·반도체 수출·무역수지",
        "(월간수출 OR 월간 수출 OR 수출실적 OR 수출 실적 OR 무역수지) "
        "(반도체수출 OR 반도체 수출 OR 역대최대 OR 역대 최대 OR 역대2위 OR 역대 2위) "
        "(site:yna.co.kr OR site:hankyung.com OR site:wowtv.co.kr OR site:newsis.com "
        "OR site:edaily.co.kr OR site:etoday.co.kr)",
    ),
    (
        "연준 FOMC 회의체계·정책결정 일정",
        "(연준 OR FOMC OR Federal Reserve) "
        "(회의축소 OR 회의 축소 OR 회의횟수 OR 회의 횟수 OR 연8회 OR 연 8회 "
        "OR 정례회의 OR 정례 회의 OR 정책결정 일정) "
        "(site:reuters.com OR site:nytimes.com OR site:mt.co.kr OR site:yna.co.kr "
        "OR site:newsis.com OR site:edaily.co.kr)",
    ),
    (
        "미국·일본 환율개입·통화공조",
        "(엔화 OR 달러엔 OR 달러·엔 OR 일본 재무부 OR 미국 재무부) "
        "(환율개입 OR 환율 개입 OR 외환개입 OR 외환 개입 OR 시장개입 OR 시장 개입 "
        "OR 미일공조 OR 미·일 공조) "
        "(site:reuters.com OR site:yna.co.kr OR site:hankyung.com OR site:edaily.co.kr "
        "OR site:etoday.co.kr OR site:biz.heraldcorp.com)",
    ),
    (
        "중국 DRAM 생산능력·메모리 증설",
        "(CXMT OR 창신메모리 OR 중국DRAM OR 중국 D램 OR 중국 메모리) "
        "(생산능력 OR 생산 능력 OR 웨이퍼 OR 월생산 OR 월 생산 OR 증설 OR 캐파 OR 점유율) "
        "(site:reuters.com OR site:asiae.co.kr OR site:hankyung.com OR site:mk.co.kr "
        "OR site:mt.co.kr OR site:etnews.com)",
    ),
    (
        "하이퍼스케일러 실적·클라우드 성장·AI CAPEX",
        "(아마존 OR AWS OR 마이크로소프트 OR Azure OR 구글 OR Alphabet OR 메타) "
        "(실적 OR 매출 OR 성장률 OR 가이던스 OR CAPEX OR 설비투자 OR AI투자) "
        "(클라우드 OR 데이터센터 OR AI OR GPU OR HBM OR 전력인프라) "
        "(site:reuters.com OR site:yna.co.kr OR site:hankyung.com OR site:wowtv.co.kr "
        "OR site:etoday.co.kr OR site:edaily.co.kr OR site:mk.co.kr)",
    ),
    (
        "미국장 빅테크 실적·한국 ADR·반도체 수급",
        "(아마존 OR AWS OR 엔비디아 OR 애플 OR 마이크로소프트 OR 구글 OR 메타) "
        "(실적 OR 가이던스 OR 매출 OR 영업이익 OR CAPEX) "
        "(SK하이닉스ADR OR SK하이닉스 ADR OR 하이닉스ADR OR 하이닉스 ADR "
        "OR 반도체주 OR 필라델피아반도체 OR SMH OR 나스닥) "
        "(급등 OR 급락 OR 상승 OR 하락 OR 차익실현 OR 시가총액) "
        "(site:wowtv.co.kr OR site:etoday.co.kr OR site:edaily.co.kr OR site:mt.co.kr "
        "OR site:mk.co.kr OR site:hankyung.com OR site:yna.co.kr)",
    ),
    (
        "HBM5·zHBM·HBF 차세대 메모리 기술·상용화",
        "(HBM5 OR HBM 5 OR zHBM OR HBF OR HBM4E OR HBM 4E OR 3D메모리 OR 3D 메모리) "
        "(공개 OR 개발 OR 샘플 OR 양산 OR 상용화 OR 성능 OR 적층 OR 스펙다운) "
        "(삼성전자 OR SK하이닉스 OR 엔비디아 OR AMD OR 마이크론) "
        "(site:yna.co.kr OR site:yonhapnewstv.co.kr OR site:mk.co.kr OR site:dt.co.kr "
        "OR site:zdnet.co.kr OR site:joongang.co.kr OR site:fnnews.com OR site:etnews.com)",
    ),
    (
        "메모리 장기공급·수요전망·고객 사양 변경",
        "(메모리 OR D램 OR DRAM OR HBM OR 낸드 OR NAND) "
        "(LTA OR 장기공급 OR 장기 공급 OR 장기계약 OR 장기 계약 OR 수요전망 "
        "OR 수요 전망 OR 스펙다운 OR 사양변경 OR 사양 변경) "
        "(삼성전자 OR SK하이닉스 OR 마이크론 OR 엔비디아 OR 머스크 OR 빅테크) "
        "(site:etoday.co.kr OR site:mk.co.kr OR site:hankyung.com OR site:dt.co.kr "
        "OR site:yna.co.kr OR site:etnews.com OR site:zdnet.co.kr)",
    ),
    (
        "삼성 파운드리 가동률·풀캐파·공정 주문",
        "(삼성파운드리 OR 삼성 파운드리 OR 파운드리) "
        "(풀캐파 OR 완전가동 OR 가동률 OR 주문증가 OR 주문 증가 OR 수주 OR 고객사) "
        "(4나노 OR 5나노 OR 3나노 OR AI OR 서버 OR HBM) "
        "(site:zdnet.co.kr OR site:etnews.com OR site:yna.co.kr OR site:mk.co.kr "
        "OR site:hankyung.com OR site:biz.chosun.com)",
    ),
    (
        "핵심 원자재 사상최고·공급차질",
        "(구리 OR 리튬 OR 우라늄 OR 원유 OR 천연가스 OR 알루미늄 OR 니켈) "
        "(사상최고 OR 사상 최고 OR 최고가 OR 공급난 OR 공급차질 OR 공급 차질 "
        "OR 생산중단 OR 생산 중단 OR 광산사고 OR 광산 사고) "
        "(site:reuters.com OR site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr "
        "OR site:hankyung.com OR site:etoday.co.kr OR site:g-enews.com)",
    ),
    (
        "레버리지 규제 후 거래대금·자금이동",
        "(단일종목레버리지 OR 단일종목 레버리지 OR 삼전닉스레버리지 OR 삼전닉스 레버리지) "
        "(거래대금 OR 거래량 OR 자금이동 OR 자금 이동 OR 리밸런싱 OR 쏠림완화 OR 쏠림 완화) "
        "(규제 OR 예탁금 OR 시행 OR 1조 OR 3조 OR 12조) "
        "(site:hankyung.com OR site:edaily.co.kr OR site:kmib.co.kr OR site:asiae.co.kr "
        "OR site:mk.co.kr OR site:yna.co.kr OR site:news1.kr)",
    ),
    (
        "한미 조선협력·미국 군함 조선소·AI 용접",
        "(HD현대 OR HD현대중공업 OR HD한국조선해양 OR 한화오션 OR 삼성중공업) "
        "(미국 조선소 OR 군함 조선소 OR 미 해군 OR 함정 OR MRO OR MASGA OR 한미 조선협력 "
        "OR AI용접 OR AI 용접 OR 자동용접 OR 스마트조선소 OR 생산성) "
        "(투입 OR 적용 OR 협력 OR 계약 OR 수주 OR 실증 OR 구축 OR 기술이전) "
        "(site:ezyeconomy.com OR site:yna.co.kr OR site:newsis.com OR site:biz.chosun.com "
        "OR site:mk.co.kr OR site:edaily.co.kr OR site:etnews.com OR site:reuters.com)",
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
    "월간 수출": 17, "월간수출": 17, "수출 실적": 16, "수출실적": 16,
    "반도체 수출": 18, "반도체수출": 18, "무역수지": 16,
    "회의 축소": 17, "회의축소": 17, "회의 횟수": 15, "회의횟수": 15,
    "연 8회": 14, "연8회": 14, "정례 회의": 14, "정례회의": 14,
    "환율 개입": 18, "환율개입": 18, "외환 개입": 18, "외환개입": 18,
    "시장 개입": 15, "시장개입": 15, "미·일 공조": 16, "미일공조": 16,
    "생산 능력": 16, "생산능력": 16, "웨이퍼": 13, "월 생산": 14,
    "클라우드 성장": 16, "aws 매출": 17,
    "아파트 정전": 18, "아파트정전": 18, "대규모 정전": 18,
    "변압기 과부하": 17, "전력 피크": 16, "전력피크": 16,
    "노후 변압기": 15, "배전 설비": 14, "배전설비": 14,
    "sk하이닉스 adr": 17, "하이닉스 adr": 17, "adr": 11,
    "zhbm": 18, "hbf": 16, "hbm4e": 16, "3d 메모리": 15,
    "풀캐파": 18, "가동률": 14, "주문 증가": 16, "주문증가": 16,
    "스펙다운": 16, "사양 변경": 15, "사양변경": 15,
    "사상 최고": 17, "사상최고": 17, "공급난": 17,
    "공급 차질": 17, "공급차질": 17, "광산 사고": 17,
    "자금 이동": 17, "자금이동": 17, "리밸런싱": 15,
    "쏠림 완화": 15, "쏠림완화": 15,
    "한미 조선협력": 18, "미국 조선소": 18, "군함 조선소": 18,
    "미 해군": 17, "masga": 17, "ai 용접": 18, "ai용접": 18,
    "자동용접": 16, "스마트조선소": 16, "조선 mro": 17,
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
        "월간 수출", "월간수출", "수출 실적", "수출실적", "반도체 수출",
        "반도체수출", "무역수지", "생산 능력", "생산능력", "웨이퍼",
        "클라우드 성장", "aws 매출", "아파트 정전", "아파트정전",
        "대규모 정전", "변압기 과부하", "전력 피크", "전력피크",
        "노후 변압기", "배전 설비", "배전설비",
        "sk하이닉스 adr", "하이닉스 adr", "adr", "zhbm", "hbf", "hbm4e",
        "3d 메모리", "풀캐파", "가동률", "주문 증가", "주문증가", "스펙다운",
        "사양 변경", "사양변경", "사상 최고", "사상최고", "공급난",
        "공급 차질", "공급차질", "광산 사고",
    ),
    "할인율": (
        "미국채", "수입 금지", "수입금지", "수입 제한", "수입제한",
        "정책 지원", "정책지원", "경기 부양", "경기부양", "재정 지출",
        "재정지출", "국고채", "채권금리",
        "회의 축소", "회의축소", "회의 횟수", "회의횟수", "연 8회",
        "연8회", "정례 회의", "정례회의", "환율 개입", "환율개입",
        "외환 개입", "외환개입", "시장 개입", "시장개입", "미·일 공조",
        "미일공조",
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
        "sk하이닉스 adr", "하이닉스 adr", "adr", "자금 이동", "자금이동",
        "리밸런싱", "쏠림 완화", "쏠림완화",
        "한미 조선협력", "미국 조선소", "군함 조선소", "미 해군", "masga",
        "ai 용접", "ai용접", "자동용접", "스마트조선소", "조선 mro",
    ),
    "시간표": (
        "공장 중단", "공장중단", "대피", "복구", "lta", "장기공급계약",
        "정치국", "전체회의", "10월", "정책 지원", "정책지원",
        "국민성장펀드", "저리 대출", "저리대출", "생산시설 증설",
        "ai 투자", "ai투자", "설비 투자", "설비투자", "투자 계획", "투자계획",
        "출자", "투자조합", "벤처펀드", "스타트업 투자", "스타트업투자",
        "월간 수출", "월간수출", "수출 실적", "수출실적", "반도체 수출",
        "반도체수출", "회의 축소", "회의축소", "정례 회의", "정례회의",
        "환율 개입", "환율개입", "외환 개입", "외환개입", "생산 능력",
        "생산능력", "월 생산", "클라우드 성장", "aws 매출",
        "아파트 정전", "아파트정전", "대규모 정전", "변압기 과부하",
        "전력 피크", "전력피크", "노후 변압기", "배전 설비", "배전설비",
        "zhbm", "hbf", "hbm4e", "3d 메모리", "풀캐파", "주문 증가",
        "주문증가", "스펙다운", "사양 변경", "사양변경", "공급난",
        "공급 차질", "공급차질", "광산 사고", "자금 이동", "자금이동",
        "리밸런싱", "쏠림 완화", "쏠림완화",
        "한미 조선협력", "미국 조선소", "군함 조선소", "미 해군", "masga",
        "ai 용접", "ai용접", "자동용접", "스마트조선소", "조선 mro",
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
        "레버리지" in text
        and ("예탁금" in text or "규제" in text)
        and any(term in text for term in ("거래", "거래대금", "거래량", "거래 급감", "거래급감", "개인 매도", "개인매도"))
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
