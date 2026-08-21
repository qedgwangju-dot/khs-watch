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
    "ezyeconomy.com": "이지경제",
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
        "테슬라·머스크 대규모 CEO 보상·희석·주주승인",
        "(테슬라 OR Tesla OR 머스크 OR Musk OR Elon Musk OR 일론 머스크) "
        "(CEO 보상 OR CEO 급여 OR CEO pay OR CEO compensation OR 보상 패키지 OR pay package "
        "OR 성과보상 OR performance award OR stock award OR 주식보상 OR 주식 보상 OR 평균 직원) "
        "(주주 승인 OR shareholder approval OR 이사회 승인 OR board approval OR 희석 OR dilution "
        "OR 베스팅 OR vesting OR 공시 OR filing) "
        "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:ft.com OR site:sec.gov "
        "OR site:ir.tesla.com OR site:theguardian.com)",
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

PUBLISHER_DOMAINS.update(
    {
        "theguru.co.kr": "더구루",
        "ngetnews.com": "전자신문 계열",
        "magazine.hankyung.com": "한경머니",
    }
)

# Coverage requested from the August 6-8 real-time review. These are event
# families, not a one-off list: a match still needs a source-faithful body
# before the final sender can publish it.
SEARCH_SOURCES.extend(
    [
        (
            "연준 위원 발언·미국 고용·서비스 물가",
            "(연준 OR Fed OR FOMC OR 리사 쿡 OR 연준 이사) "
            "(금리인상 OR 금리 인상 OR 인플레이션 OR 고용쇼크 OR 고용 충격 OR 서비스업 PMI OR ISM) "
            "(site:reuters.com OR site:edaily.co.kr OR site:biz.chosun.com OR site:yna.co.kr OR site:newsis.com)",
        ),
        (
            "AI 메모리 아키텍처·엔비디아 사양 변경",
            "(zHBM OR HBF OR CXL OR HBM4E OR 루빈 울트라 OR Rubin Ultra OR AI가속기 OR AI 가속기) "
            "(공개 OR 개발 OR 양산 OR 사양축소 OR 사양 축소 OR 공급부족 OR 공급 부족 OR 표준화) "
            "(삼성전자 OR SK하이닉스 OR 엔비디아 OR 마이크론) "
            "(site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr OR site:biz.heraldcorp.com OR site:etnews.com)",
        ),
        (
            "SK하이닉스 해외 패키징·국내 대형 CAPEX",
            "(SK하이닉스 OR SK hynix) "
            "(인디애나 OR 첨단패키징 OR 어드밴스드 패키징 OR 용인 OR 청주 OR Y2 OR M17) "
            "(착공 OR 양산 OR 투자확정 OR 투자 확정 OR CAPEX OR 공장건설 OR 생산기지) "
            "(site:theguru.co.kr OR site:etnews.com OR site:yna.co.kr OR site:newsis.com OR site:chosun.com)",
        ),
        (
            "이란·호르무즈 협상·해협 통항",
            "(이란 OR Iran OR 호르무즈 OR 오만 OR Oman OR 걸프) "
            "(협상 OR 회담 OR 합의 OR 통항 OR 항로 OR 봉쇄 OR 유조선 OR 추가공격 OR 추가 공격) "
            "(트럼프 OR 미국 OR Tehran OR 테헤란) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR site:newsis.com)",
        ),
        (
            "한국 경상수지·반도체 수출·외국인 자금",
            "(경상수지 OR 경상 흑자 OR 상품수지 OR 반도체 수출 OR 수출 호조 OR 외국인 증권자금) "
            "(사상최대 OR 역대최대 OR 최대 OR 순유출 OR 순유입 OR 497억달러 OR 2500억달러) "
            "(site:yna.co.kr OR site:news1.kr OR site:edaily.co.kr OR site:hankyung.com OR site:newsis.com)",
        ),
        (
            "코스피 사이드카·단일종목 레버리지 수급 변화",
            "(코스피 OR 코스닥 OR 삼성전자 OR SK하이닉스) "
            "(매도 사이드카 OR 매수 사이드카 OR 사이드카 발동 OR 단일종목 레버리지 OR 기본예탁금) "
            "(급락 OR 급등 OR 거래대금 OR 거래량 OR 자금유입 OR 자금 유입 OR 심사) "
            "(site:mk.co.kr OR site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr OR site:hankyung.com)",
        ),
    ]
)

