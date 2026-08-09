from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gamejoa_preopen_news_radar_full_compact_runner as radar
import gamejoa_preopen_news_radar_fda_quality_runner as quality
from khs_article_detail import extract_article_detail


CASES = (
    ("NAVER, 엔비디아 대상 1조4809억 규모 유상증자 결정", "유상증자", "수급"),
    ("SK하이닉스, 10개사와 LTA 장기공급계약 체결", "lta", "돈 버는 능력"),
    ("코스피, 2거래일 연속 매도 사이드카 발동", "사이드카", "수급"),
    ("코스닥 서킷브레이커 1단계 발동", "서킷브레이커", "수급"),
    ("구마모토 규모 7.1 강진, TSMC 공장 중단", "강진", "돈 버는 능력"),
    ("10년물 미국채 금리 4.7%, 트럼프 2기 최고", "미국채", "할인율"),
    ("삼성전기, 10개 고객과 MLCC 장기공급계약", "mlcc", "돈 버는 능력"),
    ("미국, 외국산 휴머노이드 수입 제한", "수입 제한", "할인율"),
    ("엔비디아, AI 순환금융 우려 재점화", "순환금융", "돈 버는 능력"),
    ("미국, 글로벌파운드리스에 AI 광반도체 개발비 3억달러 지원", "개발비", "돈 버는 능력"),
    ("중국 정치국, 성장 둔화 대응 정책 지원·재정 지출 약속", "정치국", "할인율"),
    ("국민연금, 국내주식 수익률 106% 기록", "국민연금", "수급"),
    ("국고채 금리, 미국 금리 여파에 동반 상승", "국고채", "할인율"),
    ("LG디스플레이, 1.5조 국민성장펀드 투자 유치", "국민성장펀드", "돈 버는 능력"),
    ("최태원 회장, SK하이닉스 주식 3620주 매수", "내부자 직접매수", "수급"),
    ("양현석 총괄 프로듀서, YG 주식 46만1940주 장내매수", "내부자 직접매수", "수급"),
    (
        "유안타증권, 단일종목 레버리지 ETF 규제 코스닥 반등 계기",
        "단일종목 레버리지",
        "수급",
    ),
    ("트럼프, 다이아몬드·석유·가스·구리 관세 면제 발표", "관세 면제", "할인율"),
    ("삼성전자, HBM4 매출 3배 증가·HBM4E 샘플 출하", "hbm4", "돈 버는 능력"),
    ("LG AI연구원, 7500억개 K-엑사원 2.0 공개", "공개", "시간표"),
    ("LG CNS, 상반기 역대 최대 매출 2.8조원", "매출", "돈 버는 능력"),
    ("8월 의무보유등록 45개사 1억8078만주 해제", "의무보유", "수급"),
    ("온코닉 자큐보, 인도 CDSCO 품목허가 권고", "품목허가", "시간표"),
    ("외국인 증권거래에 외환거래 하루 1200억달러", "외환거래", "수급"),
    ("키옥시아 영업익 시장 예상 7% 하회·주식분할", "영업익", "돈 버는 능력"),
    ("AI 패권 경쟁, 빅테크 AI 투자 1조달러·전력 인프라 확대", "ai 투자", "돈 버는 능력"),
    ("단일종목 레버리지 규제 첫날 거래대금 12조원대서 3조원대로 급감", "거래대금", "수급"),
    ("7월 수출 실적 989억달러·반도체 수출 역대 2위", "수출 실적", "돈 버는 능력"),
    ("미 연준, 연 8회 금리결정 회의 축소 검토", "회의 축소", "할인율"),
    ("미 재무부, 엔화 약세 대응 환율 개입 정황", "환율 개입", "할인율"),
    ("CXMT, D램 생산 능력 웨이퍼 월 30만장으로 증설", "생산 능력", "돈 버는 능력"),
    ("아마존 AWS 매출·클라우드 성장, AI 투자 확대", "aws 매출", "돈 버는 능력"),
    ("트럼프, 이란 추가 공격 임박 경고·쿠웨이트 드론 공격", "추가 공격", "할인율"),
    ("젤렌스키, 트럼프에 스타링크 타격 승인 요청", "스타링크", "수급"),
    ("가자 휴전, 하마스 무장해제·평화 협정 시험대", "가자 휴전", "할인율"),
    ("단일종목 레버리지 ETF 국정조사 요구", "국정조사", "수급"),
    ("서울 아파트 정전 잇따라…폭염에 변압기 과부하", "아파트 정전", "돈 버는 능력"),
)


ATTACHED_CASES = (
    ("리사 쿡 연준 이사, 인플레 지속 시 금리 인상 준비", "금리 인상", "할인율"),
    ("삼성전자, AI 가속기용 zHBM 차세대 3D 메모리 공개", "zhbm", "돈 버는 능력"),
    ("SK하이닉스, 인디애나 첨단 패키징 공장 2028년 양산 목표", "첨단 패키징", "시간표"),
    ("이란·오만, 호르무즈 해협 통항 합의 협상 최종 단계", "호르무즈", "할인율"),
    ("경상수지 497억달러 흑자, 반도체 수출 호조", "경상수지", "돈 버는 능력"),
    ("코스피 4%대 낙폭 확대, 매도 사이드카 발동", "매도 사이드카", "수급"),
)


AUGUST9_CASES = (
    ("SK하이닉스, 충칭 패키징 공장 지분 매각 검토", "지분 매각", "돈 버는 능력"),
    ("SK하이닉스 통합노조 신설 추진, 성과급 주식 보상 논의", "통합노조", "수급"),
    ("삼성전자 테일러 팹, 연말 가동 앞두고 현지 인력 채용", "테일러 팹", "시간표"),
    ("정부, 전력반도체 생산기지 투자 지원 확대", "전력반도체", "시간표"),
    ("인도네시아 AI 슈퍼컴퓨터에 한국 HBM·NPU·보안 장비 탑재", "슈퍼컴퓨터", "돈 버는 능력"),
)


