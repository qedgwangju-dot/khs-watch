#!/usr/bin/env python3
"""Full-field compact Telegram renderer for the preopen news radar."""

from __future__ import annotations

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
    "treasury", "tips", "xbi", "ibb", "ê¸°ìˆ ì´ì „", "ë§ˆì¼ìŠ¤í†¤", "ì„ ê¸‰ê¸ˆ", "ì„ìƒ", "ìŠ¹ì¸",
    "ë§¤ì¶œ", "ì˜ì—…ì´ìµ", "ë¹…íŒŒë§ˆ", "íŒŒì´í”„ë¼ì¸",
]
BIOTECH_DOMAIN_TERMS = [
    "biotech", "biopharma", "pharma", "fda", "pdufa", "complete response letter", "crl",
    "clinical trial", "phase 3", "priority review", "adcom", "nda", "bla", "drug launch",
    "pipeline priority", "big pharma", "xbi", "ibb", "ë°”ì´ì˜¤", "ì œì•½", "ì‹ ì•½", "ì„ìƒ",
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
    "adcom", "nda", "bla", "phase 3", "ì„ìƒ", "ìŠ¹ì¸",
]
BIOTECH_PHARMA_PRIORITY_TERMS = [
    "pipeline priority", "big pharma", "pfizer", "merck", "roche", "novartis", "lilly",
    "astrazeneca", "bristol myers", "bms", "johnson & johnson", "j&j", "sanofi", "gsk",
    "abbvie", "takeda", "ë¹…íŒŒë§ˆ", "íŒŒì´í”„ë¼ì¸",
]
BIOTECH_DISCOUNT_TERMS = [
    "rate cut", "real yield", "discount rate", "treasury", "tips", "fed", "ê¸ˆë¦¬", "ì‹¤ì§ˆê¸ˆë¦¬",
]
ROBOTICS_SECTOR = "ë¡œë´‡/ìƒì‚°ìë™í™”"
ROBOTICS_QUERY = (
    "ì‚¼ì„± ë¡œë´‡ ì‹¤í–‰ ë‹¨ê³„ ì²´í¬",
    "Samsung Future Robotics reorganization Rainbow Robotics RB5-850 collaborative robot cobot Samsung production line factory automation deployment procurement order capex Reuters Bloomberg Samsung Electronics IR DART",
)
ROBOTICS_TERMS = [
    "samsung", "samsung electronics", "future robotics", "robotics task force", "robot organization",
    "reorganization", "restructuring", "rainbow robotics", "rb5-850", "collaborative robot",
    "cobot", "production line", "factory automation", "pilot", "test", "deployment", "adoption",
    "procurement", "purchase order", "supply contract", "order", "capex", "ì‚¼ì„±ì „ì", "ë¯¸ë˜ë¡œë´‡ì¶”ì§„ë‹¨",
    "ì¡°ì§ê°œí¸", "ì¡°ì§ ì •ë¹„", "ë ˆì¸ë³´ìš°ë¡œë³´í‹±ìŠ¤", "í˜‘ë™ë¡œë´‡", "ìƒì‚°ë¼ì¸", "ìë™í™”", "í…ŒìŠ¤íŠ¸",
    "ì–‘ì‚°", "ë„ì…", "ë°œì£¼", "ê³µê¸‰ê³„ì•½", "ìˆ˜ì£¼",
]
ROBOTICS_DOMAIN_TERMS = [
    "future robotics", "robotics task force", "rainbow robotics", "rb5-850", "collaborative robot",
    "cobot", "robot organization", "factory automation", "ë¯¸ë˜ë¡œë´‡ì¶”ì§„ë‹¨", "ë ˆì¸ë³´ìš°ë¡œë³´í‹±ìŠ¤",
    "í˜‘ë™ë¡œë´‡", "ë¡œë´‡", "ìƒì‚°ë¼ì¸ ìë™í™”",
]
ROBOTICS_SAMSUNG_TERMS = ["samsung", "samsung electronics", "ì‚¼ì„±ì „ì", "ì‚¼ì„±"]
ROBOTICS_EXECUTION_TERMS = [
    "deployment", "adoption", "procurement", "purchase order", "supply contract", "order",
    "capex", "production line", "factory automation", "commercial", "ì–‘ì‚°", "ë„ì…", "ë°œì£¼",
    "ê³µê¸‰ê³„ì•½", "ìˆ˜ì£¼", "ìƒì‚°ë¼ì¸", "ìë™í™”", "ë§¤ì¶œ",
]
ROBOTICS_ORG_TERMS = [
    "future robotics", "reorganization", "restructuring", "robot organization", "task force",
    "ë¯¸ë˜ë¡œë´‡ì¶”ì§„ë‹¨", "ì¡°ì§ê°œí¸", "ì¡°ì§ ì •ë¹„", "ì¬ì •ë¹„",
]
ROBOTICS_TEST_TERMS = ["rb5-850", "pilot", "test", "testing", "trial", "í…ŒìŠ¤íŠ¸", "ì‹œë²”", "ì‹¤ì¦"]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


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
            "ì „ìì‹ ë¬¸ ì˜¤ëŠ˜ì˜ ë‰´ìŠ¤",
            "https://rss.etnews.com/Section901.xml",
            "trusted",
        ),
        (
            "ì „ìì‹ ë¬¸ ì†ë³´",
            "https://rss.etnews.com/Section902.xml",
            "trusted",
        ),
        (
            "ì „ìì‹ ë¬¸ ì „ìì‚°ì—…",
            "https://rss.etnews.com/06.xml",
            "trusted",
        ),
    ],
)
append_unique(base.TRUSTED, ["ì´íˆ¬ë°ì´", "etoday", "ì „ìì‹ ë¬¸", "etnews"])
append_unique(
    base.TERMS,
    [
        "ì™¸êµ­ì¸",
        "ìˆœë§¤ìˆ˜",
        "ìˆœë§¤ë„",
        "ì‚¼ì„±ì „ì",
        "skí•˜ì´ë‹‰ìŠ¤",
        "í•˜ì´ë‹‰ìŠ¤",
        "hbm",
        "cxl",
        "í…ŒìŠ¤í„°",
        "ì–‘ì‚°í‰ê°€",
        "ìƒìš©í™”",
        "ê³µê¸‰ê³„ì•½",
        "ìˆ˜ì£¼",
    ],
)
for sector_index, (sector_label, sector_terms) in enumerate(base.SECTORS):
    if sector_label == "ë°˜ë„ì²´/AI":
        merged_terms = list(sector_terms)
        append_unique(
            merged_terms,
            [
                "ì‚¼ì„±ì „ì",
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
        ("ë°˜ë„ì²´ ê°€ê²© ì‚¬ì´í´", "semiconductor selloff memory price DRAM NAND customer inventory capex valuation guidance Micron Samsung SK Hynix Reuters Bloomberg MarketWatch CNBC"),
        ("ë°˜ë„ì²´ ì •ì±… ë“œë¼ì´ë¸Œ", "semiconductor R&D tax credit tax deduction chip subsidy investment credit materials equipment components Korea Samsung SK Hynix ì†Œë¶€ì¥ ì„¸ì•¡ê³µì œ Reuters Bloomberg í•œêµ­ ì •ë¶€"),
        ("ë©”ê°€í”„ë¡œì íŠ¸ ì¼ì • - ë¯¸êµ­ í•­ë§Œ íŒŒì—…", "US East Coast port strike ILA USMX contract expires October port labor negotiations freight rates shipping megaproject project schedule equipment delivery Reuters Bloomberg CNBC MarketWatch"),
        ("ì¤‘êµ­ ë¶€ì–‘ ë²Œí¬ì„ ", "China stimulus iron ore coal dry bulk freight Baltic Dry Index bulk carrier rates Reuters Bloomberg CNBC MarketWatch"),
        ("ë¶ë¯¸ ì†¡ì „ë§ ì •ì±… ë³€ìˆ˜", "North America transmission grid investment approval regulatory permitting interconnection FERC DOE utility transmission line delay data center power grid Reuters Bloomberg CNBC MarketWatch"),
    ])
    append_unique(base.TERMS, [
        "customer inventory", "dram", "inventory", "memory price", "nand", "oversupply",
        "pricing", "selloff", "stock drop", "valuation",
        "chip subsidy", "component", "equipment", "investment credit", "materials", "r&d",
        "rd tax credit", "semiconductor tax credit", "subsidy", "tax credit", "tax deduction",
        "ì„¸ì•¡ê³µì œ", "ì†Œë¶€ì¥",
        "baltic dry", "baltic dry index", "bdi", "bulk carrier", "coal", "dockworker",
        "dry bulk", "east coast port", "freight rate", "gulf coast port", "ila", "iron ore",
        "port labor", "port strike", "shipping rate", "stimulus", "strike", "usmx",
        "capex schedule", "delivery schedule", "equipment delivery", "mega project",
        "megaproject", "project delay", "project schedule",
        "grid approval", "grid delay", "grid investment", "interconnection", "north america grid",
        "permitting", "public utility commission", "regulatory approval", "transmission grid",
        "transmission investment", "transmission line", "utility capex", "utility commission",
    ])
    for idx, (label, keys) in enumerate(base.SECTORS):
        if label == "ë°˜ë„ì²´/AI":
            merged = list(keys)
            append_unique(merged, ["dram", "nand", "memory", "inventory", "valuation", "tax credit", "tax deduction", "subsidy", "materials", "equipment", "component", "ì„¸ì•¡ê³µì œ", "ì†Œë¶€ì¥"])
            base.SECTORS[idx] = (label, merged)
            break
    for idx, (label, keys) in enumerate(base.SECTORS):
        if label == "ë°ì´í„°ì„¼í„°/ì „ë ¥ë§/ì „ë ¥ê¸°ê¸°":
            merged = list(keys)
            append_unique(merged, ["transmission grid", "transmission line", "interconnection", "permitting", "regulatory approval", "utility commission", "grid investment", "grid delay"])
            base.SECTORS[idx] = (label, merged)
            break
    if not any(label == "í•´ìš´/í•­ë§Œ/ë¬¼ë¥˜" for label, _ in base.SECTORS):
        base.SECTORS.append((
            "í•´ìš´/í•­ë§Œ/ë¬¼ë¥˜",
            ["port strike", "port labor", "dockworker", "ila", "usmx", "east coast port", "gulf coast port", "freight rate", "shipping rate"],
        ))
    if not any(label == "ë©”ê°€í”„ë¡œì íŠ¸ ì¼ì •/ë¬¼ë¥˜" for label, _ in base.SECTORS):
        base.SECTORS.append((
            "ë©”ê°€í”„ë¡œì íŠ¸ ì¼ì •/ë¬¼ë¥˜",
            [
                "capex schedule", "construction delay", "delivery schedule", "equipment delivery",
                "mega project", "megaproject", "port strike", "project delay", "project schedule",
            ],
        ))
    if not any(label == "ì¤‘êµ­ ê²½ê¸°ë¶€ì–‘/ë²Œí¬ì„ " for label, _ in base.SECTORS):
        base.SECTORS.append((
            "ì¤‘êµ­ ê²½ê¸°ë¶€ì–‘/ë²Œí¬ì„ ",
            ["china", "stimulus", "iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "baltic dry index", "bdi"],
        ))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.source_content_text(row)
        alert = original_classify(row, now)
        port_terms = ["port strike", "port labor", "dockworker", "ila", "usmx", "east coast port", "gulf coast port", "contract expires", "freight rate", "shipping rate"]
        china_bulk_terms = ["china", "stimulus", "iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "baltic dry index", "bdi"]
        grid_policy_terms = ["transmission grid", "transmission line", "grid investment", "grid approval", "grid delay", "regulatory approval", "permitting", "interconnection", "public utility commission", "utility commission", "utility capex", "ferc", "doe"]
        is_port_strike = any(base.has(text, term) for term in port_terms) and any(base.has(text, term) for term in ["port", "ila", "usmx", "dockworker"])
        is_china_bulk = base.has(text, "china") and base.has(text, "stimulus") and any(base.has(text, term) for term in ["iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "bdi"])
        is_grid_policy = any(base.has(text, term) for term in grid_policy_terms) and any(base.has(text, term) for term in ["approval", "regulatory", "permitting", "delay", "interconnection", "commission", "ferc", "doe"])

        if (is_port_strike or is_china_bulk or is_grid_policy) and not alert:
            age = base.age_hours(row, now)
            sectors = ["ë©”ê°€í”„ë¡œì íŠ¸ ì¼ì •/ë¬¼ë¥˜", "í•´ìš´/í•­ë§Œ/ë¬¼ë¥˜"] if is_port_strike else ["ì¤‘êµ­ ê²½ê¸°ë¶€ì–‘/ë²Œí¬ì„ "] if is_china_bulk else ["ë°ì´í„°ì„¼í„°/ì „ë ¥ë§/ì „ë ¥ê¸°ê¸°"]
            if is_china_bulk:
                sectors.append("í•´ìš´/í•­ë§Œ/ë¬¼ë¥˜")
            impacts = ["ì‹œê°„í‘œ", "ëˆ ë²„ëŠ” ëŠ¥ë ¥"] if is_port_strike else ["ëˆ ë²„ëŠ” ëŠ¥ë ¥"] if is_china_bulk else ["í• ì¸ìœ¨", "ì‹œê°„í‘œ"]
            score = 92 + (10 if age is not None and age <= 12 else 0)
            status = "í™•ì •" if row.get("layer") == "official" else "ê³µì‹ í™•ì¸ ì „"
            alert = {
                "score": score,
                "importance": "ìƒ" if score >= 100 else "ì¤‘",
                "status": status,
                "news": base.clean(row.get("title")),
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "í™•ì¸ ë¶ˆê°€",
                "impacts": impacts,
                "paths": ["ì´ìµ" if x == "ëˆ ë²„ëŠ” ëŠ¥ë ¥" else "ì •ì±… íƒ€ì„ë¼ì¸" for x in impacts],
                "sectors": sectors,
                "matched": [],
                "local_dc_policy": False,
                "reflection": "ë‚®ìŒ" if age is not None and age <= 6 else "ì¤‘ê°„",
                "counter": "ì œëª©Â·ìš”ì•½ ê¸°ë°˜ 1ì°¨ ê°ì§€ë¼ ì›ë¬¸ ì„¸ë¶€ì¡°ê±´ê³¼ ê³µì‹ ë¬¸ì„œ í™•ì¸ ì „ ê³¼ëŒ€í•´ì„ ê°€ëŠ¥",
                "interpretation": "",
                "failed_signal": "",
                "korea_basis": "ì˜ˆê³ ëœ ì´ë²¤íŠ¸ì˜ ê³µì‹í™”" if status == "í™•ì •" else "ì™¸ì‹  í™•ì‚°",
            }

        if alert and is_grid_policy:
            for impact in ["í• ì¸ìœ¨", "ì‹œê°„í‘œ"]:
                if impact not in alert["impacts"]:
                    alert["impacts"].append(impact)
            if "ì˜ì‚¬ê²°ì • ì˜í–¥ ì œí•œì " in alert["impacts"] and len(alert["impacts"]) > 1:
                alert["impacts"] = [x for x in alert["impacts"] if x != "ì˜ì‚¬ê²°ì • ì˜í–¥ ì œí•œì "]
            alert["paths"] = [
                "ì´ìµ" if x == "ëˆ ë²„ëŠ” ëŠ¥ë ¥" else "í• ì¸ìœ¨" if x == "í• ì¸ìœ¨" else "ìˆ˜ê¸‰" if x == "ìˆ˜ê¸‰" else "ì •ì±… íƒ€ì„ë¼ì¸"
                for x in alert["impacts"]
            ]
            if "ë°ì´í„°ì„¼í„°/ì „ë ¥ë§/ì „ë ¥ê¸°ê¸°" not in alert["sectors"]:
                alert["sectors"].append("ë°ì´í„°ì„¼í„°/ì „ë ¥ë§/ì „ë ¥ê¸°ê¸°")
            alert["score"] = max(int(alert.get("score", 0)), 100)
            alert["importance"] = "ìƒ" if alert["score"] >= 100 else "ì¤‘"
            alert["gridß~¸âÚ$z{-®éÜj×Bç7G&—‚•ĞĞ¢&WGW&â"Â"æ¦ö–â†F–7Bæg&öÖ¶W—2†&6U÷'G2²W‡G&’’÷".Ù™^ÉÛ‚«¸ª^ÙYÂÊxÊ	ÊxÙÂÉxnÉØÂ Ğ¢W†6WBW†6WF–öã Ğ¢÷WBÒµĞĞ¢–b.¸ÛÉÛNØKÈKÎØKşÊNº
^ºyÒşÊNº
^«‹«‹"–âÆW'BævWB‚'6V7F÷'2"ÂµÒ“ Ğ¢÷WB³Ò²%e%B"Â$UDâ"Â$tUb"Â$4Tr"Â%4Ô‚%ĞĞ¢–b.»	¸øNË+Bô’"–âÆW'BævWB‚'6V7F÷'2"ÂµÒ“ Ğ¢÷WB³Ò²$ådD"Â$ÕR"Â$dtò"Â$ÔB"Â%E4Ò"Â$4ÔÂ%ĞĞ¢–b.ÊNº
^ºyÒ»;NÉX‚ôd42Éê^»˜N«yÎÊ	Â"–âÆW'BævWB‚'6V7F÷'2"ÂµÒ“ Ğ¢÷WB³Ò²$e4Å""Â$Tå‚"Â%4TDr"Â%e%B"Â$UDâ"Â$tUb"Â$d426÷fW&VBÆ—7B%ĞĞ¢–b$URşÙYÎ«ZÒÊ	^ËRÉˆÙjR"–âÆW'BævWB‚'6V7F÷'2"ÂµÒ“ Ğ¢÷WB³Ò²$URÊyÙhÉÈBş«H»;B"Â.Ë*«	\+~»ØKºjÌ+~»	¸øNË+L+~ÊÈJÈ‰ËiÎÊ;Â"Â$UU"ôµ%r%ĞĞ¢–b$DôRÊNº
^ºyÒşÉ¹ÊBşÉy¸HÊxÊxÉ¹"–âÆW'BævWB‚'6V7F÷'2"ÂµÒ“ Ğ¢÷WB³Ò²$DôR"Â$dU$2"Â$å$2"Â$"Â%vW7F–æv†÷W6R"Â%e%B"Â$UDâ"Â$tUb"Â%W&æ—VÒ%ĞĞ¢–bÆW'BævWB‚&&–÷FV6…öÆVFW'6†—öf–ÇFW""“ Ğ¢÷WB³Ò²$dD"Â%ETd"Â%„$’"Â$”$""Â$Dd”“"Â#’D•2%ĞĞ¢–bÆW'BævWB‚'&ö&÷F–75öW†V7WF–öåöf–ÇFW""“ Ğ¢÷WB³Ò²%6×7VærVÆV7G&öæ–72"Â%&–æ&÷r&ö&÷F–72"Â%$#RÓƒS"Â.Ù‰¸ùºÎ»Hr%ĞĞ¢÷WB³ÒW‡G&Ğ¢–b.ÙZÉÛÉÊ‚"–âÆW'BævWB‚&–×7G2"ÂµÒ“ Ğ¢÷WB³Ò°Ğ¢b$Dd”“¶g&VBævWB‚wfÇVRr’–bg&VBævWB‚wfÇVRr’—2æ÷BæöæRVÇ6R~Ù™^ÉÛ‚»h«wÒ"ÀĞ¢b%DRD•2·FRævWB‚wfÇVRr’–bFRævWB‚wfÇVRr’—2æ÷BæöæRVÇ6R~Ù™^ÉÛ‚»h«wÒ"ÀĞ¢$•tÒõ5’"ÀĞ¢ĞĞ¢&WGW&â"Â"æ¦ö–â†F–7Bæg&öÖ¶W—2†÷WB’’÷".Ù™^ÉÛ‚«¸ª^ÙYÂÊxÊ	ÊxÙÂÉxnÉØÂ Ğ Ğ Ğ¦FVb6VÖ–6öæGV7F÷%ö7–6ÆUö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS Ğ¢–bæ÷BÆW'BævWB‚'6VÖ–6öæGV7F÷%÷6VÆÆöfb"“ Ğ¢&WGW&âæöæPĞ¢&WGW&â.º™NºªºjÂ««*œ+~«:«	ŞÈ*ÂÉêÎ«:+t4UŒ+~»ºYÉyÉÛNÈY‚»h¸»B¸ùÈ¹ÂÉX^Ù™BÉzÎ»h Ğ Ğ Ğ¦FVb6VÖ–6öæGV7F÷%÷öÆ–7•ö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS Ğ¢–bæ÷BÆW'BævWB‚'öÆ–7•öG&—fR"“ Ğ¢&WGW&âæöæPĞ¢&WGW&â%"dBÈKÉZ«;^Ê	Â¸ÈÈ8+~È¹ÎÙh’È¹ÎÊ	+~ÈhÎ»hÉêR»	ÎÊ;ÂşÈ‰Ê;ÂÉ{«+ÈK Ğ Ğ Ğ¦FVb÷'E÷7G&–¶Uö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS Ğ¢–bæ÷BÆW'BævWB‚'÷'E÷7G&–¶U÷&—6²"“ Ğ¢&WGW&âæöæPĞ¢&WGW&â$”ÄõU4Õ‚«8NÉ[ÒºxÎº8Ì+~Ù‰È8«+º
ÂÉzÎ»h+~¸ù»hş«ÙHBÙZŞºxÂË
ÊxŒ+~«‹ÉéÉêÂ¸*«‹ş¸ÈÙ‰R4U‚ÉÛÎÊ	R Ğ Ğ Ğ¦FVb6†–æö'VÆµö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS Ğ¢–bæ÷BÆW'BævWB‚&6†–æ÷7F–×VÇW5ö'VÆ²"“ Ğ¢&WGW&âæöæPĞ¢&WGW&â.ÊI«ZÒ»hÉiËRÈºNºËÂ«	^¸øL+~Ë*«IÈIÒşÈIŞØ8BºËÎ¸ù¹øœ+t$D’ş»(ÎØÎÈJÉ«NÉèB¸ùÙh’ Ğ Ğ Ğ¦FVbw&–E÷öÆ–7•ö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS Ğ¢–bæ÷BÆW'BævWB‚&w&–E÷öÆ–7•öFVÆ’"“ Ğ¢&WGW&âæöæPĞ¢&WGW&â.Ê	^»hÈ«ÉÛŒ+~«yÎÊ	ÂşÉÛÙx«+~«8NØk^Ê	ÈhÒÉÛÎÊ	\+~ÉÊØ»ºjÎØ»4U‚ÊyÙh’ÈhŞ¸øB Ğ Ğ Ğ¦FVb&–÷FV6…öÆVFW'6†—ö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS Ğ¢–bæ÷BÆW'BævWB‚&&–÷FV6…öÆVFW'6†—öf–ÇFW""“ Ğ¢&WGW&âæöæPĞ¢&WGW&âÆW'BævWB‚&&–÷FV6…ö6†V6²"’÷".ÈºNÊ	ÂºzNËiÂşÉÛNÉÛ\+~»˜^ØÈÎºx‚É«ÈJÈ‰ÎÉÈL+tdDÉÛÎÊ	\+~«ˆºjÂşÙZÉÛÉÊ‚¸ùÈ¹ÂÙ™^ÉÛ‚ Ğ Ğ Ğ¦FVb&ö&÷F–75öW†V7WF–öåö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS Ğ¢–bæ÷BÆW'BævWB‚'&ö&÷F–75öW†V7WF–öåöf–ÇFW""“ Ğ¢&WGW&âæöæPĞ¢&WGW&âÆW'BævWB‚'&ö&÷F–75ö6†V6²"’÷".È+ÎÈKÊÊx«	ÎØë‚»
Ùj\+u$#RÓƒSØXÎÈªNØ«Œ+~»	ÎÊ;Âô4U‚şºzNËiÂÉÛÈ¹ÒÉ{«+Ù™^ÉÛ‚ Ğ Ğ Ğ¦FVbF—7Æ•öæWw2†ÆW'C¢F–7B’Óâ7G# Ğ¢&WGW&â¶÷&Vå÷F—FÆR†ÆW'BĞ Ğ Ğ¦FVb6ö×7EöÆW'B†ÆW'C¢F–7BÂ–Gƒ¢–çBÂæ÷rÂg&VC¢F–7BÂFS¢F–7B’Óâ7G# ¢ÆW'BÒæ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGWB†ÆW'B¢W†×ÆW2ÒÆW'BævWB‚&W†×ÆW2"’÷"µĞ¢6÷VçE÷7Vff—‚Òb"‡¶ÆW'E²v6ÇW7FW%ö6÷VçBu×Ş«BºËnÉØÂ’"–bÆW'BævWB‚&6ÇW7FW%ö6÷VçB"’VÇ6R" Ğ¢7FGW2ÒÆW'BævWB‚'7FGW2"’÷"‚.«;^È¹ÒÙ™^ÉÛ‚ÊB"–bW†×ÆW2VÇ6R.Ù™^ÉÛ‚»h«"Ğ¢&6—2ÒÆW'BævWB‚&¶÷&Vö&6—2"’÷"‚.É›ÈºşÊxÉzÒ¸›NÈªBÙ™^È+"–bW†×ÆW2VÇ6R.É›ÈºÙ™^È+"Ğ¢–×7G2ÒÆW'BævWB‚&–×7G2"’÷"².ÉÙÈ*Î«+Ê	RÉˆÙjRÊ	ÎÙYÎÊ%ĞĞ¢F—7Æ–VEö–×7G2ÒF—7Æ•ö–×7G2†–×7G2Ğ¢F‡2ÒÆW'BævWB‚'F‡2"’÷"².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"–b–×7BÓÒ.È¹Î«NÙÂ"VÇ6R–×7Bf÷"–×7B–â–×7G5ĞĞ¢6V7F÷'2ÒÆW'BævWB‚'6V7F÷'2"’÷"².ÉˆÙjRÈKØKÙ™^ÉÛ‚»h«%ĞĞ¢V&Æ—6†VBÒÆW'BævWB‚'V&Æ—6†VB"’÷"‚.ÉzÎ¹úÂ«B"–bW†×ÆW2VÇ6R.Ù™^ÉÛ‚»h«"Ğ¢&–6VEö–âÒÆW'BævWB‚'&–6VEö–â"’÷"b'¶ÆW'BævWB‚w&VfÆV7F–öâr’÷"~ÊI«BwÒâÙ¸NÈhÒ«;^È¹ÒÊ«N«;ÂÈ¹ÎÉêR»	ÉÙÙ™^ÉÛ‚ÊN«˜ÎÊxÙ™^Ê	R»	ÉˆÉËÎºÂ»;N«‹ÉkNº^È«^¸¸¸ºBâ Ğ¢6÷VçFW"ÒÆW'BævWB‚&6÷VçFW""’÷".É¹ºË‚ÈK»hÊ«N«;Â«;^È¹ÒºËÈIÂÙ™^ÉÛ‚ÊB«;Î¸ÈÙ[NÈIÒ«¸ªR Ğ¢–çFW'&WFF–öâÒÆW'BævWB‚&–çFW'&WFF–öâ"’÷".¸ø‚»(N¸©B¸ª^º
RÂÙZÉÛÉÊ‚ÂÈ‰«ˆ’ÂÈ¹Î«NÙÂÊIÙY¸)º[Â»	N«øÈ‰‚Éè¸©NÊxÙ™^ÉÛÙ[NÉ[ÂÙZ¸¸¸ºBâ Ğ¢f–ÆVE÷6–væÂÒÆW'BævWB‚&f–ÆVE÷6–væÂ"’÷".«Hº
‚««*œ+~È‰«ˆœ+~«;^È¹ÒÙ¸NÈhÒÙ™^ÉÛÉÛB¸ùÙhÙYÊxÉX®ÉËÎº›B¸º»	ÎÈK¸›NÈªB Ğ Ğ¢Æ–æW2Ò¶b'¶–G‡Ò’··6fR†ÆW'BævWB‚v–×÷'Fæ6Rr’—ÒÂ·6fR‡7FGW2—ÕÒ·6fR†F—7Æ•öæWw2†ÆW'B’—×¶‡FÖÂæW66R†6÷VçE÷7Vff—‚ÂV÷FSÔfÇ6R—Ò%Ğ¢–bW†×ÆW3 ¢6÷W&6U÷FW‡BÒ6÷W&6U÷7VÖÖ'’†W†×ÆW5³£EÒ¢VÇ6S ¢6÷W&6U÷FW‡BÒ‡FÖÅöÆ–æ²€¢.É¹ºË‚¸›NÈªN»;N«‹"À¢ÆW'BævWB‚&Æ–æ²"’÷"""À¢ ¢Æ–æW2³Ò°¢b"Ò«‹ÊHşÈ¹Î«¢·6fR†&6—2—Ò+rÉ¹Ë)Â·6fR‡V&Æ—6†VB—Ò+rÊÙ¨Â¶æ÷s¢Tƒ¢TÒµ5GÒ"À¢b"ÒÙ[^ÈºÃ¢·6fR†ÆW'BævWB‚wöÆ–7•÷Æ–å÷7VÖÖ'’r’—Ò"À¢b"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢·6fR‚rÂræ¦ö–â†F—7Æ–VEö–×7G2’—Ò"À¢b"ÒØŠÎÉéØúÎÉÛØ«ƒ¢·6fR†ÆW'BævWB‚v–çfW7FÖVçE÷f–Wrr’—Ò"À¢b"ÒÙYÎ«ZŞÉêS¢·6fR†ÆW'BævWB‚v¶÷&VöÖ&¶WEö–×7Br’—Ò"À¢b"Ò«+ŞºÂşÈKØK¢·6fR‚rÂræ¦ö–â‡F‡2’—ÒÂ·6fR‚rÂræ¦ö–â‡6V7F÷'2’—Ò"À¢b"Ò»	Éˆş»	¸È¢·6fR‡&–6VEö–â—Òò·6fR†6÷VçFW"—Ò"À¢Ğ¢Æ–æW2³Ò°¢b"ÒÈºNØÊ‚ÈºÙ‹ƒ¢·6fR†f–ÆVE÷6–væÂ—Ò"À¢b"ÒËiÎË)ƒ¢·6÷W&6U÷FW‡GÒ"À¢""À¢Ğ¢&WGW&â%Æâ"æ¦ö–â†Æ–æW2 Ğ Ğ¦FVb6ö×7E÷&W÷'B†ÆW'G3¢Æ—7E¶F–7EÒÂg&VC¢F–7BÂFS¢F–7BÂæ÷r’Óâ7G# Ğ¢Æ–Ö—BÒÖ‚ƒÂÖ–âƒrÂ–çB†÷2ævWFVçb‚%$D%ôD•5Ä•ôÄ”Ô•B"Â#R"’’’Ğ¢f—6–&ÆRÒÆW'G5³¦Æ–Ö—EĞĞ¢Æ—fUöÖöFRÒ÷2ævWFVçb‚%$D%õ%TåôÔôDR"Â""’ç7G&—‚’æÆ÷vW"‚’ÓÒ&Æ—fR Ğ¢–bÆ—fUöÖöFS Ğ¢F—FÆRÒb/	ù;tÔT¤ôÈºNÈ¹Î«BÙ[^ÈºÂ¸›NÈªBºÉÛN¸ÙB+r¶æ÷s¢U¸XBVŞÉ¹BVNÉÛÇÒ+r¶æ÷s¢Tƒ¢T×Ò Ğ¢6öÖÖVçE÷F—FÆRÒ/	ù*ÈºNÈ¹Î«B¸›NÈªBËÙNº™Ø«‚ Ğ¢föÆÆ÷wWöÆ–æRÒ.¸ºNÉØÂØŠÎÉé«‹È8¸øNÉyÈIÂÈ‰Ë™Œ+~È‰«ˆœ+~ØXÎºxÉ˜ÉêÎÙ™^ÉÛ‚ÙXNÉ©Bâ Ğ¢V×G•öÆ–æRÒ.ÈºNÈ¹Î«B«:Ëj«*’¸›NÈªBÊxÊ	Ù™^ÉÛ‚ÉxnÉØÂ Ğ¢VÇ6S Ğ¢F—FÆRÒb/	ù;tÔT¤ôÉê^ÊBÙ[^ÈºÂ¸›NÈªBºÉÛN¸ÙB+r¶æ÷s¢U¸XBVŞÉ¹BVNÉÛÇÒ+rc£3 Ğ¢6öÖÖVçE÷F—FÆRÒ/	ù*c£3Éê^ÊB¸›NÈªBËÙNº™Ø«‚ Ğ¢föÆÆ÷wWöÆ–æRÒ#c£SØŠÎÉé«‹È8¸øNÉyÈIÂÈ‰Ë™Œ+~È‰«ˆœ+~ØXÎºxÉ˜ÉêÎÙ™^ÉÛ‚ÙXNÉ©Bâ Ğ¢V×G•öÆ–æRÒ.Éê^ÊB«:Ëj«*’¸›NÈªBÊxÊ	Ù™^ÉÛ‚ÉxnÉØÂ Ğ¢Æ–æW2Ò·F—FÆRÂb.ÊÙ¨Ã¢¶æ÷s¢U’ÒVÒÒVBTƒ¢TÒµ5GÒ"Âb.ÈJ»8C¢Ù[^ÈºÂ¶ÆVâ‡f—6–&ÆR—Ş«B"Â"%ĞĞ¢–bf—6–&ÆS Ğ¢f÷"–G‚ÂÆW'B–âVçVÖW&FR‡f—6–&ÆRÂ“ Ğ¢Æ–æW2æVæB†6ö×7EöÆW'B†ÆW'BÂ–G‚Âæ÷rÂg&VBÂFR’Ğ¢6†ævVBÒ,+r"æ¦ö–â†F—7Æ•ö–×7G2‡f—6–&ÆU³ÒævWB‚&–×7G2"’’Ğ¢VÇ6S Ğ¢Æ–æW2³Ò¶V×G•öÆ–æRÂ"%ĞĞ¢6†ævVBÒ.º¨^Ù™^ÙYÂ»8Ù™BÉxnÉØÂ Ğ¢Æ–æW2³Ò°Ğ¢6öÖÖVçE÷F—FÆRÀĞ¢b.ÉŠN¸©‚Ù[^ÈºÂ»8Ù™N¸©B·6fR†6†ævVB—ÖÉè^¸¸¸ºBâÙYÎ«ZŞÉê^ÉyÈIÎ¸©B«Hº
‚Ù[NÉ›‚Ø»ËºB»	ÉÙ«;Â«ZŞ¸+BÈ‰«ˆ’Ù™^È+ÉzÎ»hº[Âº‹ÎÊÙ™^ÉÛÙZ¸¸¸ºBâ"ÀĞ¢b.ÙZÉÛÉÊƒ¢·6fR‡FVÆVw&Òæ6ö×7E÷&VÅ÷––VÆB†g&VBÂFR’—Ò"ÀĞ¢föÆÆ÷wWöÆ–æRÀĞ¢""ÀĞ¢.ØŠÎÉéÊÉkÉÛBÉXN¸¸ÂË«:Éª’¸›NÈªB»ˆÎºjÎÙYÉè^¸¸¸ºBâ"ÀĞ¢ĞĞ¢&W÷'BÒ%Æâ"æ¦ö–â†Æ–æW2’ç7G&—‚’²%Æâ Ğ¢wV&E÷&V÷Vå÷&W÷'B‡&W÷'BĞ¢&WGW&â&W÷'@Ğ Ğ Ğ¦FVbwV&E÷&V÷Vå÷&W÷'B‡FW‡C¢7G"’ÓâæöæS Ğ¢W'&÷'3¢Æ—7E·7G%ÒÒµĞĞ¢fÆ–E÷F—FÆRÒ€Ğ¢FW‡Bç7F'G7v—F‚‚/	ù;tÔT¤ôÉê^ÊBÙ[^ÈºÂ¸›NÈªBºÉÛN¸ÙB+r"Ğ¢÷"FW‡Bç7F'G7v—F‚‚/	ù;tÔT¤ôÈºNÈ¹Î«BÙ[^ÈºÂ¸›NÈªBºÉÛN¸ÙB+r"Ğ¢Ğ¢–bæ÷BfÆ–E÷F—FÆS ¢W'&÷'2æVæB‚'F—FÆUö6öçG&7B"¢—FVÕö6÷VçBÒ7VÒƒf÷"Æ–æR–âFW‡Bç7Æ—FÆ–æW2‚’–b&RæÖF6‚‡"%åÆBµÂ•Ç2µÅ²"ÂÆ–æR’¢&WV—&VBÒ°¢"Ò«‹ÊHşÈ¹Î«¢"À¢"ÒÙ[^ÈºÃ¢"À¢"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢"À¢"ÒØŠÎÉéØúÎÉÛØ«ƒ¢"À¢"ÒÙYÎ«ZŞÉêS¢"À¢"Ò«+ŞºÂşÈKØK¢"À¢"Ò»	Éˆş»	¸È¢"À¢"ÒÈºNØÊ‚ÈºÙ‹ƒ¢"À¢"ÒËiÎË)ƒ¢"À¢Ğ¢f÷"Ö&¶W"–â&WV—&VC Ğ¢–b—FVÕö6÷VçBæBFW‡Bæ6÷VçB†Ö&¶W"’Â—FVÕö6÷VçC Ğ¢W'&÷'2æVæB†b&Ö—76–æu÷¶Ö&¶W'Ò"Ğ¢–b—FVÕö6÷VçBæB"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢ÉÙÈ*Î«+Ê	RÉˆÙjRÊ	ÎÙYÎÊ"–âFW‡C Ğ¢W'&÷'2æVæB‚&Æ–Ö—FVEöFV6—6–öåö–×7EöF—7Æ–VB"Ğ¢f÷"‡&6R–âtTäU$”5ôU…ÄäD”ôåõ…$4U3 Ğ¢–b—FVÕö6÷VçBæB‡&6R–âFW‡C Ğ¢W'&÷'2æVæB‚&vVæW&–5÷öÆ–7•öW‡ÆæF–öåöF—7Æ–VB"Ğ¢f÷"Æ–æR–âFW‡Bç7Æ—FÆ–æW2‚“ Ğ¢–bæ÷B&RæÖF6‚‡"%åÆBµÂ•Ç2µÅ²"ÂÆ–æR“ Ğ¢6öçF–çVPĞ¢F—FÆRÒ&Rç7V"‡"%åÆBµÂ•Ç2µÅµµåÅÕÒµÅÕÇ2¢"Â""ÂÆ–æR’ç7G&—‚Ğ¢F—FÆRÒ&Rç7V"‡"%Â…ÆB¾«BºËnÉØÅÂ’B"Â""ÂF—FÆR’ç7G&—‚Ğ¢–bÖ÷7FÇ•ö66–’‡F—FÆR“ Ğ¢W'&÷'2æVæB†b'&uöVævÆ—6…ö†VF–æs×·F—FÆU³£ƒ×Ò"Ğ¢Æ÷rÒ&Rç7V"‡"&‡GG3ó¢òõÅ2²"Â""ÂFW‡B’æÆ÷vW"‚Ğ¢f÷"Ö&¶W"–â°Ğ¢'F†—2Fö7VÖVçB—2Ç6òf–Æ&ÆR–âF†RföÆÆ÷v–ærf÷&ÖG2"ÀĞ¢&æ÷&ÖÆ—¦VBGG&–'WFW2æBÖWFFF"ÀĞ¢&÷&–v–æÂgVÆÂFW‡B†ÖÂ"ÀĞ¢&v÷fW&æÖVçBV&Æ—6†–æröff–6RÖWFFF"ÀĞ¢&FWfVÆ÷W"FööÇ2vW2"ÀĞ¢Ó Ğ¢–bÖ&¶W"–âÆ÷s Ğ¢W'&÷'2æVæB†b&fVFW&Å÷&Vv—7FW%ö&ö–ÆW'ÆFS×¶Ö&¶W'Ò"Ğ¢–bW'&÷'3 Ğ¢&—6R'VçF–ÖTW'&÷"‚$tÔT¤ô&V÷Vâ&F"VÆ—G’wV&B&Æö6¶VBFVÆVw&Ò÷WGWC¢"²#²"æ¦ö–â†W'&÷'2’Ğ Ğ Ğ¦FVb6VæE÷FVÆVw&Ò‡FW‡C¢7G"’ÓâæöæS Ğ¢wV&E÷&V÷Vå÷&W÷'B‡FW‡BĞ¢6†Eö–BÒ÷2ævWFVçb‚%DTÄTu$Õô4„Eô”B"Â""’ç7G&—‚Ğ¢–b—5öV×G•÷&F%÷&W÷'B‡FW‡B’æBæ÷B6†÷VÆE÷6VæEöV×G•÷&F"‚“ Ğ¢w&—FUöFVÆ—fW'•÷7FGW2‚'6¶—VEöV×G’"Â6†Eö–BÂÆVâ‡FW‡B’Â$æò†–v‚Ö–×7B&F"—FVÒ6VÆV7FVB"Ğ¢&–çB†b%FVÆVw&Ó¢6¶—VBV×G’&F"÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—Ò"Ğ¢&WGW&àĞ¢–bæ÷B&V÷Vå÷6VæE÷v–æF÷uö÷Vâ‚“ Ğ¢w&—FUöFVÆ—fW'•÷7FGW2‚'6¶—VEööfe÷v–æF÷r"Â6†Eö–BÂÆVâ‡FW‡B’Â$÷WG6–FRtÔT¤ô&V÷VâFVÆVw&Ò6VæBv–æF÷r"Ğ¢&–çB†b%FVÆVw&Ó¢6¶—VB÷WG6–FR&V÷Vâ6VæBv–æF÷r÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—Ò"Ğ¢&WGW&àĞ¢Fö¶VâÒ÷2ævWFVçb‚%DTÄTu$Õô$õEõDô´Tâ"Â""’ç7G&—‚Ğ¢–bæ÷BFö¶Vâ÷"æ÷B6†Eö–C Ğ¢w&—FUöFVÆ—fW'•÷7FGW2‚&&Æö6¶VB"Â6†Eö–BÂÆVâ‡FW‡B’Â%DTÄTu$Õô$õEõDô´Tâ÷"DTÄTu$Õô4„Eô”BÖ—76–ær"Ğ¢&—6R'VçF–ÖTW'&÷"‚%FVÆVw&ÒFVÆ—fW'’&Æö6¶VC¢DTÄTu$Õô$õEõDô´Tâ÷"DTÄTu$Õô4„Eô”BÖ—76–ær"Ğ¢ÖW76vRÒf—E÷FVÆVw&Õö‡FÖÂ‡FW‡BÂ&6RåDTÄTu$ÕôÄ”Ô•BĞ¢&öG’ÒW&ÆÆ–"ç'6RçW&ÆVæ6öFR‡°Ğ¢&6†Eö–B#¢6†Eö–BÀĞ¢'FW‡B#¢ÖW76vRÀĞ¢&F—6&ÆU÷vV%÷vU÷&Wf–Wr#¢'G'VR"ÀĞ¢''6UöÖöFR#¢$…DÔÂ"ÀĞ¢Ò’æVæ6öFR‚'WFbÓ‚"Ğ¢Æ7EöW'&÷"Ò" Ğ¢f÷"GFV×B–â&ævRƒÂB“ Ğ¢&WÒW&ÆÆ–"ç&WVW7Bå&WVW7B†b&‡GG3¢òö’çFVÆVw&Òæ÷&rö&÷G·Fö¶VçÒ÷6VæDÖW76vR"ÂFFÖ&öG’ÂÖWF†öCÒ%õ5B"Ğ¢G'“ Ğ¢v—F‚W&ÆÆ–"ç&WVW7BçW&Æ÷Vâ‡&WÂF–ÖV÷WCÓ#R’2&W7 Ğ¢&W7ç&VB‚Ğ¢w&—FUöFVÆ—fW'•÷7FGW2‚'6VçB"Â6†Eö–BÂÆVâ‡FW‡B’Â""ÂÆVâ†ÖW76vR’ÂGFV×BĞ¢&–çB†b%FVÆVw&Ó¢6VçB6†'3×¶ÆVâ†ÖW76vR—Ò÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—ÒGFV×C×¶GFV×GÒ"Ğ¢&WGW&àĞ¢W†6WBW&ÆÆ–"æW'&÷"ä…EEW'&÷"2W†3 Ğ¢W'&÷%÷FW‡BÒW†2ç&VB‚’æFV6öFR‚'WFbÓ‚"Â'&WÆ6R"•³£SĞĞ¢Æ7EöW'&÷"Òb%FVÆVw&Ò…EE¶W†2æ6öFWÓ¢¶W'&÷%÷FW‡GÒ Ğ¢–bGFV×BÂ2æB†W†2æ6öFRÓÒC#’÷"W†2æ6öFRãÒS“ Ğ¢&WG'•ögFW"ÒW†2æ†VFW'2ævWB‚'&WG'’ÖgFW""Ğ¢FVÆ’Ò–çB‡&WG'•ögFW"’–b&WG'•ögFW"æB&WG'•ögFW"æ—6F–v—B‚’VÇ6RGFV×@Ğ¢F–ÖRç6ÆVW†FVÆ’Ğ¢6öçF–çVPĞ¢'&V°Ğ¢W†6WBW†6WF–öâ2W†3 Ğ¢Æ7EöW'&÷"Òb'·G—R†W†2’åõöæÖUõ÷Ó¢¶W†7Ò Ğ¢–bGFV×BÂ3 Ğ¢F–ÖRç6ÆVW†GFV×BĞ¢6öçF–çVPĞ¢'&V°Ğ¢w&—FUöFVÆ—fW'•÷7FGW2‚&f–ÆVB"Â6†Eö–BÂÆVâ‡FW‡B’ÂÆ7EöW'&÷"ÂÆVâ†ÖW76vR’Â2Ğ¢&—6R'VçF–ÖTW'&÷"†b%FVÆVw&ÒFVÆ—fW'’f–ÆVC¢¶Æ7EöW'&÷'Ò"Ğ Ğ Ğ¦FVb—5öV×G•÷&F%÷&W÷'B‡FW‡C¢7G"’Óâ&ööÃ Ğ¢&WGW&â.ÈJ»8C¢Ù[^ÈºÂ«B"–âFW‡@Ğ Ğ Ğ¦FVb6†÷VÆE÷6VæEöV×G•÷&F"‚’Óâ&ööÃ Ğ¢&WGW&â÷2ævWFVçb‚%4TäEôTÕE•õ$D""Â""’æÆ÷vW"‚’–â²#"Â'G'VR"Â'–W2"Â'’'ĞĞ Ğ Ğ¦FVb'6Uö††ÖÒ‡fÇVS¢7G"ÂfÆÆ&6³¢GWÆU¶–çBÂ–çEÒ’Óâ–çC Ğ¢ÖF6‚Ò&RæÖF6‚‡"%åÇ2¢…ÆG³Ã'Ò“¢…ÆG³'Ò•Ç2¢B"ÂfÇVR÷"""Ğ¢–bæ÷BÖF6ƒ Ğ¢&WGW&âfÆÆ&6µ³Ò¢c²fÆÆ&6µ³ĞĞ¢†÷W"ÂÖ–çWFRÒ–çB†ÖF6‚æw&÷Wƒ’’Â–çB†ÖF6‚æw&÷Wƒ"’Ğ¢&WGW&âÖ‚ƒÂÖ–âƒ#2Â†÷W"’’¢c²Ö‚ƒÂÖ–âƒS’ÂÖ–çWFR’Ğ Ğ Ğ¦FVb&V÷Vå÷6VæE÷v–æF÷uö÷Vâ‚’Óâ&ööÃ Ğ¢–b÷2ævWFVçb‚%$D%õ%TåôÔôDR"Â""’ç7G&—‚’æÆ÷vW"‚’ÓÒ&Æ—fR# Ğ¢&WGW&âG'VPĞ¢–b÷2ævWFVçb‚$ÄÄõuôôdeõt”äDõuõDTÄTu$Ò"Â""’æÆ÷vW"‚’–â²#"Â'G'VR"Â'–W2"Â'’'Ó Ğ¢&WGW&âG'VPĞ¢æ÷rÒ&6Ræ·7Eöæ÷r‚Ğ¢7W'&VçBÒæ÷ræ†÷W"¢c²æ÷ræÖ–çWFPĞ¢7F'BÒ'6Uö††ÖÒ†÷2ævWFVçb‚%$TõTåõ4TäEõt”äDõuõ5D%Eôµ5B"Â#S£3"’ÂƒRÂ3’Ğ¢VæBÒ'6Uö††ÖÒ†÷2ævWFVçb‚%$TõTåõ4TäEõt”äDõuôTäEôµ5B"Â#s£3"’ÂƒrÂ3’Ğ¢–b7F'BÃÒVæC Ğ¢&WGW&â7F'BÃÒ7W'&VçBÃÒVæ@Ğ¢&WGW&â7W'&VçBãÒ7F'B÷"7W'&VçBÃÒVæ@Ğ Ğ Ğ¦FVbf—E÷FVÆVw&Õö‡FÖÂ‡FW‡C¢7G"ÂÆ–Ö—C¢–çB’Óâ7G# Ğ¢–bÆVâ‡FW‡B’ÃÒÆ–Ö—C Ğ¢&WGW&âFW‡@Ğ¢7Vff—‚Ò%ÆåÆîÊNË+B»;N«:ÈIÎ¸©Bv—D‡V"7F–öç2'F–f7NÉyÈIÂÙ™^ÉÛ‚ÙXNÉ©Bâ Ğ¢6æF–FFRÒFW‡E³¢Ö‚ƒÂÆ–Ö—BÒÆVâ‡7Vff—‚’•ĞĞ¢æWvÆ–æRÒ6æF–FFRç&f–æB‚%Æâ"Ğ¢–bæWvÆ–æRâƒ Ğ¢6æF–FFRÒ6æF–FFU³¦æWvÆ–æUĞĞ¢–b6æF–FFRæ6÷VçB‚#Æ"’â6æF–FFRæ6÷VçB‚#Âöâ"“ Ğ¢6æF–FFRÒ6æF–FFU³¢6æF–FFRç&f–æB‚#Æ"•Òç'7G&—‚Ğ¢&WGW&â†6æF–FFRç'7G&—‚’²7Vff—‚•³¦Æ–Ö—EĞĞ Ğ Ğ¦FVbw&—FUöFVÆ—fW'•÷7FGW2€Ğ¢7FGW3¢7G"ÀĞ¢6†Eö–C¢7G"ÀĞ¢÷&–v–æÅö6†'3¢–çBÀĞ¢W'&÷#¢7G"Ò""ÀĞ¢6VçEö6†'3¢–çBÂæöæRÒæöæRÀĞ¢GFV×G3¢–çBÂæöæRÒæöæRÀĞ¢’ÓâæöæS Ğ¢–ÆöBÒ°Ğ¢'7FGW2#¢7FGW2ÀĞ¢&6†Eö–EöÖ6¶VB#¢Ö6µö6†Eö–B†6†Eö–B’ÀĞ¢&÷&–v–æÅö6†'2#¢÷&–v–æÅö6†'2ÀĞ¢'6VçEö6†'2#¢6VçEö6†'2ÀĞ¢&GFV×G2#¢GFV×G2ÀĞ¢&W'&÷"#¢W'&÷"ÀĞ¢ĞĞ¢&6RäõUBæÖ¶F—"†W†—7Eöö³ÕG'VRĞ¢†&6RäõUBò&vÖV¦ö÷&V÷VåöæWw5÷&F%öFVÆ—fW'’æ§6öâ"’çw&—FU÷FW‡B€Ğ¢§6öâæGV×2‡–ÆöBÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"’²%Æâ"ÀĞ¢Væ6öF–æsÒ'WFbÓ‚"ÀĞ¢Ğ Ğ Ğ¦FVbÖ6µö6†Eö–B‡fÇVS¢7G"’Óâ7G# Ğ¢–bæ÷BfÇVS Ğ¢&WGW&â" Ğ¢&WGW&â"¢"¢Ö‚ƒÂÆVâ‡fÇVR’ÒB’²fÇVU²ÓC¥ĞĞ Ğ Ğ§FVÆVw&Òæ6ö×7E÷&W÷'BÒ6ö×7E÷&W÷'@Ğ§FVÆVw&Òç6VæE÷FVÆVw&ÒÒ6VæE÷FVÆVw&ĞĞ§FVÆVw&Òæf–æÅöÆW'G5öf÷%ö÷WGWBÒVÆ—G•öF—7Æ•öÆW'G0Ğ§FVÆVw&Òæ6æöæ–6ÅöÆW'Eöf÷%÷6VVâÒæ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGW@Ğ Ğ Ğ¦–bõöæÖUõòÓÒ%õöÖ–åõò# Ğ¢&—6R7—7FVÔW†—B‡FVÆVw&ÒæÖ–â‚’Ğ