# August 9 coverage: each lane requires a company, operating action, and a
# concrete financial, capacity, supply-chain, or timetable consequence.
SEARCH_SOURCES.extend(
    [
        (
            "SK하이닉스 중국 패키징 지분·운영 재편",
            "(SK하이닉스 OR SK hynix) (충칭 OR 중국 패키징 OR 후공정 OR 테스트공장 OR 테스트 공장) "
            "(지분매각 OR 지분 매각 OR 매각검토 OR 매각 검토 OR 운영재편 OR 운영 재편 OR 소수지분) "
            "(Bloomberg OR 블룸버그 OR Reuters OR 로이터 OR site:news1.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:reuters.com)",
        ),
        (
            "SK하이닉스 노사·성과급 주식 보상",
            "(SK하이닉스 OR SK hynix) (통합노조 OR 노조 신설 OR 임금교섭 OR 성과급 OR 주식보상 OR 주식 보상) "
            "(교섭 OR 제안 OR 합의 OR 파업 OR 쟁의 OR 매도제한 OR 매도 제한) "
            "(site:hankyung.com OR site:magazine.hankyung.com OR site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr)",
        ),
        (
            "삼성 테일러 팹 가동·미국 파운드리 인력",
            "(삼성전자 OR 삼성 파운드리 OR Samsung Foundry) (테일러팹 OR 테일러 팹 OR Taylor fab OR Texas fab) "
            "(가동 OR 양산 OR 인턴십 OR 채용 OR 현지인력 OR 현지 인력 OR 장비반입 OR 장비 반입) "
            "(연말 OR 일정 OR 고객사 OR 생산능력 OR 생산 능력) "
            "(site:biz.chosun.com OR site:fnnews.com OR site:yna.co.kr OR site:newsis.com OR site:reuters.com)",
        ),
        (
            "전력반도체 정책·대형 투자·생산기지",
            "(전력반도체 OR 전력 반도체 OR SiC OR GaN) "
            "(정부지원 OR 정부 지원 OR 정책금융 OR 정책 금융 OR 예산 OR 세액공제 OR 투자확정 OR 투자 확정 OR 생산기지) "
            "(삼성전자 OR SK OR 현대차 OR 산업부 OR 과기정통부) "
            "(site:dt.co.kr OR site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr OR site:motie.go.kr)",
        ),
        (
            "해외 AI 슈퍼컴퓨터·한국 반도체·보안 수주",
            "(슈퍼컴퓨터 OR AI 슈퍼컴퓨터 OR 국가AI OR 국가 AI) "
            "(SK하이닉스 OR 삼성전자 OR 퓨리오사AI OR 안랩 OR 펜타시큐리티 OR 한국) "
            "(HBM OR NPU OR 보안 OR 공급 OR 탑재 OR 구축 OR 계약 OR 수주) "
            "(인도네시아 OR 동남아 OR 해외) "
            "(site:mk.co.kr OR site:yna.co.kr OR site:newsis.com OR site:etnews.com OR site:edaily.co.kr)",
        ),
    ]
)

# August 10 coverage: these lanes are durable event families. They deliberately
# require both a market mechanism and a concrete consequence so a generic
# commentary article does not become a Telegram alert.
SEARCH_SOURCES.extend(
    [
        (
            "회사채 차환·신용등급·시설투자 위축",
            "(회사채 OR 회사 채 OR 차환 OR 만기상환 OR 신용등급 OR 신용 스프레드) "
            "(시설자금 OR 설비투자 OR 신규투자 OR 자금조달 OR 발행금리 OR 발행) "
            "(비중 OR 감소 OR 급감 OR 하향 OR 상승 OR 확대) "
            "(site:mk.co.kr OR site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr OR site:hankyung.com)",
        ),
        (
            "중국 CPI·PPI·디플레이션·전자부품 가격",
            "(중국 OR China) (CPI OR PPI OR 소비자물가 OR 생산자물가 OR 도매물가 OR 디플레이션) "
            "(반도체 OR 컴퓨터 OR 태블릿 OR 휴대폰 OR 전자부품 OR 내수 OR 수요) "
            "(상승 OR 하락 OR 둔화 OR 반등 OR 발표) "
            "(site:reuters.com OR site:scmp.com OR site:yna.co.kr OR site:mk.co.kr OR site:newsis.com)",
        ),
        (
            "중국 피지컬 AI·휴머노이드 로봇·반도체 경쟁",
            "(유니트리 OR Unitree OR CXMT OR 창신메모리 OR 중국 로봇 OR 휴머노이드 OR 피지컬 AI) "
            "(상장 OR IPO OR 생산능력 OR 생산 능력 OR 정부지원 OR 정부 지원 OR 투자 OR 양산) "
            "(미국 OR 중국 OR 경쟁 OR 공급망) "
            "(site:reuters.com OR site:scmp.com OR site:ft.com OR site:dt.co.kr OR site:yna.co.kr)",
        ),
        (
            "토큰화 주식·24시간 거래·가상자산 증권 규제",
            "(토큰주식 OR 토큰 주식 OR tokenized stock OR 24시간 거래 OR 증권 토큰) "
            "(거래액 OR 거래 규모 OR 규제 OR 인가 OR 금지 OR ETF OR 엔비디아 OR 테슬라) "
            "(site:reuters.com OR site:ft.com OR site:dt.co.kr OR site:yna.co.kr OR site:newsis.com)",
        ),
        (
            "미국 고용·CPI·달러/원·미 국채금리",
            "(미국 고용 OR 비농업고용 OR 실업률 OR CPI OR 소비자물가 OR 미 국채금리 OR 달러/원 OR 원/달러) "
            "(연준 OR Fed OR 금리인하 OR 금리 인하 OR 금리동결 OR 약달러 OR 달러 약세) "
            "(발표 OR 예상치 OR 쇼크 OR 하회 OR 상회 OR 9월) "
            "(site:reuters.com OR site:yna.co.kr OR site:newsis.com OR site:news1.kr OR site:edaily.co.kr)",
        ),
    ]
)

