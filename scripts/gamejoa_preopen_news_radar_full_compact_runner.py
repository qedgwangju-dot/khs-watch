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
            alert["grid_policy_delay"] = True
            alert["news"] = "ë¶ë¯¸ ì†¡ì „ë§ íˆ¬ì ì •ì±… ë³€ìˆ˜: ì •ë¶€ ìŠ¹ì¸Â·ê·œì œ ì§€ì—° ë¦¬ìŠ¤í¬"
            alert["interpretation"] = "ë¶ë¯¸ ì†¡ì „ë§ íˆ¬ìëŠ” ì „ë ¥ ìˆ˜ìš”ë³´ë‹¤ ì •ë¶€ ìŠ¹ì¸, ê·œì œ, ì¸í—ˆê°€, ê³„í†µì ‘ì† ì¼ì •ì— ì†ë„ê°€ ì¢Œìš°ë©ë‹ˆë‹¤. ì§€ì—° ì‹œ ì „ë ¥ê¸°ê¸°Â·ì „ì„ Â·ë³€ì••ê¸° ìˆ˜ì£¼ ê¸°ëŒ€ì˜ ì¸ì‹ ì‹œì ê³¼ ë°¸ë¥˜ì—ì´ì…˜ í”„ë¦¬ë¯¸ì—„ì„ ì¬ì ê²€í•´ì•¼ í•©ë‹ˆë‹¤."
            alert["failed_signal"] = "FERC/DOEÂ·ì£¼ ê³µê³µì„œë¹„ìŠ¤ìœ„ì›íšŒ ìŠ¹ì¸ê³¼ ìœ í‹¸ë¦¬í‹° CAPEX ì¼ì •ì´ ìœ ì§€ë˜ê³  ê³„í†µì ‘ì†Â·ì†¡ì „ì„  ì¸í—ˆê°€ ì§€ì—° ì‹ í˜¸ê°€ ì—†ìœ¼ë©´ ì¬ë£Œ ì•½í™”"

        if alert and is_port_strike:
            for impact in ["ì‹œê°„í‘œ", "ëˆ ë²„ëŠ” ëŠ¥ë ¥"]:
                if impact not in alert["impacts"]:
                    alert["impacts"].append(impact)
            if "ì˜ì‚¬ê²°ì • ì˜í–¥ ì œí•œì " in alert["impacts"] and len(alert["impacts"]) > 1:
                alert["impacts"] = [x for x in alert["impacts"] if x != "ì˜ì‚¬ê²°ì • ì˜í–¥ ì œí•œì "]
            impact_order = ["ì‹œê°„í‘œ", "ëˆ ë²„ëŠ” ëŠ¥ë ¥", "í• ì¸ìœ¨", "ìˆ˜ê¸‰"]
            alert["impacts"] = [x for x in impact_order if x in alert["impacts"]] + [x for x in alert["impacts"] if x not in impact_order]
            alert["paths"] = [
                "ì´ìµ" if x == "ëˆ ë²„ëŠ” ëŠ¥ë ¥" else "í• ì¸ìœ¨" if x == "í• ì¸ìœ¨" else "ìˆ˜ê¸‰" if x == "ìˆ˜ê¸‰" else "ë©”ê°€í”„ë¡œì íŠ¸ ì¼ì •"
                for x in alert["impacts"]
            ]
            for sector in ["ë©”ê°€í”„ë¡œì íŠ¸ ì¼ì •/ë¬¼ë¥˜", "í•´ìš´/í•­ë§Œ/ë¬¼ë¥˜"]:
                if sector not in alert["sectors"]:
                    alert["sectors"].append(sector)
            alert["score"] = max(int(alert.get("score", 0)), 102)
            alert["importance"] = "ìƒ" if alert["score"] >= 100 else "ì¤‘"
            alert["port_strike_risk"] = True
            alert["news"] = "ë©”ê°€í”„ë¡œì íŠ¸ ì¼ì •: ë¯¸êµ­ ë™ë¶€Â·ê±¸í”„ í•­ë§Œ ê³„ì•½ ë§Œë£Œ/íŒŒì—… ë¦¬ìŠ¤í¬"
            alert["interpretation"] = "ë¯¸êµ­ ë™ë¶€Â·ê±¸í”„ í•­ë§Œ íŒŒì—… ë¦¬ìŠ¤í¬ëŠ”ÛıÚÚ$z{-®éÜj×ºÎ»Hr%Ğ¢÷WB³ÒW‡G&¢–b.ÙZÉÛÉÊ‚"–âÆW'BævWB‚&–×7G2"ÂµÒ“ ¢÷WB³Ò°¢b$Dd”“¶g&VBævWB‚wfÇVRr’–bg&VBævWB‚wfÇVRr’—2æ÷BæöæRVÇ6R~Ù™^ÉÛ‚»h«wÒ"À¢b%DRD•2·FRævWB‚wfÇVRr’–bFRævWB‚wfÇVRr’—2æ÷BæöæRVÇ6R~Ù™^ÉÛ‚»h«wÒ"À¢$•tÒõ5’"À¢Ğ¢&WGW&â"Â"æ¦ö–â†F–7Bæg&öÖ¶W—2†÷WB’’÷".Ù™^ÉÛ‚«¸ª^ÙYÂÊxÊ	ÊxÙÂÉxnÉØÂ   ¦FVb6VÖ–6öæGV7F÷%ö7–6ÆUö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS ¢–bæ÷BÆW'BævWB‚'6VÖ–6öæGV7F÷%÷6VÆÆöfb"“ ¢&WGW&âæöæP¢&WGW&â.º™NºªºjÂ««*œ+~«:«	ŞÈ*ÂÉêÎ«:+t4UŒ+~»ºYÉyÉÛNÈY‚»h¸»B¸ùÈ¹ÂÉX^Ù™BÉzÎ»h   ¦FVb6VÖ–6öæGV7F÷%÷öÆ–7•ö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS ¢–bæ÷BÆW'BævWB‚'öÆ–7•öG&—fR"“ ¢&WGW&âæöæP¢&WGW&â%"dBÈKÉZ«;^Ê	Â¸ÈÈ8+~È¹ÎÙh’È¹ÎÊ	+~ÈhÎ»hÉêR»	ÎÊ;ÂşÈ‰Ê;ÂÉ{«+ÈK   ¦FVb÷'E÷7G&–¶Uö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS ¢–bæ÷BÆW'BævWB‚'÷'E÷7G&–¶U÷&—6²"“ ¢&WGW&âæöæP¢&WGW&â$”ÄõU4Õ‚«8NÉ[ÒºxÎº8Ì+~Ù‰È8«+º