def main() -> int:
    failures = []
    now = datetime.now().astimezone()
    fda_runner_source = (ROOT / "scripts" / "gamejoa_preopen_news_radar_fda_quality_runner.py").read_text(
        encoding="utf-8"
    )
    if "return original_classify(row, now)" not in fda_runner_source:
        failures.append("production_fda_wrapper=title_fallback_not_preserved")
    if (
        'if row.get("_article_verification_failed") or not row.get("body_verified"):\n'
        "                return None"
    ) in fda_runner_source:
        failures.append("production_fda_wrapper=body_fetch_failure_still_blocked")
    for index, (title, required_term, required_impact) in enumerate(CASES + ATTACHED_CASES + AUGUST9_CASES):
        row = {
            "title": title,
            "summary": title,
            "published": now,
        }
        score, _timestamp = radar.korean_business_detail_priority(row)
        material = [
            term
            for term in radar.KOREAN_BUSINESS_MATERIAL_TERMS
            if radar.korean_business_title_has_material_term(title.lower(), term)
        ]
        impacts = radar.korean_business_impacts(title.lower(), [])
        if score < 10:
            failures.append(f"case={index} priority={score}")
        if required_term not in material:
            failures.append(f"case={index} missing_material={required_term}")
        if required_impact not in impacts:
            failures.append(f"case={index} missing_impact={required_impact}")

    expected_domains = {
        "newsis.com",
        "chosun.com",
        "wowtv.co.kr",
        "kmib.co.kr",
        "zdnet.co.kr",
        "techm.kr",
        "investchosun.com",
        "inews24.com",
        "scmp.com",
        "isplus.com",
        "reuters.com",
        "apnews.com",
        "cnbc.com",
        "ezyeconomy.com",
        "theguru.co.kr",
        "ngetnews.com",
        "magazine.hankyung.com",
    }
    missing_domains = expected_domains - set(radar.KOREAN_BUSINESS_PUBLISHER_DOMAINS)
    if missing_domains:
        failures.append(f"missing_domains={sorted(missing_domains)}")

    if not radar.is_korean_business_row({
        "source": "뉴시스 경제",
        "publisher": "뉴시스",
        "link": "https://www.newsis.com/view/example",
    }):
        failures.append("korean_business_source=newsis_not_routed")
    if not radar.is_korean_business_row({
        "source": "AP",
        "publisher": "AP",
        "link": "https://apnews.com/article/example",
        "title": "트럼프, 이란 추가 공격 임박 경고·쿠웨이트 드론 공격 보고",
    }):
        failures.append("trusted_geopolitical_source=ap_not_routed")

    expected_direct_sources = {
        "https://www.newsis.com/RSS/sokbo.xml",
        "https://www.newsis.com/RSS/economy.xml",
        "https://www.newsis.com/RSS/bank.xml",
        "https://www.newsis.com/RSS/industry.xml",
        "https://www.newsis.com/RSS/entertain.xml",
    }
    configured_source_urls = {source[1] for source in radar.base.SOURCES}
    missing_direct_sources = expected_direct_sources - configured_source_urls
    if missing_direct_sources:
        failures.append(f"missing_direct_sources={sorted(missing_direct_sources)}")

    search_names = {source[0] for source in radar.KOREAN_BUSINESS_SEARCH_SOURCES}
    if "국내 경영진·최대주주 직접매수" not in search_names:
        failures.append("missing_search=국내 경영진·최대주주 직접매수")
    if "단일종목 레버리지 규제·코스닥 수급" not in search_names:
        failures.append("missing_search=단일종목 레버리지 규제·코스닥 수급")
    if "국내 대기업 전략기술 출자·스타트업 투자" not in search_names:
        failures.append("missing_search=국내 대기업 전략기술 출자·스타트업 투자")
    for required_search in (
        "기업 실적·공급부족·시장점유율",
        "AI 모델·데이터센터 구축",
        "바이오 허가·상업화",
        "수급·자본행사·외환",
        "트럼프 관세·원자재·중동",
        "빅테크 AI 투자·반도체·전력 인프라 CAPEX",
        "단일종목 레버리지 규제 시행효과·거래급감",
        "한국 월간 수출·반도체 수출·무역수지",
        "연준 FOMC 회의체계·정책결정 일정",
        "미국·일본 환율개입·통화공조",
        "중국 DRAM 생산능력·메모리 증설",
        "하이퍼스케일러 실적·클라우드 성장·AI CAPEX",
        "트럼프 이란·걸프 군사긴장",
        "우크라이나 스타링크 군사사용 승인",
        "가자 휴전·하마스 무장해제",
        "단일종목 레버리지 국정조사·청문회",
        "한미 조선협력·미국 군함 조선소·AI 용접",
    ):
        if required_search not in search_names:
            failures.append(f"missing_search={required_search}")

    for required_search in (
        "연준 위원 발언·미국 고용·서비스 물가",
        "AI 메모리 아키텍처·엔비디아 사양 변경",
        "SK하이닉스 해외 패키징·국내 대형 CAPEX",
        "이란·호르무즈 협상·해협 통항",
        "한국 경상수지·반도체 수출·외국인 자금",
        "코스피 사이드카·단일종목 레버리지 수급 변화",
        "SK하이닉스 중국 패키징 지분·운영 재편",
        "SK하이닉스 노사·성과급 주식 보상",
        "삼성 테일러 팹 가동·미국 파운드리 인력",
        "전력반도체 정책·대형 투자·생산기지",
        "해외 AI 슈퍼컴퓨터·한국 반도체·보안 수주",
    ):
        if required_search not in search_names:
            failures.append(f"missing_attached_search={required_search}")

    leverage_effect_urls = {
        "https://www.kmib.co.kr/article/view.asp?arcid=9000000424&cp=nv",
        "https://view.asiae.co.kr/article/2026073116442893935",
    }
    configured_direct_urls = {
        row.get("url") for row in radar.coverage.DIRECT_ARTICLES
    }
    if not leverage_effect_urls.issubset(configured_direct_urls):
        failures.append("missing_direct_articles=single_stock_leverage_rule_effect")

    leverage_effect_a = {
        "news": "레버리지 규제 첫날 거래 ‘뚝’…12조원대서 3조원대로 급감",
        "published": now,
    }
    leverage_effect_b = {
        "news": "단일레버리지 예탁금 상향 첫날…거래량 감소, 개미는 매도",
        "published": now,
    }
    if radar.alert_dedup_key(leverage_effect_a) != radar.alert_dedup_key(leverage_effect_b):
        failures.append("semantic_duplicate=single_stock_leverage_rule_effect")

    if not any(
        row.get("url") == "https://www.mk.co.kr/article/12113486"
        and row.get("publisher") == "매일경제"
        for row in radar.coverage.DIRECT_ARTICLES
    ):
        failures.append("missing_direct_article=bigtech_ai_capex_one_trillion")

    if not any(
        row.get("url") == "https://www.yna.co.kr/view/AKR20260730034600008"
        for row in radar.coverage.DIRECT_ARTICLES
    ):
        failures.append("missing_direct_article=yuanta_single_stock_leverage_kosdaq")

    if not any(
        row.get("url") == (
            "https://biz.chosun.com/it-science/ict/2026/07/30/"
            "E5GYIUCGO5HNPGVB6P7ZT3IBWA/"
        )
        and row.get("fetch_url") == (
            "https://biz.chosun.com/it-science/ict/2026/07/30/"
            "E5GYIUCGO5HNPGVB6P7ZT3IBWA/?outputType=amp"
        )
        for row in radar.coverage.DIRECT_ARTICLES
    ):
        failures.append("missing_direct_article=samsung_strategic_technology_funds_amp")

    duplicate_a = {
        "news": "삼성전기 2분기 영업이익 4404억원, 10개 고객과 MLCC 장기계약",
        "published": now,
    }
    duplicate_b = {
        "news": "삼성전기, 하이퍼스케일러 10여곳과 MLCC LTA 체결",
        "published": now,
    }
    if radar.alert_dedup_key(duplicate_a) != radar.alert_dedup_key(duplicate_b):
        failures.append("semantic_duplicate=mlcc_lta")

    structured_title = "엔비디아, 오픈AI 데이터센터에 2500억달러 보증 논의"
    structured_body = (
        "엔비디아가 오픈AI의 오하이오 데이터센터 자금조달에 "
        "2500억달러 규모의 보증을 제공하는 방안을 논의하고 있다. "
        "프로젝트는 10기가와트 규모이며 구체 조건은 확정되지 않았다. "
        "보증이 성사되면 투자등급 신용등급이 없는 오픈AI의 조달 조건이 "
        "개선될 수 있지만, 반도체 구매 비용은 이번 보증 대상에 포함되지 않는다. "
        "전체 사업비와 전력 배분, 임차 계약은 후속 협상에서 확정될 예정이다."
    )
    structured_html = f"""
    <html><head><script type="application/ld+json">
    {{"@context":"https://schema.org","@type":"NewsArticle",
      "headline":"{structured_title}","articleBody":"{structured_body}",
      "datePublished":"2026-07-27T15:37:00+09:00"}}
    </script></head><body><div>동적 기사 본문</div></body></html>
    """
    detail = extract_article_detail(structured_html, structured_title)
    if not detail.get("body_verified") or "2500억달러" not in detail.get("body", ""):
        failures.append("structured_article_body=not_verified")

    insider_core = radar.detailed_article_core(
        "최태원 회장, SK하이닉스 주식 3620주 매수",
        "최태원 SK그룹 회장이 SK하이닉스 주식 3620주를 장내 매수했다.",
    )
    if "최태원" not in insider_core or "3620주" not in insider_core or "개인 명의" not in insider_core:
        failures.append(f"insider_purchase_core={insider_core}")

    viral_title = '"일론 머스크인 줄 알았네"… SNS 달군 中 \'도플갱어\' 바비큐 사장'
    contaminated_core = "삼성전자 사장 171만8000원, 10주를 개인 명의로 매수했습니다."
    contaminated_sentences = [
        "삼성전자 사장이 삼성전자 주식 10주를 171만8000원에 개인 명의로 매수했다."
    ]
    if radar.insider_purchase_fact(viral_title, contaminated_sentences):
        failures.append("viral_related_article_insider_fact=not_blocked")
    if radar.korean_title_core_aligned(viral_title, contaminated_core):
        failures.append("viral_generic_role_alignment=not_blocked")

    reporter_prefixed_core = radar.detailed_article_core(
        "워시, FOMC 정례회의 연 8회 축소 검토",
        (
            "[이데일리 김윤지 기자] 케빈 워시 연준 의장이 현재 연 8회인 "
            "연방공개시장위원회 정례회의 횟수를 줄이는 방안을 검토하고 있다."
        ),
    )
    if "기자" in reporter_prefixed_core or "이데일리" in reporter_prefixed_core:
        failures.append(f"reporter_boilerplate_not_removed={reporter_prefixed_core}")

    viral_alert = {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "뉴시스",
        "news": viral_title,
        "source_title": viral_title,
        "source_abstract": "",
        "policy_plain_summary": contaminated_core,
        "telegram_core_fact": contaminated_core,
        "link": "https://www.newsis.com/view/NISX20260731_0003730920",
        "korean_business_news": True,
        "body_verified": True,
    }
    if radar.source_output_aligned(viral_alert):
        failures.append("viral_source_output_alignment=not_blocked")
    if not radar.is_low_value_market_commentary(viral_alert):
        failures.append("viral_low_value_filter=not_blocked")

    entertainment_core = radar.detailed_article_core(
        "YG 양현석 200억·JYP 박진영 50억 자사주 매입",
        (
            "양현석 YG 총괄 프로듀서가 200억원을 들여 자사 주식 "
            "46만1940주를 장내 매수했다. "
            "박진영 JYP CCO가 50억원을 들여 자사 주식 "
            "6만200주를 장내 매수했다."
        ),
    )
    for fact in ("양현석", "200억원", "46만1940주", "박진영", "50억원", "6만200주"):
        if fact not in entertainment_core:
            failures.append(f"entertainment_insider_core_missing={fact}:{entertainment_core}")

    company_buyback_core = radar.detailed_article_core(
        "현대차, 1조원 규모 자사주 취득·소각",
        "현대차는 이사회에서 1조원 규모의 자사주를 취득해 전량 소각하기로 결정했다.",
    )
    if "개인 명의" in company_buyback_core:
        failures.append(f"company_buyback_misclassified={company_buyback_core}")

    leverage_core = radar.detailed_article_core(
        "유안타증권, 단일종목 레버리지 ETF 규제 코스닥 반등 계기",
        (
            "오는 31일부터 단일종목 레버리지 ETF 규제가 시행된다. "
            "유안타증권 연구원은 대형 반도체 레버리지 상품의 자금 효율과 "
            "접근성이 낮아지면 코스닥 우량 성장주의 상대적 기회비용이 "
            "정상화될 수 있다고 분석했다."
        ),
    )
    for fact in ("31일부터", "대형 반도체", "코스닥 우량 성장주", "수급"):
        if fact not in leverage_core:
            failures.append(f"leverage_kosdaq_core_missing={fact}:{leverage_core}")

    leverage_effect_row = {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "국민일보",
        "title": "레버리지 규제 첫날 거래 ‘뚝’…12조원대서 3조원대로 급감",
        "source_title": "레버리지 규제 첫날 거래 ‘뚝’…12조원대서 3조원대로 급감",
        "source_body": (
            "삼성전자와 SK하이닉스 단일종목 레버리지 ETF 기본예탁금이 "
            "1000만원에서 3000만원으로 상향된 첫날 관련 ETF 거래액이 "
            "12조원대에서 3조원대로 급감했다."
        ),
        "source_abstract": "",
        "link": "https://www.kmib.co.kr/article/view.asp?arcid=9000000424&cp=nv",
        "published": now,
        "body_verified": True,
        "_pinned_direct_article": True,
    }
    leverage_effect_text = " ".join(
        str(leverage_effect_row.get(key) or "")
        for key in ("title", "source_body", "source_abstract")
    ).lower()
    leverage_effect_alert = radar.build_single_stock_leverage_rule_alert(
        leverage_effect_row, now, leverage_effect_text
    )
    if not leverage_effect_alert:
        failures.append("single_stock_leverage_rule_effect_alert=missing")
    else:
        effect_core = str(leverage_effect_alert.get("telegram_core_fact") or "")
        for fact in ("1000만원", "3000만원", "12조원대", "3조원대", "급감"):
            if fact not in effect_core:
                failures.append(
                    f"single_stock_leverage_rule_effect_core_missing={fact}:{effect_core}"
                )
        if "유안타증권" in effect_core or "코스닥 우량 성장주" in effect_core:
            failures.append(
                f"single_stock_leverage_rule_effect_stale_template={effect_core}"
            )

    emergency_leverage_row = {
        "source": "이투데이 경제",
        "publisher": "이투데이",
        "title": "금융당국, 증시 급변에 긴급조치권 확보 추진…단일종목 레버리지 정조준",
        "source_title": "금융당국, 증시 급변에 긴급조치권 확보 추진…단일종목 레버리지 정조준",
        "source_body": (
            "금융당국이 증시 급변 때 단일종목 레버리지 ETF 거래를 제한할 수 있는 "
            "긴급조치권 확보를 추진한다. 기본예탁금 상향에 이은 추가 규제 검토다."
        ),
        "source_abstract": "단일종목 레버리지 ETF 긴급조치권 확보 추진",
        "link": "https://www.etoday.co.kr/news/view/example",
        "published": now,
        "body_verified": True,
    }
    emergency_text = " ".join(
        str(emergency_leverage_row.get(key) or "")
        for key in ("title", "source_body", "source_abstract")
    ).lower()
    emergency_alert = radar.build_single_stock_leverage_rule_alert(
        emergency_leverage_row, now, emergency_text
    )
    if not emergency_alert:
        failures.append("single_stock_leverage_emergency_alert=missing")
    elif not radar.source_output_aligned(emergency_alert):
        failures.append(
            "single_stock_leverage_emergency_alignment=source_body_mismatch:"
            + str(emergency_alert.get("telegram_core_fact") or "")
        )

    aquaculture_row = {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "아시아경제",
        "title": "끓는 바다에 양식어류 3만마리 떼죽음…양식장 시름",
        "source_title": "끓는 바다에 양식어류 3만마리 떼죽음…양식장 시름",
        "source_body": (
            "고수온으로 양식어류 3만마리가 집단 폐사했다. 어가는 출하량 감소와 "
            "추가 피해를 우려하고 지자체는 피해 규모를 조사 중이다."
        ),
        "source_abstract": "고수온 양식어류 집단 폐사",
        "link": "https://n.news.naver.com/article/277/0005797720",
        "published": now,
        "body_verified": True,
    }
    aquaculture_text = " ".join(
        str(aquaculture_row.get(key) or "")
        for key in ("title", "source_body", "source_abstract")
    ).lower()
    aquaculture_alert = radar.build_korea_aquaculture_heat_loss_alert(
        aquaculture_row, now, aquaculture_text
    )
    if not aquaculture_alert:
        failures.append("aquaculture_heat_mass_mortality_alert=missing")
    elif not radar.source_output_aligned(aquaculture_alert):
        failures.append(
            "aquaculture_heat_mass_mortality_alignment=source_body_mismatch:"
            + str(aquaculture_alert.get("telegram_core_fact") or "")
        )

    samsung_fund_row = {
        "source": "국내 신뢰매체 직접감시",
        "publisher": "조선비즈",
        "title": "삼성전자, 반도체 스타트업 투자·기술 확보에 8000억 출자",
        "source_title": "삼성전자, 반도체 스타트업 투자·기술 확보에 8000억 출자",
        "source_body": (
            "30일 삼성전자 공시에 따르면 DS 부문은 SVIC 82호에 4950억원을 출자한다. "
            "DX 부문은 SVIC 83호에 2970억원을 출자한다. "
            "두 펀드는 다음 달부터 각각 13년과 10년간 운용되며 "
            "반도체·AI·로봇 스타트업 기술 확보에 활용된다."
        ),
        "source_abstract": (
            "삼성전자 공시에 따르면 SVIC 82호 4950억원, "
            "SVIC 83호 2970억원 출자가 확정됐다."
        ),
        "link": (
            "https://biz.chosun.com/it-science/ict/2026/07/30/"
            "E5GYIUCGO5HNPGVB6P7ZT3IBWA/"
        ),
        "published": now,
        "body_verified": True,
        "_pinned_direct_article": True,
    }
    samsung_fund_alert = radar.build_verified_korean_business_alert(samsung_fund_row, now)
    if not samsung_fund_alert:
        failures.append("samsung_strategic_fund_alert=missing")
    else:
        samsung_core = str(samsung_fund_alert.get("telegram_core_fact") or "")
        for fact in ("4,950억원", "2,970억원", "7,920억원", "13년", "10년"):
            if fact not in samsung_core:
                failures.append(
                    f"samsung_strategic_fund_core_missing={fact}:{samsung_core}"
                )
        if not samsung_fund_alert.get("_pinned_direct_article"):
            failures.append("samsung_strategic_fund_direct_priority=missing")
        if samsung_fund_alert.get("impacts") != ["돈 버는 능력", "시간표"]:
            failures.append(
                f"samsung_strategic_fund_impacts={samsung_fund_alert.get('impacts')}"
            )

    sovereign_row = {
        "source": "뉴시스 경제",
        "publisher": "뉴시스",
        "title": "정부, 'K-국부펀드'로 전략적 투자 나선다…20조+α 규모",
        "source_title": "정부, 'K-국부펀드'로 전략적 투자 나선다…20조+α 규모",
        "source_body": (
            "정부가 20조원+α 규모의 K-국부펀드를 조성해 국가전략산업에 "
            "전략적으로 투자하고 민간 자금을 연계할 계획이다. "
            "구체적인 출자 구조와 투자 대상, 집행 일정은 후속 발표한다."
        ),
        "link": "https://news.google.com/rss/articles/example-sovereign-fund",
        "published": now,
        "body_verified": False,
        "_article_verification_failed": True,
    }
    sovereign_alert = radar.build_title_verified_korean_business_alert(sovereign_row, now)
    if not sovereign_alert:
        failures.append("korea_sovereign_fund_alert=missing")
    else:
        if not {"돈 버는 능력", "수급", "시간표"}.issubset(set(sovereign_alert.get("impacts") or [])):
            failures.append(f"korea_sovereign_fund_impacts={sovereign_alert.get('impacts')}")
        sovereign_normalized = radar.normalize_alert_for_output(sovereign_alert)
        if not radar.has_decision_impact(sovereign_normalized):
            failures.append(
                "korea_sovereign_fund_decision_impact=blocked:"
                f"{sovereign_normalized.get('guardrail_note')}:"
                f"kind={sovereign_normalized.get('korean_business_kind')}:"
                f"sectors={sovereign_normalized.get('sectors')}"
            )
        sovereign_selected = radar.quality_display_alerts([sovereign_alert], 1)
        if sovereign_selected:
            failures.append(
                "korea_sovereign_fund_title_only=published_without_verified_body"
            )

    hyperscaler_row = {
        "source": "뉴시스 경제",
        "publisher": "뉴시스",
        "title": "아마존, AWS 37% 성장에 자신감…AI 투자 314조원 확대",
        "source_title": "아마존, AWS 37% 성장에 자신감…AI 투자 314조원 확대",
        "source_body": (
            "아마존은 AWS 매출이 37% 성장했다고 밝혔다. "
            "AI 데이터센터와 클라우드 설비에 314조원을 투자해 "
            "GPU와 서버, 전력 인프라를 확대할 계획이다."
        ),
        "link": "https://news.google.com/rss/articles/example-aws-capex",
        "published": now,
        "body_verified": False,
        "_article_verification_failed": True,
    }
    hyperscaler_alert = radar.build_title_verified_korean_business_alert(hyperscaler_row, now)
    if not hyperscaler_alert:
        failures.append("hyperscaler_ai_capex_alert=missing")
    else:
        if not {"돈 버는 능력", "수급", "시간표"}.issubset(set(hyperscaler_alert.get("impacts") or [])):
            failures.append(f"hyperscaler_ai_capex_impacts={hyperscaler_alert.get('impacts')}")
        hyperscaler_normalized = radar.normalize_alert_for_output(hyperscaler_alert)
        if not radar.has_decision_impact(hyperscaler_normalized):
            failures.append(
                "hyperscaler_ai_capex_decision_impact=blocked:"
                f"{hyperscaler_normalized.get('guardrail_note')}:"
                f"kind={hyperscaler_normalized.get('korean_business_kind')}:"
                f"sectors={hyperscaler_normalized.get('sectors')}"
            )
        hyperscaler_selected = radar.quality_display_alerts([hyperscaler_alert], 1)
        if hyperscaler_selected:
            failures.append(
                "hyperscaler_ai_capex_title_only=published_without_verified_body"
            )

    title_only_row = {
        "source": "서울신문",
        "publisher": "서울신문",
        "title": "트럼프, 다이아몬드·석유·가스·구리 관세 면제 발표",
        "source_title": "트럼프, 다이아몬드·석유·가스·구리 관세 면제 발표",
        "source_body": "",
        "source_abstract": "",
        "link": "https://www.seoul.co.kr/news/international/example",
        "published": now,
        "body_verified": False,
        "_article_verification_failed": True,
    }
    title_only_alert = radar.build_title_verified_korean_business_alert(title_only_row, now)
    if not title_only_alert:
        failures.append("trusted_title_material_event=missing")
    else:
        if title_only_alert.get("status") != "예비":
            failures.append(f"trusted_title_status={title_only_alert.get('status')}")
        if not title_only_alert.get("title_fact_verified") or title_only_alert.get("body_verified"):
            failures.append("trusted_title_verification_flags=invalid")
        if not str(title_only_alert.get("telegram_core_fact") or "").startswith(
            "공개된 제목에 따르면"
        ):
            failures.append(
                f"trusted_title_core={title_only_alert.get('telegram_core_fact')}"
            )
        mismatched_alert = dict(title_only_alert)
        mismatched_alert.update(
            {
                "news": "구마모토 규모 7.1 강진, TSMC 공장 중단",
                "original_news": "구마모토 규모 7.1 강진, TSMC 공장 중단",
                "source_title": "구마모토 규모 7.1 강진, TSMC 공장 중단",
                "telegram_core_fact": "외국인이 삼성전자 주식을 순매수했습니다.",
                "policy_plain_summary": "외국인이 삼성전자 주식을 순매수했습니다.",
            }
        )
        synced = radar.compact_quality_final_alerts(
            [mismatched_alert, title_only_alert],
            2,
        )
        if synced:
            failures.append(
                "title_only_render_json_delivery_sync="
                f"{[(row.get('source_title'), row.get('_exclusion_reason')) for row in synced]}"
            )

    vague_title_row = {
        "source": "지디넷코리아",
        "publisher": "지디넷코리아",
        "title": "데이터센터가 국가 경쟁력이다",
        "source_title": "데이터센터가 국가 경쟁력이다",
        "source_body": "",
        "link": "https://zdnet.co.kr/view/?no=example",
        "published": now,
        "body_verified": False,
        "_article_verification_failed": True,
    }
    if radar.build_title_verified_korean_business_alert(vague_title_row, now):
        failures.append("vague_title_fallback=not_blocked")

    opinion_alert = {
        "korean_business_news": True,
        "source_title": "“반도체 투자, 의심할 때 사서 확신할 때 팔아야”…그게 언제일까요",
        "news": "“반도체 투자, 의심할 때 사서 확신할 때 팔아야”…그게 언제일까요",
    }
    if not radar.is_low_value_market_commentary(opinion_alert):
        failures.append("low_value_market_commentary=not_blocked")

    leverage_opinion_alert = {
        "korean_business_news": True,
        "source_title": "'ETF 아버지' 또 경고…단일종목 레버리지에 투자하지 않는 것이 최선",
        "news": "'ETF 아버지' 또 경고…단일종목 레버리지에 투자하지 않는 것이 최선",
    }
    if not radar.is_low_value_market_commentary(leverage_opinion_alert):
        failures.append("leverage_opinion_commentary=not_blocked")

    retrospective_alert = {
        "korean_business_news": True,
        "source_title": "좋은 꿈을 꾸었습니다…한때 수익률 106% 국민연금, 지금은?",
        "news": "좋은 꿈을 꾸었습니다…한때 수익률 106% 국민연금, 지금은?",
    }
    if not radar.is_low_value_market_commentary(retrospective_alert):
        failures.append("retrospective_clickbait=not_blocked")

    if not radar.korean_business_source_allowed({
        "publisher": "뉴시스",
        "source": "뉴시스 경제",
        "link": "https://news.google.com/rss/articles/example",
    }):
        failures.append("trusted_publisher_google_news_link=blocked")

    glyph_amounts = radar.extract_foreign_amounts("7월 수출 988.9억弗·반도체 400억弗 돌파")
    if len(glyph_amounts) != 2 or any(item.get("code") != "USD" for item in glyph_amounts):
        failures.append(f"dollar_glyph_not_normalized={glyph_amounts}")
    glyph_core = radar.apply_krw_conversions(
        "7월 수출 988.9억弗을 기록했습니다.",
        {
            "amounts": [
                {
                    "original": "988.9억달러",
                    "krw_value": 137_000_000_000_000,
                    "krw_text": "137조원",
                }
            ]
        },
    )
    if "988.9억달러(약 137조원)" not in glyph_core or "弗" in glyph_core:
        failures.append(f"dollar_glyph_conversion_core={glyph_core}")

    export_row = {
        "source": "한국경제",
        "publisher": "한국경제",
        "title": "7월 수출 989억달러로 62.8% 증가·반도체 410억달러 역대 2위",
        "source_title": "7월 수출 989억달러로 62.8% 증가·반도체 410억달러 역대 2위",
        "source_body": (
            "7월 수출은 989억달러로 전년 대비 62.8% 증가했다. "
            "반도체 수출은 410억달러로 179% 늘어 역대 월간 2위를 기록했다."
        ),
        "link": "https://www.hankyung.com/article/example-exports",
        "published": now,
        "body_verified": True,
    }
    export_alert = radar.build_verified_korean_business_alert(export_row, now)
    if not export_alert or export_alert.get("korean_business_kind") != "korea_monthly_exports":
        failures.append(f"korea_monthly_exports_alert={export_alert}")
    else:
        export_core = str(export_alert.get("telegram_core_fact") or "")
        for fact in ("989억달러", "62.8%", "410억달러", "179%"):
            if fact not in export_core:
                failures.append(f"korea_monthly_exports_core_missing={fact}:{export_core}")

    fed_title_row = {
        "source": "머니투데이",
        "publisher": "머니투데이",
        "title": "워시 미 연준 의장, 연 8회 금리 결정 회의 축소 검토",
        "source_title": "워시 미 연준 의장, 연 8회 금리 결정 회의 축소 검토",
        "source_body": "",
        "link": "https://www.mt.co.kr/world/example-fed-meetings",
        "published": now,
        "body_verified": False,
        "_article_verification_failed": True,
    }
    fed_title_alert = radar.build_title_verified_korean_business_alert(fed_title_row, now)
    if not fed_title_alert or fed_title_alert.get("korean_business_kind") != "fed_meeting_structure":
        failures.append(f"fed_meeting_title_fallback={fed_title_alert}")
    else:
        if fed_title_alert.get("status") != "예비":
            failures.append(f"fed_meeting_title_status={fed_title_alert.get('status')}")

    fx_row = {
        "source": "이투데이",
        "publisher": "이투데이",
        "title": "일본, 60조원 안팎 환율 개입 추정·미일 공조설 확산",
        "source_title": "일본, 60조원 안팎 환율 개입 추정·미일 공조설 확산",
        "source_body": "엔화 약세를 막기 위해 일본 재무부가 외환시장에 개입한 정황이 포착됐다.",
        "link": "https://www.etoday.co.kr/news/view/example-fx",
        "published": now,
        "body_verified": True,
    }
    fx_alert = radar.build_verified_korean_business_alert(fx_row, now)
    if not fx_alert or fx_alert.get("korean_business_kind") != "us_japan_fx_intervention":
        failures.append(f"fx_intervention_alert={fx_alert}")

    china_memory_row = {
        "source": "아시아경제",
        "publisher": "아시아경제",
        "title": "CXMT, D램 생산 능력 웨이퍼 월 30만장으로 증설",
        "source_title": "CXMT, D램 생산 능력 웨이퍼 월 30만장으로 증설",
        "source_body": "CXMT가 2028년까지 D램 웨이퍼 월 생산 능력을 확대할 계획이다.",
        "link": "https://view.asiae.co.kr/article/example-cxmt-capacity",
        "published": now,
        "body_verified": True,
    }
    china_memory_alert = radar.build_verified_korean_business_alert(china_memory_row, now)
    if not china_memory_alert or china_memory_alert.get("korean_business_kind") != "china_memory_capacity":
        failures.append(f"china_memory_capacity_alert={china_memory_alert}")

    iran_row = {
        "source": "AP",
        "publisher": "AP",
        "title": "트럼프, 이란 추가 공격 임박 경고…쿠웨이트는 드론 공격 보고",
        "source_title": "트럼프, 이란 추가 공격 임박 경고…쿠웨이트는 드론 공격 보고",
        "source_body": (
            "트럼프 대통령은 이란에 대한 추가 공격이 임박했다고 경고했다. "
            "쿠웨이트 당국은 자국 시설을 겨냥한 드론 공격을 보고했다."
        ),
        "link": "https://apnews.com/article/example-iran-kuwait",
        "published": now,
        "body_verified": True,
    }
    iran_alert = radar.build_verified_korean_business_alert(iran_row, now)
    if not iran_alert or iran_alert.get("korean_business_kind") != "iran_gulf_attack_escalation":
        failures.append(f"iran_gulf_attack_alert={iran_alert}")
    else:
        iran_core = str(iran_alert.get("telegram_core_fact") or "")
        if "추가 공격" not in iran_core or "쿠웨이트" not in iran_core or "드론 공격" not in iran_core:
            failures.append(f"iran_gulf_attack_core={iran_core}")

    starlink_row = {
        "source": "Reuters",
        "publisher": "Reuters",
        "title": "젤렌스키, 트럼프에 러시아 타격용 스타링크 승인 지원 요청",
        "source_title": "젤렌스키, 트럼프에 러시아 타격용 스타링크 승인 지원 요청",
        "source_body": "젤렌스키 대통령은 트럼프 대통령에게 러시아 타격 지원을 위한 스타링크 사용 승인을 도와달라고 요청했다.",
        "link": "https://www.reuters.com/world/example-starlink-request",
        "published": now,
        "body_verified": True,
    }
    starlink_alert = radar.build_verified_korean_business_alert(starlink_row, now)
    if not starlink_alert or starlink_alert.get("korean_business_kind") != "ukraine_starlink_military_request":
        failures.append(f"ukraine_starlink_alert={starlink_alert}")
    else:
        if starlink_alert.get("status") != "예비":
            failures.append(f"ukraine_starlink_status={starlink_alert.get('status')}")
        starlink_core = str(starlink_alert.get("telegram_core_fact") or "")
        if "요청" not in starlink_core or "승인했다" in starlink_core:
            failures.append(f"ukraine_starlink_core={starlink_core}")

    gaza_row = {
        "source": "AP",
        "publisher": "AP",
        "title": "가자 휴전 위원회, 하마스 무장해제·평화 협정 시험대",
        "source_title": "가자 휴전 위원회, 하마스 무장해제·평화 협정 시험대",
        "source_body": "2주간의 가자 휴전은 하마스 무장해제와 평화 협정 개시를 목표로 한다.",
        "link": "https://apnews.com/article/example-gaza-ceasefire",
        "published": now,
        "body_verified": True,
    }
    gaza_alert = radar.build_verified_korean_business_alert(gaza_row, now)
    if not gaza_alert or gaza_alert.get("korean_business_kind") != "gaza_ceasefire_disarmament":
        failures.append(f"gaza_ceasefire_alert={gaza_alert}")

    inquiry_row = {
        "source": "메트로신문",
        "publisher": "메트로신문",
        "title": "국민의힘, 단일종목 레버리지 ETF 국정조사 요구",
        "source_title": "국민의힘, 단일종목 레버리지 ETF 국정조사 요구",
        "source_body": "국민의힘은 단일종목 레버리지 ETF 사태의 국정조사를 요구하겠다고 밝혔다.",
        "link": "https://www.metroseoul.co.kr/article/example-leverage-inquiry",
        "published": now,
        "body_verified": True,
    }
    inquiry_alert = radar.build_verified_korean_business_alert(inquiry_row, now)
    if not inquiry_alert or inquiry_alert.get("korean_business_kind") != "single_stock_leverage_parliamentary_inquiry":
        failures.append(f"leverage_parliamentary_inquiry_alert={inquiry_alert}")
    elif inquiry_alert.get("status") != "예비":
        failures.append(f"leverage_parliamentary_inquiry_status={inquiry_alert.get('status')}")

    for noisy, expected in (
        (
            "fn 공유 공유하기 글자크기 글자크기 설정 프린트 구독 구독 증권 증권일반 "
            "코스피가 10.2% 급등했다.",
            "코스피가 10.2% 급등했다.",
        ),
        (
            "페이스북 X(트위터) 메일 URL 복사 작게 보통 크게 "
            "금융당국이 단일종목 레버리지 규제를 시행한다.",
            "금융당국이 단일종목 레버리지 규제를 시행한다.",
        ),
    ):
        cleaned = radar.clean_article_summary_text(noisy)
        if cleaned != expected:
            failures.append(f"article_ui_noise_not_removed={cleaned}")

    insider_core = radar.insider_purchase_fact(
        "최태원 회장, SK하이닉스 주식 3620주 매수",
        [
            "SK하이닉스는 최대주주등소유주식변동신고서를 통해 "
            "최태원 회장이 3620주를 개인 명의로 매수했다고 밝혔다."
        ],
    )
    if not insider_core.startswith("최태원 회장 3620주"):
        failures.append(f"insider_buyer_prefix_polluted={insider_core}")

    lta_core = radar.detailed_article_core(
        "SK하이닉스, AI 메모리 수요 강세 속 10개 고객사와 장기공급계약 체결",
        (
            "SK하이닉스가 10개 고객사와 AI 메모리 장기공급계약을 체결했다. "
            "관련 매출은 24조원으로 보도됐다."
        ),
    )
    for fact in ("10개 고객사", "장기공급계약", "24조원"):
        if fact not in lta_core:
            failures.append(f"lta_compact_core_missing={fact}:{lta_core}")

    growth_core = radar.detailed_article_core(
        "국민성장펀드, OLED 초격차 LG디스플레이에 1.5조 저리대출",
        (
            "국민성장펀드가 LG디스플레이에 1.5조원 저리대출을 지원한다. "
            "HBM 공급망 강화를 위해 테크윙에도 500억원을 저리 대출한다."
        ),
    )
    for fact in ("LG디스플레이에 1.5조원", "테크윙에 500억원", "OLED·HBM"):
        if fact not in growth_core:
            failures.append(f"growth_fund_compact_core_missing={fact}:{growth_core}")

    buy_sidecar_core = radar.detailed_article_core(
        "[속보]코스피, 10% 넘는 급등세에 매수 사이드카 발동",
        (
            "코스피가 10.2% 급등했다. 코스피200선물 급등으로 프로그램 "
            "매수호가 효력을 5분간 정지하는 매수 사이드카가 발동됐다."
        ),
    )
    if "매수 사이드카" not in buy_sidecar_core or "5분간" not in buy_sidecar_core:
        failures.append(f"buy_sidecar_compact_core_invalid={buy_sidecar_core}")
    if any(term in buy_sidecar_core for term in ("공유하기", "글자크기", "프린트", "구독")):
        failures.append(f"buy_sidecar_boilerplate_leaked={buy_sidecar_core}")

    duplicate_insider_core = radar.detailed_article_core(
        "최태원 회장, SK하이닉스 주식 3620주 매수",
        (
            "최태원 SK그룹 회장이 SK하이닉스 주식 3620주를 매수했다. "
            "최 회장이 개인 명의로 3620주를 취득했다고 공시했다."
        ),
    )
    if duplicate_insider_core.count("3620주") != 1:
        failures.append(f"duplicate_insider_purchase_not_removed={duplicate_insider_core}")

    mismatch_errors = radar.compact_alert_block_errors(
        "1) [중 | 예비] 일본 강진 직후 기업 방재 허점\n"
        "- 핵심: 코스피 급등으로 프로그램 매수호가를 5분간 정지하는 매수 사이드카가 발동됐다.\n"
        "- 출처: 원문 뉴스보기"
    )
    if "title_core_mismatch" not in mismatch_errors:
        failures.append(f"title_core_mismatch_not_blocked={mismatch_errors}")

    repaired_core = radar.complete_prose_text(
        "미국이 AI 데이터센터용 광반도체 개발비 지원을 확대…",
        limit=radar.GAMEJOA_CORE_MAX_CHARS,
    )
    if "…" in repaired_core or "..." in repaired_core:
        failures.append(f"compact_core_ellipsis_not_repaired={repaired_core}")
    if radar.compact_alert_block_errors(
        "1) [상 | 확정] 미국, AI 광반도체 개발 지원 확대\n"
        f"- 핵심: {repaired_core}\n"
        "- 출처: 원문 뉴스보기"
    ):
        failures.append(f"repaired_compact_core_rejected={repaired_core}")

    malformed_errors = radar.compact_alert_block_errors(
        "1) [상 | 확정] 미국, AI 광반도체 개발 지원 확대\n"
        "- 핵심: 미국이 AI 데이터센터용 광반도체 개발비 지원을 확대…\n"
        "- 출처: 원문 뉴스보기"
    )
    if "truncated_core" not in malformed_errors:
        failures.append(f"malformed_compact_core_not_detected={malformed_errors}")

    search_names = {source[0] for source in radar.KOREAN_BUSINESS_SEARCH_SOURCES}
    if "국내 폭염·전력피크·아파트 정전" not in search_names:
        failures.append("missing_search=국내 폭염·전력피크·아파트 정전")

    heat_outage_row = {
        "title": "서울 아파트 정전 잇따라…극한 폭염에 변압기 과부하",
        "source_title": "서울 아파트 정전 잇따라…극한 폭염에 변압기 과부하",
        "source_body": (
            "극한 폭염과 열대야로 냉방 전력 사용량이 급증하면서 서울 곳곳의 "
            "아파트에서 정전 사고가 발생했다. 변압기 불량과 과부하로 주민들이 불편을 겪었다."
        ),
        "published": now,
        "link": "https://example.com/seoul-heat-grid-outage",
    }
    heat_outage = quality.heat_grid_outage_alert(
        heat_outage_row,
        now,
        f"{heat_outage_row['source_title']} {heat_outage_row['source_body']}".lower(),
    )
    if not heat_outage:
        failures.append("heat_grid_outage=not_promoted")
    else:
        if heat_outage.get("korean_business_kind") != "korea_heat_grid_outage":
            failures.append("heat_grid_outage=wrong_kind")
        if "배전용 변압기/차단기" not in heat_outage.get("sectors", []):
            failures.append("heat_grid_outage=missing_distribution_sector")
        if "정전" not in str(heat_outage.get("telegram_core_fact") or ""):
            failures.append("heat_grid_outage=missing_article_fact")

    generic_heat_row = {
        "title": "서울 폭염과 열대야 이어져",
        "source_body": "서울의 낮 기온이 크게 올라 무더위가 이어졌다.",
        "published": now,
    }
    if quality.heat_grid_outage_alert(
        generic_heat_row,
        now,
        f"{generic_heat_row['title']} {generic_heat_row['source_body']}".lower(),
    ):
        failures.append("heat_grid_outage=generic_weather_not_blocked")

    shipbuilding_row = {
        "title": "HD현대, 미국 군함 조선소에 AI 용접기술 투입…한미 조선협력 본격화",
        "summary": "HD현대가 미국 군함 조선소에 AI 용접기술을 적용하는 협력을 추진한다.",
        "published": now,
    }
    shipbuilding_score, _ = radar.korean_business_detail_priority(shipbuilding_row)
    shipbuilding_text = f"{shipbuilding_row['title']} {shipbuilding_row['summary']}".lower()
    shipbuilding_material = [
        term
        for term in radar.KOREAN_BUSINESS_MATERIAL_TERMS
        if radar.korean_business_title_has_material_term(shipbuilding_text, term)
    ]
    shipbuilding_impacts = radar.korean_business_impacts(shipbuilding_text, [])
    if shipbuilding_score < 10:
        failures.append(f"shipbuilding_ai_welding=priority:{shipbuilding_score}")
    if "ai 용접" not in shipbuilding_material:
        failures.append(f"shipbuilding_ai_welding=material:{shipbuilding_material}")
    if not shipbuilding_impacts:
        failures.append(f"shipbuilding_ai_welding=missing_impact:{shipbuilding_impacts}")

    rendered_format = radar.compact_alert(
        {
            "importance": "상",
            "status": "예비",
            "news": "SK하이닉스, 충칭 패키징 공장 지분 매각 검토",
            "original_news": "SK하이닉스, 충칭 패키징 공장 지분 매각 검토",
            "source_title": "SK하이닉스, 충칭 패키징 공장 지분 매각 검토",
            "source_abstract": "SK하이닉스가 충칭 패키징 공장 지분 매각을 포함한 운영 방안을 검토 중입니다.",
            "telegram_core_fact": "충칭 패키징 공장 지분 매각을 포함한 운영 방안을 검토 중입니다.",
            "policy_plain_summary": "충칭 패키징 공장 지분 매각을 포함한 운영 방안을 검토 중입니다.",
            "link": "https://example.com/hynix-chongqing",
            "publisher": "뉴스1",
            "impacts": ["돈 버는 능력"],
            "sectors": ["반도체/HBM/CXL"],
            "korean_business_news": True,
        },
        1,
        now,
        {},
        {},
    )
    format_first_line = rendered_format.splitlines()[0] if rendered_format else ""
    if "[상" in format_first_line or "예비" in format_first_line or "확정" in format_first_line:
        failures.append(f"telegram_display_labels_not_removed={format_first_line}")
    if radar.compact_alert_block_errors(rendered_format):
        failures.append(f"telegram_display_format_invalid={rendered_format}")

    title_only_alert = {
        "news": "본문 미확인 제목 전용 후보",
        "source_title": "본문 미확인 제목 전용 후보",
        "telegram_core_fact": "공개된 제목에 따르면, 본문 미확인 제목 전용 후보입니다.",
        "policy_plain_summary": "공개된 제목에 따르면, 본문 미확인 제목 전용 후보입니다.",
        "korean_business_kind": "trusted_title_material_event",
        "korean_business_news": True,
        "body_verified": False,
        "impacts": ["수급"],
        "sectors": ["금융/자본시장"],
        "link": "https://example.com/title-only",
        "publisher": "테스트",
        "published": now.isoformat(),
    }
    if radar.quality_display_alerts([title_only_alert], 1):
        failures.append("title_only_summary=published_without_verified_body")

    if failures:
        print("GAMEJOA news coverage contract failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"GAMEJOA news coverage contract OK: cases={len(CASES) + len(ATTACHED_CASES) + len(AUGUST9_CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