# Corporate execution and shareholder-policy monitoring. A securities-firm
# estimate stays an estimate until the board or company announces the policy.
SEARCH_SOURCES.extend(
    [
        (
            "고려아연·핵심광물·미국 제련소·정부 프로젝트",
            "(고려아연 OR Korea Zinc) (핵심광물 OR 핵심 광물 OR 제련소 OR 통합제련소 OR 미국 제련소) "
            "(트럼프 OR 미국 정부 OR 상무부 OR 프로젝트 OR 모범사례 OR 투자 OR 생산) "
            "(site:yna.co.kr OR site:wowtv.co.kr OR site:newsis.com OR site:reuters.com OR site:mk.co.kr)",
        ),
        (
            "네이버·삼성·SKT 앤트로픽 투자·AI 협업",
            "(NAVER OR 네이버 OR 삼성전자 OR SK텔레콤 OR SKT) (앤트로픽 OR Anthropic OR 클로드 OR Claude) "
            "(투자 OR 출자 OR 지분 OR 협업 OR 협력 OR 전략 OR 데이터센터 OR AI) "
            "(site:hankyung.com OR site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr OR site:etnews.com)",
        ),
        (
            "애플·CXMT 중국 메모리 탑재시험·공급망",
            "(애플 OR Apple) (CXMT OR 창신메모리 OR 중국 메모리 OR 중국 D램) "
            "(탑재 시험 OR 테스트 OR 공급 OR 협력 OR 채택 OR 모바일 AI OR 아이폰) "
            "(site:mk.co.kr OR site:dt.co.kr OR site:reuters.com OR site:yna.co.kr OR site:newsis.com)",
        ),
        (
            "AI 데이터센터 금융플랫폼·대형 자금조달",
            "(엔비디아 OR Nvidia OR 오픈AI OR OpenAI OR 아폴로 OR 블랙스톤 OR 블랙록 OR 브룩필드) "
            "(금융플랫폼 OR 금융 플랫폼 OR 자금조달 OR 투자플랫폼 OR 투자 플랫폼 OR 보증 OR 대출 OR 금융지원) "
            "(AI 인프라 OR AI인프라 OR 데이터센터 OR GPU OR 컴퓨팅) "
            "(site:reuters.com OR site:ft.com OR site:dt.co.kr OR site:yna.co.kr OR site:newsis.com)",
        ),
        (
            "SK하이닉스·키옥시아 지분·CB 전환·경쟁당국",
            "(SK하이닉스 OR SK hynix) (키옥시아 OR Kioxia) "
            "(최대주주 OR 최대 주주 OR 전환사채 OR CB OR 의결권 OR 경쟁당국 OR 기업결합) "
            "(전환 OR 승인 OR 지분 OR 낸드 OR NAND) "
            "(site:mk.co.kr OR site:fnnews.com OR site:zdnet.co.kr OR site:yna.co.kr OR site:newsis.com)",
        ),
        (
            "국내 ETF 순자산·설정·환매·대규모 자금 유출입",
            "(ETF OR 상장지수펀드) (자금유출 OR 자금 유출 OR 자금유입 OR 자금 유입 OR 순자산 OR 설정액 OR 환매) "
            "(조원 OR 억원 OR 7000억 OR 1조 OR 2조 OR 3조) "
            "(site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr OR site:dailian.co.kr OR site:mk.co.kr)",
        ),
        (
            "국내 태양광 모듈 생산라인·양산·공장 증설",
            "(태양광 모듈 OR 태양광모듈 OR solar module OR 신성이엔지 OR 한화솔루션 OR HD현대에너지솔루션) "
            "(신규 라인 OR 신규라인 OR 양산 OR 생산라인 OR 공장 가동 OR 증설 OR 실증 OR KS 인증) "
            "(site:newsis.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:hankyung.com)",
        ),
        (
            "국내 대형 M&A·PEF 인수·인수자금·신용등급",
            "(인수한다 OR 인수 계약 OR 인수계약 OR M&A OR 매각 계약 OR 매각계약) "
            "(조원 OR 억원 OR PEF OR 사모펀드 OR TPG OR KKR OR MBK) "
            "(신용등급 OR 인수자금 OR 자기자본 OR 차입매수 OR LBO OR 지분) "
            "(site:hankyung.com OR site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:edaily.co.kr)",
        ),
        (
            "국내 전략산업 ETF 신규상장·편입·리밸런싱",
            "(ETF OR 상장지수펀드) (신규상장 OR 신규 상장 OR 상장예정 OR 상장 예정 OR 상장) "
            "(반도체 OR 금융 OR 지주 OR 방산 OR AI OR 전력 OR 전략산업 OR 전략 산업) "
            "(운용 OR 자산운용 OR 편입 OR 채권혼합 OR 액티브 OR 리밸런싱) "
            "(site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr OR site:mk.co.kr "
            "OR site:hankyung.com OR site:etoday.co.kr OR site:fnnews.com)",
        ),
        (
            "한미반도체 미국 법인·북미 장비 수주·고객지원",
            "(한미반도체 OR Hanmi Semiconductor) "
            "(한미 USA OR 미국 법인 OR 미국법인 OR 현지 법인 OR 현지법인) "
            "(설립 OR 출범 OR 출자 OR 고객지원 OR 기술지원 OR 수주 OR 하이퍼스케일러 OR HBM) "
            "(site:yna.co.kr OR site:newsis.com OR site:etnews.com OR site:edaily.co.kr OR site:mk.co.kr)",
        ),
        (
            "삼성전자 주주환원·배당·자사주 이사회 정책",
            "(삼성전자) (주주환원 OR 주주 환원 OR 배당 OR 자사주 OR 자기주식) "
            "(이사회 OR 정책 OR 발표 OR 확정 OR 전망 OR 소각 OR 매입 OR 배당수익률) "
            "(site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:edaily.co.kr OR site:metroseoul.co.kr)",
        ),
    ]
)

