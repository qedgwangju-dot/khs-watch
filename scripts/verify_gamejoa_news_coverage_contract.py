from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gamejoa_preopen_news_radar_full_compact_runner as radar
from khs_article_detail import extract_article_detail


CASES = (
    ("NAVER, ?붾퉬?붿븘 ???1議?809??洹쒕え ?좎긽利앹옄 寃곗젙", "?좎긽利앹옄", "?섍툒"),
    ("SK?섏씠?됱뒪, 10媛쒖궗? LTA ?κ린怨듦툒怨꾩빟 泥닿껐", "lta", "??踰꾨뒗 ?λ젰"),
    ("肄붿뒪?? 2嫄곕옒???곗냽 留ㅻ룄 ?ъ씠?쒖뭅 諛쒕룞", "?ъ씠?쒖뭅", "?섍툒"),
    ("肄붿뒪???쒗궥釉뚮젅?댁빱 1?④퀎 諛쒕룞", "?쒗궥釉뚮젅?댁빱", "?섍툒"),
    ("援щ쭏紐⑦넗 洹쒕え 7.1 媛뺤쭊, TSMC 怨듭옣 以묐떒", "媛뺤쭊", "??踰꾨뒗 ?λ젰"),
    ("10?꾨Ъ 誘멸뎅梨?湲덈━ 4.7%, ?몃읆??2湲?理쒓퀬", "誘멸뎅梨?, "?좎씤??),
    ("?쇱꽦?꾧린, 10媛?怨좉컼怨?MLCC ?κ린怨듦툒怨꾩빟", "mlcc", "??踰꾨뒗 ?λ젰"),
    ("誘멸뎅, ?멸뎅???대㉧?몄씠???섏엯 ?쒗븳", "?섏엯 ?쒗븳", "?좎씤??),
    ("?붾퉬?붿븘, AI ?쒗솚湲덉쑖 ?곕젮 ?ъ젏??, "?쒗솚湲덉쑖", "??踰꾨뒗 ?λ젰"),
    ("誘멸뎅, 湲濡쒕쾶?뚯슫?쒕━?ㅼ뿉 AI 愿묐컲?꾩껜 媛쒕컻鍮?3?듬떖??吏??, "媛쒕컻鍮?, "??踰꾨뒗 ?λ젰"),
    ("以묎뎅 ?뺤튂援? ?깆옣 ?뷀솕 ????뺤콉 吏?먃룹옱??吏異??쎌냽", "?뺤튂援?, "?좎씤??),
    ("援???곌툑, 援?궡二쇱떇 ?섏씡瑜?106% 湲곕줉", "援???곌툑", "?섍툒"),
    ("援?퀬梨?湲덈━, 誘멸뎅 湲덈━ ?ы뙆???숇컲 ?곸듅", "援?퀬梨?, "?좎씤??),
    ("LG?붿뒪?뚮젅?? 1.5議?援???깆옣????ъ옄 ?좎튂", "援???깆옣???, "??踰꾨뒗 ?λ젰"),
    ("理쒗깭???뚯옣, SK?섏씠?됱뒪 二쇱떇 3620二?留ㅼ닔", "?대???吏곸젒留ㅼ닔", "?섍툒"),
    ("?묓쁽??珥앷큵 ?꾨줈??? YG 二쇱떇 46留?940二??λ궡留ㅼ닔", "?대???吏곸젒留ㅼ닔", "?섍툒"),
    (
        "?좎븞?利앷텒, ?⑥씪醫낅ぉ ?덈쾭由ъ? ETF 洹쒖젣 肄붿뒪??諛섎벑 怨꾧린",
        "?⑥씪醫낅ぉ ?덈쾭由ъ?",
        "?섍툒",
    ),
    ("?몃읆?? ?ㅼ씠?꾨が?쑣룹꽍?졖룰??ㅒ룰뎄由?愿??硫댁젣 諛쒗몴", "愿??硫댁젣", "?좎씤??),
    ("?쇱꽦?꾩옄, HBM4 留ㅼ텧 3諛?利앷?쨌HBM4E ?섑뵆 異쒗븯", "hbm4", "??踰꾨뒗 ?λ젰"),
    ("LG AI?곌뎄?? 7500?듦컻 K-?묒궗??2.0 怨듦컻", "怨듦컻", "?쒓컙??),
    ("LG CNS, ?곷컲湲???? 理쒕? 留ㅼ텧 2.8議곗썝", "留ㅼ텧", "??踰꾨뒗 ?λ젰"),
    ("8???섎Т蹂댁쑀?깅줉 45媛쒖궗 1??078留뚯＜ ?댁젣", "?섎Т蹂댁쑀", "?섍툒"),
    ("?⑥퐫???먰걧蹂? ?몃룄 CDSCO ?덈ぉ?덇? 沅뚭퀬", "?덈ぉ?덇?", "?쒓컙??),
    ("?멸뎅??利앷텒嫄곕옒???명솚嫄곕옒 ?섎（ 1200?듬떖??, "?명솚嫄곕옒", "?섍툒"),
    ("?ㅼ삦?쒖븘 ?곸뾽???쒖옣 ?덉긽 7% ?섑쉶쨌二쇱떇遺꾪븷", "?곸뾽??, "??踰꾨뒗 ?λ젰"),
    ("AI ?④텒 寃쎌웳, 鍮낇뀒??AI ?ъ옄 1議곕떖??룹쟾???명봽???뺣?", "ai ?ъ옄", "??踰꾨뒗 ?λ젰"),
    ("?⑥씪醫낅ぉ ?덈쾭由ъ? 洹쒖젣 泥ル궇 嫄곕옒?湲?12議곗썝???3議곗썝?濡?湲됯컧", "嫄곕옒?湲?, "?섍툒"),
    ("7???섏텧 ?ㅼ쟻 989?듬떖??룸컲?꾩껜 ?섏텧 ??? 2??, "?섏텧 ?ㅼ쟻", "??踰꾨뒗 ?λ젰"),
    ("誘??곗?, ??8??湲덈━寃곗젙 ?뚯쓽 異뺤냼 寃??, "?뚯쓽 異뺤냼", "?좎씤??),
    ("誘??щТ遺, ?뷀솕 ?쎌꽭 ????섏쑉 媛쒖엯 ?뺥솴", "?섏쑉 媛쒖엯", "?좎씤??),
    ("CXMT, D???앹궛 ?λ젰 ?⑥씠????30留뚯옣?쇰줈 利앹꽕", "?앹궛 ?λ젰", "??踰꾨뒗 ?λ젰"),
    ("?꾨쭏議?AWS 留ㅼ텧쨌?대씪?곕뱶 ?깆옣, AI ?ъ옄 ?뺣?", "aws 留ㅼ텧", "??踰꾨뒗 ?λ젰"),
    ("?몃읆?? ?대? 異붽? 怨듦꺽 ?꾨컯 寃쎄퀬쨌荑좎썾?댄듃 ?쒕줎 怨듦꺽", "異붽? 怨듦꺽", "?좎씤??),
    ("?ㅻ젋?ㅽ궎, ?몃읆?꾩뿉 ?ㅽ?留곹겕 ?寃??뱀씤 ?붿껌", "?ㅽ?留곹겕", "?섍툒"),
    ("媛???댁쟾, ?섎쭏??臾댁옣?댁젣쨌?됲솕 ?묒젙 ?쒗뿕?", "媛???댁쟾", "?좎씤??),
    ("?⑥씪醫낅ぉ ?덈쾭由ъ? ETF 援?젙議곗궗 ?붽뎄", "援?젙議곗궗", "?섍툒"),
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
        "reuters.com",
        "apnews.com",
        "cnbc.com",
    }
    missing_domains = expected_domains - set(radar.KOREAN_BUSINESS_PUBLISHER_DOMAINS)
    if missing_domains:
        failures.append(f"missing_domains={sorted(missing_domains)}")

    if not radar.is_korean_business_row({
        "source": "?댁떆??寃쎌젣",
        "publisher": "?댁떆??,
        "link": "https://www.newsis.com/view/example",
    }):
        failures.append("korean_business_source=newsis_not_routed")
    if not radar.is_korean_business_row({
        "source": "AP",
        "publisher": "AP",
        "link": "https://apnews.com/article/example",
        "title": "?몃읆?? ?대? 異붽? 怨듦꺽 ?꾨컯 寃쎄퀬쨌荑좎썾?댄듃 ?쒕줎 怨듦꺽 蹂닿퀬",
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
    if "援?궡 寃쎌쁺吏꽷룹턀?二쇱＜ 吏곸젒留ㅼ닔" not in search_names:
        failures.append("missing_search=援?궡 寃쎌쁺吏꽷룹턀?二쇱＜ 吏곸젒留ㅼ닔")
    if "?⑥씪醫낅ぉ ?덈쾭由ъ? 洹쒖젣쨌肄붿뒪???섍툒" not in search_names:
        failures.append("missing_search=?⑥씪醫낅ぉ ?덈쾭由ъ? 洹쒖젣쨌肄붿뒪???섍툒")
    if "援?궡 ?湲곗뾽 ?꾨왂湲곗닠 異쒖옄쨌?ㅽ??몄뾽 ?ъ옄" not in search_names:
        failures.append("missing_search=援?궡 ?湲곗뾽 ?꾨왂湲곗닠 異쒖옄쨌?ㅽ??몄뾽 ?ъ옄")
    for required_search in (
        "湲곗뾽 ?ㅼ쟻쨌怨듦툒遺議굿룹떆?μ젏?좎쑉",
        "AI 紐⑤뜽쨌?곗씠?곗꽱??援ъ텞",
        "諛붿씠???덇?쨌?곸뾽??,
        "?섍툒쨌?먮낯?됱궗쨌?명솚",
        "?몃읆??愿?맞룹썝?먯옱쨌以묐룞",
        "鍮낇뀒??AI ?ъ옄쨌諛섎룄泥는룹쟾???명봽??CAPEX",
        "?⑥씪醫낅ぉ ?덈쾭由ъ? 洹쒖젣 ?쒗뻾?④낵쨌嫄곕옒湲됯컧",
        "?쒓뎅 ?붽컙 ?섏텧쨌諛섎룄泥??섏텧쨌臾댁뿭?섏?",
        "?곗? FOMC ?뚯쓽泥닿퀎쨌?뺤콉寃곗젙 ?쇱젙",
        "誘멸뎅쨌?쇰낯 ?섏쑉媛쒖엯쨌?듯솕怨듭“",
        "以묎뎅 DRAM ?앹궛?λ젰쨌硫붾え由?利앹꽕",
        "?섏씠?쇱뒪耳?쇰윭 ?ㅼ쟻쨌?대씪?곕뱶 ?깆옣쨌AI CAPEX",
        "?몃읆???대?쨌嫄명봽 援곗궗湲댁옣",
        "?고겕?쇱씠???ㅽ?留곹겕 援곗궗?ъ슜 ?뱀씤",
        "媛???댁쟾쨌?섎쭏??臾댁옣?댁젣",
        "?⑥씪醫낅ぉ ?덈쾭由ъ? 援?젙議곗궗쨌泥?Ц??,
    ):
        if required_search not in search_names:
            failures.append(f"missing_search={required_search}")

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
        "news": "?덈쾭由ъ? 洹쒖젣 泥ル궇 嫄곕옒 ?섎슍?쇺?2議곗썝???3議곗썝?濡?湲됯컧",
        "published": now,
    }
    leverage_effect_b = {
        "news": "?⑥씪?덈쾭由ъ? ?덊긽湲??곹뼢 泥ル궇??굅?섎웾 媛먯냼, 媛쒕???留ㅻ룄",
        "published": now,
    }
    if radar.alert_dedup_key(leverage_effect_a) != radar.alert_dedup_key(leverage_effect_b):
        failures.append("semantic_duplicate=single_stock_leverage_rule_effect")

    if not any(
        row.get("url") == "https://www.mk.co.kr/article/12113486"
        and row.get("publisher") == "留ㅼ씪寃쎌젣"
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
        "news": "?쇱꽦?꾧린 2遺꾧린 ?곸뾽?댁씡 4404?듭썝, 10媛?怨좉컼怨?MLCC ?κ린怨꾩빟",
        "published": now,
    }
    duplicate_b = {
        "news": "?쇱꽦?꾧린, ?섏씠?쇱뒪耳?쇰윭 10?ш납怨?MLCC LTA 泥닿껐",
        "published": now,
    }
    if radar.alert_dedup_key(duplicate_a) != radar.alert_dedup_key(duplicate_b):
        failures.append("semantic_duplicate=mlcc_lta")

    structured_title = "?붾퉬?붿븘, ?ㅽ뵂AI ?곗씠?곗꽱?곗뿉 2500?듬떖??蹂댁쬆 ?쇱쓽"
    structured_body = (
        "?붾퉬?붿븘媛 ?ㅽ뵂AI???ㅽ븯?댁삤 ?곗씠?곗꽱???먭툑議곕떖??"
        "2500?듬떖??洹쒕え??蹂댁쬆???쒓났?섎뒗 諛⑹븞???쇱쓽?섍퀬 ?덈떎. "
        "?꾨줈?앺듃??10湲곌????洹쒕え?대ŉ 援ъ껜 議곌굔? ?뺤젙?섏? ?딆븯?? "
        "蹂댁쬆???깆궗?섎㈃ ?ъ옄?깃툒 ?좎슜?깃툒???녿뒗 ?ㅽ뵂AI??議곕떖 議곌굔??"
        "媛쒖꽑?????덉?留? 諛섎룄泥?援щℓ 鍮꾩슜? ?대쾲 蹂댁쬆 ??곸뿉 ?ы븿?섏? ?딅뒗?? "
        "?꾩껜 ?ъ뾽鍮꾩? ?꾨젰 諛곕텇, ?꾩감 怨꾩빟? ?꾩냽 ?묒긽?먯꽌 ?뺤젙???덉젙?대떎."
    )
    structured_html = f"""
    <html><head><script type="application/ld+json">
    {{"@context":"https://schema.org","@type":"NewsArticle",
      "headline":"{structured_title}","articleBody":"{structured_body}",
      "datePublished":"2026-07-27T15:37:00+09:00"}}
    </script></head><body><div>?숈쟻 湲곗궗 蹂몃Ц</div></body></html>
    """
    detail = extract_article_detail(structured_html, structured_title)
    if not detail.get("body_verified") or "2500?듬떖?? not in detail.get("body", ""):
        failures.append("structured_article_body=not_verified")

    insider_core = radar.detailed_article_core(
        "理쒗깭???뚯옣, SK?섏씠?됱뒪 二쇱떇 3620二?留ㅼ닔",
        "理쒗깭??SK洹몃９ ?뚯옣??SK?섏씠?됱뒪 二쇱떇 3620二쇰? ?λ궡 留ㅼ닔?덈떎.",
    )
    if "理쒗깭?? not in insider_core or "3620二? not in insider_core or "媛쒖씤 紐낆쓽" not in insider_core:
        failures.append(f"insider_purchase_core={insider_core}")

    viral_title = '"?쇰줎 癒몄뒪?ъ씤 以??뚯븯????SNS ?ш뎔 訝?\'?꾪뵆媛깆뼱\' 諛붾퉬???ъ옣'
    contaminated_core = "?쇱꽦?꾩옄 ?ъ옣 171留?000?? 10二쇰? 媛쒖씤 紐낆쓽濡?留ㅼ닔?덉뒿?덈떎."
    contaminated_sentences = [
        "?쇱꽦?꾩옄 ?ъ옣???쇱꽦?꾩옄 二쇱떇 10二쇰? 171留?000?먯뿉 媛쒖씤 紐낆쓽濡?留ㅼ닔?덈떎."
    ]
    if radar.insider_purchase_fact(viral_title, contaminated_sentences):
        failures.append("viral_related_article_insider_fact=not_blocked")
    if radar.korean_title_core_aligned(viral_title, contaminated_core):
        failures.append("viral_generic_role_alignment=not_blocked")

    reporter_prefixed_core = radar.detailed_article_core(
        "?뚯떆, FOMC ?뺣??뚯쓽 ??8??異뺤냼 寃??,
        (
            "[?대뜲?쇰━ 源?ㅼ? 湲곗옄] 耳鍮??뚯떆 ?곗? ?섏옣???꾩옱 ??8?뚯씤 "
            "?곕갑怨듦컻?쒖옣?꾩썝???뺣??뚯쓽 ?잛닔瑜?以꾩씠??諛⑹븞??寃?좏븯怨??덈떎."
        ),
    )
    if "湲곗옄" in reporter_prefixed_core or "?대뜲?쇰━" in reporter_prefixed_core:
        failures.append(f"reporter_boilerplate_not_removed={reporter_prefixed_core}")

    viral_alert = {
        "source": "援?궡 ?좊ː留ㅼ껜 吏곸젒媛먯떆",
        "publisher": "?댁떆??,
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
        "YG ?묓쁽??200?돠텷YP 諛뺤쭊??50???먯궗二?留ㅼ엯",
        (
            "?묓쁽??YG 珥앷큵 ?꾨줈??쒓? 200?듭썝???ㅼ뿬 ?먯궗 二쇱떇 "
            "46留?940二쇰? ?λ궡 留ㅼ닔?덈떎. "
            "諛뺤쭊??JYP CCO媛 50?듭썝???ㅼ뿬 ?먯궗 二쇱떇 "
            "6留?00二쇰? ?λ궡 留ㅼ닔?덈떎."
        ),
    )
    for fact in ("?묓쁽??, "200?듭썝", "46留?940二?, "諛뺤쭊??, "50?듭썝", "6留?00二?):
        if fact not in entertainment_core:
            failures.append(f"entertainment_insider_core_missing={fact}:{entertainment_core}")

    company_buyback_core = radar.detailed_article_core(
        "?꾨?李? 1議곗썝 洹쒕え ?먯궗二?痍⑤뱷쨌?뚭컖",
        "?꾨?李⑤뒗 ?댁궗?뚯뿉??1議곗썝 洹쒕え???먯궗二쇰? 痍⑤뱷???꾨웾 ?뚭컖?섍린濡?寃곗젙?덈떎.",
    )
    if "媛쒖씤 紐낆쓽" in company_buyback_core:
        failures.append(f"company_buyback_misclassified={company_buyback_core}")

    leverage_core = radar.detailed_article_core(
        "?좎븞?利앷텒, ?⑥씪醫낅ぉ ?덈쾭由ъ? ETF 洹쒖젣 肄붿뒪??諛섎벑 怨꾧린",
        (
            "?ㅻ뒗 31?쇰????⑥씪醫낅ぉ ?덈쾭由ъ? ETF 洹쒖젣媛 ?쒗뻾?쒕떎. "
            "?좎븞?利앷텒 ?곌뎄?먯? ???諛섎룄泥??덈쾭由ъ? ?곹뭹???먭툑 ?⑥쑉怨?"
            "?묎렐?깆씠 ??븘吏硫?肄붿뒪???곕웾 ?깆옣二쇱쓽 ?곷???湲고쉶鍮꾩슜??"
            "?뺤긽?붾맆 ???덈떎怨?遺꾩꽍?덈떎."
        ),
    )
    for fact in ("31?쇰???, "???諛섎룄泥?, "肄붿뒪???곕웾 ?깆옣二?, "?섍툒"):
        if fact not in leverage_core:
            failures.append(f"leverage_kosdaq_core_missing={fact}:{leverage_core}")

    leverage_effect_row = {
        "source": "援?궡 ?좊ː留ㅼ껜 吏곸젒媛먯떆",
        "publisher": "援???쇰낫",
        "title": "?덈쾭由ъ? 洹쒖젣 泥ル궇 嫄곕옒 ?섎슍?쇺?2議곗썝???3議곗썝?濡?湲됯컧",
        "source_title": "?덈쾭由ъ? 洹쒖젣 泥ル궇 嫄곕옒 ?섎슍?쇺?2議곗썝???3議곗썝?濡?湲됯컧",
        "source_body": (
            "?쇱꽦?꾩옄? SK?섏씠?됱뒪 ?⑥씪醫낅ぉ ?덈쾭由ъ? ETF 湲곕낯?덊긽湲덉씠 "
            "1000留뚯썝?먯꽌 3000留뚯썝?쇰줈 ?곹뼢??泥ル궇 愿??ETF 嫄곕옒?≪씠 "
            "12議곗썝??먯꽌 3議곗썝?濡?湲됯컧?덈떎."
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
        for fact in ("1000留뚯썝", "3000留뚯썝", "12議곗썝?", "3議곗썝?", "湲됯컧"):
            if fact not in effect_core:
                failures.append(
                    f"single_stock_leverage_rule_effect_core_missing={fact}:{effect_core}"
                )
        if "?좎븞?利앷텒" in effect_core or "肄붿뒪???곕웾 ?깆옣二? in effect_core:
            failures.append(
                f"single_stock_leverage_rule_effect_stale_template={effect_core}"
            )

    emergency_leverage_row = {
        "source": "?댄닾?곗씠 寃쎌젣",
        "publisher": "?댄닾?곗씠",
        "title": "湲덉쑖?밴뎅, 利앹떆 湲됰???湲닿툒議곗튂沅??뺣낫 異붿쭊??떒?쇱쥌紐??덈쾭由ъ? ?뺤“以",
        "source_title": "湲덉쑖?밴뎅, 利앹떆 湲됰???湲닿툒議곗튂沅??뺣낫 異붿쭊??떒?쇱쥌紐??덈쾭由ъ? ?뺤“以",
        "source_body": (
            "湲덉쑖?밴뎅??利앹떆 湲됰? ???⑥씪醫낅ぉ ?덈쾭由ъ? ETF 嫄…1641 tokens truncated…ot radar.has_decision_impact(hyperscaler_normalized):
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

    title_only_row = {
        "source": "?쒖슱?좊Ц",
        "publisher": "?쒖슱?좊Ц",
        "title": "?몃읆?? ?ㅼ씠?꾨が?쑣룹꽍?졖룰??ㅒ룰뎄由?愿??硫댁젣 諛쒗몴",
        "source_title": "?몃읆?? ?ㅼ씠?꾨が?쑣룹꽍?졖룰??ㅒ룰뎄由?愿??硫댁젣 諛쒗몴",
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
        if title_only_alert.get("status") != "?덈퉬":
            failures.append(f"trusted_title_status={title_only_alert.get('status')}")
        if not title_only_alert.get("title_fact_verified") or title_only_alert.get("body_verified"):
            failures.append("trusted_title_verification_flags=invalid")
        if not str(title_only_alert.get("telegram_core_fact") or "").startswith(
            "怨듦컻???쒕ぉ???곕Ⅴ硫?
        ):
            failures.append(
                f"trusted_title_core={title_only_alert.get('telegram_core_fact')}"
            )
        mismatched_alert = dict(title_only_alert)
        mismatched_alert.update(
            {
                "news": "援щ쭏紐⑦넗 洹쒕え 7.1 媛뺤쭊, TSMC 怨듭옣 以묐떒",
                "original_news": "援щ쭏紐⑦넗 洹쒕え 7.1 媛뺤쭊, TSMC 怨듭옣 以묐떒",
                "source_title": "援щ쭏紐⑦넗 洹쒕え 7.1 媛뺤쭊, TSMC 怨듭옣 以묐떒",
                "telegram_core_fact": "?멸뎅?몄씠 ?쇱꽦?꾩옄 二쇱떇???쒕ℓ?섑뻽?듬땲??",
                "policy_plain_summary": "?멸뎅?몄씠 ?쇱꽦?꾩옄 二쇱떇???쒕ℓ?섑뻽?듬땲??",
            }
        )
        synced = radar.compact_quality_final_alerts(
            [mismatched_alert, title_only_alert],
            2,
        )
        if len(synced) != 1 or synced[0].get("source_title") != title_only_row["source_title"]:
            failures.append(
                "render_json_delivery_sync="
                f"{[(row.get('source_title'), row.get('_exclusion_reason')) for row in synced]}"
            )

    vague_title_row = {
        "source": "吏?붾꽬肄붾━??,
        "publisher": "吏?붾꽬肄붾━??,
        "title": "?곗씠?곗꽱?곌? 援?? 寃쎌웳?μ씠??,
        "source_title": "?곗씠?곗꽱?곌? 援?? 寃쎌웳?μ씠??,
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
        "source_title": "?쒕컲?꾩껜 ?ъ옄, ?섏떖?????ъ꽌 ?뺤떊?????붿븘?쇄앪?렇寃??몄젣?쇨퉴??,
        "news": "?쒕컲?꾩껜 ?ъ옄, ?섏떖?????ъ꽌 ?뺤떊?????붿븘?쇄앪?렇寃??몄젣?쇨퉴??,
    }
    if not radar.is_low_value_market_commentary(opinion_alert):
        failures.append("low_value_market_commentary=not_blocked")

    leverage_opinion_alert = {
        "korean_business_news": True,
        "source_title": "'ETF ?꾨쾭吏' ??寃쎄퀬??떒?쇱쥌紐??덈쾭由ъ????ъ옄?섏? ?딅뒗 寃껋씠 理쒖꽑",
        "news": "'ETF ?꾨쾭吏' ??寃쎄퀬??떒?쇱쥌紐??덈쾭由ъ????ъ옄?섏? ?딅뒗 寃껋씠 理쒖꽑",
    }
    if not radar.is_low_value_market_commentary(leverage_opinion_alert):
        failures.append("leverage_opinion_commentary=not_blocked")

    retrospective_alert = {
        "korean_business_news": True,
        "source_title": "醫뗭? 轅덉쓣 袁몄뿀?듬땲?ㅲ?븳???섏씡瑜?106% 援???곌툑, 吏湲덉??",
        "news": "醫뗭? 轅덉쓣 袁몄뿀?듬땲?ㅲ?븳???섏씡瑜?106% 援???곌툑, 吏湲덉??",
    }
    if not radar.is_low_value_market_commentary(retrospective_alert):
        failures.append("retrospective_clickbait=not_blocked")

    if not radar.korean_business_source_allowed({
        "publisher": "?댁떆??,
        "source": "?댁떆??寃쎌젣",
        "link": "https://news.google.com/rss/articles/example",
    }):
        failures.append("trusted_publisher_google_news_link=blocked")

    glyph_amounts = radar.extract_foreign_amounts("7???섏텧 988.9?드폌쨌諛섎룄泥?400?드폌 ?뚰뙆")
    if len(glyph_amounts) != 2 or any(item.get("code") != "USD" for item in glyph_amounts):
        failures.append(f"dollar_glyph_not_normalized={glyph_amounts}")
    glyph_core = radar.apply_krw_conversions(
        "7???섏텧 988.9?드폌??湲곕줉?덉뒿?덈떎.",
        {
            "amounts": [
                {
                    "original": "988.9?듬떖??,
                    "krw_value": 137_000_000_000_000,
                    "krw_text": "137議곗썝",
                }
            ]
        },
    )
    if "988.9?듬떖????137議곗썝)" not in glyph_core or "凉? in glyph_core:
        failures.append(f"dollar_glyph_conversion_core={glyph_core}")

    export_row = {
        "source": "?쒓뎅寃쎌젣",
        "publisher": "?쒓뎅寃쎌젣",
        "title": "7???섏텧 989?듬떖?щ줈 62.8% 利앷?쨌諛섎룄泥?410?듬떖????? 2??,
        "source_title": "7???섏텧 989?듬떖?щ줈 62.8% 利앷?쨌諛섎룄泥?410?듬떖????? 2??,
        "source_body": (
            "7???섏텧? 989?듬떖?щ줈 ?꾨뀈 ?鍮?62.8% 利앷??덈떎. "
            "諛섎룄泥??섏텧? 410?듬떖?щ줈 179% ?섏뼱 ??? ?붽컙 2?꾨? 湲곕줉?덈떎."
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
        for fact in ("989?듬떖??, "62.8%", "410?듬떖??, "179%"):
            if fact not in export_core:
                failures.append(f"korea_monthly_exports_core_missing={fact}:{export_core}")

    fed_title_row = {
        "source": "癒몃땲?щ뜲??,
        "publisher": "癒몃땲?щ뜲??,
        "title": "?뚯떆 誘??곗? ?섏옣, ??8??湲덈━ 寃곗젙 ?뚯쓽 異뺤냼 寃??,
        "source_title": "?뚯떆 誘??곗? ?섏옣, ??8??湲덈━ 寃곗젙 ?뚯쓽 異뺤냼 寃??,
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
        if fed_title_alert.get("status") != "?덈퉬":
            failures.append(f"fed_meeting_title_status={fed_title_alert.get('status')}")

    fx_row = {
        "source": "?댄닾?곗씠",
        "publisher": "?댄닾?곗씠",
        "title": "?쇰낯, 60議곗썝 ?덊뙉 ?섏쑉 媛쒖엯 異붿젙쨌誘몄씪 怨듭“???뺤궛",
        "source_title": "?쇰낯, 60議곗썝 ?덊뙉 ?섏쑉 媛쒖엯 異붿젙쨌誘몄씪 怨듭“???뺤궛",
        "source_body": "?뷀솕 ?쎌꽭瑜?留됯린 ?꾪빐 ?쇰낯 ?щТ遺媛 ?명솚?쒖옣??媛쒖엯???뺥솴???ъ갑?먮떎.",
        "link": "https://www.etoday.co.kr/news/view/example-fx",
        "published": now,
        "body_verified": True,
    }
    fx_alert = radar.build_verified_korean_business_alert(fx_row, now)
    if not fx_alert or fx_alert.get("korean_business_kind") != "us_japan_fx_intervention":
        failures.append(f"fx_intervention_alert={fx_alert}")

    china_memory_row = {
        "source": "?꾩떆?꾧꼍??,
        "publisher": "?꾩떆?꾧꼍??,
        "title": "CXMT, D???앹궛 ?λ젰 ?⑥씠????30留뚯옣?쇰줈 利앹꽕",
        "source_title": "CXMT, D???앹궛 ?λ젰 ?⑥씠????30留뚯옣?쇰줈 利앹꽕",
        "source_body": "CXMT媛 2028?꾧퉴吏 D???⑥씠?????앹궛 ?λ젰???뺣???怨꾪쉷?대떎.",
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
        "title": "?몃읆?? ?대? 異붽? 怨듦꺽 ?꾨컯 寃쎄퀬??퓼?⑥씠?몃뒗 ?쒕줎 怨듦꺽 蹂닿퀬",
        "source_title": "?몃읆?? ?대? 異붽? 怨듦꺽 ?꾨컯 寃쎄퀬??퓼?⑥씠?몃뒗 ?쒕줎 怨듦꺽 蹂닿퀬",
        "source_body": (
            "?몃읆????듬졊? ?대??????異붽? 怨듦꺽???꾨컯?덈떎怨?寃쎄퀬?덈떎. "
            "荑좎썾?댄듃 ?밴뎅? ?먭뎅 ?쒖꽕??寃⑤깷???쒕줎 怨듦꺽??蹂닿퀬?덈떎."
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
        if "異붽? 怨듦꺽" not in iran_core or "荑좎썾?댄듃" not in iran_core or "?쒕줎 怨듦꺽" not in iran_core:
            failures.append(f"iran_gulf_attack_core={iran_core}")

    starlink_row = {
        "source": "Reuters",
        "publisher": "Reuters",
        "title": "?ㅻ젋?ㅽ궎, ?몃읆?꾩뿉 ?ъ떆???寃⑹슜 ?ㅽ?留곹겕 ?뱀씤 吏???붿껌",
        "source_title": "?ㅻ젋?ㅽ궎, ?몃읆?꾩뿉 ?ъ떆???寃⑹슜 ?ㅽ?留곹겕 ?뱀씤 吏???붿껌",
        "source_body": "?ㅻ젋?ㅽ궎 ??듬졊? ?몃읆????듬졊?먭쾶 ?ъ떆???寃?吏?먯쓣 ?꾪븳 ?ㅽ?留곹겕 ?ъ슜 ?뱀씤???꾩??щ씪怨??붿껌?덈떎.",
        "link": "https://www.reuters.com/world/example-starlink-request",
        "published": now,
        "body_verified": True,
    }
    starlink_alert = radar.build_verified_korean_business_alert(starlink_row, now)
    if not starlink_alert or starlink_alert.get("korean_business_kind") != "ukraine_starlink_military_request":
        failures.append(f"ukraine_starlink_alert={starlink_alert}")
    else:
        if starlink_alert.get("status") != "?덈퉬":
            failures.append(f"ukraine_starlink_status={starlink_alert.get('status')}")
        starlink_core = str(starlink_alert.get("telegram_core_fact") or "")
        if "?붿껌" not in starlink_core or "?뱀씤?덈떎" in starlink_core:
            failures.append(f"ukraine_starlink_core={starlink_core}")

    gaza_row = {
        "source": "AP",
        "publisher": "AP",
        "title": "媛???댁쟾 ?꾩썝?? ?섎쭏??臾댁옣?댁젣쨌?됲솕 ?묒젙 ?쒗뿕?",
        "source_title": "媛???댁쟾 ?꾩썝?? ?섎쭏??臾댁옣?댁젣쨌?됲솕 ?묒젙 ?쒗뿕?",
        "source_body": "2二쇨컙??媛???댁쟾? ?섎쭏??臾댁옣?댁젣? ?됲솕 ?묒젙 媛쒖떆瑜?紐⑺몴濡??쒕떎.",
        "link": "https://apnews.com/article/example-gaza-ceasefire",
        "published": now,
        "body_verified": True,
    }
    gaza_alert = radar.build_verified_korean_business_alert(gaza_row, now)
    if not gaza_alert or gaza_alert.get("korean_business_kind") != "gaza_ceasefire_disarmament":
        failures.append(f"gaza_ceasefire_alert={gaza_alert}")

    inquiry_row = {
        "source": "硫뷀듃濡쒖떊臾?,
        "publisher": "硫뷀듃濡쒖떊臾?,
        "title": "援???섑옒, ?⑥씪醫낅ぉ ?덈쾭由ъ? ETF 援?젙議곗궗 ?붽뎄",
        "source_title": "援???섑옒, ?⑥씪醫낅ぉ ?덈쾭由ъ? ETF 援?젙議곗궗 ?붽뎄",
        "source_body": "援???섑옒? ?⑥씪醫낅ぉ ?덈쾭由ъ? ETF ?ы깭??援?젙議곗궗瑜??붽뎄?섍쿋?ㅺ퀬 諛앺삍??",
        "link": "https://www.metroseoul.co.kr/article/example-leverage-inquiry",
        "published": now,
        "body_verified": True,
    }
    inquiry_alert = radar.build_verified_korean_business_alert(inquiry_row, now)
    if not inquiry_alert or inquiry_alert.get("korean_business_kind") != "single_stock_leverage_parliamentary_inquiry":
        failures.append(f"leverage_parliamentary_inquiry_alert={inquiry_alert}")
    elif inquiry_alert.get("status") != "?덈퉬":
        failures.append(f"leverage_parliamentary_inquiry_status={inquiry_alert.get('status')}")

    for noisy, expected in (
        (
            "fn 怨듭쑀 怨듭쑀?섍린 湲?먰겕湲?湲?먰겕湲??ㅼ젙 ?꾨┛??援щ룆 援щ룆 利앷텒 利앷텒?쇰컲 "
            "肄붿뒪?쇨? 10.2% 湲됰벑?덈떎.",
            "肄붿뒪?쇨? 10.2% 湲됰벑?덈떎.",
        ),
        (
            "?섏씠?ㅻ턿 X(?몄쐞?? 硫붿씪 URL 蹂듭궗 ?묎쾶 蹂댄넻 ?ш쾶 "
            "湲덉쑖?밴뎅???⑥씪醫낅ぉ ?덈쾭由ъ? 洹쒖젣瑜??쒗뻾?쒕떎.",
            "湲덉쑖?밴뎅???⑥씪醫낅ぉ ?덈쾭由ъ? 洹쒖젣瑜??쒗뻾?쒕떎.",
        ),
    ):
        cleaned = radar.clean_article_summary_text(noisy)
        if cleaned != expected:
            failures.append(f"article_ui_noise_not_removed={cleaned}")

    insider_core = radar.insider_purchase_fact(
        "理쒗깭???뚯옣, SK?섏씠?됱뒪 二쇱떇 3620二?留ㅼ닔",
        [
            "SK?섏씠?됱뒪??理쒕?二쇱＜?깆냼?좎＜?앸??숈떊怨좎꽌瑜??듯빐 "
            "理쒗깭???뚯옣??3620二쇰? 媛쒖씤 紐낆쓽濡?留ㅼ닔?덈떎怨?諛앺삍??"
        ],
    )
    if not insider_core.startswith("理쒗깭???뚯옣 3620二?):
        failures.append(f"insider_buyer_prefix_polluted={insider_core}")

    lta_core = radar.detailed_article_core(
        "SK?섏씠?됱뒪, AI 硫붾え由??섏슂 媛뺤꽭 ??10媛?怨좉컼?ъ? ?κ린怨듦툒怨꾩빟 泥닿껐",
        (
            "SK?섏씠?됱뒪媛 10媛?怨좉컼?ъ? AI 硫붾え由??κ린怨듦툒怨꾩빟??泥닿껐?덈떎. "
            "愿??留ㅼ텧? 24議곗썝?쇰줈 蹂대룄?먮떎."
        ),
    )
    for fact in ("10媛?怨좉컼??, "?κ린怨듦툒怨꾩빟", "24議곗썝"):
        if fact not in lta_core:
            failures.append(f"lta_compact_core_missing={fact}:{lta_core}")

    growth_core = radar.detailed_article_core(
        "援???깆옣??? OLED 珥덇꺽李?LG?붿뒪?뚮젅?댁뿉 1.5議??由щ?異?,
        (
            "援???깆옣??쒓? LG?붿뒪?뚮젅?댁뿉 1.5議곗썝 ?由щ?異쒖쓣 吏?먰븳?? "
            "HBM 怨듦툒留?媛뺥솕瑜??꾪빐 ?뚰겕?숈뿉??500?듭썝???由??異쒗븳??"
        ),
    )
    for fact in ("LG?붿뒪?뚮젅?댁뿉 1.5議곗썝", "?뚰겕?숈뿉 500?듭썝", "OLED쨌HBM"):
        if fact not in growth_core:
            failures.append(f"growth_fund_compact_core_missing={fact}:{growth_core}")

    buy_sidecar_core = radar.detailed_article_core(
        "[?띾낫]肄붿뒪?? 10% ?섎뒗 湲됰벑?몄뿉 留ㅼ닔 ?ъ씠?쒖뭅 諛쒕룞",
        (
            "肄붿뒪?쇨? 10.2% 湲됰벑?덈떎. 肄붿뒪??00?좊Ъ 湲됰벑?쇰줈 ?꾨줈洹몃옩 "
            "留ㅼ닔?멸? ?⑤젰??5遺꾧컙 ?뺤??섎뒗 留ㅼ닔 ?ъ씠?쒖뭅媛 諛쒕룞?먮떎."
        ),
    )
    if "留ㅼ닔 ?ъ씠?쒖뭅" not in buy_sidecar_core or "5遺꾧컙" not in buy_sidecar_core:
        failures.append(f"buy_sidecar_compact_core_invalid={buy_sidecar_core}")
    if any(term in buy_sidecar_core for term in ("怨듭쑀?섍린", "湲?먰겕湲?, "?꾨┛??, "援щ룆")):
        failures.append(f"buy_sidecar_boilerplate_leaked={buy_sidecar_core}")

    duplicate_insider_core = radar.detailed_article_core(
        "理쒗깭???뚯옣, SK?섏씠?됱뒪 二쇱떇 3620二?留ㅼ닔",
        (
            "理쒗깭??SK洹몃９ ?뚯옣??SK?섏씠?됱뒪 二쇱떇 3620二쇰? 留ㅼ닔?덈떎. "
            "理??뚯옣??媛쒖씤 紐낆쓽濡?3620二쇰? 痍⑤뱷?덈떎怨?怨듭떆?덈떎."
        ),
    )
    if duplicate_insider_core.count("3620二?) != 1:
        failures.append(f"duplicate_insider_purchase_not_removed={duplicate_insider_core}")

    mismatch_errors = radar.compact_alert_block_errors(
        "1) [以?| ?덈퉬] ?쇰낯 媛뺤쭊 吏곹썑 湲곗뾽 諛⑹옱 ?덉젏\n"
        "- ?듭떖: 肄붿뒪??湲됰벑?쇰줈 ?꾨줈洹몃옩 留ㅼ닔?멸?瑜?5遺꾧컙 ?뺤??섎뒗 留ㅼ닔 ?ъ씠?쒖뭅媛 諛쒕룞?먮떎.\n"
        "- 異쒖쿂: ?먮Ц ?댁뒪蹂닿린"
    )
    if "title_core_mismatch" not in mismatch_errors:
        failures.append(f"title_core_mismatch_not_blocked={mismatch_errors}")

    repaired_core = radar.complete_prose_text(
        "誘멸뎅??AI ?곗씠?곗꽱?곗슜 愿묐컲?꾩껜 媛쒕컻鍮?吏?먯쓣 ?뺣???,
        limit=radar.GAMEJOA_CORE_MAX_CHARS,
    )
    if "?? in repaired_core or "..." in repaired_core:
        failures.append(f"compact_core_ellipsis_not_repaired={repaired_core}")
    if radar.compact_alert_block_errors(
        "1) [??| ?뺤젙] 誘멸뎅, AI 愿묐컲?꾩껜 媛쒕컻 吏???뺣?\n"
        f"- ?듭떖: {repaired_core}\n"
        "- 異쒖쿂: ?먮Ц ?댁뒪蹂닿린"
    ):
        failures.append(f"repaired_compact_core_rejected={repaired_core}")

    malformed_errors = radar.compact_alert_block_errors(
        "1) [??| ?뺤젙] 誘멸뎅, AI 愿묐컲?꾩껜 媛쒕컻 吏???뺣?\n"
        "- ?듭떖: 誘멸뎅??AI ?곗씠?곗꽱?곗슜 愿묐컲?꾩껜 媛쒕컻鍮?吏?먯쓣 ?뺣???n"
        "- 異쒖쿂: ?먮Ц ?댁뒪蹂닿린"
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

