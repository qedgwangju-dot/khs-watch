Warning: truncated output (original token count: 7090)
Total output lines: 483

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
        "source": "국내 신뢰매…6090 tokens truncated…ERS)


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