DIRECT_RSS_SOURCES = [
    ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml", "trusted"),
    ("연합뉴스 산업", "https://www.yna.co.kr/rss/industry.xml", "trusted"),
    ("연합뉴스 증권", "https://www.yna.co.kr/rss/market.xml", "trusted"),
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

# August 6-8 coverage: all terms below must be material before the runner builds
# its title/body filter. This prevents a search hit from being discarded later.
PRIORITY_TERMS.update(
    {
        "연준 이사": 16,
        "금리 인상": 18,
        "고용 충격": 18,
        "서비스업 pmi": 15,
        "cxl": 16,
        "루빈 울트라": 17,
        "사양 축소": 16,
        "공급 부족": 17,
        "첨단패키징": 17,
        "첨단 패키징": 17,
        "어드밴스드 패키징": 17,
        "인디애나": 16,
        "투자확정": 18,
        "투자 확정": 18,
        "호르무즈": 18,
        "해협 통항": 18,
        "이란 오만": 16,
        "경상수지": 18,
        "경상 흑자": 18,
        "외국인 증권자금": 16,
        "매도 사이드카": 18,
        "매수 사이드카": 18,
        "사이드카 발동": 18,
    }
)

PRIORITY_TERMS.update(
    {
        "고려아연": 18,
        "etf": 12,
        "핵심광물": 17,
        "핵심 광물": 17,
        "통합제련소": 16,
        "앤트로픽": 18,
        "anthropic": 18,
        "cxmt": 17,
        "창신메모리": 17,
        "탑재 시험": 16,
        "탑재시험": 16,
        "금융플랫폼": 16,
        "금융 플랫폼": 16,
        "키옥시아": 17,
        "kioxia": 17,
        "의결권": 15,
        "의결권 확보": 16,
        "cb 전환": 16,
        "기업결합": 16,
        "자금유출": 16,
        "자금 유출": 16,
        "자금유입": 16,
        "자금 유입": 16,
        "순자산": 15,
        "설정액": 15,
        "환매": 15,
        "태양광 모듈": 16,
        "태양광모듈": 16,
        "신규 라인": 15,
        "신규라인": 15,
        "인수 계약": 18,
        "인수계약": 18,
        "차입매수": 16,
        "lbo": 16,
        "신규상장": 16,
        "신규 상장": 16,
        "상장 예정": 14,
        "상장예정": 14,
        "상장지수펀드": 13,
        "채권혼합": 13,
        "액티브 etf": 13,
        "반도체·금융·지주": 16,
        "전략산업 etf": 15,
        "전략산업etf": 15,
        "브이아이자산운용": 16,
        "브이아이운용": 16,
        "한미반도체": 18,
        "hanmi semiconductor": 18,
        "한미 usa": 18,
        "미국 법인": 15,
        "미국법인": 15,
        "현지 법인": 14,
        "현지법인": 14,
        "고객지원": 13,
        "기술지원": 13,
        "주주환원": 17,
        "주주 환원": 17,
        "배당수익률": 15,
        "배당 수익률": 15,
        "이사회 결정": 17,
        "이사회": 11,
    }
)

PRIORITY_TERMS.update(
    {
        "회사채": 15,
        "차환": 16,
        "만기상환": 15,
        "신용등급 하향": 18,
        "신용등급": 13,
        "신용 스프레드": 16,
        "발행금리": 16,
        "시설자금": 15,
        "시설자금용": 16,
        "설비투자 위축": 17,
        "신규투자 위축": 17,
        "중국 cpi": 15,
        "중국 ppi": 15,
        "cpi": 12,
        "ppi": 12,
        "중국 소비자물가": 15,
        "중국 생산자물가": 15,
        "중국 디플레이션": 16,
        "도매물가": 12,
        "유니트리": 16,
        "unitree": 16,
        "휴머노이드": 14,
        "피지컬 ai": 15,
        "토큰주식": 15,
        "토큰 주식": 15,
        "tokenized stock": 15,
        "24시간 거래": 14,
        "비농업고용": 17,
        "미국 고용": 16,
        "고용 쇼크": 18,
        "미국 cpi": 17,
        "달러/원": 17,
        "원/달러": 17,
        "약달러": 15,
        "달러 약세": 15,
    }
)

PRIORITY_TERMS.update(
    {
        "충칭": 15,
        "지분매각": 17,
        "지분 매각": 17,
        "매각검토": 15,
        "매각 검토": 15,
        "통합노조": 15,
        "노조 신설": 15,
        "주식보상": 14,
        "주식 보상": 14,
        "테일러팹": 17,
        "테일러 팹": 17,
        "taylor fab": 17,
        "현지 인력": 14,
        "현지인력": 14,
        "전력반도체": 16,
        "전력 반도체": 16,
        "인도네시아": 14,
        "슈퍼컴퓨터": 15,
        "ai 슈퍼컴퓨터": 16,
    }
)

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


# Keep the impact matrix tied to the new coverage lanes. A matching headline
# must carry the economic dimension that caused it to be sent.
ATTACHED_NEWS_IMPACT_TERMS = {
    "돈 버는 능력": (
        "zhbm", "hbf", "cxl", "hbm4e", "루빈 울트라", "사양 축소", "공급 부족",
        "첨단패키징", "첨단 패키징", "어드밴스드 패키징", "인디애나",
        "투자확정", "투자 확정", "경상수지", "경상 흑자",
    ),
    "할인율": (
        "연준 이사", "금리 인상", "고용 충격", "서비스업 pmi", "호르무즈", "해협 통항", "이란 오만",
    ),
    "수급": (
        "외국인 증권자금", "매도 사이드카", "매수 사이드카", "사이드카 발동",
    ),
    "시간표": (
        "첨단패키징", "첨단 패키징", "어드밴스드 패키징", "인디애나",
        "투자확정", "투자 확정", "호르무즈", "해협 통항",
    ),
}
for _impact_label, _impact_terms in ATTACHED_NEWS_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))

