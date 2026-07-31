from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gamejoa_preopen_news_radar_full_compact_runner as radar
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
)


def main() -> int:
    failures = []
    now = datetime.now().astimezone()
    for index, (title, required_term, required_impact) in enumerate(CASES):
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
        if not sovereign_selected:
            failures.append(
                "korea_sovereign_fund_final_selection=blocked:"
                f"{sovereign_alert.get('_exclusion_reason')}:"
                f"{sovereign_alert.get('guardrail_note')}:"
                f"{sovereign_alert.get('_decision_debug')}"
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
        if not hyperscaler_selected:
            failures.append(
                "hyperscaler_ai_capex_final_selection=blocked:"
                f"{hyperscaler_alert.get('_exclusion_reason')}:"
                f"{hyperscaler_alert.get('guardrail_note')}:"
                f"{hyperscaler_alert.get('_decision_debug')}"
            )

    opinion_alert = {
        "korean_business_news": True,
        "source_title": "“반도체 투자, 의심할 때 사서 확신할 때 팔아야”…그게 언제일까요",
        "news": "“반도체 투자, 의심할 때 사서 확신할 때 팔아야”…그게 언제일까요",
    }
    if not radar.is_low_value_market_commentary(opinion_alert):
        failures.append("low_value_market_commentary=not_blocked")

    if not radar.korean_business_source_allowed({
        "publisher": "뉴시스",
        "source": "뉴시스 경제",
        "link": "https://news.google.com/rss/articles/example",
    }):
        failures.append("trusted_publisher_google_news_link=blocked")

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

    if failures:
        print("GAMEJOA news coverage contract failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"GAMEJOA news coverage contract OK: cases={len(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