ÂÉzÎ»h+~¸ù»hş«ÙHBÙZŞºxÂË
ÊxŒ+~«‹ÉéÉêÂ¸*«‹ş¸ÈÙ‰R4U‚ÉÛÎÊ	R   ¦FVb6†–æö'VÆµö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS ¢–bæ÷BÆW'BævWB‚&6†–æ÷7F–×VÇW5ö'VÆ²"“ ¢&WGW&âæöæP¢&WGW&â.ÊI«ZÒ»hÉiËRÈºNºËÂ«	^¸øL+~Ë*«IÈIÒşÈIŞØ8BºËÎ¸ù¹øœ+t$D’ş»(ÎØÎÈJÉ«NÉèB¸ùÙh’   ¦FVbw&–E÷öÆ–7•ö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS ¢–bæ÷BÆW'BævWB‚&w&–E÷öÆ–7•öFVÆ’"“ ¢&WGW&âæöæP¢&WGW&â.Ê	^»hÈ«ÉÛŒ+~«yÎÊ	ÂşÉÛÙx«+~«8NØk^Ê	ÈhÒÉÛÎÊ	\+~ÉÊØ»ºjÎØ»4U‚ÊyÙh’ÈhŞ¸øB   ¦FVb&–÷FV6…öÆVFW'6†—ö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS ¢–bæ÷BÆW'BævWB‚&&–÷FV6…öÆVFW'6†—öf–ÇFW""“ ¢&WGW&âæöæP¢&WGW&âÆW'BævWB‚&&–÷FV6…ö6†V6²"’÷".ÈºNÊ	ÂºzNËiÂşÉÛNÉÛ\+~»˜^ØÈÎºx‚É«ÈJÈ‰ÎÉÈL+tdDÉÛÎÊ	\+~«ˆºjÂşÙZÉÛÉÊ‚¸ùÈ¹ÂÙ™^ÉÛ‚   ¦FVb&ö&÷F–75öW†V7WF–öåö6†V6²†ÆW'C¢F–7B’Óâ7G"ÂæöæS ¢–bæ÷BÆW'BævWB‚'&ö&÷F–75öW†V7WF–öåöf–ÇFW""“ ¢&WGW&âæöæP¢&WGW&âÆW'BævWB‚'&ö&÷F–75ö6†V6²"’÷".È+ÎÈKÊÊx«	ÎØë‚»
Ùj\+u$#RÓƒSØXÎÈªNØ«Œ+~»	ÎÊ;Âô4U‚şºzNËiÂÉÛÈ¹ÒÉ{«+Ù™^ÉÛ‚   ¦FVbF—7Æ•öæWw2†ÆW'C¢F–7B’Óâ7G# ¢&WGW&â¶÷&Vå÷F—FÆR†ÆW'B  ¦FVb6ö×7EöÆW'B†ÆW'C¢F–7BÂ–Gƒ¢–çBÂæ÷rÂg&VC¢F–7BÂFS¢F–7B’Óâ7G# ¢ÆW'BÒæ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGWB†ÆW'B¢W†×ÆW2ÒÆW'BævWB‚&W†×ÆW2"’÷"µĞ¢6÷VçE÷7Vff—‚Òb"‡¶ÆW'E²v6ÇW7FW%ö6÷VçBu×Ş«BºËnÉØÂ’"–bÆW'BævWB‚&6ÇW7FW%ö6÷VçB"’VÇ6R" ¢7FGW2ÒÆW'BævWB‚'7FGW2"’÷"‚.«;^È¹ÒÙ™^ÉÛ‚ÊB"–bW†×ÆW2VÇ6R.Ù™^ÉÛ‚»h«"¢&6—2ÒÆW'BævWB‚&¶÷&Vö&6—2"’÷"‚.É›ÈºşÊxÉzÒ¸›NÈªBÙ™^È+"–bW†×ÆW2VÇ6R.É›ÈºÙ™^È+"¢–×7G2ÒÆW'BævWB‚&–×7G2"’÷"².ÉÙÈ*Î«+Ê	RÉˆÙjRÊ	ÎÙYÎÊ%Ğ¢F—7Æ–VEö–×7G2ÒF—7Æ•ö–×7G2†–×7G2¢F‡2ÒÆW'BævWB‚'F‡2"’÷"².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"–b–×7BÓÒ.È¹Î«NÙÂ"VÇ6R–×7Bf÷"–×7B–â–×7G5Ğ¢6V7F÷'2ÒÆW'BævWB‚'6V7F÷'2"’÷"².ÉˆÙjRÈKØKÙ™^ÉÛ‚»h«%Ğ¢V&Æ—6†VBÒÆW'BævWB‚'V&Æ—6†VB"’÷"‚.ÉzÎ¹úÂ«B"–bW†×ÆW2VÇ6R.Ù™^ÉÛ‚»h«"¢&–6VEö–âÒÆW'BævWB‚'&–6VEö–â"’÷"b'¶ÆW'BævWB‚w&VfÆV7F–öâr’÷"~ÊI«BwÒâÙ¸NÈhÒ«;^È¹ÒÊ«N«;ÂÈ¹ÎÉêR»	ÉÙÙ™^ÉÛ‚ÊN«˜ÎÊxÙ™^Ê	R»	ÉˆÉËÎºÂ»;N«‹ÉkNº^È«^¸¸¸ºBâ ¢6÷VçFW"ÒÆW'BævWB‚&6÷VçFW""’÷".É¹ºË‚ÈK»hÊ«N«;Â«;^È¹ÒºËÈIÂÙ™^ÉÛ‚ÊB«;Î¸ÈÙ[NÈIÒ«¸ªR ¢–çFW'&WFF–öâÒÆW'BævWB‚&–çFW'&WFF–öâ"’÷".¸ø‚»(N¸©B¸ª^º
RÂÙZÉÛÉÊ‚ÂÈ‰«ˆ’ÂÈ¹Î«NÙÂÊIÙY¸)º[Â»	N«øÈ‰‚Éè¸©NÊxÙ™^ÉÛÙ[NÉ[ÂÙZ¸¸¸ºBâ ¢f–ÆVE÷6–væÂÒÆW'BævWB‚&f–ÆVE÷6–væÂ"’÷".«Hº
‚««*œ+~È‰«ˆœ+~«;^È¹ÒÙ¸NÈhÒÙ™^ÉÛÉÛB¸ùÙhÙYÊxÉX®ÉËÎº›B¸º»	ÎÈK¸›NÈªB  ¢Æ–æW2Ò¶b'¶–G‡Ò’··6fR†ÆW'BævWB‚v–×÷'Fæ6Rr’—ÒÂ·6fR‡7FGW2—ÕÒ·6fR†F—7Æ•öæWw2†ÆW'B’—×¶‡FÖÂæW66R†6÷VçE÷7Vff—‚ÂV÷FSÔfÇ6R—Ò%Ğ¢–bW†×ÆW3 ¢Æ–æW2æVæB†b"ÒÙ™^ÉÛƒ¢É¹ºËŒ+~»;N¸øB¶Ö–â†ÆVâ†W†×ÆW2’ÂB—Ş«BºËnÉØÂÙ™^ÉÛ‚"¢6÷W&6U÷FW‡BÒ6÷W&6U÷7VÖÖ'’†W†×ÆW5³£EÒ¢VÇ6S ¢6÷W&6U÷FW‡BÒ‡FÖÅöÆ–æ²†ÆW'BævWB‚'V&Æ—6†W""’÷"ÆW'BævWB‚'6÷W&6R"’÷".ËiÎË)‚Ù™^ÉÛ‚»h«"ÂÆW'BævWB‚&Æ–æ²"’÷""" ¢Æ–æW2³Ò°¢b"ÒÙYÎ«ZŞÉêR«‹ÊH¢·6fR†&6—2—Ò"À¢b"ÒØ8ÉèN¹ÛÎÉÛƒ¢É¹Ë)Â·6fR‡V&Æ—6†VB—Ò+rÙYÎ«ZÒØŠÎÉéÉéÙ™^È+¶æ÷s¢Tƒ¢TÒµ5GÒ"À¢b"ÒÙ[^ÈºÂ¸+NÉª“¢·6fR†ÆW'BævWB‚wöÆ–7•÷Æ–å÷7VÖÖ'’r’—Ò"À¢b"ÒØŠÎÉé«HÊ	¢·6fR†ÆW'BævWB‚v–çfW7FÖVçE÷f–Wrr’—Ò"À¢b"ÒÙYÎ«ZŞÉêRÉˆÙjS¢·6fR†ÆW'BævWB‚v¶÷&VöÖ&¶WEö–×7Br’—Ò"À¢b"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢·6fR‚rÂræ¦ö–â†F—7Æ–VEö–×7G2’—Ò"À¢b"Ò»hNºY‚ºzNØ«ºjŞÈªC¢·6fR†FV6—6–öåöÖG&—‚†–×7G2’—Ò"À¢b"ÒÉˆÙjR«+ŞºÃ¢·6fR‚rÂræ¦ö–â‡F‡2’—Ò"À¢b"ÒÉˆÙjRÈKØK¢·6fR‚rÂræ¦ö–â‡6V7F÷'2’—Ò"À¢b"Ò«Hº
‚Ù[NÉ›‚Ø»ËºBşÊxÙÃ¢·6fR‡&VÆFVE÷FW‡B†ÆW'BÂg&VBÂFR’—Ò"À¢b"Ò»	Éˆ«¸ª^ÈK¢·6fR‡&–6VEö–â—Ò"À¢b"Ò»	¸È«{Î«¢·6fR†6÷VçFW"—Ò"À¢b"ÒÙ[NÈIÓ¢·6fR†–çFW'&WFF–öâ—Ò"À¢Ğ¢6VÖ•ö6†V6²Ò6VÖ–6öæGV7F÷%ö7–6ÆUö6†V6²†ÆW'B¢öÆ–7•ö6†V6²Ò6VÖ–6öæGV7F÷%÷öÆ–7•ö6†V6²†ÆW'B¢÷'Eö6†V6²Ò÷'E÷7G&–¶Uö6†V6²†ÆW'B¢'VÆµö6†V6²Ò6†–æö'VÆµö6†V6²†ÆW'B¢w&–Eö6†V6²Òw&–E÷öÆ–7•ö6†V6²†ÆW'B¢&–÷FV6…ö6†V6²Ò&–÷FV6…öÆVFW'6†—ö6†V6²†ÆW'B¢&ö&÷F–75ö6†V6²Ò&ö&÷F–75öW†V7WF–öåö6†V6²†ÆW'B¢–böÆ–7•ö6†V6³ ¢Æ–æW2æVæB†b"Ò»	¸øNË+BÊ	^ËRË+NØÃ¢·6fR‡öÆ–7•ö6†V6²—Ò"¢VÆ–b6VÖ•ö6†V6³ ¢Æ–æW2æVæB†b"Ò»	¸øNË+B«ˆ¹ÛÒË+NØÃ¢·6fR‡6VÖ•ö6†V6²—Ò"¢–b÷'Eö6†V6³ ¢Æ–æW2æVæB†b"Òº™N«ÙHNºÎÊ	ŞØ«‚ÉÛÎÊ	RË+NØÃ¢·6fR‡÷'Eö6†V6²—Ò"¢–b'VÆµö6†V6³ ¢Æ–æW2æVæB†b"ÒÊI«ZÒ»hÉi+~»(ÎØÎÈJË+NØÃ¢·6fR†'VÆµö6†V6²—Ò"¢–bw&–Eö6†V6³ ¢Æ–æW2æVæB†b"ÒÈjÊNºyÒÊ	^ËRË+NØÃ¢·6fR†w&–Eö6†V6²—Ò"¢–b&–÷FV6…ö6†V6³ ¢Æ–æW2æVæB†b"Ò»	NÉÛNÉŠBÊ;Î¸øNÊ;ÂË+NØÃ¢·6fR†&–÷FV6…ö6†V6²—Ò"¢–b&ö&÷F–75ö6†V6³ ¢Æ–æW2æVæB†b"ÒÈ+ÎÈKºÎ»HrË+NØÃ¢·6fR‡&ö&÷F–75ö6†V6²—Ò"¢Æ–æW2³Ò°¢b"ÒÈºNØÊ‚ÈºÙ‹ƒ¢·6fR†f–ÆVE÷6–væÂ—Ò"À¢b"ÒËiÎË)ƒ¢·6÷W&6U÷FW‡GÒ+rÊÙ¨Â¶æ÷s¢Tƒ¢TÒµ5GÒ"À¢""À¢Ğ¢&WGW&â%Æâ"æ¦ö–â†Æ–æW2  ¦FVb6ö×7E÷&W÷'B†ÆW'G3¢Æ—7E¶F–7EÒÂg&VC¢F–7BÂFS¢F–7BÂæ÷r’Óâ7G# ¢Æ–Ö—BÒÖ‚ƒÂÖ–âƒrÂ–çB†÷2ævWFVçb‚%$D%ôD•5Ä•ôÄ”Ô•B"Â#R"’’’¢f—6–&ÆRÒÆW'G5³¦Æ–Ö—EĞ¢Æ—fUöÖöFRÒ÷2ævWFVçb‚%$D%õ%TåôÔôDR"Â""’ç7G&—‚’æÆ÷vW"‚’ÓÒ&Æ—fR ¢–bÆ—fUöÖöFS ¢F—FÆRÒb/	ù;tÔT¤ôÈºNÈ¹Î«BÙ[^ÈºÂ¸›NÈªBºÉÛN¸ÙB+r¶æ÷s¢U¸XBVŞÉ¹BVNÉÛÇÒ+r¶æ÷s¢Tƒ¢T×Ò ¢6öÖÖVçE÷F—FÆRÒ/	ù*ÈºNÈ¹Î«B¸›NÈªBËÙNº™Ø«‚ ¢föÆÆ÷wWöÆ–æRÒ.¸ºNÉØÂØŠÎÉé«‹È8¸øNÉyÈIÂÈ‰Ë™Œ+~È‰«ˆœ+~ØXÎºxÉ˜ÉêÎÙ™^ÉÛ‚ÙXNÉ©Bâ ¢V×G•öÆ–æRÒ.ÈºNÈ¹Î«B«:Ëj«*’¸›NÈªBÊxÊ	Ù™^ÉÛ‚ÉxnÉØÂ ¢VÇ6S ¢F—FÆRÒb/	ù;tÔT¤ôÉê^ÊBÙ[^ÈºÂ¸›NÈªBºÉÛN¸ÙB+r¶æ÷s¢U¸XBVŞÉ¹BVNÉÛÇÒ+rc£3 ¢6öÖÖVçE÷F—FÆRÒ/	ù*c£3Éê^ÊB¸›NÈªBËÙNº™Ø«‚ ¢föÆÆ÷wWöÆ–æRÒ#c£SØŠÎÉé«‹È8¸øNÉyÈIÂÈ‰Ë™Œ+~È‰«ˆœ+~ØXÎºxÉ˜ÉêÎÙ™^ÉÛ‚ÙXNÉ©Bâ ¢V×G•öÆ–æRÒ.Éê^ÊB«:Ëj«*’¸›NÈªBÊxÊ	Ù™^ÉÛ‚ÉxnÉØÂ ¢Æ–æW2Ò·F—FÆRÂb.ÊÙ¨Ã¢¶æ÷s¢U’ÒVÒÒVBTƒ¢TÒµ5GÒ"Âb.ÈJ»8C¢Ù[^ÈºÂ¶ÆVâ‡f—6–&ÆR—Ş«B"Â"%Ğ¢–bf—6–&ÆS ¢f÷"–G‚ÂÆW'B–âVçVÖW&FR‡f—6–&ÆRÂ“ ¢Æ–æW2æVæB†6ö×7EöÆW'B†ÆW'BÂ–G‚Âæ÷rÂg&VBÂFR’¢6†ævVBÒ,+r"æ¦ö–â†F—7Æ•ö–×7G2‡f—6–&ÆU³ÒævWB‚&–×7G2"’’¢VÇ6S ¢Æ–æW2³Ò¶V×G•öÆ–æRÂ"%Ğ¢6†ævVBÒ.º¨^Ù™^ÙYÂ»8Ù™BÉxnÉØÂ ¢Æ–æW2³Ò°¢6öÖÖVçE÷F—FÆRÀ¢b.ÉŠN¸©‚Ù[^ÈºÂ»8Ù™N¸©B·6fR†6†ævVB—ÖÉè^¸¸¸ºBâÙYÎ«ZŞÉê^ÉyÈIÎ¸©B«Hº
‚Ù[NÉ›‚Ø»ËºB»	ÉÙ«;Â«ZŞ¸+BÈ‰«ˆ’Ù™^È+ÉzÎ»hº[Âº‹ÎÊÙ™^ÉÛÙZ¸¸¸ºBâ"À¢b.ÙZÉÛÉÊƒ¢·6fR‡FVÆVw&Òæ6ö×7E÷&VÅ÷––VÆB†g&VBÂFR’—Ò"À¢föÆÆ÷wWöÆ–æRÀ¢""À¢.ØŠÎÉéÊÉkÉÛBÉXN¸¸ÂË«:Éª’¸›NÈªB»ˆÎºjÎÙYÉè^¸¸¸ºBâ"À¢Ğ¢&W÷'BÒ%Æâ"æ¦ö–â†Æ–æW2’ç7G&—‚’²%Æâ ¢wV&E÷&V÷Vå÷&W÷'B‡&W÷'B¢&WGW&â&W÷'@  ¦FVbwV&E÷&V÷Vå÷&W÷'B‡FW‡C¢7G"’ÓâæöæS ¢W'&÷'3¢Æ—7E·7G%ÒÒµĞ¢fÆ–E÷F—FÆRÒ€¢FW‡Bç7F'G7v—F‚‚/	ù;tÔT¤ôÉê^ÊBÙ[^ÈºÂ¸›NÈªBºÉÛN¸ÙB+r"¢÷"FW‡Bç7F'G7v—F‚‚/	ù;tÔT¤ôÈºNÈ¹Î«BÙ[^ÈºÂ¸›NÈªBºÉÛN¸ÙB+r"¢¢–bæ÷BfÆ–E÷F—FÆS ¢W'&÷'2æVæB‚'F—FÆUö6öçG&7B"¢—FVÕö6÷VçBÒ7VÒƒf÷"Æ–æR–âFW‡Bç7Æ—FÆ–æW2‚’–b&RæÖF6‚‡"%åÆBµÂ•Ç2µÅ²"ÂÆ–æR’¢&WV—&VBÒ°¢"ÒÙ[^ÈºÂ¸+NÉª“¢"À¢"ÒØŠÎÉé«HÊ	¢"À¢"ÒÙYÎ«ZŞÉêRÉˆÙjS¢"À¢"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢"À¢"ÒÉˆÙjR«+ŞºÃ¢"À¢"ÒÉˆÙjRÈKØK¢"À¢"Ò»	Éˆ«¸ª^ÈK¢"À¢"Ò»	¸È«{Î«¢"À¢"ÒÈºNØÊ‚ÈºÙ‹ƒ¢"À¢Ğ¢f÷"Ö&¶W"–â&WV—&VC ¢–b—FVÕö6÷VçBæBFW‡Bæ6÷VçB†Ö&¶W"’Â—FVÕö6÷VçC ¢W'&÷'2æVæB†b&Ö—76–æu÷¶Ö&¶W'Ò"¢–b—FVÕö6÷VçBæB"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢ÉÙÈ*Î«+Ê	RÉˆÙjRÊ	ÎÙYÎÊ"–âFW‡C ¢W'&÷'2æVæB‚&Æ–Ö—FVEöFV6—6–öåö–×7EöF—7Æ–VB"¢f÷"‡&6R–âtTäU$”5ôU…ÄäD”ôåõ…$4U3 ¢–b—FVÕö6÷VçBæB‡&6R–âFW‡C ¢W'&÷'2æVæB‚&vVæW&–5÷öÆ–7•öW‡ÆæF–öåöF—7Æ–VB"¢f÷"Æ–æR–âFW‡Bç7Æ—FÆ–æW2‚“ ¢–bæ÷B&RæÖF6‚‡"%åÆBµÂ•Ç2µÅ²"ÂÆ–æR“ ¢6öçF–çVP¢F—FÆRÒ&Rç7V"‡"%åÆBµÂ•Ç2µÅµµåÅÕÒµÅÕÇ2¢"Â""ÂÆ–æR’ç7G&—‚¢F—FÆRÒ&Rç7V"‡"%Â…ÆB¾«BºËnÉØÅÂ’B"Â""ÂF—FÆR’ç7G&—‚¢–bÖ÷7FÇ•ö66–’‡F—FÆR“ ¢W'&÷'2æVæB†b'&uöVævÆ—6…ö†VF–æs×·F—FÆU³£ƒ×Ò"¢Æ÷rÒ&Rç7V"‡"&‡GG3ó¢òõÅ2²"Â""ÂFW‡B’æÆ÷vW"‚¢f÷"Ö&¶W"–â°¢'F†—2Fö7VÖVçB—2Ç6òf–Æ&ÆR–âF†RföÆÆ÷v–ærf÷&ÖG2"À¢&æ÷&ÖÆ—¦VBGG&–'WFW2æBÖWFFF"À¢&÷&–v–æÂgVÆÂFW‡B†ÖÂ"À¢&v÷fW&æÖVçBV&Æ—6†–æröff–6RÖWFFF"À¢&FWfVÆ÷W"FööÇ2vW2"À¢Ó ¢–bÖ&¶W"–âÆ÷s ¢W'&÷'2æVæB†b&fVFW&Å÷&Vv—7FW%ö&ö–ÆW'ÆFS×¶Ö&¶W'Ò"¢–bW'&÷'3 ¢&—6R'VçF–ÖTW'&÷"‚$tÔT¤ô&V÷Vâ&F"VÆ—G’wV&B&Æö6¶VBFVÆVw&Ò÷WGWC¢"²#²"æ¦ö–â†W'&÷'2’  ¦FVb6VæE÷FVÆVw&Ò‡FW‡C¢7G"’ÓâæöæS ¢wV&E÷&V÷Vå÷&W÷'B‡FW‡B¢6†Eö–BÒ÷2ævWFVçb‚%DTÄTu$Õô4„Eô”B"Â""’ç7G&—‚¢–b—5öV×G•÷&F%÷&W÷'B‡FW‡B’æBæ÷B6†÷VÆE÷6VæEöV×G•÷&F"‚“ ¢w&—FUöFVÆ—fW'•÷7FGW2‚'6¶—VEöV×G’"Â6†Eö–BÂÆVâ‡FW‡B’Â$æò†–v‚Ö–×7B&F"—FVÒ6VÆV7FVB"¢&–çB†b%FVÆVw&Ó¢6¶—VBV×G’&F"÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—Ò"¢&WGW&à¢–bæ÷B&V÷Vå÷6VæE÷v–æF÷uö÷Vâ‚“ ¢w&—FUöFVÆ—fW'•÷7FGW2‚'6¶—VEööfe÷v–æF÷r"Â6†Eö–BÂÆVâ‡FW‡B’Â$÷WG6–FRtÔT¤ô&V÷VâFVÆVw&Ò6VæBv–æF÷r"¢&–çB†b%FVÆVw&Ó¢6¶—VB÷WG6–FR&V÷Vâ6VæBv–æF÷r÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—Ò"¢&WGW&à¢Fö¶VâÒ÷2ævWFVçb‚%DTÄTu$Õô$õEõDô´Tâ"Â""’ç7G&—‚¢–bæ÷BFö¶Vâ÷"æ÷B6†Eö–C ¢w&—FUöFVÆ—fW'•÷7FGW2‚&&Æö6¶VB"Â6†Eö–BÂÆVâ‡FW‡B’Â%DTÄTu$Õô$õEõDô´Tâ÷"DTÄTu$Õô4„Eô”BÖ—76–ær"¢&—6R'VçF–ÖTW'&÷"‚%FVÆVw&ÒFVÆ—fW'’&Æö6¶VC¢DTÄTu$Õô$õEõDô´Tâ÷"DTÄTu$Õô4„Eô”BÖ—76–ær"¢ÖW76vRÒf—E÷FVÆVw&Õö‡FÖÂ‡FW‡BÂ&6RåDTÄTu$ÕôÄ”Ô•B¢&öG’ÒW&ÆÆ–"ç'6RçW&ÆVæ6öFR‡°¢&6†Eö–B#¢6†Eö–BÀ¢'FW‡B#¢ÖW76vRÀ¢&F—6&ÆU÷vV%÷vU÷&Wf–Wr#¢'G'VR"À¢''6UöÖöFR#¢$…DÔÂ"À¢Ò’æVæ6öFR‚'WFbÓ‚"¢Æ7EöW'&÷"Ò" ¢f÷"GFV×B–â&ævRƒÂB“ ¢&WÒW&ÆÆ–"ç&WVW7Bå&WVW7B†b&‡GG3¢òö’çFVÆVw&Òæ÷&rö&÷G·Fö¶VçÒ÷6VæDÖW76vR"ÂFFÖ&öG’ÂÖWF†öCÒ%õ5B"¢G'“ ¢v—F‚W&ÆÆ–"ç&WVW7BçW&Æ÷Vâ‡&WÂF–ÖV÷WCÓ#R’2&W7 ¢&W7ç&VB‚¢w&—FUöFVÆ—fW'•÷7FGW2‚'6VçB"Â6†Eö–BÂÆVâ‡FW‡B’Â""ÂÆVâ†ÖW76vR’ÂGFV×B¢&–çB†b%FVÆVw&Ó¢6VçB6†'3×¶ÆVâ†ÖW76vR—Ò÷&–v–æÅö6†'3×¶ÆVâ‡FW‡B—ÒGFV×C×¶GFV×GÒ"¢&WGW&à¢W†6WBW&ÆÆ–"æW'&÷"ä…EEW'&÷"2W†3 ¢W'&÷%÷FW‡BÒW†2ç&VB‚’æFV6öFR‚'WFbÓ‚"Â'&WÆ6R"•³£SĞ¢Æ7EöW'&÷"Òb%FVÆVw&Ò…EE¶W†2æ6öFWÓ¢¶W'&÷%÷FW‡GÒ ¢–bGFV×BÂ2æB†W†2æ6öFRÓÒC#’÷"W†2æ6öFRãÒS“ ¢&WG'•ögFW"ÒW†2æ†VFW'2ævWB‚'&WG'’ÖgFW""¢FVÆ’Ò–çB‡&WG'•ögFW"’–b&WG'•ögFW"æB&WG'•ögFW"æ—6F–v—B‚’VÇ6RGFV×@¢F–ÖRç6ÆVW†FVÆ’¢6öçF–çVP¢'&V°¢W†6WBW†6WF–öâ2W†3 ¢Æ7EöW'&÷"Òb'·G—R†W†2’åõöæÖUõ÷Ó¢¶W†7Ò ¢–bGFV×BÂ3 ¢F–ÖRç6ÆVW†GFV×B¢6öçF–çVP¢'&V°¢w&—FUöFVÆ—fW'•÷7FGW2‚&f–ÆVB"Â6†Eö–BÂÆVâ‡FW‡B’ÂÆ7EöW'&÷"ÂÆVâ†ÖW76vR’Â2¢&—6R'VçF–ÖTW'&÷"†b%FVÆVw&ÒFVÆ—fW'’f–ÆVC¢¶Æ7EöW'&÷'Ò"  ¦FVb—5öV×G•÷&F%÷&W÷'B‡FW‡C¢7G"’Óâ&ööÃ ¢&WGW&â.ÈJ»8C¢Ù[^ÈºÂ«B"–âFW‡@  ¦FVb6†÷VÆE÷6VæEöV×G•÷&F"‚’Óâ&ööÃ ¢&WGW&â÷2ævWFVçb‚%4TäEôTÕE•õ$D""Â""’æÆ÷vW"‚’–â²#"Â'G'VR"Â'–W2"Â'’'Ğ  ¦FVb'6Uö††ÖÒ‡fÇVS¢7G"ÂfÆÆ&6³¢GWÆU¶–çBÂ–çEÒ’Óâ–çC ¢ÖF6‚Ò&RæÖF6‚‡"%åÇ2¢…ÆG³Ã'Ò“¢…ÆG³'Ò•Ç2¢B"ÂfÇVR÷"""¢–bæ÷BÖF6ƒ ¢&WGW&âfÆÆ&6µ³Ò¢c²fÆÆ&6µ³Ğ¢†÷W"ÂÖ–çWFRÒ–çB†ÖF6‚æw&÷Wƒ’’Â–çB†ÖF6‚æw&÷Wƒ"’¢&WGW&âÖ‚ƒÂÖ–âƒ#2Â†÷W"’’¢c²Ö‚ƒÂÖ–âƒS’ÂÖ–çWFR’  ¦FVb&V÷Vå÷6VæE÷v–æF÷uö÷Vâ‚’Óâ&ööÃ ¢–b÷2ævWFVçb‚%$D%õ%TåôÔôDR"Â""’ç7G&—‚’æÆ÷vW"‚’ÓÒ&Æ—fR# ¢&WGW&âG'VP¢–b÷2ævWFVçb‚$ÄÄõuôôdeõt”äDõuõDTÄTu$Ò"Â""’æÆ÷vW"‚’–â²#"Â'G'VR"Â'–W2"Â'’'Ó ¢&WGW&âG'VP¢æ÷rÒ&6Ræ·7Eöæ÷r‚¢7W'&VçBÒæ÷ræ†÷W"¢c²æ÷ræÖ–çWFP¢7F'BÒ'6Uö††ÖÒ†÷2ævWFVçb‚%$TõTåõ4TäEõt”äDõuõ5D%Eôµ5B"Â#S£3"’ÂƒRÂ3’¢VæBÒ'6Uö††ÖÒ†÷2ævWFVçb‚%$TõTåõ4TäEõt”äDõuôTäEôµ5B"Â#s£3"’ÂƒrÂ3’¢–b7F'BÃÒVæC ¢&WGW&â7F'BÃÒ7W'&VçBÃÒVæ@¢&WGW&â7W'&VçBãÒ7F'B÷"7W'&VçBÃÒVæ@  ¦FVbf—E÷FVÆVw&Õö‡FÖÂ‡FW‡C¢7G"ÂÆ–Ö—C¢–çB’Óâ7G# ¢–bÆVâ‡FW‡B’ÃÒÆ–Ö—C ¢&WGW&âFW‡@¢7Vff—‚Ò%ÆåÆîÊNË+B»;N«:ÈIÎ¸©Bv—D‡V"7F–öç2'F–f7NÉyÈIÂÙ™^ÉÛ‚ÙXNÉ©Bâ ¢6æF–FFRÒFW‡E³¢Ö‚ƒÂÆ–Ö—BÒÆVâ‡7Vff—‚’•Ğ¢æWvÆ–æRÒ6æF–FFRç&f–æB‚%Æâ"¢–bæWvÆ–æRâƒ ¢6æF–FFRÒ6æF–FFU³¦æWvÆ–æUĞ¢–b6æF–FFRæ6÷VçB‚#Æ"’â6æF–FFRæ6÷VçB‚#Âöâ"“ ¢6æF–FFRÒ6æF–FFU³¢6æF–FFRç&f–æB‚#Æ"•Òç'7G&—‚¢&WGW&â†6æF–FFRç'7G&—‚’²7Vff—‚•³¦Æ–Ö—EĞ  ¦FVbw&—FUöFVÆ—fW'•÷7FGW2€¢7FGW3¢7G"À¢6†Eö–C¢7G"À¢÷&–v–æÅö6†'3¢–çBÀ¢W'&÷#¢7G"Ò""À¢6VçEö6†'3¢–çBÂæöæRÒæöæRÀ¢GFV×G3¢–çBÂæöæRÒæöæRÀ¢’ÓâæöæS ¢–ÆöBÒ°¢'7FGW2#¢7FGW2À¢&6†Eö–EöÖ6¶VB#¢Ö6µö6†Eö–B†6†Eö–B’À¢&÷&–v–æÅö6†'2#¢÷&–v–æÅö6†'2À¢'6VçEö6†'2#¢6VçEö6†'2À¢&GFV×G2#¢GFV×G2À¢&W'&÷"#¢W'&÷"À¢Ğ¢&6RäõUBæÖ¶F—"†W†—7Eöö³ÕG'VR¢†&6RäõUBò&vÖV¦ö÷&V÷VåöæWw5÷&F%öFVÆ—fW'’æ§6öâ"’çw&—FU÷FW‡B€¢§6öâæGV×2‡–ÆöBÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"’²%Æâ"À¢Væ6öF–æsÒ'WFbÓ‚"À¢  ¦FVbÖ6µö6†Eö–B‡fÇVS¢7G"’Óâ7G# ¢–bæ÷BfÇVS ¢&WGW&â" ¢&WGW&â"¢"¢Ö‚ƒÂÆVâ‡fÇVR’ÒB’²fÇVU²ÓC¥Ğ  §FVÆVw&Òæ6ö×7E÷&W÷'BÒ6ö×7E÷&W÷'@§FVÆVw&Òç6VæE÷FVÆVw&ÒÒ6VæE÷FVÆVw&Ğ§FVÆVw&Òæf–æÅöÆW'G5öf÷%ö÷WGWBÒVÆ—G•öF—7Æ•öÆW'G0§FVÆVw&Òæ6æöæ–6ÅöÆW'Eöf÷%÷6VVâÒæ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGW@  ¦–bõöæÖUõòÓÒ%õöÖ–åõò# ¢&—6R7—7FVÔW†—B‡FVÆVw&ÒæÖ–â‚’