AUGUST9_IMPACT_TERMS = {
    "돈 버는 능력": (
        "충칭", "지분매각", "지분 매각", "테일러팹", "테일러 팹", "taylor fab",
        "전력반도체", "전력 반도체", "슈퍼컴퓨터", "ai 슈퍼컴퓨터",
    ),
    "수급": ("통합노조", "노조 신설", "주식보상", "주식 보상"),
    "시간표": (
        "매각검토", "매각 검토", "테일러팹", "테일러 팹", "taylor fab",
        "현지 인력", "현지인력", "전력반도체", "전력 반도체", "인도네시아",
    ),
}
for _impact_label, _impact_terms in AUGUST9_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))

AUGUST10_IMPACT_TERMS = {
    "돈 버는 능력": (
        "시설자금", "시설자금용", "설비투자 위축", "신규투자 위축",
        "중국 디플레이션", "유니트리", "unitree", "휴머노이드", "피지컬 ai",
        "hbf",
    ),
    "할인율": (
        "회사채", "차환", "만기상환", "신용등급 하향", "신용등급",
        "신용 스프레드", "발행금리", "cpi", "ppi", "중국 cpi", "중국 ppi", "중국 소비자물가",
        "중국 생산자물가", "중국 디플레이션", "비농업고용", "미국 고용",
        "고용 쇼크", "미국 cpi", "달러/원", "원/달러", "약달러", "달러 약세",
    ),
    "수급": (
        "토큰주식", "토큰 주식", "tokenized stock", "24시간 거래",
    ),
    "시간표": (
        "시설자금", "설비투자 위축", "신규투자 위축", "유니트리", "unitree",
        "휴머노이드", "피지컬 ai", "토큰주식", "토큰 주식", "tokenized stock",
        "24시간 거래", "hbf",
    ),
}
for _impact_label, _impact_terms in AUGUST10_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))

CORPORATE_EXECUTION_IMPACT_TERMS = {
    "돈 버는 능력": (
        "한미반도체", "hanmi semiconductor", "한미 usa", "미국 법인", "미국법인",
        "현지 법인", "현지법인", "고객지원", "기술지원",
    ),
    "수급": (
        "주주환원", "주주 환원", "배당수익률", "배당 수익률", "이사회 결정",
    ),
    "시간표": (
        "한미 usa", "미국 법인", "미국법인", "현지 법인", "현지법인",
        "이사회 결정", "이사회",
    ),
}
for _impact_label, _impact_terms in CORPORATE_EXECUTION_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))

STRATEGIC_ETF_LISTING_IMPACT_TERMS = {
    "수급": (
        "신규상장", "신규 상장", "상장지수펀드", "채권혼합", "액티브 etf",
        "반도체·금융·지주", "전략산업 etf", "전략산업etf",
    ),
    "시간표": (
        "신규상장", "신규 상장", "상장 예정", "상장예정", "상장지수펀드",
        "채권혼합", "액티브 etf", "전략산업 etf", "전략산업etf",
    ),
}
for _impact_label, _impact_terms in STRATEGIC_ETF_LISTING_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))

ATTACHMENT_EVENT_IMPACT_TERMS = {
    "돈 버는 능력": (
        "고려아연", "핵심광물", "핵심 광물", "통합제련소", "앤트로픽", "anthropic",
        "cxmt", "창신메모리", "탑재 시험", "탑재시험", "금융플랫폼", "금융 플랫폼",
        "키옥시아", "kioxia", "태양광 모듈", "태양광모듈", "신규 라인", "신규라인",
        "인수 계약", "인수계약", "차입매수", "lbo",
    ),
    "할인율": ("핵심광물", "핵심 광물", "기업결합", "차입매수", "lbo"),
    "수급": (
        "앤트로픽", "anthropic", "자금유출", "자금 유출", "자금유입", "자금 유입",
        "순자산", "설정액", "환매", "의결권", "인수 계약", "인수계약",
    ),
    "시간표": (
        "통합제련소", "탑재 시험", "탑재시험", "금융플랫폼", "금융 플랫폼",
        "기업결합", "cb 전환", "의결권 확보", "신규 라인", "신규라인", "인수 계약", "인수계약",
    ),
}
for _impact_label, _impact_terms in ATTACHMENT_EVENT_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))

