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

BIOTECH_SECTOR = "ë°”ì´ì˜¤/FDA"
BIOTECH_QUERY = (
    "ë°”ì´ì˜¤ ì£¼ë„ì£¼ ë³µê·€ ì²´í¬",
    "biotech FDA approval PDUFA complete response letter CRL drug launch commercial sales profit guidance royalty milestone upfront licensing technology transfer pharma pipeline priority big pharma Reuters Bloomberg CNBC MarketWatch",
)
BIOTECH_TERMS = [
    "biotech", "biopharma", "pharma", "fda", "pdufa", "approval", "complete response letter",
    "crl", "clinical trial", "phase 3", "priority review", "nda", "bla", "drug launch",
    "commercial sales", "royalty", "milestone", "upfront", "license agreement", "licensing",
    "technology transfer", "out-license", "collaboration", "pipeline priority", "big pharma",
    "revenue", "profit", "earnings", "guidance", "rate cut", "real yield", "discount rate",
    "treasury", "tips", "xbi", "ibb", "ê¸°ìˆ ì´ì „", "ë§ˆì¼ìŠ¤í†¤", "ì„ ê¸‰ê¸ˆ", "ìž„ìƒ", "ìŠ¹ì¸",
    "ë§¤ì¶œ", "ì˜ì—…ì´ìµ", "ë¹…íŒŒë§ˆ", "íŒŒì´í”„ë¼ì¸",
]
BIOTECH_DOMAIN_TERMS = [
    "biotech", "biopharma", "pharma", "fda", "pdufa", "complete response letter", "crl",
    "clinical trial", "phase 3", "priority review", "adcom", "nda", "bla", "drug launch",
    "pipeline priority", "big pharma", "xbi", "ibb", "ë°”ì´ì˜¤", "ì œì•½", "ì‹ ì•½", "ìž„ìƒ",
    "ë¹…íŒŒë§ˆ", "íŒŒì´í”„ë¼ì¸",
]
BIOTECH_TRANSFER_TERMS = [
    "technology transfer", "license agreement", "licensing", "out-license", "collaboration",
    "milestone", "upfront", "ê¸°ìˆ ì´ì „", "ë§ˆì¼ìŠ¤í†¤", "ì„ ê¸‰ê¸ˆ",
]
BIOTECH_SALES_TERMS = [
    "commercial sales", "drug launch", "revenue", "profit", "earnings", "guidance", "royalty",
    "upfront", "milestone", "ë§¤ì¶œ", "ì˜ì—…ì´ìµ", "ë§ˆì¼ìŠ¤í†¤", "ì„ ê¸‰ê¸ˆ",
]
BIOTECH_FDA_TERMS = [
    "fda", "pdufa", "approval", "complete response letter", "crl", "priority review",
    "adcom", "nda", "bla", "phase 3", "ìž„ìƒ", "ìŠ¹ì¸",
]
BIOTECH_PHARMA_PRIORITY_TERMS = [
    "pipeline priority", "big pharma", "pfizer", "merck", "roche", "novartis", "lilly",
    "astrazeneca", "bristol myers", "bms", "johnson & johnson", "j&j", "sanofi", "gsk",
    "abbvie", "takeda", "ë¹…íŒŒë§ˆ", "íŒŒì´í”„ë¼ì¸",
]
BIOTECH_DISCOUNT_TERMS = [
    "rate cut", "real yield", "discount rate", "treasury", "tips", "fed", "ê¸ˆë¦¬", "ì‹¤ì§ˆê¸ˆë¦¬",
]
ROBOTICS_SECTOR = "ë¡œë´‡/ìƒì‚°ìžë™í™”"
ROBOTICS_QUERY = (
    "ì‚¼ì„± ë¡œë´‡ ì‹¤í–‰ ë‹¨ê³„ ì²´í¬",
    "Samsung Future Robotics reorganization Rainbow Robotics RB5-850 collaborative robot cobot Samsung production line factory automation deployment procurement order capex Reuters Bloomberg Samsung Electronics IR DART",
)
ROBOTICS_TERMS = [
    "samsung", "samsung electronics", "future robotics", "robotics task force", "robot organization",
    "reorganization", "restructuring", "rainbow robotics", "rb5-850", "collaborative robot",
    "cobot", "production line", "factory automation", "pilot", "test", "deployment", "adoption",
    "procurement", "purchase order", "supply contract", "order", "capex", "ì‚¼ì„±ì „ìž", "ë¯¸ëž˜ë¡œë´‡ì¶”ì§„ë‹¨",
    "ì¡°ì§ê°œíŽ¸", "ì¡°ì§ ì •ë¹„", "ë ˆì¸ë³´ìš°ë¡œë³´í‹±ìŠ¤", "í˜‘ë™ë¡œë´‡", "ìƒì‚°ë¼ì¸", "ìžë™í™”", "í…ŒìŠ¤íŠ¸",
    "ì–‘ì‚°", "ë„ìž…", "ë°œì£¼", "ê³µê¸‰ê³„ì•½", "ìˆ˜ì£¼",
]
ROBOTICS_DOMAIN_TERMS = [
    "future robotics", "robotics task force", "rainbow robotics", "rb5-850", "collaborative robot",
    "cobot", "robot organization", "factory automation", "ë¯¸ëž˜ë¡œë´‡ì¶”ì§„ë‹¨", "ë ˆì¸ë³´ìš°ë¡œë³´í‹±ìŠ¤",
    "í˜‘ë™ë¡œë´‡", "ë¡œë´‡", "ìƒì‚°ë¼ì¸ ìžë™í™”",
]
ROBOTICS_SAMSUNG_TERMS = ["samsung", "samsung electronics", "ì‚¼ì„±ì „ìž", "ì‚¼ì„±"]
ROBOTICS_EXECUTION_TERMS = [
    "deployment", "adoption", "procurement", "purchase order", "supply contract", "order",
    "capex", "production line", "factory automation", "commercial", "ì–‘ì‚°", "ë„ìž…", "ë°œì£¼",
    "ê³µê¸‰ê³„ì•½", "ìˆ˜ì£¼", "ìƒì‚°ë¼ì¸", "ìžë™í™”", "ë§¤ì¶œ",
]
ROBOTICS_ORG_TERMS = [
    "future robotics", "reorganization", "restructuring", "robot organization", "task force",
    "ë¯¸ëž˜ë¡œë´‡ì¶”ì§„ë‹¨", "ì¡°ì§ê°œíŽ¸", "ì¡°ì§ ì •ë¹„", "ìž¬ì •ë¹„",
]
ROBOTICS_TEST_TERMS = ["rb5-850", "pilot", "test", "testing", "trial", "í…ŒìŠ¤íŠ¸", "ì‹œë²”", "ì‹¤ì¦"]


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
    "edaily.co.kr": "ì´ë°ì¼ë¦¬",
    "mk.co.kr": "ë§¤ì¼ê²½ì œ",
    "mt.co.kr": "ë¨¸ë‹ˆíˆ¬ë°ì´",
    "biz.heraldcorp.com": "í—¤ëŸ´ë“œê²½ì œ",
    "yna.co.kr": "ì—°í•©ë‰´ìŠ¤",
    "yonhapnewstv.co.kr": "ì—°í•©ë‰´ìŠ¤TV",
    "hankyung.com": "í•œêµ­ê²½ì œ",
    "sedaily.com": "ì„œìš¸ê²½ì œ",
    "etoday.co.kr": "ì´íˆ¬ë°ì´",
    "etnews.com": "ì „ìžì‹ ë¬¸",
    "fnnews.com": "íŒŒì´ë‚¸ì…œë‰´ìŠ¤",
    "asiae.co.kr": "ì•„ì‹œì•„ê²½ì œ",
    "news1.kr": "ë‰´ìŠ¤1",
    "dt.co.kr": "ë””ì§€í„¸íƒ€ìž„ìŠ¤",
}
KOREAN_BUSINESS_SEARCH_SOURCES = [
    (
        "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ AIÂ·ë°˜ë„ì²´ í˜‘ë ¥",
        (
            "(ì—”ë¹„ë””ì•„ OR ì‚¼ì„±ì „ìž OR SKí•˜ì´ë‹‰ìŠ¤ OR í˜„ëŒ€ì°¨ OR ë¸Œë¡œë“œì»´ OR ì•¤íŠ¸ë¡œí”½) "
            "(AI OR ë°˜ë„ì²´ OR HBM OR ë¡œë´‡) "
            "(í˜‘ë ¥ OR íšŒë™ OR ê³„ì•½ OR ê³µê¸‰ OR íˆ¬ìž OR ì¦ì„¤ OR ìˆ˜ì£¼) "
            "(site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:biz.heraldcorp.com OR site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ ë¯¸êµ­ ì¦ì‹œÂ·ë°˜ë„ì²´",
        (
            "(ë‚˜ìŠ¤ë‹¥ OR í•„ë¼ë¸í”¼ì•„ë°˜ë„ì²´ OR í•„ë¼ë¸í”¼ì•„ ë°˜ë„ì²´ OR SMH OR FOMC OR ì—°ì¤€ OR ìœ ê°€) "
            "(ê¸‰ë½ OR ê¸‰ë“± OR í•˜ë½ OR ìƒìŠ¹ OR ê¸ˆë¦¬ OR ì‹¤ì ) "
            "(site:edaily.co.kr OR site:mt.co.kr OR site:mk.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ ìžë³¸ì‹œìž¥ ì •ì±…",
        (
            "(ê¸ˆìœµìœ„ì›íšŒ OR ê¸ˆìœµê°ë…ì› OR í•œêµ­ê±°ëž˜ì†Œ OR ETF OR ETN OR ë ˆë²„ë¦¬ì§€ OR ê¸°ë³¸ì˜ˆíƒê¸ˆ) "
            "(ì‹œí–‰ OR ê·œì œ OR ìƒí–¥ OR ì œí•œ OR íŽ¸ìž… OR ê³µë§¤ë„) "
            "(site:mk.co.kr OR site:edaily.co.kr OR site:mt.co.kr OR "
            "site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ ì‚°ì—…ìˆ˜ìš”Â·CAPEX",
        (
            "(ë°ì´í„°ì„¼í„° OR ë°˜ë„ì²´ê³µìž¥ OR ë°˜ë„ì²´ ê³µìž¥ OR ì² ê°• OR ì „ë ¥ë§ OR ë³€ì••ê¸° OR ì›ì „ OR ë°©ì‚°) "
            "(ìˆ˜ìš” OR íˆ¬ìž OR ì¦ì„¤ OR ìˆ˜ì£¼ OR ê³„ì•½ OR ì‹¤ì  OR ë°œì£¼) "
            "(site:biz.heraldcorp.com OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:mt.co.kr OR site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "ì´ë°ì¼ë¦¬ ê¸°ì—…Â·AI",
        (
            "site:edaily.co.kr (ì—”ë¹„ë””ì•„ OR ì‚¼ì„±ì „ìž OR SKí•˜ì´ë‹‰ìŠ¤ OR í˜„ëŒ€ì°¨ OR AI OR ë°˜ë„ì²´) "
            "(í˜‘ë ¥ OR íšŒë™ OR ê³„ì•½ OR ê³µê¸‰ OR íˆ¬ìž OR ì¦ì„¤ OR ìˆ˜ì£¼)"
        ),
    ),
    (
        "ì´ë°ì¼ë¦¬ ë¯¸êµ­ ì¦ì‹œ",
        (
            "site:edaily.co.kr (ë‚˜ìŠ¤ë‹¥ OR í•„ë¼ë¸í”¼ì•„ë°˜ë„ì²´ OR í•„ë¼ë¸í”¼ì•„ ë°˜ë„ì²´ OR "
            "SMH OR FOMC OR ì—°ì¤€ OR ìœ ê°€) (ê¸‰ë½ OR ê¸‰ë“± OR í•˜ë½ OR ìƒìŠ¹)"
        ),
    ),
    (
        "ë§¤ì¼ê²½ì œ ìžë³¸ì‹œìž¥",
        (
            "site:mk.co.kr (ê¸ˆìœµìœ„ì›íšŒ OR ê¸ˆìœµê°ë…ì› OR í•œêµ­ê±°ëž˜ì†Œ OR ETF OR ETN OR "
            "ë ˆë²„ë¦¬ì§€ OR ê¸°ë³¸ì˜ˆíƒê¸ˆ OR ì™¸êµ­ì¸) (ì‹œí–‰ OR ê·œì œ OR ìƒí–¥ OR ì œí•œ OR ìˆœë§¤ìˆ˜)"
        ),
    ),
    (
        "ë¨¸ë‹ˆíˆ¬ë°ì´ ê¸€ë¡œë²Œì‹œìž¥",
        (
            "site:mt.co.kr (ë‰´ìš•ë§ˆê° OR ë‚˜ìŠ¤ë‹¥ OR í•„ë¼ë¸í”¼ì•„ë°˜ë„ì²´ OR í•„ë¼ë¸í”¼ì•„ ë°˜ë„ì²´ OR "
            "FOMC OR ì—°ì¤€ OR ìœ ê°€ OR ì—”ë¹„ë””ì•„ OR ë§ˆì´í¬ë¡ )"
        ),
    ),
    (
        "í—¤ëŸ´ë“œê²½ì œ ì‚°ì—…ìˆ˜ìš”",
        (
            "site:biz.heraldcorp.com (ë°ì´í„°ì„¼í„° OR ë°˜ë„ì²´ê³µìž¥ OR ë°˜ë„ì²´ ê³µìž¥ OR ì² ê°• OR "
            "ì „ë ¥ë§ OR ë³€ì••ê¸° OR ì›ì „ OR ë°©ì‚° OR AI) "
            "(ìˆ˜ìš” OR íˆ¬ìž OR ì¦ì„¤ OR ìˆ˜ì£¼ OR ê³„ì•½ OR ì‹¤ì )"
        ),
    ),
    (
        "í˜„ëŒ€ì°¨Â·ì—”ë¹„ë””ì•„ AI í˜‘ë ¥",
        (
            "site:edaily.co.kr (ì •ì˜ì„  OR í˜„ëŒ€ì°¨) ì—”ë¹„ë””ì•„ "
            "(íšŒë™ OR í˜‘ë ¥ OR ë¡œë´‡ OR ìžìœ¨ì£¼í–‰ OR ì œì¡°AI)"
        ),
    ),
    (
        "AI ì¸í”„ë¼ ì² ê°• ìˆ˜ìš”",
        (
            "site:biz.heraldcorp.com (ë°ì´í„°ì„¼í„° OR ë°˜ë„ì²´ê³µìž¥ OR ë°˜ë„ì²´ ê³µìž¥) "
            "(ì² ê°• OR í˜•ê°• OR í›„íŒ) ìˆ˜ìš”"
        ),
    ),
    (
        "êµ­ë‚´ AI ê³„ì•½Â·ìµœê³ ê²½ì˜ìž íšŒë™",
        (
            "(ì´ìž¬ìš© OR ì •ì˜ì„  OR SKí•˜ì´ë‹‰ìŠ¤ OR SKí…”ë ˆì½¤ OR ë„¤ì´ë²„) "
            "(ìƒ˜ì˜¬íŠ¸ë¨¼ OR ìƒ˜ ì˜¬íŠ¸ë¨¼ OR ì˜¤í”ˆAI OR ì—”ë¹„ë””ì•„ OR ì  ìŠ¨í™© OR ì  ìŠ¨ í™© "
            "OR ë§ˆì´í¬ë¡œì†Œí”„íŠ¸ OR ì•¤íŠ¸ë¡œí”½) "
            "(HBM OR íŒŒìš´ë“œë¦¬ OR ë©”ëª¨ë¦¬ OR AIíŒ©í† ë¦¬ OR AI íŒ©í† ë¦¬ OR ë°ì´í„°ì„¼í„° OR ë¡œë´‡) "
            "(ê³„ì•½ OR ê³µê¸‰ OR íšŒë™ OR í˜‘ì˜ OR ë„ìž… OR êµ¬ì¶•) "
            "(site:yna.co.kr OR site:mk.co.kr OR site:hankyung.com OR "
            "site:edaily.co.kr OR site:dt.co.kr OR site:fnnews.com)"
        ),
    ),
    (
        "ê¸€ë¡œë²Œ VCÂ·KìŠ¤íƒ€íŠ¸ì—… ìžë³¸",
        (
            "(a16z OR ë²¤ì²˜ìºí”¼í„¸ OR ì‹¤ë¦¬ì½˜ë°¸ë¦¬ OR VC) "
            "(KìŠ¤íƒ€íŠ¸ì—… OR í•œêµ­ìŠ¤íƒ€íŠ¸ì—… OR í•œêµ­ ìŠ¤íƒ€íŠ¸ì—… OR í•œêµ­íˆ¬ìž) "
            "(íˆ¬ìž OR íŽ€ë“œ OR ìš´ìš©ìžì‚° OR í˜‘ë ¥) "
            "(site:hankyung.com OR site:mk.co.kr OR site:fnnews.com OR site:asiae.co.kr)"
        ),
    ),
    (
        "ì¤‘ë™Â·ìœ ê°€Â·ë¬¼ê°€Â·í™˜ìœ¨",
        (
            "(ì´ëž€ OR í˜¸ë¥´ë¬´ì¦ˆ OR í›„í‹° OR ì‚¬ìš°ë”” OR ì¤‘ë™) "
            "(ê³µìŠµ OR íœ´ì „ OR ì¶©ëŒ OR ìœ ê°€ OR ìš´ìž„ OR ë¬¼ê°€ OR í™˜ìœ¨ OR ê¸ˆë¦¬) "
            "(site:yna.co.kr OR site:yonhapnewstv.co.kr OR site:news1.kr OR "
            "site:mt.co.kr OR site:edaily.co.kr OR site:dt.co.kr)"
        ),
    ),
    (
        "ë¹…í…Œí¬ AI CAPEXÂ·ê°ì›",
        (
            "(ë¹…í…Œí¬ OR ê¸°ìˆ ê¸°ì—… OR ë§ˆì´í¬ë¡œì†Œí”„íŠ¸ OR êµ¬ê¸€ OR ì•„ë§ˆì¡´ OR ë©”íƒ€) "
            "(AIíˆ¬ìž OR AI íˆ¬ìž OR CAPEX OR ë°ì´í„°ì„¼í„°) "
            "(ê°ì› OR ì¼ìžë¦¬ OR ì¸ë ¥ê°ì¶• OR íˆ¬ìž) "
            "(site:etoday.co.kr OR site:mk.co.kr OR site:mt.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "ì¤‘êµ­ ë©”ëª¨ë¦¬Â·IPOÂ·ETF",
        (
            "(CXMT OR ì°½ì‹ ë©”ëª¨ë¦¬ OR SMIC OR ì¤‘êµ­ë°˜ë„ì²´ OR ì¤‘êµ­ ë°˜ë„ì²´) "
            "(ìƒìž¥ OR IPO OR ETF OR ì¦ì„¤ OR ë©”ëª¨ë¦¬ê°€ê²© OR ë©”ëª¨ë¦¬ ê°€ê²©) "
            "(site:asiae.co.kr OR site:hankyung.com OR site:mk.co.kr OR site:mt.co.kr)"
        ),
    ),
    (
        "êµ­ë‚´ ETF ì‹¤ìˆ˜ìš”Â·ë ˆë²„ë¦¬ì§€ ê·œì œ",
        (
            "(ETF OR ETN) (ê°œì¸ OR ì™¸êµ­ì¸ OR ê¸°ê´€ OR ë‹¨ì¼ì¢…ëª©) "
            "(ìˆœë§¤ìˆ˜ OR ìˆœë§¤ë„ OR ê¸°ë³¸ì˜ˆíƒê¸ˆ OR ë ˆë²„ë¦¬ì§€ OR ì‹œí–‰) "
            "(site:etoday.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:edaily.co.kr OR site:asiae.co.kr)"
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
        (
            "ì´íˆ¬ë°ì´ ì „ì²´ë‰´ìŠ¤",
            "https://rss.etoday.co.kr/eto/etoday_news_all.xml",
            "trusted",
        ),
        (
            "ì´íˆ¬ë°ì´ ë§ˆì¼“",
            "https://rss.etoday.co.kr/eto/market_news.xml",
            "trusted",
        ),
        (
            "ì´íˆ¬ë°ì´ ì‚°ì—…",
            "https://rss.etoday.co.kr/eto/industry_news.xml",
            "trusted",
        ),
        (
            "ì „ìžì‹ ë¬¸ ì˜¤ëŠ˜ì˜ ë‰´ìŠ¤",
            "https://rss.etnews.com/Section901.xml",
            "trusted",
        ),
        (
            "ì „ìžì‹ ë¬¸ ì†ë³´",
            "https://rss.etnews.com/Section902.xml",
            "trusted",
        ),
        (
            "ì „ìžì‹ ë¬¸ ì „ìžì‚°ì—…",
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
        "ì´íˆ¬ë°ì´",
        "etoday",
        "ì „ìžì‹ ë¬¸",
        "etnews",
        "ì´ë°ì¼ë¦¬",
        "edaily",
        "ë§¤ì¼ê²½ì œ",
        "mk.co.kr",
        "ë¨¸ë‹ˆíˆ¬ë°ì´",
        "mt.co.kr",
        "í—¤ëŸ´ë“œê²½ì œ",
        "heraldcorp",
        "ì—°í•©ë‰´ìŠ¤",
        "yna.co.kr",
        "í•œêµ­ê²½ì œ",
        "hankyung",
        "ì„œìš¸ê²½ì œ",
        "sedaily",
        "ì—°í•©ë‰´ìŠ¤TV",
        "yonhapnewstv",
        "íŒŒì´ë‚¸ì…œë‰´ìŠ¤",
        "fnnews",
        "ì•„ì‹œì•„ê²½ì œ",
        "asiae",
        "ë‰´ìŠ¤1",
        "news1",
        "ë””ì§€í„¸íƒ€ìž„ìŠ¤",
        "dt.co.kr",
    ],
)
append_unique(
    base.TERMS,
    [
        "ì™¸êµ­ì¸",
        "ìˆœë§¤ìˆ˜",
        "ìˆœë§¤ë„",
        "ì‚¼ì„±ì „ìž",
        "skí•˜ì´ë‹‰ìŠ¤",
        "í•˜ì´ë‹‰ìŠ¤",
        "hbm",
        "cxl",
        "í…ŒìŠ¤í„°",
        "ì–‘ì‚°í‰ê°€",
        "ìƒìš©í™”",
        "ê³µê¸‰ê³„ì•½",
        "ìž¥ê¸° ê³µê¸‰",
        "ìž¥ê¸°ê³µê¸‰",
        "ìˆ˜ì£¼",
        "ê°ì›",
        "ê¸°ë³¸ì˜ˆíƒê¸ˆ",
        "ai íŒ©í† ë¦¬",
        "a16z",
        "cxmt",
        "ìƒ˜ ì˜¬íŠ¸ë¨¼",
    ],
)
for sector_index, (sector_label, sector_terms) in enumerate(base.SECTORS):
    if sector_label == "ë°˜ë„ì²´/AI":
        merged_terms = list(sector_terms)
        append_unique(
            merged_terms,
            [
                "ì‚¼ì„±ì „ìž",
                "skí•˜ì´ë‹‰ìŠ¤",
                "í•˜ì´ë‹‰ìŠ¤",
                "hbm",
                "cxl",
                "í…ŒìŠ¤í„°",
                "ì–‘ì‚°í‰ê°€",
                "ì—‘ì‹œì½˜",
            ],
        )
        base.SECTORS[sector_index] = (sector_label, merged_terms)
        break


def enforce_semiconductor_cycle_contract() -> None:
    append_unique(base.QUERIES, [
        ("ë°˜ë„ì²´ ê°€ê²© ì‚¬ì´í´", "semiconductor selloff memory price DRAM NAND customer inventory capex valuation guidance Micron Samsung SK HyniëžyæÚ$z{-®éÜj×¢F–7B’Óâ7G# ¢&WGW&â¶÷&Vå÷F—FÆR†ÆW'B  ¦FVb6ö×ÆWFU÷&÷6U÷FW‡B‡fÇVS¢ö&¦V7BÂ¢ÂfÆÆ&6³¢ö&¦V7BÒ""ÂÆ–Ö—C¢–çB’Óâ7G# ¢FW‡BÒ6ÆVåö'F–6ÆU÷7VÖÖ'•÷FW‡B‡fÇVR’÷"6ÆVåö'F–6ÆU÷7VÖÖ'•÷FW‡B†fÆÆ&6²’÷".Ù™^ÉÛ‚»hŽ« ¢FW‡BÒFW‡Bç'7G&—‚.(
b"’ç'7G&—‚¢–bÆVâ‡FW‡B’ÃÒÆ–Ö—C ¢&WGW&âFW‡@¢†VBÒFW‡E³¢Æ–Ö—B²Ð¢6VçFVæ6UöVæG2Ò°¢ÖF6‚æVæB‚¢f÷"ÖF6‚–â&Ræf–æF—FW"‡""ƒó¥²âõ×Î¸ºB’ƒóÕÇ7ÂB’"Â†VB¢–bÖF6‚æVæB‚’ãÒ–çB†Æ–Ö—B¢ãSR¢Ð¢–b6VçFVæ6UöVæG3 ¢&WGW&â†VE³¢6VçFVæ6UöVæG5²ÓÕÒç'7G&—‚¢&÷VæF'’ÒÖ‚€¢†VBç&f–æB‚"Â"Â–çB†Æ–Ö—B¢ãSR’ÂÆ–Ö—B’À¢†VBç&f–æB‚,+r"Â–çB†Æ–Ö—B¢ãSR’ÂÆ–Ö—B’À¢†VBç&f–æB‚#²"Â–çB†Æ–Ö—B¢ãSR’ÂÆ–Ö—B’À¢†VBç&f–æB‚""Â–çB†Æ–Ö—B¢ãr’ÂÆ–Ö—B’À¢¢–b&÷VæF'’Â–çB†Æ–Ö—B¢ãSR“ ¢&÷VæF'’ÒÆ–Ö—BÒ@¢&WGW&â†VE³¦&÷VæF'•Òç'7G&—‚"Ì+s³¢"’².Éè^¸¸Ž¸ºBâ   ¦FVb6ö×7EövÖV¦ö÷&÷6UöÆ–æW2†&öG“¢7G"’ÓâGWÆU·7G"Â–çEÓ ¢Æ–Ö—G2Ò°¢"ÒÙ[^ÈºÃ¢#¢tÔT¤ôô4õ$UôÔ…ô4„%2À¢Ð¢÷WGWC¢Æ—7E·7G%ÒÒµÐ¢6†ævVBÒ ¢f÷"&uöÆ–æR–â7G"†&öG’÷"""’ç7Æ—FÆ–æW2‚“ ¢7G&—VBÒ&uöÆ–æRç7G&—‚¢–æFVçBÒ&uöÆ–æU³¢ÆVâ‡&uöÆ–æR’ÒÆVâ‡&uöÆ–æRæÇ7G&—‚’•Ð¢6ö×7FVEöÆ–æRÒ&uöÆ–æP¢f÷"&Vf—‚ÂÆ–Ö—B–âÆ–Ö—G2æ—FV×2‚“ ¢–bæ÷B7G&—VBç7F'G7v—F‚‡&Vf—‚“ ¢6öçF–çVP¢fÇVRÒ7G&—VBç&VÖ÷fW&Vf—‚‡&Vf—‚’ç7G&—‚¢6ö×7FVBÒ6ö×ÆWFU÷&÷6U÷FW‡B‡fÇVRÂÆ–Ö—CÖÆ–Ö—B¢6ö×7FVEöÆ–æRÒb'¶–æFVçG×·&Vf—‡Ò¶6ö×7FVGÒ ¢6†ævVB³Ò6ö×7FVBÒfÇVP¢'&V°¢÷WGWBæVæB†6ö×7FVEöÆ–æR¢7Vff—‚Ò%Æâ"–b7G"†&öG’÷"""’æVæG7v—F‚‚%Æâ"’VÇ6R" ¢&WGW&â%Æâ"æ¦ö–â†÷WGWB’²7Vff—‚Â6†ævV@  ¦FVb6ö×7EöÆW'B†ÆW'C¢F–7BÂ–Gƒ¢–çBÂæ÷rÂg&VC¢F–7BÂFS¢F–7B’Óâ7G# ¢ÆW'BÒæ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGWB†ÆW'B¢W†×ÆW2ÒÆW'BævWB‚&W†×ÆW2"’÷"µÐ¢6÷VçE÷7Vff—‚Òb"‡¶ÆW'E²v6ÇW7FW%ö6÷VçBu×Þ«BºËnÉØÂ’"–bÆW'BævWB‚&6ÇW7FW%ö6÷VçB"’VÇ6R" ¢7FGW2ÒÆW'BævWB‚'7FGW2"’÷"‚.«;^È¹ÒÙ™^ÉÛ‚ÊB"–bW†×ÆW2VÇ6R.Ù™^ÉÛ‚»hŽ«"¢–×7G2ÒÆW'BævWB‚&–×7G2"’÷"².ÉÙŽÈ*Î«+Ê	RÉˆÙjRÊ	ÎÙYÎÊ%Ð¢F—7Æ–VEö–×7G2ÒF—7Æ•ö–×7G2†–×7G2¢–çFW'&WFF–öâÒÆW'BævWB‚&–çFW'&WFF–öâ"’÷".¸ø‚»(N¸©B¸ª^º
RÂÙZÉÛŽÉÊ‚ÂÈ‰Ž«ˆ’ÂÈ¹Î«NÙÂÊIÙYŽ¸)Žº[Â»	N«øÈ‰‚ÉèŽ¸©NÊxÙ™^ÉÛŽÙ[NÉ[ÂÙZž¸¸Ž¸ºBâ ¢F—FÆRÒF—7Æ•öæWw2†ÆW'B¢f—'7Eö–×7BÒF—7Æ–VEö–×7G5³Ò–bF—7Æ–VEö–×7G2VÇ6R.ÉÙŽÈ*Î«+Ê	R ¢'F–6ÆUö6÷&RÒ€¢ÆW'BævWB‚'FVÆVw&Õö6÷&Uöf7B"¢–bÆW'BævWB‚&¶÷&Våö'W6–æW75öæWw2"¢VÇ6R" ¢¢–bÆW'BævWB‚&ÖVÖ÷'•öçF—G'W7EöÆw7V—B"“ ¢6÷&RÒ%ÇV3&5ÇV33ÇV3ƒEÇV3s“ÇS#u4µÇVCSS…ÇV3ssEÇV#&3•ÇV3&EÇS#tÖ–7&öåÇV3VCE$ÒÇV3ÇV6•ÇV#&cEÇVCSc’ÇV3–CÇV#&S…ÇV3†5ÇV3ÇV3ssBÇV3ƒ5ÇVS3ÇV#CÇV3&#UÇV#&3…ÇV#&SBâ ¢VÇ6S ¢6÷&RÒ6ö×ÆWFU÷&÷6U÷FW‡B€¢'F–6ÆUö6÷&R÷"ÆW'BævWB‚'öÆ–7•÷Æ–å÷7VÖÖ'’"’À¢fÆÆ&6³×F—FÆRÀ¢Æ–Ö—CÔtÔT¤ôô4õ$UôÔ…ô4„%2À¢¢6öçfW'6–öâÒÆW'BævWB‚&g…ö6öçfW'6–öâ"’÷"²&Ö÷VçG2#¢µ×Ð¢6÷&RÒ6ö×7Eö6öçfW'FVEö6÷&R†6÷&RÂ6öçfW'6–öâÂÆ–Ö—CÔtÔT¤ôô4õ$UôÔ…ô4„%2 ¢Æ–æW2Ò¶b'¶–G‡Ò’··6fR†ÆW'BævWB‚v–×÷'Fæ6Rr’—ÒÂ·6fR‡7FGW2—ÕÒ·6fR‡F—FÆR—×¶‡FÖÂæW66R†6÷VçE÷7Vff—‚ÂV÷FSÔfÇ6R—Ò%Ð¢–bW†×ÆW3 ¢6÷W&6U÷FW‡BÒ6÷W&6U÷7VÖÖ'’†W†×ÆW5³£EÒ¢VÇ6S ¢6÷W&6U÷FW‡BÒ‡FÖÅöÆ–æ²€¢.É¹ºË‚¸›NÈªN»;N«‹"À¢ÆW'BævWB‚&Æ–æ²"’÷"""À¢¢g…÷6÷W&6RÒg…÷&÷fVææ6U÷FW‡B†6öçfW'6–öâ¢–bg…÷6÷W&6S ¢6÷W&6U÷FW‡BÒb'·6÷W&6U÷FW‡GÒ+rÙ™ŽÉÊƒ¢¶g…÷6÷W&6WÒ  ¢Æ–æW2³Ò°¢b"ÒÙ[^ÈºÃ¢·6fR†6÷&R—Ò"À¢b"ÒËiÎË)ƒ¢·6÷W&6U÷FW‡GÒ"À¢""À¢Ð¢&WGW&â%Æâ"æ¦ö–â†Æ–æW2 Ð Ð¦FVb6ö×7E÷&W÷'B†ÆW'G3¢Æ—7E¶F–7EÒÂg&VC¢F–7BÂFS¢F–7BÂæ÷r’Óâ7G# ¢Æ–Ö—BÒÖ‚ƒÂÖ–âƒrÂ–çB†÷2ævWFVçb‚%$D%ôD•5Ä•ôÄ”Ô•B"Â#r"’’’¢f—6–&ÆRÒÆW'G5³¦Æ–Ö—EÐ¢g…÷6æ6†÷BÒ6öÆÆV7Eög…÷6æ6†÷B‡f—6–&ÆRÂæ÷r¢f÷"ÆW'B–âf—6–&ÆS ¢ÆW'E²&g…ö6öçfW'6–öâ%ÒÒ'V–ÆEöÆW'Eög…ö6öçfW'6–öâ†ÆW'BÂg…÷6æ6†÷BÂæ÷r¢Æ—fUöÖöFRÒ÷2ævWFVçb‚%$D%õ%TåôÔôDR"Â""’ç7G&—‚’æÆ÷vW"‚’ÓÒ&Æ—fR ¢–bÆ—fUöÖöFS ¢F—FÆRÒb/	ù;ÈºNÈ¹Î«BÙ[^ÈºÂ¸›NÈªBºŽÉÛN¸ÙB+r¶æ÷s¢Už¸XBVÞÉ¹BVNÉÛÇÒ+r¶æ÷s¢Tƒ¢T×Ò ¢V×G•öÆ–æRÒ.ÈºNÈ¹Î«B«:Ëjž«*’¸›NÈªBÊxÊ	Ù™^ÉÛ‚ÉxnÉØÂ ¢VÇ6S ¢F—FÆRÒb/	ù;tÔT¤ôÉê^ÊBÙ[^ÈºÂ¸›NÈªBºŽÉÛN¸ÙB+r¶æ÷s¢Už¸XBVÞÉ¹BVNÉÛÇÒ+rc£3 ¢6öÖÖVçE÷F—FÆRÒ/	ù*c£3Éê^ÊB¸›NÈªBËÙNº™ŽØ«‚ Ð¢föÆÆ÷wWöÆ–æRÒ#c£SØŠÎÉé«‹È8¸øNÉyÈIÂÈ‰ŽË™Œ+~È‰Ž«ˆœ+~ØXÎºxŽÉ˜ÉêÎÙ™^ÉÛ‚ÙXNÉ©Bâ Ð¢V×G•öÆ–æRÒ.Éê^ÊB«:Ëjž«*’¸›NÈªBÊxÊ	Ù™^ÉÛ‚ÉxnÉØÂ Ð¢Æ–æW2Ò·F—FÆRÂb.ÈJ»8C¢Ù[^ÈºÂ¶ÆVâ‡f—6–&ÆR—Þ«B"Â"%Ð¢–bf—6–&ÆS Ð¢f÷"–G‚ÂÆW'B–âVçVÖW&FR‡f—6–&ÆRÂ“ Ð¢Æ–æW2æVæB†6ö×7EöÆW'B†ÆW'BÂ–G‚Âæ÷rÂg&VBÂFR’Ð¢6†ævVBÒ,+r"æ¦ö–â†F—7Æ•ö–×7G2‡f—6–&ÆU³ÒævWB‚&–×7G2"’’Ð¢VÇ6S Ð¢Æ–æW2³Ò¶V×G•öÆ–æRÂ"%ÐÐ¢6†ævVBÒ.º¨^Ù™^ÙYÂ»8Ù™BÉxnÉØÂ Ð¢–bæ÷BÆ—fUöÖöFS ¢Æ–æW2³Ò°¢6öÖÖVçE÷F—FÆRÀ¢b.ÉŠN¸©‚Ù[^ÈºÂ»8Ù™N¸©B·6fR†6†ævVB—ÖÉè^¸¸Ž¸ºBâ"À¢b.ÙZÉÛŽÉÊƒ¢·6fR‡FVÆVw&Òæ6ö×7E÷&VÅ÷––VÆB†g&VBÂFR’—Ò"À¢föÆÆ÷wWöÆ–æRÀ¢Ð¢&W÷'BÒ%Æâ"æ¦ö–â†Æ–æW2’ç7G&—‚’²%Æâ ¢&WGW&âwV&E÷&V÷Vå÷&W÷'B‡&W÷'B  ¦FVbwV&E÷&V÷Vå÷&W÷'B‡FW‡C¢7G"’Óâ7G# ¢FW‡BÂ6ö×7FVEöf–VÆG2Ò6ö×7EövÖV¦ö÷&÷6UöÆ–æW2‡FW‡B¢W'&÷'3¢Æ—7E·7G%ÒÒµÐ¢fÆ–E÷F—FÆRÒ€¢FW‡Bç7F'G7v—F‚‚/	ù;tÔT¤ôÉê^ÊBÙ[^ÈºÂ¸›NÈªBºŽÉÛN¸ÙB+r"¢÷"FW‡Bç7F'G7v—F‚‚/	ù;ÈºNÈ¹Î«BÙ[^ÈºÂ¸›NÈªBºŽÉÛN¸ÙB+r"¢¢–bæ÷BfÆ–E÷F—FÆS ¢W'&÷'2æVæB‚'F—FÆUö6öçG&7B"¢—FVÕö6÷VçBÒ7VÒƒf÷"Æ–æR–âFW‡Bç7Æ—FÆ–æW2‚’–b&RæÖF6‚‡"%åÆBµÂ•Ç2µÅ²"ÂÆ–æR’¢&WV—&VBÒ°¢"ÒÙ[^ÈºÃ¢"À¢"ÒËiÎË)ƒ¢"À¢Ð¢f÷"Ö&¶W"–â&WV—&VC Ð¢–b—FVÕö6÷VçBæBFW‡Bæ6÷VçB†Ö&¶W"’Â—FVÕö6÷VçC Ð¢W'&÷'2æVæB†b&Ö—76–æu÷¶Ö&¶W'Ò"Ð¢f÷&&–FFVåöÖ&¶W'2Ò€¢"Ò«‹ÊHþÈ¹Î«¢"À¢"Ò«+ÞºÂþÈKžØK¢"À¢"ÒØŠÎÉéØúÎÉÛŽØ«ƒ¢"À¢"ÒÉÙŽÈ*Î«+Ê	RÉˆÙjS¢"À¢"ÒÙYÎ«ZÞÉêS¢"À¢"Ò»	ŽÉˆþ»	Ž¸È¢"À¢"ÒÈºNØÊ‚ÈºÙ‹ƒ¢"À¢¢f÷"Ö&¶W"–âf÷&&–FFVåöÖ&¶W'3 ¢–b—FVÕö6÷VçBæBÖ&¶W"–âFW‡C ¢W'&÷'2æVæB†b&f÷&&–FFVåö6ö×7EöÖ&¶W#×¶Ö&¶W'Ò"¢–bFW‡Bç7F'G7v—F‚‚/	ù;ÈºNÈ¹Î«BÙ[^ÈºÂ¸›NÈªBºŽÉÛN¸ÙB+r"’æB/	ù*ÈºNÈ¹Î«B¸›NÈªBËÙNº™ŽØ«‚"–âFW‡C ¢W'&÷'2æVæB‚&f÷&&–FFVåöÆ—fUö6öÖÖVçF'’"¢f÷"Ö&¶W"–â‚.É›ŽÙ™BÙ™ŽÈ+¢"Â.(˜‚"“ ¢–bÖ&¶W"–âFW‡C ¢W'&÷'2æVæB†b&f÷&&–FFVåö7W'&Væ7•öf÷&ÖC×¶Ö&¶W'Ò"¢f÷"‡&6R–âtTäU$”5ôU…ÄäD”ôåõ…$4U3 Ð¢–b—FVÕö6÷VçBæB‡&6R–âFW‡C Ð¢W'&÷'2æVæB‚&vVæW&–5÷öÆ–7•öW‡ÆæF–öåöF—7Æ–VB"Ð¢f÷"Æ–æR–âFW‡Bç7Æ—FÆ–æW2‚“ Ð¢–bæ÷B&RæÖF6‚‡"%åÆBµÂ•Ç2µÅ²"ÂÆ–æR“ Ð¢6öçF–çVPÐ¢F—FÆRÒ&Rç7V"‡"%åÆBµÂ•Ç2µÅµµåÅÕÒµÅÕÇ2¢"Â""ÂÆ–æR’ç7G&—‚Ð¢F—FÆRÒ&Rç7V"‡"%Â…ÆB¾«BºËnÉØÅÂ’B"Â""ÂF—FÆR’ç7G&—‚Ð¢–bÖ÷7FÇ•ö66–’‡F—FÆR“ Ð¢W'&÷'2æVæB†b'&uöVævÆ—6…ö†VF–æs×·F—FÆU³£ƒ×Ò"Ð¢Æ÷rÒ&Rç7V"‡"&‡GG3ó¢òõÅ2²"Â""ÂFW‡B’æÆ÷vW"‚Ð¢f÷"Ö&¶W"–â°¢'F†—2Fö7VÖVçB—2Ç6òf–Æ&ÆR–âF†RföÆÆ÷v–ærf÷&ÖG2"À¢&æ÷&ÖÆ—¦VBGG&–'WFW2æBÖWFFF"À¢&÷&–v–æÂgVÆÂFW‡B†ÖÂ"À¢&v÷fW&æÖVçBV&Æ—6†–æröff–6RÖWFFF"À¢&FWfVÆ÷W"FööÇ2vW2"ÀÐ¢Ó Ð¢–bÖ&¶W"–âÆ÷s ¢W'&÷'2æVæB†b&fVFW&Å÷&Vv—7FW%ö&ö–ÆW'ÆFS×¶Ö&¶W'Ò"¢f÷"Ö&¶W"–â².ºËN¸º‚ÊNÉêÂ"Â.ÉêÎ»ØúÂ«ˆŽÊx"Â&’ÙYžÈ«R»òÙ™ÎÉª’«ˆŽÊx%Ó ¢–bÖ&¶W"–âÆ÷s ¢W'&÷'2æVæB†b&'F–6ÆUö&ö–ÆW'ÆFS×¶Ö&¶W'Ò"¢f÷"Æ–æR–âFW‡Bç7Æ—FÆ–æW2‚“ ¢f—6–&ÆUöÆ–æRÒ‡FÖÂçVæW66R†Æ–æR¢–bæ÷Bf—6–&ÆUöÆ–æRç7F'G7v—F‚‚"ÒÙ[^ÈºÃ¢"“ ¢6öçF–çVP¢&Vf—‚Ò"ÒÙ[^ÈºÃ¢ ¢7VÖÖ'’Òf—6–&ÆUöÆ–æRç&VÖ÷fW&Vf—‚‡&Vf—‚’ç7G&—‚¢Æ–Ö—BÒtÔT¤ôô4õ$UôÔ…ô4„%0¢–bÆVâ‡7VÖÖ'’’âÆ–Ö—C ¢W'&÷'2æVæB†b&6ö×7Eöf–VÆE÷FöõöÆöæs×·&Vf—‡×¶ÆVâ‡7VÖÖ'’—Ò"¢–b.(
b"–â7VÖÖ'’÷"&Rç6V&6‚‡"%Âç³2ÇÒ"Â7VÖÖ'’“ ¢W'&÷'2æVæB†b'G'Væ6FVEö6ö×7Eöf–VÆC×·&Vf—‡Ò"¢–b&Rç6V&6‚‡""ƒó®»;N¸ºGÎÉy«(ÇÎÉyÈIÇÎÉËÎºÇÎÉ˜Î«;ÇÎÉØÎ¸©GÎÉÛGÎ«ÎÉØGÎº[ÇÎÉÙ‡Îº›Î«:’B"Â7VÖÖ'’“ ¢W'&÷'2æVæB†b&–æ6ö×ÆWFUö'F–6ÆU÷7VÖÖ'“×·7VÖÖ'•²Ó3¥×Ò"¢f÷&V–våöÖ÷VçG2ÒW‡G&7Eöf÷&V–våöÖ÷VçG2‡7VÖÖ'’¢–bf÷&V–våöÖ÷VçG2æBæ÷B€¢&Rç6V&6‚‡"%ÂŽÉ[ÕÇ2¥µÆBÂåÒ²ƒó®ÊÎÉkWÎºxÂ“þÉ¹Â’"Â7VÖÖ'’¢÷".É¹Ù™BÙ™ŽÈ+Ù™^ÉÛ‚»hŽ«"–â7VÖÖ'¢“ ¢W'&÷'2æVæB‚&f÷&V–våö7W'&Væ7•öæ÷Eö6öçfW'FVB"¢7W'&VçE÷F—FÆRÒ" ¢f÷"Æ–æR–âFW‡Bç7Æ—FÆ–æW2‚“ ¢–b&RæÖF6‚‡"%åÆBµÂ•Ç2µÅ²"ÂÆ–æR“ ¢7W'&VçE÷F—FÆRÒ&Rç7V"‡"%åÆBµÂ•Ç2µÅµµåÅÕÒµÅÕÇ2¢"Â""Â‡FÖÂçVæW66R†Æ–æR’’ç7G&—‚¢7W'&VçE÷F—FÆRÒ&Rç7V"‡"%Â…ÆB¾«BºËnÉØÅÂ’B"Â""Â7W'&VçE÷F—FÆR’ç7G&—‚¢6öçF–çVP¢–b7W'&VçE÷F—FÆRæBÆ–æRç7F'G7v—F‚‚"ÒÙ[^ÈºÃ¢"“ ¢7VÖÖ'’Ò‡FÖÂçVæW66R†Æ–æRç&VÖ÷fW&Vf—‚‚"ÒÙ[^ÈºÃ¢"’ç7G&—‚’¢–b7VÖÖ'’ÓÒ7W'&VçE÷F—FÆR÷"'F–6ÆU÷F—FÆU÷&W7FFVÖVçB‡7VÖÖ'’Â7W'&VçE÷F—FÆR“ ¢W'&÷'2æVæB‚&†VFÆ–æU÷&WVFVEö5÷7VÖÖ'’"¢–bW'&÷'3 ¢&—6R'VçF–ÖTW'&÷"‚$tÔT¤ô&V÷Vâ&F"VÆ—G’wV&B&Æö6¶VBFVÆVw&Ò÷WGWC¢"²#²"æ¦ö–â†W'&÷'2’¢–b6ö×7FVEöf–VÆG3 ¢&–çB†b$tÔT¤ô6ö×7B&÷6R&Ww&—GFVã×¶6ö×7FVEöf–VÆG7Ò"¢&WGW&âFW‡@  ¦FVb6VæE÷FVÆVw&Ò‡FW‡C¢7G"’ÓâæöæS ¢FW‡BÒwV&E÷&V÷Vå÷&W÷'B‡FW‡B¢6†Eö–BÒ÷2ævWFVçb‚%DTÄTu$Õô4„Eô”B"Â""’ç7G&—‚Ð¢–b—5öV×G•÷&F%÷&W÷'B‡FW‡B’æBæ÷B6†÷VÆE÷6VæEöV×G•÷&F"‚“ Ð¢w&—FUöFVÆ—fW'•÷7FGW2‚'6¶—VEöV×G’"Â6†Eö–BÂÆVâ‡FW‡B’Â$æò†–v‚Ö–×7B&F"—FVÒ6VÆV7FVB"Ð¢&–çB†b%FVÆVw&Ó¢6¶—VBV×G’&F"÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—Ò"Ð¢&WGW&àÐ¢–bæ÷B&V÷Vå÷6VæE÷v–æF÷uö÷Vâ‚“ Ð¢w&—FUöFVÆ—fW'•÷7FGW2‚'6¶—VEööfe÷v–æF÷r"Â6†Eö–BÂÆVâ‡FW‡B’Â$÷WG6–FRtÔT¤ô&V÷VâFVÆVw&Ò6VæBv–æF÷r"Ð¢&–çB†b%FVÆVw&Ó¢6¶—VB÷WG6–FR&V÷Vâ6VæBv–æF÷r÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—Ò"Ð¢&WGW&àÐ¢Fö¶VâÒ÷2ævWFVçb‚%DTÄTu$Õô$õEõDô´Tâ"Â""’ç7G&—‚Ð¢–bæ÷BFö¶Vâ÷"æ÷B6†Eö–C Ð¢w&—FUöFVÆ—fW'•÷7FGW2‚&&Æö6¶VB"Â6†Eö–BÂÆVâ‡FW‡B’Â%DTÄTu$Õô$õEõDô´Tâ÷"DTÄTu$Õô4„Eô”BÖ—76–ær"Ð¢&—6R'VçF–ÖTW'&÷"‚%FVÆVw&ÒFVÆ—fW'’&Æö6¶VC¢DTÄTu$Õô$õEõDô´Tâ÷"DTÄTu$Õô4„Eô”BÖ—76–ær"Ð¢ÖW76vRÒf—E÷FVÆVw&Õö‡FÖÂ‡FW‡BÂ&6RåDTÄTu$ÕôÄ”Ô•BÐ¢&öG’ÒW&ÆÆ–"ç'6RçW&ÆVæ6öFR‡°Ð¢&6†Eö–B#¢6†Eö–BÀÐ¢'FW‡B#¢ÖW76vRÀÐ¢&F—6&ÆU÷vV%÷vU÷&Wf–Wr#¢'G'VR"ÀÐ¢''6UöÖöFR#¢$…DÔÂ"ÀÐ¢Ò’æVæ6öFR‚'WFbÓ‚"Ð¢Æ7EöW'&÷"Ò" Ð¢f÷"GFV×B–â&ævRƒÂB“ Ð¢&WÒW&ÆÆ–"ç&WVW7Bå&WVW7B†b&‡GG3¢òö’çFVÆVw&Òæ÷&rö&÷G·Fö¶VçÒ÷6VæDÖW76vR"ÂFFÖ&öG’ÂÖWF†öCÒ%õ5B"Ð¢G'“ Ð¢v—F‚W&ÆÆ–"ç&WVW7BçW&Æ÷Vâ‡&WÂF–ÖV÷WCÓ#R’2&W7 Ð¢&W7ç&VB‚Ð¢w&—FUöFVÆ—fW'•÷7FGW2‚'6VçB"Â6†Eö–BÂÆVâ‡FW‡B’Â""ÂÆVâ†ÖW76vR’ÂGFV×BÐ¢&–çB†b%FVÆVw&Ó¢6VçB6†'3×¶ÆVâ†ÖW76vR—Ò÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—ÒGFV×C×¶GFV×GÒ"Ð¢&WGW&àÐ¢W†6WBW&ÆÆ–"æW'&÷"ä…EEW'&÷"2W†3 Ð¢W'&÷%÷FW‡BÒW†2ç&VB‚’æFV6öFR‚'WFbÓ‚"Â'&WÆ6R"•³£SÐÐ¢Æ7EöW'&÷"Òb%FVÆVw&Ò…EE¶W†2æ6öFWÓ¢¶W'&÷%÷FW‡GÒ Ð¢–bGFV×BÂ2æB†W†2æ6öFRÓÒC#’÷"W†2æ6öFRãÒS“ Ð¢&WG'•ögFW"ÒW†2æ†VFW'2ævWB‚'&WG'’ÖgFW""Ð¢FVÆ’Ò–çB‡&WG'•ögFW"’–b&WG'•ögFW"æB&WG'•ögFW"æ—6F–v—B‚’VÇ6RGFV×@Ð¢F–ÖRç6ÆVW†FVÆ’Ð¢6öçF–çVPÐ¢'&V°Ð¢W†6WBW†6WF–öâ2W†3 Ð¢Æ7EöW'&÷"Òb'·G—R†W†2’åõöæÖUõ÷Ó¢¶W†7Ò Ð¢–bGFV×BÂ3 Ð¢F–ÖRç6ÆVW†GFV×BÐ¢6öçF–çVPÐ¢'&V°Ð¢w&—FUöFVÆ—fW'•÷7FGW2‚&f–ÆVB"Â6†Eö–BÂÆVâ‡FW‡B’ÂÆ7EöW'&÷"ÂÆVâ†ÖW76vR’Â2Ð¢&—6R'VçF–ÖTW'&÷"†b%FVÆVw&ÒFVÆ—fW'’f–ÆVC¢¶Æ7EöW'&÷'Ò"Ð Ð Ð¦FVb—5öV×G•÷&F%÷&W÷'B‡FW‡C¢7G"’Óâ&ööÃ Ð¢&WGW&â.ÈJ»8C¢Ù[^ÈºÂ«B"–âFW‡@Ð Ð Ð¦FVb6†÷VÆE÷6VæEöV×G•÷&F"‚’Óâ&ööÃ Ð¢&WGW&â÷2ævWFVçb‚%4TäEôTÕE•õ$D""Â""’æÆ÷vW"‚’–â²#"Â'G'VR"Â'–W2"Â'’'ÐÐ Ð Ð¦FVb'6Uö††ÖÒ‡fÇVS¢7G"ÂfÆÆ&6³¢GWÆU¶–çBÂ–çEÒ’Óâ–çC Ð¢ÖF6‚Ò&RæÖF6‚‡"%åÇ2¢…ÆG³Ã'Ò“¢…ÆG³'Ò•Ç2¢B"ÂfÇVR÷"""Ð¢–bæ÷BÖF6ƒ Ð¢&WGW&âfÆÆ&6µ³Ò¢c²fÆÆ&6µ³ÐÐ¢†÷W"ÂÖ–çWFRÒ–çB†ÖF6‚æw&÷Wƒ’’Â–çB†ÖF6‚æw&÷Wƒ"’Ð¢&WGW&âÖ‚ƒÂÖ–âƒ#2Â†÷W"’’¢c²Ö‚ƒÂÖ–âƒS’ÂÖ–çWFR’Ð Ð Ð¦FVb&V÷Vå÷6VæE÷v–æF÷uö÷Vâ‚’Óâ&ööÃ Ð¢–b÷2ævWFVçb‚%$D%õ%TåôÔôDR"Â""’ç7G&—‚’æÆ÷vW"‚’ÓÒ&Æ—fR# Ð¢&WGW&âG'VPÐ¢–b÷2ævWFVçb‚$ÄÄõuôôdeõt”äDõuõDTÄTu$Ò"Â""’æÆ÷vW"‚’–â²#"Â'G'VR"Â'–W2"Â'’'Ó Ð¢&WGW&âG'VPÐ¢æ÷rÒ&6Ræ·7Eöæ÷r‚Ð¢7W'&VçBÒæ÷ræ†÷W"¢c²æ÷ræÖ–çWFPÐ¢7F'BÒ'6Uö††ÖÒ†÷2ævWFVçb‚%$TõTåõ4TäEõt”äDõuõ5D%Eôµ5B"Â#S£3"’ÂƒRÂ3’Ð¢VæBÒ'6Uö††ÖÒ†÷2ævWFVçb‚%$TõTåõ4TäEõt”äDõuôTäEôµ5B"Â#s£3"’ÂƒrÂ3’Ð¢–b7F'BÃÒVæC Ð¢&WGW&â7F'BÃÒ7W'&VçBÃÒVæ@Ð¢&WGW&â7W'&VçBãÒ7F'B÷"7W'&VçBÃÒVæ@Ð Ð Ð¦FVbf—E÷FVÆVw&Õö‡FÖÂ‡FW‡C¢7G"ÂÆ–Ö—C¢–çB’Óâ7G# Ð¢–bÆVâ‡FW‡B’ÃÒÆ–Ö—C Ð¢&WGW&âFW‡@Ð¢7Vff—‚Ò%ÆåÆîÊNË+B»;N«:ÈIÎ¸©Bv—D‡V"7F–öç2'F–f7NÉyÈIÂÙ™^ÉÛ‚ÙXNÉ©Bâ Ð¢6æF–FFRÒFW‡E³¢Ö‚ƒÂÆ–Ö—BÒÆVâ‡7Vff—‚’•ÐÐ¢æWvÆ–æRÒ6æF–FFRç&f–æB‚%Æâ"Ð¢–bæWvÆ–æRâƒ Ð¢6æF–FFRÒ6æF–FFU³¦æWvÆ–æUÐÐ¢–b6æF–FFRæ6÷VçB‚#Æ"’â6æF–FFRæ6÷VçB‚#Âöâ"“ Ð¢6æF–FFRÒ6æF–FFU³¢6æF–FFRç&f–æB‚#Æ"•Òç'7G&—‚Ð¢&WGW&â†6æF–FFRç'7G&—‚’²7Vff—‚•³¦Æ–Ö—EÐÐ Ð Ð¦FVbw&—FUöFVÆ—fW'•÷7FGW2€Ð¢7FGW3¢7G"ÀÐ¢6†Eö–C¢7G"ÀÐ¢÷&–v–æÅö6†'3¢–çBÀÐ¢W'&÷#¢7G"Ò""ÀÐ¢6VçEö6†'3¢–çBÂæöæRÒæöæRÀÐ¢GFV×G3¢–çBÂæöæRÒæöæRÀÐ¢’ÓâæöæS Ð¢–ÆöBÒ°Ð¢'7FGW2#¢7FGW2ÀÐ¢&6†Eö–EöÖ6¶VB#¢Ö6µö6†Eö–B†6†Eö–B’ÀÐ¢&÷&–v–æÅö6†'2#¢÷&–v–æÅö6†'2ÀÐ¢'6VçEö6†'2#¢6VçEö6†'2ÀÐ¢&GFV×G2#¢GFV×G2ÀÐ¢&W'&÷"#¢W'&÷"ÀÐ¢ÐÐ¢&6RäõUBæÖ¶F—"†W†—7Eöö³ÕG'VRÐ¢†&6RäõUBò&vÖV¦ö÷&V÷VåöæWw5÷&F%öFVÆ—fW'’æ§6öâ"’çw&—FU÷FW‡B€Ð¢§6öâæGV×2‡–ÆöBÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"’²%Æâ"ÀÐ¢Væ6öF–æsÒ'WFbÓ‚"ÀÐ¢Ð Ð Ð¦FVbÖ6µö6†Eö–B‡fÇVS¢7G"’Óâ7G# Ð¢–bæ÷BfÇVS Ð¢&WGW&â" Ð¢&WGW&â"¢"¢Ö‚ƒÂÆVâ‡fÇVR’ÒB’²fÇVU²ÓC¥ÐÐ Ð Ð§FVÆVw&Òæ6ö×7E÷&W÷'BÒ6ö×7E÷&W÷'@Ð§FVÆVw&Òç6VæE÷FVÆVw&ÒÒ6VæE÷FVÆVw&ÐÐ§FVÆVw&Òæf–æÅöÆW'G5öf÷%ö÷WGWBÒVÆ—G•öF—7Æ•öÆW'G0Ð§FVÆVw&Òæ6æöæ–6ÅöÆW'Eöf÷%÷6VVâÒæ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGW@Ð Ð Ð¦–bõöæÖUõòÓÒ%õöÖ–åõò# Ð¢&—6R7—7FVÔW†—B‡FVÆVw&ÒæÖ–â‚’Ð