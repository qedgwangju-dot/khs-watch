#!/usr/bin/env python3
"""Full-field compact Telegram renderer for the preopen news radar."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import gamejoa_preopen_news_radar_contract_runner as contract
from khs_article_detail import extract_article_detail
from khs_compact_text import concise_text
import gamejoa_news_coverage_extension as coverage


telegram = contract.telegram
base = contract.base

BIOTECH_SECTOR = "諛붿씠??FDA"
BIOTECH_QUERY = (
    "諛붿씠??二쇰룄二?蹂듦? 泥댄겕",
    "biotech FDA approval PDUFA complete response letter CRL drug launch commercial sales profit guidance royalty milestone upfront licensing technology transfer pharma pipeline priority big pharma Reuters Bloomberg CNBC MarketWatch",
)
BIOTECH_TERMS = [
    "biotech", "biopharma", "pharma", "fda", "pdufa", "approval", "complete response letter",
    "crl", "clinical trial", "phase 3", "priority review", "nda", "bla", "drug launch",
    "commercial sales", "royalty", "milestone", "upfront", "license agreement", "licensing",
    "technology transfer", "out-license", "collaboration", "pipeline priority", "big pharma",
    "revenue", "profit", "earnings", "guidance", "rate cut", "real yield", "discount rate",
    "treasury", "tips", "xbi", "ibb", "湲곗닠?댁쟾", "留덉씪?ㅽ넠", "?좉툒湲?, "?꾩긽", "?뱀씤",
    "留ㅼ텧", "?곸뾽?댁씡", "鍮낇뙆留?, "?뚯씠?꾨씪??,
]
BIOTECH_DOMAIN_TERMS = [
    "biotech", "biopharma", "pharma", "fda", "pdufa", "complete response letter", "crl",
    "clinical trial", "phase 3", "priority review", "adcom", "nda", "bla", "drug launch",
    "pipeline priority", "big pharma", "xbi", "ibb", "諛붿씠??, "?쒖빟", "?좎빟", "?꾩긽",
    "鍮낇뙆留?, "?뚯씠?꾨씪??,
]
BIOTECH_TRANSFER_TERMS = [
    "technology transfer", "license agreement", "licensing", "out-license", "collaboration",
    "milestone", "upfront", "湲곗닠?댁쟾", "留덉씪?ㅽ넠", "?좉툒湲?,
]
BIOTECH_SALES_TERMS = [
    "commercial sales", "drug launch", "revenue", "profit", "earnings", "guidance", "royalty",
    "upfront", "milestone", "留ㅼ텧", "?곸뾽?댁씡", "留덉씪?ㅽ넠", "?좉툒湲?,
]
BIOTECH_FDA_TERMS = [
    "fda", "pdufa", "approval", "complete response letter", "crl", "priority review",
    "adcom", "nda", "bla", "phase 3", "?꾩긽", "?뱀씤",
]
BIOTECH_PHARMA_PRIORITY_TERMS = [
    "pipeline priority", "big pharma", "pfizer", "merck", "roche", "novartis", "lilly",
    "astrazeneca", "bristol myers", "bms", "johnson & johnson", "j&j", "sanofi", "gsk",
    "abbvie", "takeda", "鍮낇뙆留?, "?뚯씠?꾨씪??,
]
BIOTECH_DISCOUNT_TERMS = [
    "rate cut", "real yield", "discount rate", "treasury", "tips", "fed", "湲덈━", "?ㅼ쭏湲덈━",
]
ROBOTICS_SECTOR = "濡쒕큸/?앹궛?먮룞??
ROBOTICS_QUERY = (
    "?쇱꽦 濡쒕큸 ?ㅽ뻾 ?④퀎 泥댄겕",
    "Samsung Future Robotics reorganization Rainbow Robotics RB5-850 collaborative robot cobot Samsung production line factory automation deployment procurement order capex Reuters Bloomberg Samsung Electronics IR DART",
)
ROBOTICS_TERMS = [
    "samsung", "samsung electronics", "future robotics", "robotics task force", "robot organization",
    "reorganization", "restructuring", "rainbow robotics", "rb5-850", "collaborative robot",
    "cobot", "production line", "factory automation", "pilot", "test", "deployment", "adoption",
    "procurement", "purchase order", "supply contract", "order", "capex", "?쇱꽦?꾩옄", "誘몃옒濡쒕큸異붿쭊??,
    "議곗쭅媛쒗렪", "議곗쭅 ?뺣퉬", "?덉씤蹂댁슦濡쒕낫?깆뒪", "?묐룞濡쒕큸", "?앹궛?쇱씤", "?먮룞??, "?뚯뒪??,
    "?묒궛", "?꾩엯", "諛쒖＜", "怨듦툒怨꾩빟", "?섏＜",
]
ROBOTICS_DOMAIN_TERMS = [
    "future robotics", "robotics task force", "rainbow robotics", "rb5-850", "collaborative robot",
    "cobot", "robot organization", "factory automation", "誘몃옒濡쒕큸異붿쭊??, "?덉씤蹂댁슦濡쒕낫?깆뒪",
    "?묐룞濡쒕큸", "濡쒕큸", "?앹궛?쇱씤 ?먮룞??,
]
ROBOTICS_SAMSUNG_TERMS = ["samsung", "samsung electronics", "?쇱꽦?꾩옄", "?쇱꽦"]
ROBOTICS_EXECUTION_TERMS = [
    "deployment", "adoption", "procurement", "purchase order", "supply contract", "order",
    "capex", "production line", "factory automation", "commercial", "?묒궛", "?꾩엯", "諛쒖＜",
    "怨듦툒怨꾩빟", "?섏＜", "?앹궛?쇱씤", "?먮룞??, "留ㅼ텧",
]
ROBOTICS_ORG_TERMS = [
    "future robotics", "reorganization", "restructuring", "robot organization", "task force",
    "誘몃옒濡쒕큸異붿쭊??, "議곗쭅媛쒗렪", "議곗쭅 ?뺣퉬", "?ъ젙鍮?,
]
ROBOTICS_TEST_TERMS = ["rb5-850", "pilot", "test", "testing", "trial", "?뚯뒪??, "?쒕쾾", "?ㅼ쬆"]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def korean_news_search_url(query: str) -> str:
    return "https://www.bing.com/news/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "format": "rss",
            "setlang": "ko-KR",
            "cc": "KR",
        }
    )


KOREAN_BUSINESS_PUBLISHER_DOMAINS = {
    "edaily.co.kr": "?대뜲?쇰━",
    "mk.co.kr": "留ㅼ씪寃쎌젣",
    "mt.co.kr": "癒몃땲?щ뜲??,
    "biz.heraldcorp.com": "?ㅻ윺?쒓꼍??,
    "yna.co.kr": "?고빀?댁뒪",
    "yonhapnewstv.co.kr": "?고빀?댁뒪TV",
    "hankyung.com": "?쒓뎅寃쎌젣",
    "sedaily.com": "?쒖슱寃쎌젣",
    "etoday.co.kr": "?댄닾?곗씠",
    "etnews.com": "?꾩옄?좊Ц",
    "fnnews.com": "?뚯씠?몄뀥?댁뒪",
    "asiae.co.kr": "?꾩떆?꾧꼍??,
    "news1.kr": "?댁뒪1",
    "dt.co.kr": "?붿??명??꾩뒪",
    "seoul.co.kr": "?쒖슱?좊Ц",
    "zdnet.co.kr": "吏?붾꽬肄붾━??,
    "thebell.co.kr": "?붾꺼",
    "newsis.com": "?댁떆??,
    "bloter.net": "釉붾줈??,
    "wowtv.co.kr": "?쒓뎅寃쎌젣TV",
    "hankookilbo.com": "?쒓뎅?쇰낫",
    "reuters.com": "Reuters",
    "apnews.com": "AP",
    "cnbc.com": "CNBC",
}
KOREAN_BUSINESS_SEARCH_SOURCES = [
    (
        "援?궡 ?좊ː留ㅼ껜 AI쨌諛섎룄泥??묐젰",
        (
            "(?붾퉬?붿븘 OR ?쇱꽦?꾩옄 OR SK?섏씠?됱뒪 OR ?꾨?李?OR 釉뚮줈?쒖뺨 OR ?ㅽ듃濡쒗뵿) "
            "(AI OR 諛섎룄泥?OR HBM OR 濡쒕큸) "
            "(?묐젰 OR ?뚮룞 OR 怨꾩빟 OR 怨듦툒 OR ?ъ옄 OR 利앹꽕 OR ?섏＜) "
            "(site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:biz.heraldcorp.com OR site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "援?궡 ?좊ː留ㅼ껜 誘멸뎅 利앹떆쨌諛섎룄泥?,
        (
            "(?섏뒪??OR ?꾨씪?명뵾?꾨컲?꾩껜 OR ?꾨씪?명뵾??諛섎룄泥?OR SMH OR FOMC OR ?곗? OR ?좉?) "
            "(湲됰씫 OR 湲됰벑 OR ?섎씫 OR ?곸듅 OR 湲덈━ OR ?ㅼ쟻) "
            "(site:edaily.co.kr OR site:mt.co.kr OR site:mk.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "援?궡 ?좊ː留ㅼ껜 ?먮낯?쒖옣 ?뺤콉",
        (
            "(湲덉쑖?꾩썝??OR 湲덉쑖媛먮룆??OR ?쒓뎅嫄곕옒??OR ETF OR ETN OR ?덈쾭由ъ? OR 湲곕낯?덊긽湲? "
            "(?쒗뻾 OR 洹쒖젣 OR ?곹뼢 OR ?쒗븳 OR ?몄엯 OR 怨듬ℓ?? "
            "(site:mk.co.kr OR site:edaily.co.kr OR site:mt.co.kr OR "
            "site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "援?궡 ?좊ː留ㅼ껜 ?곗뾽?섏슂쨌CAPEX",
        (
            "(?곗씠?곗꽱??OR 諛섎룄泥닿났??OR 諛섎룄泥?怨듭옣 OR 泥좉컯 OR ?꾨젰留?OR 蹂?뺢린 OR ?먯쟾 OR 諛⑹궛) "
            "(?섏슂 OR ?ъ옄 OR 利앹꽕 OR ?섏＜ OR 怨꾩빟 OR ?ㅼ쟻 OR 諛쒖＜) "
            "(site:biz.heraldcorp.com OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:mt.co.kr OR site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "?대뜲?쇰━ 湲곗뾽쨌AI",
        (
            "site:edaily.co.kr (?붾퉬?붿븘 OR ?쇱꽦?꾩옄 OR SK?섏씠?됱뒪 OR ?꾨?李?OR AI OR 諛섎룄泥? "
            "(?묐젰 OR ?뚮룞 OR 怨꾩빟 OR 怨듦툒 OR ?ъ옄 OR 利앹꽕 OR ?섏＜)"
        ),
    ),
    (
        "?대뜲?쇰━ 誘멸뎅 利앹떆",
        (
            "site:edaily.co.kr (?섏뒪??OR ?꾨씪?명뵾?꾨컲?꾩껜 OR ?꾨씪?명뵾??諛섎룄泥?OR "
            "SMH OR FOMC OR ?곗? OR ?좉?) (湲됰씫 OR 湲됰벑 OR ?섎씫 OR ?곸듅)"
        ),
    ),
    (
        "留ㅼ씪寃쎌젣 ?먮낯?쒖옣",
        (
            "site:mk.co.kr (湲덉쑖?꾩썝??OR 湲덉쑖媛먮룆??OR ?쒓뎅嫄곕옒??OR ETF OR ETN OR "
            "?덈쾭由ъ? OR 湲곕낯?덊긽湲?OR ?멸뎅?? (?쒗뻾 OR 洹쒖젣 OR ?곹뼢 OR ?쒗븳 OR ?쒕ℓ??"
        ),
    ),
    (
        "癒몃땲?щ뜲??湲濡쒕쾶?쒖옣",
        (
            "site:mt.co.kr (?댁슃留덇컧 OR ?섏뒪??OR ?꾨씪?명뵾?꾨컲?꾩껜 OR ?꾨씪?명뵾??諛섎룄泥?OR "
            "FOMC OR ?곗? OR ?좉? OR ?붾퉬?붿븘 OR 留덉씠?щ줎)"
        ),
    ),
    (
        "?ㅻ윺?쒓꼍???곗뾽?섏슂",
        (
            "site:biz.heraldcorp.com (?곗씠?곗꽱??OR 諛섎룄泥닿났??OR 諛섎룄泥?怨듭옣 OR 泥좉컯 OR "
            "?꾨젰留?OR 蹂?뺢린 OR ?먯쟾 OR 諛⑹궛 OR AI) "
            "(?섏슂 OR ?ъ옄 OR 利앹꽕 OR ?섏＜ OR 怨꾩빟 OR ?ㅼ쟻)"
        ),
    ),
    (
        "?꾨?李㉱룹뿏鍮꾨뵒??AI ?묐젰",
        (
            "site:edaily.co.kr (?뺤쓽??OR ?꾨?李? ?붾퉬?붿븘 "
            "(?뚮룞 OR ?묐젰 OR 濡쒕큸 OR ?먯쑉二쇳뻾 OR ?쒖“AI)"
        ),
    ),
    (
        "AI ?명봽??泥좉컯 ?섏슂",
        (
            "site:biz.heraldcorp.com (?곗씠?곗꽱??OR 諛섎룄泥닿났??OR 諛섎룄泥?怨듭옣) "
            "(泥좉컯 OR ?뺢컯 OR ?꾪뙋) ?섏슂"
        ),
    ),
    (
        "援?궡 AI 怨꾩빟쨌理쒓퀬寃쎌쁺???뚮룞",
        (
            "(?댁옱??OR ?뺤쓽??OR SK?섏씠?됱뒪 OR SK?붾젅肄?OR ?ㅼ씠踰? "
            "(?섏삱?몃㉫ OR ???ы듃癒?OR ?ㅽ뵂AI OR ?붾퉬?붿븘 OR ?좎뒯??OR ?좎뒯 ??"
            "OR 留덉씠?щ줈?뚰봽??OR ?ㅽ듃濡쒗뵿) "
            "(HBM OR ?뚯슫?쒕━ OR 硫붾え由?OR AI?⑺넗由?OR AI ?⑺넗由?OR ?곗씠?곗꽱??OR 濡쒕큸) "
            "(怨꾩빟 OR 怨듦툒 OR ?뚮룞 OR ?묒쓽 OR ?꾩엯 OR 援ъ텞) "
            "(site:yna.co.kr OR site:mk.co.kr OR site:hankyung.com OR "
            "site:edaily.co.kr OR site:dt.co.kr OR site:fnnews.com)"
        ),
    ),
    (
        "湲濡쒕쾶 VC쨌K?ㅽ??몄뾽 ?먮낯",
        (
            "(a16z OR 踰ㅼ쿂罹먰뵾??OR ?ㅻ━肄섎갭由?OR VC) "
            "(K?ㅽ??몄뾽 OR ?쒓뎅?ㅽ??몄뾽 OR ?쒓뎅 ?ㅽ??몄뾽 OR ?쒓뎅?ъ옄) "
            "(?ъ옄 OR ???OR ?댁슜?먯궛 OR ?묐젰) "
            "(site:hankyung.com OR site:mk.co.kr OR site:fnnews.com OR site:asiae.co.kr)"
        ),
    ),
    (
        "以묐룞쨌?좉?쨌臾쇨?쨌?섏쑉",
        (
            "(?대? OR ?몃Ⅴ臾댁쫰 OR ?꾪떚 OR ?ъ슦??OR 以묐룞) "
            "(怨듭뒿 OR ?댁쟾 OR 異⑸룎 OR ?좉? OR ?댁엫 OR 臾쇨? OR ?섏쑉 OR 湲덈━) "
            "(site:yna.co.kr OR site:yonhapnewstv.co.kr OR site:news1.kr OR "
            "site:mt.co.kr OR site:edaily.co.kr OR site:dt.co.kr)"
        ),
    ),
    (
        "鍮낇뀒??AI CAPEX쨌媛먯썝",
        (
            "(鍮낇뀒??OR 湲곗닠湲곗뾽 OR 留덉씠?щ줈?뚰봽??OR 援ш? OR ?꾨쭏議?OR 硫뷀?) "
            "(AI?ъ옄 OR AI ?ъ옄 OR CAPEX OR ?곗씠?곗꽱?? "
            "(媛먯썝 OR ?쇱옄由?OR ?몃젰媛먯텞 OR ?ъ옄) "
            "(site:etoday.co.kr OR site:mk.co.kr OR site:mt.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "以묎뎅 硫붾え由?텶PO쨌ETF",
        (
            "(CXMT OR 李쎌떊硫붾え由?OR SMIC OR 以묎뎅諛섎룄泥?OR 以묎뎅 諛섎룄泥? "
            "(?곸옣 OR IPO OR ETF OR 利앹꽕 OR 硫붾え由ш?寃?OR 硫붾え由?媛寃? "
            "(site:asiae.co.kr OR site:hankyung.com OR site:mk.co.kr OR site:mt.co.kr)"
        ),
    ),
    (
        "援?궡 ETF ?ㅼ닔?붋룸젅踰꾨━吏 洹쒖젣",
        (
            "(ETF OR ETN) (媛쒖씤 OR ?멸뎅??OR 湲곌? OR ?⑥씪醫낅ぉ) "
            "(?쒕ℓ??OR ?쒕ℓ??OR 湲곕낯?덊긽湲?OR ?덈쾭由ъ? OR ?쒗뻾) "
            "(site:etoday.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:edaily.co.kr OR site:asiae.co.kr)"
        ),
    ),
    (
        "湲곗뾽 ?ㅼ쟻쨌怨듦툒遺議굿룹떆?μ젏?좎쑉",
        (
            "(?쇱꽦?꾩옄 OR SK?섏씠?됱뒪 OR ?좏뵆 OR ?꾨쭏議?OR ?ㅼ삦?쒖븘 OR LG CNS) "
            "(?ㅼ쟻 OR ?곸뾽?댁씡 OR 留ㅼ텧 OR 媛?대뜕??OR 怨듦툒遺議?OR 怨듦툒 遺議?OR ?먯쑀??OR HBM4 OR HBM4E) "
            "(site:seoul.co.kr OR site:zdnet.co.kr OR site:thebell.co.kr OR site:newsis.com OR "
            "site:bloter.net OR site:wowtv.co.kr OR site:hankookilbo.com OR site:yna.co.kr)"
        ),
    ),
    (
        "AI 紐⑤뜽쨌?곗씠?곗꽱??援ъ텞",
        (
            "(K-?묒궗??OR ?뚯슫?곗씠?섎え??OR ?뚯슫?곗씠??紐⑤뜽 OR ?μ떆??OR AI?곗씠?곗꽱??OR AI ?곗씠?곗꽱?? "
            "(怨듦컻 OR 異쒖떆 OR 嫄댁꽕 OR ?ъ옄 OR ?섏슂 OR ?곸슜?? "
            "(site:zdnet.co.kr OR site:thebell.co.kr OR site:newsis.com OR site:bloter.net OR "
            "site:wowtv.co.kr OR site:hankookilbo.com OR site:hankyung.com)"
        ),
    ),
    (
        "諛붿씠???덇?쨌?곸뾽??,
        (
            "(?덈ぉ?덇? OR ?덇?沅뚭퀬 OR ?덇? 沅뚭퀬 OR ?꾩긽寃곌낵 OR ?꾩긽 寃곌낵 OR ?곸뾽?? "
            "(?좎빟 OR ?섏빟??OR 諛붿씠??OR 移섎즺?? "
            "(site:newsis.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mt.co.kr OR "
            "site:hankyung.com OR site:thebell.co.kr)"
        ),
    ),
    (
        "?섍툒쨌?먮낯?됱궗쨌?명솚",
        (
            "(?섎Т蹂댁쑀 OR 蹂댄샇?덉닔 OR ?좎긽利앹옄 OR ?몄닔 OR ?⑸퀝 OR ?명솚嫄곕옒 OR 吏遺?OR 二쇱떇遺꾪븷) "
            "(?댁젣 OR 寃곗젙 OR 理쒕? OR 怨듭떆 OR 痍⑤뱷 OR 留ㅼ닔 OR 利앷?) "
            "(site:newsis.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:mt.co.kr OR site:thebell.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "?몃읆??愿?맞룹썝?먯옱쨌以묐룞",
        (
            "(?몃읆??OR 誘멸뎅 OR ?대? OR ?섎쭏?? "
            "(愿?몃㈃??OR 愿??硫댁젣 OR 援щ━ OR ?앹쑀 OR 媛??OR ?ㅼ씠?꾨が??OR 臾댁옣?댁젣 OR 以묐룞?꾩웳 OR 以묐룞 ?꾩웳) "
            "(site:seoul.co.kr OR site:newsis.com OR site:yna.co.kr OR site:edaily.co.kr OR "
            "site:mt.co.kr OR site:hankookilbo.com OR site:wowtv.co.kr)"
        ),
    ),
    (
        "?몃읆???대?쨌嫄명봽 援곗궗湲댁옣",
        (
            "(?몃읆??OR Trump) (?대? OR Iran OR 荑좎썾?댄듃 OR Kuwait OR 嫄명봽) "
            "(異붽?怨듦꺽 OR 異붽? 怨듦꺽 OR 怨듦꺽?꾨컯 OR 怨듦꺽 ?꾨컯 OR ?쒕줎怨듦꺽 OR ?쒕줎 怨듦꺽) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:newsis.com OR site:seoul.co.kr OR site:yonhapnewstv.co.kr)"
        ),
    ),
    (
        "?고겕?쇱씠???ㅽ?留곹겕 援곗궗?ъ슜 ?뱀씤",
        (
            "(?ㅻ젋?ㅽ궎 OR Zelensky OR ?고겕?쇱씠??OR Ukraine) "
            "(?ㅽ?留곹겕 OR Starlink) (?몃읆??OR Trump OR ?뱀씤 OR ?寃?OR strike) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:newsis.com OR site:seoul.co.kr)"
        ),
    ),
    (
        "媛???댁쟾쨌?섎쭏??臾댁옣?댁젣",
        (
            "(媛??OR Gaza OR ?섎쭏??OR Hamas) "
            "(?댁쟾 OR ceasefire OR 臾댁옣?댁젣 OR 臾댁옣 ?댁젣 OR disarmament OR ?됲솕?묒젙) "
            "(?몃읆??OR Trump OR ?꾩썝??OR committee) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:newsis.com OR site:seoul.co.kr OR site:yonhapnewstv.co.kr)"
        ),
    ),
    (
        "?⑥씪醫낅ぉ ?덈쾭由ъ? 援?젙議곗궗쨌泥?Ц??,
        (
            "(?⑥씪醫낅ぉ?덈쾭由ъ? OR ?⑥씪醫낅ぉ ?덈쾭由ъ? OR ?덈쾭由ъ?ETF OR ?덈쾭由ъ? ETF) "
            "(援?젙議곗궗 OR 泥?Ц??OR 議곗궗?붽뎄 OR 議곗궗 ?붽뎄 OR 諛쒖쓽 OR 議곗궗李⑹닔 OR 議곗궗 李⑹닔) "
            "(site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:kmib.co.kr OR site:metroseoul.co.kr OR site:asiae.co.kr)"
        ),
    ),
]

coverage.apply_source_extensions(
    KOREAN_BUSINESS_PUBLISHER_DOMAINS,
    KOREAN_BUSINESS_SEARCH_SOURCES,
    base.TRUSTED,
)

append_unique(
    base.SOURCES,
    [
        *coverage.DIRECT_RSS_SOURCES,
        (
            "?댄닾?곗씠 ?꾩껜?댁뒪",
            "https://rss.etoday.co.kr/eto/etoday_news_all.xml",
            "trusted",
        ),
        (
            "?댄닾?곗씠 留덉폆",
            "https://rss.etoday.co.kr/eto/market_news.xml",
            "trusted",
        ),
        (
            "?댄닾?곗씠 ?곗뾽",
            "https://rss.etoday.co.kr/eto/industry_news.xml",
            "trusted",
        ),
        (
            "?꾩옄?좊Ц ?ㅻ뒛???댁뒪",
            "https://rss.etnews.com/Section901.xml",
            "trusted",
        ),
        (
            "?꾩옄?좊Ц ?띾낫",
            "https://rss.etnews.com/Section902.xml",
            "trusted",
        ),
        (
            "?꾩옄?좊Ц ?꾩옄?곗뾽",
            "https://rss.etnews.com/06.xml",
            "trusted",
        ),
        *[
            (name, korean_news_search_url(query), "trusted")
            for name, query in KOREAN_BUSINESS_SEARCH_SOURCES
        ],
    ],
)
append_unique(
    base.TRUSTED,
    [
        "?댄닾?곗씠",
        "etoday",
        "?꾩옄?좊Ц",
        "etnews",
        "?대뜲?쇰━",
        "edaily",
        "留ㅼ씪寃쎌젣",
        "mk.co.kr",
        "癒몃땲?щ뜲??,
        "mt.co.kr",
        "?ㅻ윺?쒓꼍??,
        "heraldcorp",
        "?고빀?댁뒪",
        "yna.co.kr",
        "?쒓뎅寃쎌젣",
        "hankyung",
        "?쒖슱寃쎌젣",
        "sedaily",
        "?고빀?댁뒪TV",
        "yonhapnewstv",
        "?뚯씠?몄뀥?댁뒪",
        "fnnews",
        "?꾩떆?꾧꼍??,
        "asiae",
        "?댁뒪1",
        "news1",
        "?붿??명??꾩뒪",
        "dt.co.kr",
    ],
)
append_unique(
    base.TERMS,
    [
        "?멸뎅??,
        "?쒕ℓ??,
        "?쒕ℓ??,
        "?쇱꽦?꾩옄",
        "sk?섏씠?됱뒪",
        "?섏씠?됱뒪",
        "hbm",
        "cxl",
        "?뚯뒪??,
        "?묒궛?됯?",
        "?곸슜??,
        "怨듦툒怨꾩빟",
        "?κ린 怨듦툒",
        "?κ린怨듦툒",
        "?섏＜",
        "媛먯썝",
        "湲곕낯?덊긽湲?,
        "ai ?⑺넗由?,
        "a16z",
        "cxmt",
        "???ы듃癒?,…63706 tokens truncated…ize it before length handling so one damaged snippet cannot
    # invalidate the complete Telegram payload.
    text = re.sub(r"\s*(?:??|\.{3,})\s*", ". ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        if re.search(r"[.!???$", text):
            return text
        suffix = "." if re.search(r"(?:????????????$", text) else "?낅땲??"
        if len(text) + len(suffix) <= limit:
            return text + suffix
    head = text[: limit + 1]
    sentence_ends = [
        match.end()
        for match in re.finditer(r"(?:[.!???|??(?=\s|$)", head)
        if match.end() >= int(limit * 0.55)
    ]
    if sentence_ends:
        return head[: sentence_ends[-1]].rstrip()
    boundary = max(
        head.rfind(",", int(limit * 0.55), limit),
        head.rfind("쨌", int(limit * 0.55), limit),
        head.rfind(";", int(limit * 0.55), limit),
        head.rfind(" ", int(limit * 0.7), limit),
    )
    if boundary < int(limit * 0.55):
        boundary = limit - 4
    return head[:boundary].rstrip(" ,쨌;:.") + "?낅땲??"


def compact_gamejoa_prose_lines(body: str) -> tuple[str, int]:
    limits = {
        "- ?듭떖:": GAMEJOA_CORE_MAX_CHARS,
    }
    output: list[str] = []
    changed = 0
    for raw_line in str(body or "").splitlines():
        stripped = raw_line.strip()
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        compacted_line = raw_line
        for prefix, limit in limits.items():
            if not stripped.startswith(prefix):
                continue
            value = stripped.removeprefix(prefix).strip()
            compacted = complete_prose_text(value, limit=limit)
            compacted_line = f"{indent}{prefix} {compacted}"
            changed += compacted != value
            break
        output.append(compacted_line)
    suffix = "\n" if str(body or "").endswith("\n") else ""
    return "\n".join(output) + suffix, changed


def compact_title_summary_aligned(title: str, summary: str) -> bool:
    title_low = clean_article_summary_text(title).lower()
    summary_low = clean_article_summary_text(summary).lower()
    event_rules = (
        (("吏吏?, "媛뺤쭊", "?곕굹誘?), ("吏吏?, "媛뺤쭊", "?곕굹誘?, "???, "諛⑹옱", "??컻")),
        (("?ъ씠?쒖뭅", "?쒗궥釉뚮젅?댁빱"), ("?ъ씠?쒖뭅", "?쒗궥釉뚮젅?댁빱", "?꾨줈洹몃옩 留ㅼ닔", "?꾨줈洹몃옩 留ㅻ룄")),
    )
    for title_terms, summary_terms in event_rules:
        if any(term in title_low for term in title_terms):
            return any(term in summary_low for term in summary_terms)
    if "?ъ씠?쒖뭅" in summary_low and not any(
        term in title_low for term in ("?ъ씠?쒖뭅", "肄붿뒪??, "肄붿뒪??, "利앹떆")
    ):
        return False
    return True


def compact_alert_block_errors(block: str) -> list[str]:
    errors: list[str] = []
    title = ""
    summary = ""
    for line in str(block or "").splitlines():
        visible = html.unescape(line).strip()
        if re.match(r"^\d+\)\s+\[", visible):
            title = re.sub(r"^\d+\)\s+\[[^\]]+\]\s*", "", visible).strip()
            title = re.sub(r"\(\d+嫄?臾띠쓬\)$", "", title).strip()
        elif visible.startswith("- ?듭떖:"):
            summary = visible.removeprefix("- ?듭떖:").strip()
    if not title:
        errors.append("missing_title")
    elif mostly_ascii(title):
        errors.append("raw_english_heading")
    if not summary:
        errors.append("missing_core")
        return errors
    if len(summary) > GAMEJOA_CORE_MAX_CHARS:
        errors.append("core_too_long")
    if "?? in summary or re.search(r"\.{3,}", summary):
        errors.append("truncated_core")
    if re.search(
        r"(?:蹂대떎|?먭쾶|?먯꽌|?쇰줈|?|怨??|????媛|??瑜???硫?怨?(?:[.!???)?$",
        summary,
    ):
        errors.append("incomplete_core")
    if title and (summary == title or article_title_restatement(summary, title)):
        errors.append("headline_repeated_as_summary")
    if title and not compact_title_summary_aligned(title, summary):
        errors.append("title_core_mismatch")
    if any(term.lower() in summary.lower() for term in ARTICLE_UI_BOILERPLATE_TERMS):
        errors.append("article_ui_boilerplate")
    foreign_amounts = extract_foreign_amounts(summary)
    if foreign_amounts and not (
        re.search(r"\(??s*[\d,.]+(?:議???留????)", summary)
        or "?먰솕 ?섏궛 ?뺤씤 遺덇?" in summary
    ):
        errors.append("foreign_currency_not_converted")
    return errors


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    alert = normalize_alert_for_output(alert)
    examples = alert.get("examples") or []
    count_suffix = f" ({alert['cluster_count']}嫄?臾띠쓬)" if alert.get("cluster_count") else ""
    status = alert.get("status") or ("怨듭떇 ?뺤씤 ?? if examples else "?뺤씤 遺덇?")
    impacts = alert.get("impacts") or ["?섏궗寃곗젙 ?곹뼢 ?쒗븳??]
    displayed_impacts = display_impacts(impacts)
    interpretation = alert.get("interpretation") or "??踰꾨뒗 ?λ젰, ?좎씤?? ?섍툒, ?쒓컙??以??섎굹瑜?諛붽? ???덈뒗吏 ?뺤씤?댁빞 ?⑸땲??"
    title = display_news(alert)
    first_impact = displayed_impacts[0] if displayed_impacts else "?섏궗寃곗젙"
    article_core = (
        alert.get("telegram_core_fact")
        if alert.get("korean_business_news")
        else ""
    )
    if alert.get("memory_antitrust_lawsuit"):
        core = "\uc0bc\uc131\uc804\uc790\u00b7SK\ud558\uc774\ub2c9\uc2a4\u00b7Micron\uc5d0 DRAM \uac00\uaca9\ub2f4\ud569 \uc9d1\ub2e8\uc18c\uc1a1\uc774 \uc81c\uae30\ub410\uc2b5\ub2c8\ub2e4."
    else:
        core = complete_prose_text(
            article_core or alert.get("policy_plain_summary"),
            fallback=title,
            limit=GAMEJOA_CORE_MAX_CHARS,
        )
    conversion = alert.get("fx_conversion") or {"amounts": []}
    core = compact_converted_core(core, conversion, limit=GAMEJOA_CORE_MAX_CHARS)

    lines = [f"{idx}) [{safe(alert.get('importance'))} | {safe(status)}] {safe(title)}{html.escape(count_suffix, quote=False)}"]
    if examples:
        source_text = source_summary(examples[:4])
    else:
        source_text = html_link(
            "?먮Ц ?댁뒪蹂닿린",
            alert.get("link") or "",
        )
    fx_source = fx_provenance_text(conversion)
    if fx_source:
        source_text = f"{source_text} 쨌 ?섏쑉: {fx_source}"

    lines += [
        f"- ?듭떖: {safe(core)}",
        f"- 異쒖쿂: {source_text}",
        "",
    ]
    return "\n".join(lines)


def compact_quality_final_alerts(alerts: list[dict], limit: int) -> list[dict]:
    """Return only alerts that can be rendered, keeping report/JSON/send in sync."""
    now = base.kst_now()
    candidates = quality_display_alerts(alerts, max(limit * 2, limit))
    needs_fx = any(extract_foreign_amounts(alert_text(alert)) for alert in candidates)
    fx_snapshot = collect_fx_snapshot(candidates, now) if needs_fx else {"rates": {}}
    selected: list[dict] = []
    for alert in candidates:
        alert["fx_conversion"] = build_alert_fx_conversion(alert, fx_snapshot, now)
        block = compact_alert(alert, len(selected) + 1, now, {}, {})
        block_errors = compact_alert_block_errors(block)
        if block_errors:
            alert["_exclusion_reason"] = "compact_quality:" + ",".join(block_errors)
            print(
                "GAMEJOA final alert dropped "
                f"title={display_news(alert)!r} errors={','.join(block_errors)}"
            )
            continue
        selected.append(alert)
        if len(selected) >= limit:
            break
    return selected


def compact_report(alerts: list[dict], fred: dict, te: dict, now) -> str:
    limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "7"))))
    candidates = alerts[: max(limit * 2, limit)]
    fx_snapshot = collect_fx_snapshot(candidates, now)
    for alert in candidates:
        alert["fx_conversion"] = build_alert_fx_conversion(alert, fx_snapshot, now)
    live_mode = os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live"
    if live_mode:
        title = f"?벐 ?ㅼ떆媛??듭떖 ?댁뒪 ?덉씠??쨌 {now:%Y??%m??%d?? 쨌 {now:%H:%M}"
        empty_line = "?ㅼ떆媛?怨좎땐寃??댁뒪 吏곸젒 ?뺤씤 ?놁쓬"
    else:
        title = f"?벐 GAMEJOA ?μ쟾 ?듭떖 ?댁뒪 ?덉씠??쨌 {now:%Y??%m??%d?? 쨌 06:30"
        comment_title = "?뮕 06:30 ?μ쟾 ?댁뒪 肄붾찘??
        followup_line = "06:50 ?ъ옄湲곗긽?꾩뿉???섏튂쨌?섍툒쨌?뚮쭏? ?ы솗???꾩슂."
        empty_line = "?μ쟾 怨좎땐寃??댁뒪 吏곸젒 ?뺤씤 ?놁쓬"

    visible: list[dict] = []
    rendered: list[str] = []
    for alert in candidates:
        block = compact_alert(alert, len(rendered) + 1, now, fred, te)
        block_errors = compact_alert_block_errors(block)
        if block_errors:
            print(
                "GAMEJOA compact item dropped "
                f"title={display_news(alert)!r} errors={','.join(block_errors)}"
            )
            continue
        visible.append(alert)
        rendered.append(block)
        if len(rendered) >= limit:
            break

    lines = [title, f"?좊퀎: ?듭떖 {len(rendered)}嫄?, ""]
    if rendered:
        lines.extend(rendered)
        changed = "쨌".join(display_impacts(visible[0].get("impacts")))
    else:
        lines += [empty_line, ""]
        changed = "紐낇솗??蹂???놁쓬"
    if not live_mode:
        lines += [
            comment_title,
            f"?ㅻ뒛 ?듭떖 蹂?붾뒗 `{safe(changed)}`?낅땲??",
            f"?좎씤?? {safe(telegram.compact_real_yield(fred, te))}",
            followup_line,
        ]
    report = "\n".join(lines).strip() + "\n"
    return guard_preopen_report(report)


def guard_preopen_report(text: str) -> str:
    text, compacted_fields = compact_gamejoa_prose_lines(text)
    errors: list[str] = []
    valid_title = (
        text.startswith("?벐 GAMEJOA ?μ쟾 ?듭떖 ?댁뒪 ?덉씠??쨌 ")
        or text.startswith("?벐 ?ㅼ떆媛??듭떖 ?댁뒪 ?덉씠??쨌 ")
    )
    if not valid_title:
        errors.append("title_contract")
    item_count = sum(1 for line in text.splitlines() if re.match(r"^\d+\)\s+\[", line))
    required = [
        "- ?듭떖:",
        "- 異쒖쿂:",
    ]
    for marker in required:
        if item_count and text.count(marker) < item_count:
            errors.append(f"missing_{marker}")
    forbidden_markers = (
        "- 湲곗?/?쒓컖:",
        "- 寃쎈줈/?뱁꽣:",
        "- ?ъ옄 ?ъ씤??",
        "- ?섏궗寃곗젙 ?곹뼢:",
        "- ?쒓뎅??",
        "- 諛섏쁺/諛섎?:",
        "- ?ㅽ뙣 ?좏샇:",
    )
    for marker in forbidden_markers:
        if item_count and marker in text:
            errors.append(f"forbidden_compact_marker={marker}")
    if text.startswith("?벐 ?ㅼ떆媛??듭떖 ?댁뒪 ?덉씠??쨌 ") and "?뮕 ?ㅼ떆媛??댁뒪 肄붾찘?? in text:
        errors.append("forbidden_live_commentary")
    for marker in ("?명솕 ?섏궛:", "??):
        if marker in text:
            errors.append(f"forbidden_currency_format={marker}")
    for phrase in GENERIC_EXPLANATION_PHRASES:
        if item_count and phrase in text:
            errors.append("generic_policy_explanation_displayed")
    for line in text.splitlines():
        if not re.match(r"^\d+\)\s+\[", line):
            continue
        title = re.sub(r"^\d+\)\s+\[[^\]]+\]\s*", "", line).strip()
        title = re.sub(r"\(\d+嫄?臾띠쓬\)$", "", title).strip()
        if mostly_ascii(title):
            errors.append(f"raw_english_heading={title[:80]}")
    low = re.sub(r"https?://\S+", "", text).lower()
    for marker in [
        "this document is also available in the following formats",
        "normalized attributes and metadata",
        "original full text xml",
        "government publishing office metadata",
        "developer tools pages",
    ]:
        if marker in low:
            errors.append(f"federal_register_boilerplate={marker}")
    for marker in ["臾대떒 ?꾩옱", "?щ같??湲덉?", "ai ?숈뒿 諛??쒖슜 湲덉?"]:
        if marker in low:
            errors.append(f"article_boilerplate={marker}")
    for line in text.splitlines():
        visible_line = html.unescape(line)
        if not visible_line.startswith("- ?듭떖:"):
            continue
        prefix = "- ?듭떖:"
        summary = visible_line.removeprefix(prefix).strip()
        limit = GAMEJOA_CORE_MAX_CHARS
        if len(summary) > limit:
            errors.append(f"compact_field_too_long={prefix}{len(summary)}")
        if "?? in summary or re.search(r"\.{3,}", summary):
            errors.append(f"truncated_compact_field={prefix}")
        if any(term.lower() in summary.lower() for term in ARTICLE_UI_BOILERPLATE_TERMS):
            errors.append("article_ui_boilerplate")
        if re.search(
            r"(?:蹂대떎|?먭쾶|?먯꽌|?쇰줈|?|怨??|????媛|??瑜???硫?怨?(?:[.!???)?$",
            summary,
        ):
            errors.append(f"incomplete_article_summary={summary[-30:]}")
        foreign_amounts = extract_foreign_amounts(summary)
        if foreign_amounts and not (
            re.search(r"\(??s*[\d,.]+(?:議???留????)", summary)
            or "?먰솕 ?섏궛 ?뺤씤 遺덇?" in summary
        ):
            errors.append("foreign_currency_not_converted")
    current_title = ""
    for line in text.splitlines():
        if re.match(r"^\d+\)\s+\[", line):
            current_title = re.sub(r"^\d+\)\s+\[[^\]]+\]\s*", "", html.unescape(line)).strip()
            current_title = re.sub(r"\(\d+嫄?臾띠쓬\)$", "", current_title).strip()
            continue
        if current_title and line.startswith("- ?듭떖:"):
            summary = html.unescape(line.removeprefix("- ?듭떖:").strip())
            if summary == current_title or article_title_restatement(summary, current_title):
                errors.append("headline_repeated_as_summary")
    if errors:
        raise RuntimeError("GAMEJOA preopen radar quality guard blocked Telegram output: " + "; ".join(errors))
    if compacted_fields:
        print(f"GAMEJOA compact prose rewritten={compacted_fields}")
    return text


def send_telegram(text: str) -> None:
    text = guard_preopen_report(text)
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if is_empty_radar_report(text) and not should_send_empty_radar():
        write_delivery_status("skipped_empty", chat_id, len(text), "No high-impact radar item selected")
        print(f"Telegram: skipped empty radar original_chars={len(text)}")
        return
    if not preopen_send_window_open():
        write_delivery_status("skipped_off_window", chat_id, len(text), "Outside GAMEJOA preopen Telegram send window")
        print(f"Telegram: skipped outside preopen send window original_chars={len(text)}")
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not chat_id:
        write_delivery_status("blocked", chat_id, len(text), "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        raise RuntimeError("Telegram delivery blocked: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
    message = fit_telegram_html(text, base.TELEGRAM_LIMIT)
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
        "parse_mode": "HTML",
    }).encode("utf-8")
    last_error = ""
    for attempt in range(1, 4):
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                resp.read()
            write_delivery_status("sent", chat_id, len(text), "", len(message), attempt)
            print(f"Telegram: sent chars={len(message)} original_chars={len(text)} attempt={attempt}")
            return
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", "replace")[:500]
            last_error = f"Telegram HTTP {exc.code}: {error_text}"
            if attempt < 3 and (exc.code == 429 or exc.code >= 500):
                retry_after = exc.headers.get("retry-after")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else attempt
                time.sleep(delay)
                continue
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < 3:
                time.sleep(attempt)
                continue
            break
    write_delivery_status("failed", chat_id, len(text), last_error, len(message), 3)
    raise RuntimeError(f"Telegram delivery failed: {last_error}")


def is_empty_radar_report(text: str) -> bool:
    return "?좊퀎: ?듭떖 0嫄? in text


def should_send_empty_radar() -> bool:
    return os.getenv("SEND_EMPTY_RADAR", "").lower() in {"1", "true", "yes", "y"}


def parse_hhmm(value: str, fallback: tuple[int, int]) -> int:
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", value or "")
    if not match:
        return fallback[0] * 60 + fallback[1]
    hour, minute = int(match.group(1)), int(match.group(2))
    return max(0, min(23, hour)) * 60 + max(0, min(59, minute))


def preopen_send_window_open() -> bool:
    if os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live":
        return True
    if os.getenv("ALLOW_OFF_WINDOW_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        return True
    now = base.kst_now()
    current = now.hour * 60 + now.minute
    start = parse_hhmm(os.getenv("PREOPEN_SEND_WINDOW_START_KST", "05:30"), (5, 30))
    end = parse_hhmm(os.getenv("PREOPEN_SEND_WINDOW_END_KST", "07:30"), (7, 30))
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def fit_telegram_html(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n\n?꾩껜 蹂닿퀬?쒕뒗 GitHub Actions artifact?먯꽌 ?뺤씤 ?꾩슂."
    candidate = text[: max(0, limit - len(suffix))]
    newline = candidate.rfind("\n")
    if newline > 1800:
        candidate = candidate[:newline]
    if candidate.count("<a ") > candidate.count("</a>"):
        candidate = candidate[: candidate.rfind("<a ")].rstrip()
    return (candidate.rstrip() + suffix)[:limit]


def write_delivery_status(
    status: str,
    chat_id: str,
    original_chars: int,
    error: str = "",
    sent_chars: int | None = None,
    attempts: int | None = None,
) -> None:
    payload = {
        "status": status,
        "chat_id_masked": mask_chat_id(chat_id),
        "original_chars": original_chars,
        "sent_chars": sent_chars,
        "attempts": attempts,
        "error": error,
    }
    base.OUT.mkdir(exist_ok=True)
    (base.OUT / "gamejoa_preopen_news_radar_delivery.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def mask_chat_id(value: str) -> str:
    if not value:
        return ""
    return "*" * max(0, len(value) - 4) + value[-4:]


telegram.compact_report = compact_report
telegram.send_telegram = send_telegram
telegram.final_alerts_for_output = compact_quality_final_alerts
telegram.canonical_alert_for_seen = normalize_alert_for_output


if __name__ == "__main__":
    raise SystemExit(telegram.main())