# August 12 full-attachment coverage. These are recurring event families, not
# pinned articles: the final sender still requires a source-faithful body.
SEARCH_SOURCES.extend(
    [
        (
            "AI 클라우드·GPU 임대 사업자 실적·가이던스",
            "(CoreWeave OR 코어위브 OR Nebius OR Crusoe OR GPU cloud OR GPU 클라우드) "
            "(earnings OR revenue OR guidance OR 매출 OR 실적 OR 가이던스 OR 수요 OR 계약) "
            "(site:reuters.com OR site:cnbc.com OR site:ft.com OR site:mt.co.kr OR site:yna.co.kr OR site:newsis.com)",
        ),
        (
            "CXMT DDR5 수율·PC OEM 공급·범용 DRAM 가격",
            "(CXMT OR 창신메모리 OR 중국 메모리) (DDR5 OR D램 OR DRAM) "
            "(수율 OR yield OR HP OR 에이수스 OR ASUS OR 에이서 OR Acer OR PC 제조사 OR 공급) "
            "(site:reuters.com OR site:mt.co.kr OR site:dt.co.kr OR site:yna.co.kr OR site:newsis.com)",
        ),
        (
            "반도체 산단 전력공급·송변전 협약·비용분담",
            "(한국전력 OR 한전 OR 삼성전자 OR SK하이닉스) (반도체 산단 OR 반도체산단 OR 메가프로젝트) "
            "(전력공급 OR 전력 공급 OR 송전 OR 변전 OR 송변전 OR 비용분담 OR 협약) "
            "(site:edaily.co.kr OR site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:hankyung.com)",
        ),
        (
            "해외 국부펀드·장기자금 한국 반도체 직접 투자",
            "(테마섹 OR Temasek OR 국부펀드 OR sovereign fund OR 연기금) "
            "(삼성전자 OR SK하이닉스 OR 한국 반도체 OR K증시) "
            "(투자 OR 지분 OR 매수 OR 편입 OR 출자 OR 보유) "
            "(site:asiae.co.kr OR site:yna.co.kr OR site:newsis.com OR site:reuters.com OR site:mk.co.kr)",
        ),
        (
            "국내 공모펀드 순자산·대규모 설정·환매",
            "(공모펀드 OR 인덱스펀드 OR 펀드) (순자산 OR 설정액 OR 환매 OR 자금유입 OR 자금 유입 OR 자금유출 OR 자금 유출) "
            "(조원 OR 억원) (site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:metroseoul.co.kr OR site:edaily.co.kr)",
        ),
        (
            "TSMC 첨단패키징·CoWoS 자본지출·투자승인",
            "(TSMC OR 대만적층 OR Taiwan Semiconductor) (CoWoS OR 첨단패키징 OR 첨단 패키징 OR 2나노) "
            "(자본지출 OR CAPEX OR 투자승인 OR 투자 승인 OR 이사회 승인 OR 증설) "
            "(site:reuters.com OR site:yna.co.kr OR site:newsis.com OR site:biz.chosun.com OR site:ft.com)",
        ),
    ]
)

PRIORITY_TERMS.update(
    {
        "코어위브": 18,
        "coreweave": 18,
        "gpu 클라우드": 16,
        "gpu cloud": 16,
        "gpu 임대": 16,
        "매출 2배": 17,
        "매출 두배": 17,
        "ddr5 수율": 17,
        "수율 90%": 18,
        "pc 제조사 공급": 16,
        "반도체 산단 전력공급": 18,
        "전력공급 협약": 18,
        "송변전 협약": 18,
        "비용분담": 15,
        "테마섹": 17,
        "temasek": 17,
        "국부펀드": 15,
        "공모펀드": 14,
        "공모 펀드": 14,
        "인덱스펀드": 14,
        "펀드 순자산": 16,
        "순자산 1조": 16,
        "tsmc": 14,
        "cowos": 17,
        "투자승인": 17,
        "투자 승인": 17,
        "자본지출 승인": 18,
    }
)

AUGUST12_ATTACHMENT_IMPACT_TERMS = {
    "돈 버는 능력": (
        "코어위브", "coreweave", "gpu 클라우드", "gpu cloud", "gpu 임대", "매출 2배", "매출 두배",
        "ddr5 수율", "수율 90%", "pc 제조사 공급", "반도체 산단 전력공급", "전력공급 협약",
        "송변전 협약", "cowos", "자본지출 승인",
    ),
    "할인율": ("반도체 산단 전력공급", "전력공급 협약", "송변전 협약", "비용분담"),
    "수급": ("테마섹", "temasek", "국부펀드", "공모펀드", "인덱스펀드", "펀드 순자산", "순자산 1조"),
    "시간표": ("전력공급 협약", "송변전 협약", "비용분담", "cowos", "투자승인", "투자 승인", "자본지출 승인"),
}
for _impact_label, _impact_terms in AUGUST12_ATTACHMENT_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))

# August 13 full-attachment coverage. These are recurring event families,
# not pinned articles: the final sender still requires a source-faithful body.
PUBLISHER_DOMAINS.update(
    {
        "digitaltoday.co.kr": "디지털투데이",
        "economist.co.kr": "이코노미스트",
    }
)

SEARCH_SOURCES.extend(
    [
        (
            "테슬라·미국 태양광 제조공장·대형 CAPEX",
            "(테슬라 OR Tesla) (태양광 OR solar) (공장 OR factory OR 제조 OR 생산라인) "
            "(투자 OR CAPEX OR 건설 OR 고용 OR 증설) "
            "(site:reuters.com OR site:cnbc.com OR site:yna.co.kr OR site:newsis.com OR site:digitaltoday.co.kr)",
        ),
        (
            "엔비디아 루빈·HBM4E 사양변경·공급망",
            "(엔비디아 OR NVIDIA) (루빈 OR Rubin OR HBM4E OR HBM 4E) "
            "(사양 OR 변경 OR 낮추 OR 검토 OR 공급 OR 메모리) "
            "(site:reuters.com OR site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:dt.co.kr)",
        ),
        (
            "SK하이닉스 미국 인디애나 첨단패키징 착공·양산",
            "(SK하이닉스 OR SK hynix) (인디애나 OR Indiana) (첨단패키징 OR 첨단 패키징 OR HBM) "
            "(착공 OR 공장 OR 양산 OR 가동 OR 투자) "
            "(site:reuters.com OR site:yna.co.kr OR site:newsis.com OR site:dt.co.kr OR site:mk.co.kr)",
        ),
        (
            "AI 데이터센터 광통신·광인터커넥트 병목",
            "(광통신 OR 실리콘포토닉스 OR 실리콘 포토닉스 OR 광인터커넥트 OR 광 송수신기) "
            "(AI OR GPU OR HBM OR 데이터센터 OR data center) "
            "(수요 OR 투자 OR 증설 OR 병목 OR 공급 OR CAPEX) "
            "(site:reuters.com OR site:etoday.co.kr OR site:yna.co.kr OR site:newsis.com OR site:biz.chosun.com)",
        ),
        (
            "삼성 데이터센터 공조·냉각 생산능력·해외 증설",
            "(삼성 OR Samsung) (데이터센터 OR data center) (공조 OR 냉각 OR HVAC OR 칠러 OR chiller) "
            "(공장 OR 생산라인 OR 투자 OR 증설 OR 양산) "
            "(site:yna.co.kr OR site:newsis.com OR site:economist.co.kr OR site:etoday.co.kr OR site:biz.chosun.com)",
        ),
    ]
)

PRIORITY_TERMS.update(
    {
        "테슬라 태양광": 16,
        "solar factory": 16,
        "태양광 공장": 16,
        "루빈 울트라": 17,
        "hbm4e 사양": 18,
        "광통신": 15,
        "광인터커넥트": 16,
        "실리콘 포토닉스": 16,
        "데이터센터 공조": 17,
        "데이터센터 냉각": 17,
        "hvac": 15,
        "인디애나 팹": 17,
    }
)

AUGUST13_ATTACHMENT_IMPACT_TERMS = {
    "돈 버는 능력": (
        "태양광 공장", "solar factory", "루빈 울트라", "hbm4e 사양",
        "광통신", "광인터커넥트", "실리콘 포토닉스", "데이터센터 공조",
        "데이터센터 냉각", "인디애나 팹",
    ),
    "수급": ("루빈 울트라", "hbm4e 사양"),
    "시간표": ("태양광 공장", "인디애나 팹", "데이터센터 공조", "데이터센터 냉각"),
}
for _impact_label, _impact_terms in AUGUST13_ATTACHMENT_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))


# Full-attachment coverage (2026-08-10 through 2026-08-21).
# These are discovery lanes only. Historical examples are never pinned for
# replay; the normal freshness, body-verification, decision-impact, and seen
# state gates still decide whether a new article may be sent.
SEARCH_SOURCES.extend(
    [
        (
            "AI 메모리 고객선점·CPO·광연결",
            "(삼성전자 OR SK하이닉스 OR 마이크론 OR 엔비디아 OR 애플) "
            "(HBM OR CPO OR 공동패키징광학 OR co-packaged optics OR 광연결 OR 광인터커넥트 OR 계약부채) "
            "(고객선점 OR 선구매 OR 공급 OR 양산 OR 논문 OR 상용화 OR 가격) "
            "(site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:edaily.co.kr OR "
            "site:etnews.com OR site:dt.co.kr OR site:hankyung.com)",
        ),
        (
            "반도체 팹 용수·수처리·소부장 수주",
            "(삼성전자 OR SK하이닉스 OR 반도체 팹 OR 반도체공장 OR 반도체 공장) "
            "(용수 OR 초순수 OR 수처리 OR 폐수처리 OR 소재 OR 장비) "
            "(수주 OR 공급계약 OR 계약 OR 증설 OR 양산 OR 투자 OR 인허가) "
            "(site:yna.co.kr OR site:newsis.com OR site:etnews.com OR site:edaily.co.kr OR "
            "site:mk.co.kr OR site:fnnews.com OR site:thebell.co.kr)",
        ),
        (
            "상장사 주주환원·조회공시·사업재편",
            "(삼성전자 OR SK하이닉스 OR 대기업 OR 코스피) "
            "(주주환원 OR 현금배당 OR 자사주소각 OR 자사주 소각 OR 조회공시 OR 조회 공시 OR "
            "사업재편 OR 자회사 상장 OR 지분매각 OR 지분 매각) "
            "(이사회 OR 결정 OR 공시 OR 요구 OR 검토 OR 확정) "
            "(site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:edaily.co.kr OR "
            "site:fnnews.com OR site:hankyung.com OR site:asiae.co.kr)",
        ),
        (
            "AI 인프라 차입·장기국채·장기금리",
            "(빅테크 OR 엔비디아 OR 오픈AI OR 마이크로소프트 OR 아마존 OR 구글 OR 메타 OR 데이터센터) "
            "(차입 OR 회사채 OR 채무보증 OR 채무 보증 OR 채권발행 OR 장기국채 OR 미국채30년물 OR "
            "미국채 30년물 OR 장기금리 OR term premium) "
            "(AI OR 데이터센터 OR 설비투자 OR CAPEX OR 금리 OR 수익률) "
            "(site:reuters.com OR site:ft.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:newsis.com OR site:mk.co.kr OR site:edaily.co.kr)",
        ),
        (
            "공식 AI 협업·전장·로봇·데이터센터",
            "(삼성전자 OR LG전자 OR 현대차 OR SK텔레콤 OR 네이버 OR 카카오 OR 한화) "
            "(엔비디아 OR 오픈AI OR 앤트로픽 OR 마이크로소프트 OR 구글) "
            "(공식화 OR 공식 협력 OR 계약 OR 공급 OR 공동개발 OR 전장 OR 차량 OR 로봇 OR 데이터센터) "
            "(site:yna.co.kr OR site:newsis.com OR site:edaily.co.kr OR site:etnews.com OR "
            "site:mk.co.kr OR site:dt.co.kr OR site:biz.chosun.com)",
        ),
        (
            "K방산 미국·NATO 시험·수주",
            "(한화에어로스페이스 OR 한화 OR LIG넥스원 OR 현대로템 OR 한국항공우주 OR K9 OR K2 OR "
            "천궁 OR 레드백 OR FA-50) "
            "(미 육군 OR 미국 육군 OR NATO OR 시험평가 OR 선정 OR 수주 OR 계약 OR 양산 OR 수출) "
            "(site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:edaily.co.kr OR "
            "site:fnnews.com OR site:biz.chosun.com OR site:dt.co.kr)",
        ),
    ]
)

PRIORITY_TERMS.update(
    {
        "cpo": 18,
        "co-packaged optics": 18,
        "공동패키징광학": 18,
        "광 연결": 17,
        "광연결": 17,
        "고객선점": 17,
        "고객 선점": 17,
        "선구매": 17,
        "계약부채": 17,
        "계약 부채": 17,
        "조회공시": 17,
        "조회 공시": 17,
        "공시 요구": 16,
        "현금배당": 17,
        "현금 배당": 17,
        "대규모 주주환원": 18,
        "역대급 주주환원": 18,
        "자회사 상장": 16,
        "수처리": 17,
        "초순수": 17,
        "반도체 수처리": 18,
        "용수 공급": 17,
        "파운드리 가격 인상": 18,
        "파운드리 가격": 16,
        "메모리 연구소": 17,
        "메모리 전문연구소": 18,
        "대미 메모리 연구": 18,
        "ai 차입": 18,
        "ai 빚": 17,
        "채무보증": 17,
        "채무 보증": 17,
        "미국채 30년물": 17,
        "미국채30년물": 17,
        "장기금리": 16,
        "장기 금리": 16,
        "협업 공식화": 17,
        "공식 협력": 16,
        "ai 차량": 16,
        "전력사용량": 15,
        "재생에너지 발전소": 17,
        "미 육군": 17,
        "미국 육군": 17,
        "k9": 18,
        "테슬라 ceo 보상": 18,
        "tesla ceo compensation": 18,
        "tesla ceo pay": 17,
        "머스크 보상": 16,
        "musk compensation": 16,
        "musk pay package": 16,
        "보상 패키지": 16,
        "pay package": 16,
        "성과보상": 16,
        "성과 보상": 16,
        "performance award": 18,
        "stock award": 17,
        "주주 승인": 15,
        "shareholder approval": 17,
        "희석": 15,
        "dilution": 15,
    }
)

FULL_ATTACHMENT_IMPACT_TERMS = {
    "돈 버는 능력": (
        "cpo", "co-packaged optics", "공동패키징광학", "광연결",
        "고객선점", "선구매", "계약부채", "수처리", "초순수",
        "반도체 수처리", "파운드리 가격 인상", "메모리 연구소",
        "대미 메모리 연구", "메모리 전문연구소", "공식 협력", "협업 공식화", "ai 차량", "k9", "미 육군",
        "미국 육군", "재생에너지 발전소",
        "주주 승인", "shareholder approval", "이사회 승인", "board approval",
        "베스팅", "vesting", "performance award",
    ),
    "할인율": (
        "ai 차입", "ai 빚", "채무보증", "채무 보증", "미국채 30년물",
        "미국채30년물", "장기금리", "장기 금리",
    ),
    "수급": (
        "현금배당", "현금 배당", "대규모 주주환원", "역대급 주주환원",
        "조회공시", "조회 공시", "자회사 상장",
        "테슬라 ceo 보상", "tesla ceo compensation", "tesla ceo pay",
        "머스크 보상", "musk compensation", "musk pay package", "보상 패키지",
        "pay package", "성과보상", "성과 보상", "performance award", "stock award",
        "희석", "dilution",
    ),
    "시간표": (
        "조회공시", "조회 공시", "공시 요구", "수처리", "초순수",
        "반도체 수처리", "메모리 연구소", "메모리 전문연구소", "공식 협력", "협업 공식화", "미 육군",
        "미국 육군", "재생에너지 발전소",
    ),
}
for _impact_label, _impact_terms in FULL_ATTACHMENT_IMPACT_TERMS.items():
    IMPACT_TERMS[_impact_label] = tuple((*IMPACT_TERMS[_impact_label], *_impact_terms))

# Rebuild after every extension. A stale material tuple would score a new lane
# but then silently discard it during the final material-title quality gate.
MATERIAL_TERMS = tuple(PRIORITY_TERMS)


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
    if (
        any(alias in text for alias in ("삼성전자", "sk하이닉스", "하이닉스"))
        and any(term in text for term in ("주주환원", "현금배당", "자사주 소각", "자사주소각"))
    ):
        return f"korean_business:shareholder_return:{event_date}"
    if (
        any(alias in text for alias in ("삼성전자", "sk하이닉스", "하이닉스"))
        and any(term in text for term in ("조회공시", "조회 공시", "공시 요구"))
    ):
        return f"korean_business:krx_inquiry_disclosure:{event_date}"
    if (
        any(alias in text for alias in ("sk하이닉스", "하이닉스"))
        and any(term in text for term in ("cpo", "공동패키징광학", "광연결", "광 연결"))
    ):
        return f"korean_business:skhynix_cpo:{event_date}"
    if (
        "ai" in text
        and any(term in text for term in ("차입", "ai 빚", "채무보증", "채무 보증"))
        and any(term in text for term in ("장기금리", "장기 금리", "미국채 30년물", "미국채30년물"))
    ):
        return f"global_market:ai_financing_long_yield:{event_date}"
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

