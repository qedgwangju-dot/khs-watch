#!/usr/bin/env python3
"""Shared Korean market-impact explanation helpers for KHS policy alerts."""

from __future__ import annotations

import re
from typing import Any


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[,|/]", value) if part.strip()]
        return parts or [value.strip()]
    return [str(value)]


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def matched_terms(item: dict) -> str:
    matched = item.get("matched") or {}
    if isinstance(matched, dict):
        return " ".join(term for terms in matched.values() for term in as_list(terms))
    return " ".join(as_list(matched))


def text_for(item: dict) -> str:
    return " ".join(
        str(part or "")
        for part in (
            item.get("source"),
            item.get("title"),
            item.get("source_title"),
            item.get("source_abstract"),
            item.get("source_body"),
            item.get("original_title"),
            item.get("summary"),
            item.get("link"),
            item.get("core"),
            item.get("point"),
            item.get("impact"),
            item.get("policy_plain_summary"),
            matched_terms(item),
            " ".join(as_list(item.get("sectors"))),
        )
    ).lower()


def has_any(text: str, terms: list[str]) -> bool:
    for term in terms:
        term = term.lower()
        if re.fullmatch(r"[a-z0-9]+", term):
            if re.search(rf"\b{re.escape(term)}\b", text):
                return True
            continue
        if term in text:
            return True
    return False


def is_china_mofcom_trade_control(text: str, item: dict) -> bool:
    source = str(item.get("source") or "").lower()
    has_authority = (
        "china mofcom" in source
        or has_any(text, ["mofcom", "china ministry of commerce", "chinese ministry of commerce", "ä¸­å›½å•†åŠ¡éƒ¨", "å•†åŠ¡éƒ¨"])
    )
    has_action = has_any(
        text,
        [
            "export ban", "export suspension", "export control", "export licensing",
            "tariff", "anti-dumping", "antidumping", "countervailing",
            "å‡ºå£ç®¡åˆ¶", "æš‚åœå‡ºå£", "åœæ­¢å‡ºå£", "ç¦æ­¢å‡ºå£", "å…³ç¨Ž", "åå€¾é”€", "åè¡¥è´´",
        ],
    ) or ("å‡ºå£" in text and has_any(text, ["ç®¡åˆ¶", "æš‚åœ", "åœæ­¢", "ç¦æ­¢", "è®¸å¯", "ç¦ä»¤"])) or (
        has_any(text, ["export", "exports"])
        and has_any(text, ["suspend", "suspends", "suspended", "ban", "bans", "banned"])
    )
    return has_authority and has_action


def china_mofcom_product(text: str) -> str:
    products = [
        (["helium", "æ°¦"], "í—¬ë¥¨"),
        (["rare earth", "rare-earth", "ç¨€åœŸ"], "í¬í† ë¥˜"),
        (["gallium", "é•“"], "ê°ˆë¥¨"),
        (["germanium", "é”—"], "ê²Œë¥´ë§ˆëŠ„"),
        (["graphite", "çŸ³å¢¨"], "í‘ì—°"),
        (["antimony", "é”‘"], "ì•ˆí‹°ëª¬"),
        (["tungsten", "é’¨"], "í……ìŠ¤í…"),
        (["indium", "é“Ÿ"], "ì¸ë“"),
        (["battery", "cathode", "anode", "lfp", "ç”µæ± "], "ë°°í„°ë¦¬ ì†Œìž¬Â·ê¸°ìˆ "),
        (["semiconductor", "chip", "åŠå¯¼ä½“"], "ë°˜ë„ì²´ í’ˆëª©"),
        (["steel", "é’¢é“"], "ì² ê°•"),
        (["dual-use", "ä¸¤ç”¨ç‰©é¡¹"], "ì´ì¤‘ìš©ë„ í’ˆëª©"),
    ]
    for terms, label in products:
        if has_any(text, terms):
            return label
    return "ì „ëžµ í’ˆëª©"


def china_mofcom_action(text: str) -> str:
    if has_any(text, ["export suspension", "suspend exports", "suspended exports", "æš‚åœå‡ºå£", "åœæ­¢å‡ºå£"]) or (
        "å‡ºå£" in text and has_any(text, ["æš‚åœ", "åœæ­¢"])
    ) or (has_any(text, ["export", "exports"]) and has_any(text, ["suspend", "suspends", "suspended"])):
        return "ìˆ˜ì¶œ ì¼ì‹œ ì¤‘ë‹¨"
    if has_any(text, ["export ban", "banned exports", "ç¦æ­¢å‡ºå£", "å‡ºå£ç¦ä»¤"]) or (
        has_any(text, ["export", "exports"]) and has_any(text, ["ban", "bans", "banned"])
    ):
        return "ìˆ˜ì¶œ ê¸ˆì§€"
    if has_any(text, ["anti-dumping", "antidumping", "åå€¾é”€"]):
        return "ë°˜ë¤í•‘ ì¡°ì¹˜"
    if has_any(text, ["countervailing", "åè¡¥è´´"]):
        return "ìƒê³„ê´€ì„¸ ì¡°ì¹˜"
    if has_any(text, ["tariff", "tariffs", "å…³ç¨Ž"]):
        return "ê´€ì„¸ ì¡°ì¹˜"
    if has_any(text, ["export licensing", "å‡ºå£è®¸å¯"]):
        return "ìˆ˜ì¶œ í—ˆê°€ì œ"
    return "ìˆ˜ì¶œí†µì œ"


def put(item: dict, **values: Any) -> None:
    for key, value in values.items():
        if value is not None:
            item[key] = value


DECISION_QUESTION = "ì´ ë‰´ìŠ¤ê°€ ë§¤ì¶œÂ·ë§ˆì§„Â·í˜„ê¸ˆíë¦„, ë°¸ë¥˜ì—ì´ì…˜/í• ì¸ìœ¨, ìˆ˜ê¸‰, ì‹œê°„í‘œ ì¤‘ ë¬´ì—‡ì„ ë°”ê¾¸ëŠ”ê°€?"
DECISION_IMPACTS = ("ëˆ ë²„ëŠ” ëŠ¥ë ¥", "í• ì¸ìœ¨", "ìˆ˜ê¸‰", "ì‹œê°„í‘œ")
LIMITED_IMPACT = "ì˜ì‚¬ê²°ì • ì˜í–¥ ì œí•œì "
DECISION_DISPLAY_LABELS = {
    "ëˆ ë²„ëŠ” ëŠ¥ë ¥": "ë§¤ì¶œÂ·ë§ˆì§„Â·í˜„ê¸ˆíë¦„",
    "í• ì¸ìœ¨": "ë°¸ë¥˜ì—ì´ì…˜/í• ì¸ìœ¨",
    "ìˆ˜ê¸‰": "ìˆ˜ê¸‰",
    "ì‹œê°„í‘œ": "ì‹œê°„í‘œ",
    LIMITED_IMPACT: LIMITED_IMPACT,
}


def normalize_decision_impacts(item: dict, text: str = "") -> list[str]:
    raw_impacts = unique(as_list(item.get("impacts")))
    decision_text = " ".join(
        [
            text,
            " ".join(raw_impacts),
            " ".join(as_list(item.get("paths"))),
            " ".join(as_list(item.get("sectors"))),
            str(item.get("investment_view") or ""),
            str(item.get("korea_market_impact") or ""),
        ]
    ).lower()
    mapped: list[str] = []

    def add(label: str) -> None:
        if label not in mapped:
            mapped.append(label)

    for impact in raw_impacts:
        low = impact.lower()
        if impact in DECISION_IMPACTS:
            add(impact)
        elif impact == LIMITED_IMPACT:
            continue
        elif has_any(low, ["ë§¤ì¶œ", "ë§ˆì§„", "ì´ìµ", "ì›ê°€", "capex", "ìˆ˜ì£¼", "ê³„ì•½", "ëˆ ë²„ëŠ”"]):
            add("ëˆ ë²„ëŠ” ëŠ¥ë ¥")
        elif has_any(low, ["í• ì¸ìœ¨", "ê¸ˆë¦¬", "í™˜ìœ¨", "ê·œì œ ê°•ë„", "ë°¸ë¥˜", "valuation", "risk premium"]):
            add("í• ì¸ìœ¨")
        elif has_any(low, ["ìˆ˜ê¸‰", "etf", "ê¸°ê´€", "ì™¸êµ­ì¸", "í…Œë§ˆ"]):
            add("ìˆ˜ê¸‰")
        elif has_any(low, ["ì‹œê°„í‘œ", "ì‹œí–‰ì¼", "deadline", "approval", "permit", "ì¸í—ˆê°€", "í—ˆê°€"]):
            add("ì‹œê°„í‘œ")

    if not mapped:
        if has_any(decision_text, ["ë§¤ì¶œ", "ë§ˆì§„", "ì´ìµ", "ì›ê°€", "capex", "ìˆ˜ì£¼", "ê³„ì•½", "price competitiveness", "margin", "earnings"]):
            add("ëˆ ë²„ëŠ” ëŠ¥ë ¥")
        if has_any(decision_text, ["í• ì¸ìœ¨", "ê¸ˆë¦¬", "í™˜ìœ¨", "ê·œì œ ê°•ë„", "ë°¸ë¥˜", "valuation", "risk premium", "ëŒ€ì¶œ", "loan"]):
            add("í• ì¸ìœ¨")
        if has_any(decision_text, ["ìˆ˜ê¸‰", "etf", "ê¸°ê´€", "ì™¸êµ­ì¸", "í…Œë§ˆ", "ëŒ€ì²´ ê³µê¸‰ë§", "order flow", "supply chain"]):
            add("ìˆ˜ê¸‰")
        if has_any(
            decision_text,
            [
                "ì‹œê°„í‘œ",
                "ì‹œí–‰ì¼",
                "deadline",
                "effective date",
                "approval",
                "permit",
                "ì¸í—ˆê°€",
                "í—ˆê°€",
                "rulemaking",
                "request for comments",
                "comment deadline",
                "pdufa",
                "ì •ì±… íƒ€ìž„ë¼ì¸",
            ],
        ):
            add("ì‹œê°„í‘œ")

    if not mapped:
        mapped = [LIMITED_IMPACT]
    item["impacts"] = mapped
    item["decision_question"] = DECISION_QUESTION
    item["decision_answer"] = ", ".join(display_decision_impacts(mapped))
    item["decision_classification"] = decision_classification_text(mapped)
    return mapped


def display_decision_impacts(impacts: list[str] | tuple[str, ...] | str | None) -> list[str]:
    return unique([DECISION_DISPLAY_LABELS.get(value, value) for value in as_list(impacts)])


def decision_classification_text(impacts: list[str] | tuple[str, ...] | str | None) -> str:
    labels = display_decision_impacts(impacts)
    if not labels or labels == [LIMITED_IMPACT]:
        return LIMITED_IMPACT
    return ", ".join(labels)


def decision_matrix_text(impacts: list[str] | tuple[str, ...] | str | None) -> str:
    labels = set(display_decision_impacts(impacts))
    if LIMITED_IMPACT in labels and len(labels) == 1:
        return LIMITED_IMPACT
    buckets = [
        ("ë§¤ì¶œÂ·ë§ˆì§„Â·í˜„ê¸ˆíë¦„", "í•´ë‹¹" if "ë§¤ì¶œÂ·ë§ˆì§„Â·í˜„ê¸ˆíë¦„" in labels else "í•´ë‹¹ ì—†ìŒ"),
        ("ë°¸ë¥˜ì—ì´ì…˜/í• ì¸ìœ¨", "í•´ë‹¹" if "ë°¸ë¥˜ì—ì´ì…˜/í• ì¸ìœ¨" in labels else "í•´ë‹¹ ì—†ìŒ"),
        ("ìˆ˜ê¸‰", "í•´ë‹¹" if "ìˆ˜ê¸‰" in labels else "í•´ë‹¹ ì—†ìŒ"),
        ("ì‹œê°„í‘œ", "í•´ë‹¹" if "ì‹œê°„í‘œ" in labels else "í•´ë‹¹ ì—†ìŒ"),
    ]
    return " | ".join(f"{name}: {status}" for name, status in buckets)


def infer_korea_value_chain(item: dict, text: str = "") -> list[str]:
    existing = unique(as_list(item.get("korea_value_chain")))
    if existing:
        item["korea_value_chain"] = existing
        return existing

    combined = " ".join([text, " ".join(as_list(item.get("sectors"))), " ".join(as_list(item.get("paths")))]).lower()
    chains: list[str] = []

    def add(values: list[str]) -> None:
        for value in values:
            if value not in chains:
                chains.append(value)

    if has_any(combined, ["transformer", "ë³€ì••ê¸°", "power grid", "ì „ë ¥ë§", "transmission", "data center", "ë°ì´í„°ì„¼í„°"]):
        add(["ì „ë ¥ê¸°ê¸°/ë³€ì••ê¸°", "ì „ì„ /ì†¡ì „ë§", "ë°ì´í„°ì„¼í„° ì „ë ¥ ì¸í”„ë¼"])
    if has_any(combined, ["inverter", "solar", "íƒœì–‘ê´‘", "ì „ë ¥ë³€í™˜", "ess", "pcs"]):
        add(["íƒœì–‘ê´‘ ì¸ë²„í„°/ì „ë ¥ë³€í™˜ìž¥ì¹˜", "ESS/PCS", "ì „ë ¥ë§ ë³´ì•ˆ"])
    if has_any(combined, ["robot", "robotics", "ë¡œë´‡", "ìŠ¤ë§ˆíŠ¸íŒ©í† ë¦¬", "ê°ì†ê¸°", "automation", "fa"]):
        add(["ë¡œë´‡/ìŠ¤ë§ˆíŠ¸íŒ©í† ë¦¬", "ê°ì†ê¸°/FA", "ì‚°ì—…ìžë™í™”"])
    if has_any(combined, ["fertilizer", "phosphate", "agriculture", "farm", "biofuel", "ë¹„ë£Œ", "ì¸ì‚°", "ë†ì—…", "ë°”ì´ì˜¤ì—°ë£Œ", "ì‹ëŸ‰"]):
        add(["ë¹„ë£Œ/ë†í™”í•™", "ê³¡ë¬¼Â·ë†ì—… ì›ê°€", "ìŒì‹ë£Œ ì›ê°€ ë¯¼ê°ì£¼"])
    if has_any(combined, ["steel", "ì² ê°•", "quota", "safeguard", "ê°•ê´€"]):
        add(["ì² ê°•/ê°•ê´€", "EUÂ·ë¯¸êµ­í–¥ ìˆ˜ì¶œì£¼", "ìžë™ì°¨ê°•íŒ/ì¡°ì„ í›„íŒ"])
    if has_any(combined, ["semiconductor", "chips", "hbm", "ë°˜ë„ì²´", "ai chip"]):
        add(["ë°˜ë„ì²´/HBM", "ìž¥ë¹„Â·ì†Œìž¬", "AI ì„œë²„ ë°¸ë¥˜ì²´ì¸"])
    if has_any(combined, ["nuclear", "reactor", "smr", "uranium", "ì›ì „", "ìš°ë¼ëŠ„", "ap1000"]):
        add(["ì›ì „/SMR", "ì›ì „ ê¸°ìžìž¬", "ìš°ë¼ëŠ„/í•µì—°ë£Œ", "ì „ë ¥ê¸°ê¸°"])
    if has_any(combined, ["telecom", "fcc", "broadband", "satellite", "spectrum", "í†µì‹ ", "ìœ„ì„±", "ì£¼íŒŒìˆ˜"]):
        add(["í†µì‹ ìž¥ë¹„", "ìœ„ì„±í†µì‹ ", "ë„¤íŠ¸ì›Œí¬ ìž¥ë¹„"])
    if has_any(combined, ["stablecoin", "ìŠ¤í…Œì´ë¸”ì½”ì¸", "ê²°ì œ", "í•€í…Œí¬", "ì€í–‰"]):
        add(["ì€í–‰/í•€í…Œí¬", "ê²°ì œ ì¸í”„ë¼", "ê°€ìƒìžì‚°ê±°ëž˜ì†Œ"])
    if has_any(combined, ["defense", "missile", "ë°©ì‚°", "ìœ ë„ë¬´ê¸°", "ìž¥ê°‘ì°¨", "ë ˆì´ë”", "k9", "ì²œë¬´", "k2"]):
        add(["K-ë°©ì‚°", "ìœ ë„ë¬´ê¸°/íƒ„ì•½", "í•­ê³µÂ·ìž¥ê°‘ì°¨", "ë ˆì´ë”/ì „ìžì „"])
    if has_any(combined, ["tariff", "customs", "duty", "ê´€ì„¸", "í†µê´€", "ìˆ˜ì¶œì£¼"]) and not has_any(combined, ["fertilizer", "phosphate", "ë¹„ë£Œ", "ì¸ì‚°"]):
        add(["ê´€ì„¸ ë¯¼ê° ìˆ˜ì¶œì£¼", "ì†Œë¹„ìž¬Â·ì‚°ì—…ìž¬", "ë¬¼ë¥˜/ê³µê¸‰ë§"])

    if not chains:
        chains = ["ì§ì ‘ ì—°ê²° ì—…ì¢… í™•ì¸ í•„ìš”"]
    item["korea_value_chain"] = chains
    return chains


def has_korean(value: str) -> bool:
    return bool(re.search(r"[ê°€-íž£]", value or ""))


def infer_korean_title(item: dict, text: str = "") -> str:
    existing = str(item.get("title_ko") or "").strip()
    if existing:
        return existing
    title = str(item.get("title") or "").strip()
    low = " ".join([text, title]).lower()

    if has_korean(title):
        korean = title
    elif has_any(low, ["quantum innovation", "next frontier of quantum"]):
        korean = "ë°±ì•…ê´€, ì–‘ìžê¸°ìˆ  í˜ì‹ Â·êµ­ê°€ì•ˆë³´ í–‰ì •ëª…ë ¹ ë°œí‘œ"
    elif has_any(low, ["advanced cryptographic attacks", "cryptographic attack"]):
        korean = "ë°±ì•…ê´€, ì²¨ë‹¨ ì•”í˜¸ê³µê²© ëŒ€ì‘ í–‰ì •ëª…ë ¹ ë°œí‘œ"
    elif has_any(low, ["advanced artificial intelligence innovation", "ai innovation and security"]):
        korean = "ë°±ì•…ê´€, ì²¨ë‹¨ AI í˜ì‹ Â·ë³´ì•ˆ í–‰ì •ëª…ë ¹ ë°œí‘œ"
    elif has_any(low, ["commercial aircraft", "jet engines", "aircraft and engine parts"]):
        korean = "ë¯¸êµ­, ìƒì—…ìš© í•­ê³µê¸°Â·ì—”ì§„ ìˆ˜ìž… ì¡°ì • í¬ê³ ë¬¸ ë°œí‘œ"
    elif has_any(low, ["freedom to fix", "right to repair"]):
        korean = "ë°±ì•…ê´€, ìˆ˜ë¦¬ê¶Œ í™•ëŒ€Â·ìƒí™œë¹„ ì ˆê° ì •ì±… ë°œí‘œ"
    elif has_any(low, ["grid infrastructure, equipment, and supply chain capacity"]):
        korean = "ë°±ì•…ê´€, ì „ë ¥ë§Â·ì „ë ¥ê¸°ê¸° ê³µê¸‰ë§ êµ­ë°©ë¬¼ìžìƒì‚°ë²• ì¡°ì¹˜ ë°œí‘œ"
    elif has_any(low, ["large-scale energy", "energy-related infrastructure"]):
        korean = "ë°±ì•…ê´€, ëŒ€ê·œëª¨ ì—ë„ˆì§€ ì¸í”„ë¼ êµ­ë°©ë¬¼ìžìƒì‚°ë²• ì¡°ì¹˜ ë°œí‘œ"
    elif has_any(low, ["national security presidential memorandum", "nspm-"]):
        korean = "ë°±ì•…ê´€, êµ­ê°€ì•ˆë³´ ëŒ€í†µë ¹ê°ì„œ ë°œí‘œ"
    elif has_any(low, ["restoring integrity to america's financial system"]):
        korean = "ë°±ì•…ê´€, ë¯¸êµ­ ê¸ˆìœµì‹œìŠ¤í…œ ê±´ì „ì„± ê°•í™” ì •ì±… ë°œí‘œ"
    elif has_any(low, ["financial technology innovation", "fintech innovation"]):
        korean = "ë°±ì•…ê´€, ê¸ˆìœµê¸°ìˆ  í˜ì‹  ê·œì œì²´ê³„ ì •ì±… ë°œí‘œ"
    elif has_any(low, ["commercial fishing in the pacific"]):
        korean = "ë°±ì•…ê´€, íƒœí‰ì–‘ ìƒì—…ì–´ì—… ì´‰ì§„ ì •ì±… ë°œí‘œ"
    elif has_any(low, ["federal lands"]):
        korean = "ë°±ì•…ê´€, ì—°ë°©í† ì§€ ì ‘ê·¼ ì œí•œ ì™„í™” ì •ì±… ë°œí‘œ"
    elif has_any(low, ["resilient networks", "dirs", "disruptions to communications"]):
        korean = "FCC, ìž¬ë‚œ ì‹œ í†µì‹ ë§ ìž¥ì• ë³´ê³  ì‹œìŠ¤í…œ(DIRS) í˜„ëŒ€í™” ê·œì¹™ ê³µí‘œ"
    elif has_any(low, ["foreign energy inverter", "energy inverter", "solar inverter"]):
        korean = "ë¯¸êµ­ FCC, ì™¸êµ­ì‚° ì—ë„ˆì§€ ì¸ë²„í„° ìˆ˜ìž…ì œí•œ ì •ì±… ì‹ í˜¸"
    elif has_any(low, ["phosphate fertilizer", "duty-free importation"]):
        korean = "ë¯¸êÛNõÞÚ$z{-®éÜj×„$Òô’Ë+NÉÛ‚È‰Ž«ˆžÉØBÉ«ÈJÙ™^ÉÛŽÙZž¸¸Ž¸ºBâ"ÀÐ¢&–6VEö–ãÒ.ÊI«BâºûŽÊI«‹ÈŠ«yÎÊ	Î¸©B»	Ž»;RÉêÎº8ÎÊxºxÂÈ8‚Ù(Žºªœ+~È8‚«‹Éx\+~È8‚È¹ÎÙhžÉÛÎÉÛNº›BÈºNÊËiNÊ	^Éy»	ŽÉˆ¹
È‰‚ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢6÷VçFW#Ò.ËHŽÉXŒ+~«(Øj+~»;N¸øB¸ºŽ«8NÉÛNº›BÈºNÊ	ÂÊÉª’»)NÉÈN«Ëi^ÈhÎ¹
È‰‚ÉèŽ«:ÂÉˆŽÉ›‚¹ÛÎÉÛNÈJÈªN«É{NºjÎº›BËjž«*žÉØÊHNÉkN¹:Þ¸¸Ž¸ºBâ"ÀÐ¢f–ÇW&U÷6–væÃÒ.ËYÎÊ(R«yÎÊ	RÂÈ¹ÎÙhžÉÛÂÂ¸ÈÈ8«‹Éx\+~Ù(Žºª’Â¹ÛÎÉÛNÈJÈªBÊ	ÎÙYÎÉÛBÙ™^ÉÛŽ¹	ŽÊxÉX®ÉËÎº›BØXÎºxŽÈK»	ŽÉÙÉËÎºÂ¸Þ¸*ž¸¸Ž¸ºBâ"ÀÐ¢Ð¢VÆ–b—5öw&–7VÇGW&U÷7WÇ•÷öÆ–7’‡FW‡BÂ—FVÒ“ Ð¢WB€Ð¢—FVÒÀÐ¢–×÷'Fæ6SÒ.ÊI"ÀÐ¢–×7G3Õ².¸ø‚»(N¸©B¸ª^º
R"Â.È‰Ž«ˆ’"Â.È¹Î«NÙÂ%ÒÀÐ¢F‡3Õ².É¹«"Â.«;^«ˆžºyÒ"Â.Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.È¹Þ¹øœ+~¸hÞÉxRØŠÎÉè^»˜B%ÒÀÐ¢6V7F÷'3Õ².»˜Nº8Âþ¸hÞÙ™NÙY’"Â.«:ºËÂþ¸hÞÉxRÉ¹«"Â.ÉØÎÈ¹Þº8ÂÉ¹«"Â.»	NÉÛNÉŠNÉ{º8Â%ÒÀÐ¢öÆ–7•÷Æ–å÷7VÖÖ'“Ò.¸hÞÉx\+~»˜Nº8Ì+~»	NÉÛNÉŠNÉ{º8Â«Hº
‚Ê	^Ë^ÉØ¸hÞÉxRØŠÎÉè^»˜BÂ»˜Nº8Ì+~«:ºËÂ«;^«ˆ’ÂÉØÎÈ¹Þº8ÂÉ¹«ÂË™ÎÙ™Ž«+ÒÉ{º8ÂÉ¹º8ÂÈ‰ŽÉ©Nº[Â»	N«øÈ‰‚ÉèŽ¸©BÈ+Éx^»˜NÉª’»8È‰ŽÉè^¸¸Ž¸ºBâ"ÀÐ¢–çfW7FÖVçE÷f–WsÒ.ÉÛB¸›NÈªN«ÊIÉ©NÙYÎÊx¸©BÊ	^ËRÊ	Îºªž»;N¸ºB»˜Nº8Ì+~«:ºËÌ+~»	NÉÛNÉŠNÉ{º8ÂÉ¹«É˜«;^«ˆž¹ø’Â«{ŽºjÎ«:ÙYÎ«ZÒÉØÎÈ¹Þº8Ì+~¸hÞÙ™NÙY’»ŽºYŽË+NÉÛŽÉÙ‚ºxŽÊxB«Ê	^ÉØB»	N«ëŽ¸©NÊxÉy¸ºÎº
BÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢¶÷&VöÖ&¶WEö–×7CÒ.ÙYÎ«ZÞÉê^ÉyÈIÎ¸©B»˜Nº8Âþ¸hÞÙ™NÙY’Â«:ºËÂÉ¹«ÂÉØÎÈ¹Þº8ÂÉ¹«ºûÎ«	Ê;ÂÂ»	NÉÛNÉŠNÉ{º8ÂÉ¹º8Â»ŽºYŽË+NÉÛŽÉØB«HËÙZž¸¸Ž¸ºBâºûŽ«ZÒ¸+BÈ‰ŽÉè\+~¸hÞÉxRÊ	^Ë^ÉÛNº›B«ZÞ¸+BÊxÊ	È‰ŽÙ‰Î¸©B««*œ+~«;^«ˆžºyÒÉ{«+ÉÛBÙ™^ÉÛŽ¹
¹XÎºxÂÉÛŽÊ	^ÙZž¸¸Ž¸ºBâ"ÀÐ¢&–6VEö–ãÒ.¸*îÉØÇîÊI«Bâ¸hÞÉxRÊ	^Ë^ÉØØXÎºx‚»	ŽÉÙÉÛBÉ[ÞÙZÈ‰‚ÉèŽÊxºxÂÂ»˜Nº8Â««*œ+~«:ºËÂ««*œ+~È¹ÞÙ(‚É¹«É˜É{«+¹	Žº›BºxŽÊxBËiNÊ	^Éy»	ŽÉˆ¹
È‰‚ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢6÷VçFW#Ò.ºûŽ«ZÒÈ‰ŽÉè\+~¸hÞÉxRÊxÉ¹Ê	^Ë^ÉÛBÙYÎ«ZÒ«‹ÉxRºzNËiÎºÂ»	NºÂÉ{«+¹	Ž¸©B«(>ÉØÉXN¸¹ž¸¸Ž¸ºBâÙ(Žºª’ÂÈ‰ŽÉè^¹ø’ÂÊÉª’«‹«BÂ«ˆºÎ»(Â««*’ÊNÉÛBÉzÎ»h«Ù™^ÉÛŽ¸ûÎÉ[ÂÙZž¸¸Ž¸ºBâ"ÀÐ¢f–ÇW&U÷6–væÃÒ.»˜Nº8Ì+~«:ºËÂ««*’Â«ZÞ¸+BÉØÎÈ¹Þº8Âþ¸hÞÙ™NÙY’È‰Ž«ˆ’ÂÙYÎ«ZÒ«‹Éx^ÉÙ‚É¹«+~«;^«ˆžºyÒ¸[ŽËiÎÉÛB¸ùžÙhžÙYŽÊxÉX®ÉËÎº›B«HËÉêÎº8ÎºÎºxÂË)ŽºjÎÙZž¸¸Ž¸ºBâ"ÀÐ¢Ð¢VÆ–b†5öç’‡FW‡BÂ²'F&–fb"Â'6V7F–öâ3"Â&7W7Fö×2"Â&GWG’"Â.«HÈK‚"Â.Øk^«H%Ò“ Ð¢WB€Ð¢—FVÒÀÐ¢–×7G3Õ².¸ø‚»(N¸©B¸ª^º
R"Â.ÙZÉÛŽÉÊ‚"Â.È‰Ž«ˆ’"Â.È¹Î«NÙÂ%ÒÀÐ¢F‡3Õ².ÉÛNÉÛR"Â.«;^«ˆžºyÒ"Â.Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.È‰Ž«ˆ’%ÒÀÐ¢6V7F÷'3Õ².«HÈK‚þÈ‰ŽËiÎÊ;Â"Â.ÈhÎ»˜NÉêÌ+~È+Éx^ÉêÂ"Â.ºËÎºY‚þ«;^«ˆžºyÒ%ÒÀÐ¢öÆ–7•÷Æ–å÷7VÖÖ'“Ò.«HÈKŒ+~Øk^«HÊyÙh’»8Ù™N¸©BÈ‰ŽÉèRÉ¹«Â««*žÊN«Â«;^«ˆžºyÒÉêÎ»Ë™‚ÂÈ‰ŽËiÎÊ;ÂºxŽÊxNÉØB»	N«øÈ‰‚ÉèŽ¸©BÊ	^ËR»8È‰ŽÉè^¸¸Ž¸ºBâ"ÀÐ¢–çfW7FÖVçE÷f–WsÒ.Ù(Žºªœ+~«ZÞ«+~ÈKŽÉÊŒ+~È¹ÎÙhžÉÛÎÉÛBÙ™^ÉÛŽ¹	Žº›BÙ[N¸»’»ŽºYŽË+NÉÛŽÉÙ‚ºzNËiÎËIÞÉÛNÉÛ^ºZ«;ÂÊ;ÎºË‚ÉÛNÊB«‹¸È«»	NºÂ»	N¸	Þ¸¸Ž¸ºBâ"ÀÐ¢¶÷&VöÖ&¶WEö–×7CÒ.ÙYÎ«ZÞÉê^ÉyÈIÎ¸©BºûŽ«ZÞÙjRÈ‰ŽËiÎÊ;ÂÂÊI«ZÒ¸ÈË+B«;^«ˆžºyÒÂ«HÈK‚ºûÎ«	ÈhÎ»˜NÉêÌ+~È+Éx^ÉêÂÂºËÎºYŽ»˜BºûÎ«	Éx^Ê(^ÉØBÈJ»8BÙ™^ÉÛŽÙZž¸¸Ž¸ºBâ"ÀÐ¢&–6VEö–ãÒ.¸*îÉØÇîÊI«Bâ¸ºŽÈ‰Â»	ÎÉkŽÉØ»šŽºjÂÈhÎº›ŽÙYŽÊxºxÂ«H»;L+~ÙhžÊ	^º¨^ºœ+uU5E"ºËŽÈIÎºÂÙ™^Ê	^¹	Žº›BÉêÎØøž«ÉzÎÊx«ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢6÷VçFW#Ò.Ù(ŽºªžËÙN¹9ÂÂÉˆŽÉ›‚ÊÙZÒÂÉÊÉˆ‚«‹«NÉÛBÙ™^ÉÛŽ¹	ŽÊxÉX®ÉËÎº›B«	Î»8BÊ(^ºª’ÉˆÙjRËiNÊ	^ÉØ«;Î¸ÈÙ[NÈIÞÉÛÂÈ‰‚ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢f–ÇW&U÷6–væÃÒ.«;^È¹ÒÈKŽÉÊŒ+~Ù(Žºªœ+~È¹ÎÙhžÉÛÎÉÛB¸)ŽÉŠNÊxÉX®«¸)‚«‹ÉxR««*žÊN«þÈ‰ŽÊ;Â»8Ù™N«Ù™^ÉÛŽ¹	ŽÊxÉX®ÉËÎº›BÈºNØÊŽÉè^¸¸Ž¸ºBâ"ÀÐ¢Ð¢VÆ–b†5öç’‡FW‡BÂ²&çV6ÆV""Â'&V7F÷""Â'W&æ—VÒ"Â&"Â'vW7F–æv†÷W6R"Â&FF6VçFW""Â&ç&2"Â.É¹ÊB%Ò“ Ð¢WB€Ð¢—FVÒÀÐ¢–×7G3Õ².È¹Î«NÙÂ"Â.¸ø‚»(N¸©B¸ª^º
R"Â.È‰Ž«ˆ’%ÒÀÐ¢F‡3Õ².É¹ÊBÊ	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â$’¸ÛÉÛNØKÈKÎØKÊNº
^È‰ŽÉ©B"Â.É¹ÊB»ŽºYŽË+NÉÛ‚"Â.È‰Ž«ˆ’%ÒÀÐ¢6V7F÷'3Õ².É¹ÊBþÊNº
^«‹«‹"Â.ÊNº
^ºyÒþ¸ÛÉÛNØKÈKÎØK"Â.É«¹ÛÎ¸¨B"Â%4Õ"þ¸ÈÙ‰^É¹ÊB«‹ÉéÉêÂ%ÒÀÐ¢öÆ–7•÷Æ–å÷7VÖÖ'“Ò.É¹ÊBÉÛŽÙxŽ«ÂÙ[^É{º8ÂÂÈº«yÂÉ¹ÊBÂ’¸ÛÉÛNØKÈKÎØKÊNº
^È‰ŽÉ©N«Ê	^ËRÈ¹Î«NÙÎºÂ«;^È¹ÞÙ™N¹	Ž¸©NÊx»;N¸©BÈ*ÎÉXŽÉè^¸¸Ž¸ºBâ"ÀÐ¢–çfW7FÖVçE÷f–WsÒ.Ù™^Ê	RºzNËiÎÉØÉXN¸¸ŽÊxºxÂ¸ÈÙ‰R4UŽÉ˜ÉÛŽÙxŽ«È¹Î«NÉÛBÉYî¸»ž«*ŽÊxº›BÉ¹ÊN«‹«‹+~ÊNº
^«‹«‹+~É«¹ÛÎ¸¨BË+NÉÛŽÉÙ‚È‰ŽÊ;Â«‹¸È«ËºNÊy¸¸Ž¸ºBâ"ÀÐ¢¶÷&VöÖ&¶WEö–×7CÒ.ÙYÎ«ZÞÉê^ÉyÈIÎ¸©BÉ¹ÊB«‹ÉéÉêÂÂÊNº
^«‹«‹ÂÈjÊNºyÒÂ¹È+Éy¸HŽ»˜ÎºjÎØ»+~ÙYÎÊN«‹ÈŠ+~ÙYÎÊDµ2¹;»ŽºYŽË+NÉÛ‚È‰Ž«ˆžÉØBÙ™^ÉÛŽÙZž¸¸Ž¸ºBâ"ÀÐ¢&–6VEö–ãÒ.ÊI«BâÉ¹ÊBØXÎºxŽ¸©BÈJ»	ŽÉˆÉÛB«	^ÙYŽÊxºxÂÊ	^Ë\+~¸ÈËiÌ+tå$2ÉÛÎÊ	^ÉÛB¸ùžÈ¹ÎÉyÙ™^ÉÛŽ¹	Žº›BËiN«ÉêÎØøž«ÉzÎÊx«ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢6÷VçFW#Ò.»hÊxÂËYÎÊ(R«8NÉ[ÒÂÉˆŽÈ++~¸ÈËiÂÊ«BÂå$2ÉÛŽÙxŽ«ÂË
ž«;RÉÛÎÊ	^ÉÛBÙ™^Ê	^¹	ŽÊxÉX®ÉËÎº›BÈºNÊ	ÂºzNËiÂÉÛŽÈ¹Þ«˜ÎÊxÈ¹ÎË
Ž«ØÞ¸¸Ž¸ºBâ"ÀÐ¢f–ÇW&U÷6–væÃÒ.¸ÈËiÂÊ«BÂ»hÊxÂå$2ÉÛÎÊ	RÂÉ¹ÊN«‹«‹»	ÎÊ;Î«Ù™^ÉÛŽ¹	ŽÊxÉX®ÉËÎº›BÊ	^ËR«‹¸ÈÉyÈIÂ¸Þ¸*ž¸¸Ž¸ºBâ"ÀÐ¢Ð¢VÆ–b†5öç’‡FW‡BÂ²&fW&2"Â'÷vW"w&–B"Â'G&ç6Ö—76–öâ"Â&–çFW&6öææV7F–öâ"Â&VÆV7G&–2w&–B"Â.ÊNº
^ºyÒ%Ò“ Ð¢WB€Ð¢—FVÒÀÐ¢–×7G3Õ².È¹Î«NÙÂ"Â.¸ø‚»(N¸©B¸ª^º
R"Â.È‰Ž«ˆ’%ÒÀÐ¢F‡3Õ².ÊNº
^ºyÒØŠÎÉé"Â.Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.»ŽºYŽË+NÉÛ‚"Â.È‰Ž«ˆ’%ÒÀÐ¢6V7F÷'3Õ².ÊNº
^ºyÒþÊNº
^«‹«‹"Â.ÊNÈJþ»8ÉY^«‹"Â.¸ÛÉÛNØKÈKÎØKÊNº
RÉÛŽÙHN¹ÛÂ%ÒÀÐ¢öÆ–7•÷Æ–å÷7VÖÖ'“Ò.ÊNº
^ºyÜ+~ÈjÊL+~«8NØk^É{«8BÊ	^Ë^ÉØ¸ÛÉÛNØKÈKÎØKÉ˜ÊNº
RÉÛŽÙHN¹ÛÂ4U‚È¹Î«NÙÎº[Â»	N«øÈ‰‚ÉèŽ¸©BÈ*ÎÉXŽÉè^¸¸Ž¸ºBâ"ÀÐ¢–çfW7FÖVçE÷f–WsÒ.«8NØk^É{«8B»9ºª’É˜NÙ™N¸)‚ØŠÎÉéÉÛŽÈKÎØ»»ˆÎ«Ù™^ÉÛŽ¹	Žº›B»8ÉY^«‹+~ÊNÈJ+~ÊNº
^«‹«‹È‰ŽÊ;Â«‹¸È«ËºNÊy¸¸Ž¸ºBâ"ÀÐ¢¶÷&VöÖ&¶WEö–×7CÒ.ÙYÎ«ZÞÉê^ÉyÈIÎ¸©BÊNÈJÂ»8ÉY^«‹ÂÊNº
^«‹«‹Â¸ÛÉÛNØKÈKÎØKÊNº
RÉÛŽÙHN¹ÛÂ«Hº
‚Ê(^ºªžÉÙ‚È‰Ž«ˆž«;ÂÈ‰ŽÊ;Â«;^È¹Îº[ÂÙ™^ÉÛŽÙZž¸¸Ž¸ºBâ"ÀÐ¢&–6VEö–ãÒ.ÊI«BâÊNº
^ºyÒØXÎºxŽ«ÉÛNºû‚«	^ÙYŽº›BÈ¹ÎÙhžÉÛÌ+~ÉˆŽÈ++~»	ÎÊ;ÂÉxnÉÛN¸©BËiN«»	ŽÉÙÉÛBÊ	ÎÙYÎ¹
ž¸¸Ž¸ºBâ"ÀÐ¢6÷VçFW#Ò.«yÎË™’Ê	ÎÉXŽÉÛN¸)‚ÉÙŽ«*ÎÈ‰ŽºB¸ºŽ«8N¸©BÈºNÊ	Â»	ÎÊ;ÎÉ˜«ºjÎ«ÉèŽÉØBÈ‰‚ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢f–ÇW&U÷6–væÃÒ$dU$2ôDôRÙ¸NÈhÒÉÛÎÊ	RÂÉÊØ»ŽºjÎØ»4U‚ÂÉê^»˜B»	ÎÊ;Î«ÉxnÉËÎº›BØXÎºxŽÈK»	ŽÉÙÉy«{ŽËšž¸¸Ž¸ºBâ"ÀÐ¢Ð¢VÆ–b†5öç’‡FW‡BÂ²&fF"Â&6Æ–æ–6Â"Â&G'Vr"Â&6ö×ÆWFR&W7öç6RÆWGFW""Â&&÷fÂ"Â&7&Â"Â.ÉèNÈ8"Â.ÙxŽ«%Ò“ Ð¢WB€Ð¢—FVÒÀÐ¢–×7G3Õ².¸ø‚»(N¸©B¸ª^º
R"Â.È¹Î«NÙÂ"Â.È‰Ž«ˆ’%ÒÀÐ¢F‡3Õ².ÉèNÈ8þÙxŽ«È¹Î«NÙÂ"Â.ÉÛNÉÛR"Â.È‰Ž«ˆ’%ÒÀÐ¢6V7F÷'3Õ².»	NÉÛNÉŠBôdD"Â.Ê	ÎÉ[Ò"Â.ÙzÎÈªNËÈÉkB%ÒÀÐ¢öÆ–7•÷Æ–å÷7VÖÖ'“Ò$dDÈ«žÉÛŒ+~«ÊŒ+~ÉèNÈ8«Hº
‚«+Ê	^ÉØ«	Î»	ÂÈ¹Î«NÙÎÉ˜È8Éx^Ù™B«¸ª^ÈKÉØBÊxÊ	»	N«ëŽ¸©B»	NÉÛNÉŠBÉÛN»*NØ«ŽÉè^¸¸Ž¸ºBâ"ÀÐ¢–çfW7FÖVçE÷f–WsÒ.È«žÉÛŒ+t5$Ì+~ÉèNÈ8«+«;Î¸©BºzNËiÂ«	ÎÈ¹ÂÈ¹ÎÊ	ÂËiN«»˜NÉª’Â«‹ÈŠÉÛNÊBÙ‰È8º
^ÉØB»	N«øÈ‰‚ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢¶÷&VöÖ&¶WEö–×7CÒ.ÙYÎ«ZÞÉê^ÉyÈIÎ¸©BÙ[N¸»’ØÈÎÉÛNÙHN¹ÛÎÉÛ‚»;NÉÊÈ*ÂÂ4DÔòÂ»	NÉÛNÉŠNØXÒÈKžØKÈ‰Ž«ˆžÉØBÙ™^ÉÛŽÙYŽ¹	‚É¹ºË‚ÊÉÙÊiÜ+~¸ÈÈ8«‹ÉxR«{Î««ÙXNÉ©NÙZž¸¸Ž¸ºBâ"ÀÐ¢&–6VEö–ãÒ.ÊI«Gî¸i.ÉØÂâ»	NÉÛNÉŠBÉÛN»*NØ«Ž¸©B«‹¸È«ÈJ»	ŽÉˆ¹	Ž«‹ÈšÎÉ¸Â«+«;ÎÉ˜È¹ÎÉêR«‹¸ÈÉÙ‚Ë
ŽÉÛN«ÊIÉ©NÙZž¸¸Ž¸ºBâ"ÀÐ¢6÷VçFW#Ò.»h»hBÈ«žÉÛ‚Â¹ÛÎ»*‚Ê	ÎÙYÂÂËiN«ÉèNÈ8É©N«ZÂÂÉXŽÊNÈKÉÛNÈ¨Ž«ÉèŽÉËÎº›B†VFÆ–æ^»;N¸ºBÉˆÙj^ÉÛBÉ[ÞÙZÈ‰‚ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢f–ÇW&U÷6–væÃÒ.¹ÛÎ»*Œ+~È¹ÎÉê^«yÎºªŒ+~È8Éx^Ù™BØÈÎØ«Ž¸HŒ+~Ù¸NÈhÒ»˜NÉªžÉÛBÙ™^ÉÛŽ¹	ŽÊxÉX®ÉËÎº›BÊ;Î«ÉêÎº8Î«É[ÞÙ[NÊy¸¸Ž¸ºBâ"ÀÐ¢Ð¢VÆ–b†5öç’‡FW‡BÂ²'&ö&÷B"Â'&ö&÷F–72"Â&6öÖÖW&6R"Â&6†–æ"Â&6†–æW6R"Â'&ö&÷F–72F&–fg2%Ò“ Ð¢WB€Ð¢—FVÒÀÐ¢–×7G3Õ².È¹Î«NÙÂ"Â.È‰Ž«ˆ’"Â.¸ø‚»(N¸©B¸ª^º
R%ÒÀÐ¢F‡3Õ².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.ÊI«ZÒ¸ÈË+B«;^«ˆžºyÒ"Â.«HÈK‚þÈ‰ŽÉè^Ê	ÎÙYÂ"Â.È‰Ž«ˆ’%ÒÀÐ¢6V7F÷'3Õ².ºÎ»HrþÈªNºxŽØ«ŽØÊžØjºjÂ"Â.«	ÈhÞ«‹ôd"Â.È+Éx^Éé¸ùžÙ™B"Â.«HÈK‚þÈ‰ŽËiÎÊ;Â%ÒÀÐ¢öÆ–7•÷Æ–å÷7VÖÖ'“Ò.ºûŽ«ZÞÉÛBÊI«ZÞÈ+ºÎ»HrÈ‰ŽÉè\+~»;NÊ«ˆŒ+~«ZÞ«ÉXŽ»;BºjÎÈªNØÎº[Â«(ØjÙYÎ¸ºN¸©BÈºÙ‹Ž¸©BºÎ»HrÈ+Éx^ÉØBºûŽÊI«‹ÈŠØÊŽ«hÎÉÙ‚¸ºNÉØÂÊNÈJÉËÎºÂ»;N¸©BÉêÎº8ÎÉè^¸¸Ž¸ºBâ"ÀÐ¢–çfW7FÖVçE÷f–WsÒ.«HÈKŒ+~È‰ŽÉè^Ê	ÎÙYÌ+~ºûŽ«ZÒ¸+BÊ	ÎÊÊxÉ¹ÉËÎºÂÉÛNÉkNÊxº›BÊI«ZÒ¸ÈË+B»ŽºYŽË+NÉÛŽ«;ÂÉé¸ùžÙ™BÉê^»˜BÈ‰ŽÉ©B«‹¸È«ËºNÊx‚È‰‚ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢¶÷&VöÖ&¶WEö–×7CÒ.ÙYÎ«ZÞÉê^ÉyÈIÎ¸©BºÎ»HrÂ«	ÈhÞ«‹ÂÈªNºxŽØ«ŽØÊžØjºjÂÂdÉê^»˜BÂÊI«ZÒ¸ÈË+B«;^«ˆžºyÒØXÎºx‚È‰Ž«ˆžÉØB»;N¹	‚«;^È¹ÒÈ8ºËN»h»	ÎÙÂÊNÉÛNº›BÉˆŽ»˜NºÂ»IÉ[ÂÙZž¸¸Ž¸ºBâ"ÀÐ¢&–6VEö–ãÒ.¸*îÉØÇîÊI«Bâ»;N¸øBÊxÙ¸BØXÎºx‚È‰Ž«ˆžÉØ»šº[NÊxºxÂ«;^È¹ÒÊË™‚ÊNÉy¸©B¹	Ž¸øÎºkÂÉÈNÙyŽÉÛBØÞ¸¸Ž¸ºBâ"ÀÐ¢6÷VçFW#Ò.ÉÛ^º¨RÈhÎÈ¹ÞØkR»;N¸øB¸ºŽ«8N¹ÛÂÙ(Žºª’Â«HÈKŽÉÊ‚ÂÈ¹ÎÙhžÉÛÂÂ¸ÈËiÂÊ«BÂ¸ÈÈ8«‹Éx^ÉØºûŽÙ™^Ê	^Éè^¸¸Ž¸ºBâ"ÀÐ¢f–ÇW&U÷6–væÃÒ.È8ºËN»h«;^È¹ÒÊÈ*Ì+~«HÈKŒ+tõ42¸ÈËiÂÊ«NÉÛB¸)ŽÉŠNÊxÉX®ÉËÎº›B¸ºŽ«‹ØXÎºxŽÈK»	ŽÉÙÉËÎºÂ¸Þ¸*ž¸¸Ž¸ºBâ"ÀÐ¢Ð¢VÆ–b†5öç’‡FW‡BÂ²'7V7G'VÒ"Â'6FVÆÆ—FR"Â'76R'W&VR"Â'v—&VÆW72"Â&'&öF&æB"Â&f62%Ò“ Ð¢WB€Ð¢—FVÒÀÐ¢–×7G3Õ².È¹Î«NÙÂ"Â.È‰Ž«ˆ’%ÒÀÐ¢F‡3Õ².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.Ê;ÎØÈÎÈ‰‚þØk^Èº«yÎÊ	Â"Â.È‰Ž«ˆ’%ÒÀÐ¢6V7F÷'3Õ².Øk^Èºôd42þÉÈNÈK"Â.Øk^ÈºÉê^»˜B"Â.ÉÈNÈKØk^Èº%ÒÀÐ¢öÆ–7•÷Æ–å÷7VÖÖ'“Ò$d42Øk^Èº+~Ê;ÎØÈÎÈ‰Œ+~ÉÈNÈK«yÎÊ	ÂºËŽÈIÎ¸©BØk^ÈºÉÛŽÙHN¹ÛÂÊ	^ËRÈ¹Î«NÙÎº[Â»	N«øÈ‰‚ÉèŽÊxºxÂÂºËŽÈIÂÈK«*žÉy¹K¹ÛÂÈ¹ÎÉêRÉˆÙjRË
ŽÉÛN«ØÞ¸¸Ž¸ºBâ"ÀÐ¢–çfW7FÖVçE÷f–WsÒ.Ê;ÎØÈÎÈ‰‚«+ÞºzBÂÉÈNÈKÉÛŽÙxŽ«ÂÉê^»˜BÉÛŽÊiÒÂ»;NÉX‚ÉÙŽºËNË)Ž¹ûÂ4UŽ¸)‚Ê¸ºÎºÂÉÛNÉkNÊx‚¹XÎºxÂÈºNÊÉêÎº8Î«¹
ž¸¸Ž¸ºBâ"ÀÐ¢¶÷&VöÖ&¶WEö–×7CÒ.ÙYÎ«ZÞÉê^ÉyÈIÎ¸©BØk^ÈºÉê^»˜L+~ÉÈNÈKØk^Èº+~¸JNØ«ŽÉ¸ÎØÂÉê^»˜BØXÎºxŽº[ÂÙ™^ÉÛŽÙYŽ¹	‚ÂÙhžÊ	R«;^Êx+~Ù¨ÎÉÙ‚«;^«:È‰ŽÊHÉÛNº›BÊxÊ	ÉˆÙj^ÉØÊ	ÎÙYÎÊÉè^¸¸Ž¸ºBâ"ÀÐ¢&–6VEö–ãÒ.¸*îÉØÇîÊI«Bâ«ZÎË+BÉÛŽÙxŽ«+~«+ÞºzL+~»;NÉX‚ÉÙŽºËN«ÉxnÉËÎº›B««*’»	ŽÉÙÉØÉ[ÞÙZž¸¸Ž¸ºBâ"ÀÐ¢6÷VçFW#Ò$d42ºËŽÈIÎ¹ÛÎ¸øBÙ¨ÎÉÙ‚«;^ÊxÂ¸ÛÉÛNØKÈ‰ŽÊyÂ»;N«:ÉiÈ¹ÒÊ	^»˜N¸©B«:Ëjž«*’ÉêÎº8Î«ÉXN¸¹È‰‚ÉèŽÈ«^¸¸Ž¸ºBâ"ÀÐ¢f–ÇW&U÷6–væÃÒ.Ê;ÎØÈÎÈ‰‚«+ÞºzBÂÉê^»˜BÉÙŽºËNÙ™BÂÉÛŽÙxŽ«ÂØk^ÈºÈ*Â4U‚»8Ù™N«ÉxnÉËÎº›BÊ	ÎÉ›ŽÙ[NÉ[ÂÙZž¸¸Ž¸ºBâ"ÀÐ¢Ð Ð¢FW‡BÒFW‡Eöf÷"†—FVÒÐ¢–æfW%ö¶÷&V÷fÇVUö6†–â†—FVÒÂFW‡BÐ¢æ÷&ÖÆ—¦UöFV6—6–öåö–×7G2†—FVÒÂFW‡BÐ¢–æfW%ö¶÷&Vå÷F—FÆR†—FVÒÂFW‡BÐ¢—FVÕ²&–×7G2%ÒÒVæ—VR†5öÆ—7B†—FVÒævWB‚&–×7G2"’’÷"´Ä”Ô•DTEô”Õ5EÒÐ¢—FVÕ²'F‡2%ÒÒVæ—VR†5öÆ—7B†—FVÒævWB‚'F‡2"’’÷"².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚%ÒÐ¢—FVÕ²'6V7F÷'2%ÒÒVæ—VR†5öÆ—7B†—FVÒævWB‚'6V7F÷'2"’’÷"².Ê	^ËRþ«yÎÊ	ÂÉÛÎ»	‚%ÒÐ¢&WGW&â—FVÐÐ Ð Ð¦FVb6Æ—÷FW‡B‡fÇVS¢ö&¦V7BÂÆ–Ö—C¢–çB’Óâ7G# Ð¢FW‡BÒ&Rç7V"‡"%Ç2²"Â""Â7G"‡fÇVR÷"""’’ç7G&—‚Ð¢–bÆVâ‡FW‡B’ÃÒÆ–Ö—C Ð¢&WGW&âFW‡@Ð¢&WGW&âFW‡E³¢Ö‚ƒÂÆ–Ö—BÒ•Òç'7G&—‚’².(
b Ð Ð Ð¦FVb¦ö–åöÆ–Ö—FVB‡fÇVW3¢ö&¦V7BÂ¢ÂÖ…ö—FV×3¢–çBÒRÂ6†%öÆ–Ö—C¢–çBÒCÂfÆÆ&6³¢7G"Ò.Ù™^ÉÛ‚ÙXNÉ©B"’Óâ7G# Ð¢—FV×2Ò¶6Æ—÷FW‡B‡fÇVRÂC’f÷"fÇVR–â5öÆ—7B‡fÇVW2’–b7G"‡fÇVR÷"""’ç7G&—‚•ÐÐ¢–bæ÷B—FV×3 Ð¢—FV×2Ò¶fÆÆ&6µÐÐ¢6†÷vâÒ—FV×5³¦Ö…ö—FV×5ÐÐ¢–bÆVâ†—FV×2’âÖ…ö—FV×3 Ð¢6†÷vâæVæB†b.É›‚¶ÆVâ†—FV×2’ÒÖ…ö—FV×7Þ«	Â"Ð¢&WGW&â6Æ—÷FW‡B‚"Â"æ¦ö–â‡6†÷vâ’Â6†%öÆ–Ö—BÐ Ð Ð¦FVbW‡ÆæF–öåöÆ–æW2†—FVÓ¢F–7B’ÓâÆ—7E·7G%Ó Ð¢Vç7W&UöW‡Æ–æVB†—FVÒÐ¢–×7EöÆ&VÇ2ÒF—7Æ•öFV6—6–öåö–×7G2†—FVÒævWB‚&–×7G2"’Ð¢&WGW&â°Ð¢b"ÒÙ[^ÈºÂ¸+NÉª“¢¶6Æ—÷FW‡B†—FVÒævWB‚wöÆ–7•÷Æ–å÷7VÖÖ'’r’÷"~Ê	^ËRÈKŽ»h¸+NÉª’Ù™^ÉÛ‚ÙXNÉ©BrÂƒ—Ò"ÀÐ¢b"ÒØŠÎÉé«HÊ	¢¶6Æ—÷FW‡B†—FVÒævWB‚v–çfW7FÖVçE÷f–Wrr’÷"~ÈºNÊ+~ÙZÉÛŽÉÊŒ+~È‰Ž«ˆœ+~È¹Î«NÙÂ»8Ù™BÉzÎ»hÙ™^ÉÛ‚ÙXNÉ©BrÂƒ—Ò"ÀÐ¢b"ÒÙYÎ«ZÞÉêRÉˆÙjS¢¶6Æ—÷FW‡B†—FVÒævWB‚v¶÷&VöÖ&¶WEö–×7Br’÷"~ÙYÎ«ZÞÉêRÊxÊ	ÉˆÙjRÙ™^ÉÛ‚ÙXNÉ©BrÂƒ—Ò"ÀÐ¢b"ÒÉÙŽÈ*Î«+Ê	RÉˆÙjS¢¶¦ö–åöÆ–Ö—FVB†–×7EöÆ&VÇ2÷"´Ä”Ô•DTEô”Õ5EÒÂÖ…ö—FV×3ÓBÂ6†%öÆ–Ö—CÓ“ÂfÆÆ&6³ÔÄ”Ô•DTEô”Õ5B—Ò"ÀÐ¢b"ÒÉˆÙjR«+ÞºÃ¢¶¦ö–åöÆ–Ö—FVB†—FVÒævWB‚wF‡2r’÷"²~Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚uÒÂÖ…ö—FV×3ÓRÂ6†%öÆ–Ö—CÓ#ÂfÆÆ&6³Ò~Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚r—Ò"ÀÐ¢b"ÒÉˆÙjRÈKžØK¢¶¦ö–åöÆ–Ö—FVB†—FVÒævWB‚w6V7F÷'2r’÷"²~Ê	^ËRþ«yÎÊ	ÂÉÛÎ»	‚uÒÂÖ…ö—FV×3ÓBÂ6†%öÆ–Ö—CÓ#ÂfÆÆ&6³Ò~Ê	^ËRþ«yÎÊ	ÂÉÛÎ»	‚r—Ò"ÀÐ¢b"ÒÙYÎ«ZÒ»ŽºYŽË+NÉÛƒ¢¶¦ö–åöÆ–Ö—FVB†—FVÒævWB‚v¶÷&V÷fÇVUö6†–âr’ÂÖ…ö—FV×3ÓRÂ6†%öÆ–Ö—CÓSÂfÆÆ&6³Ò~ÊxÊ	É{«+Éx^Ê(RÙ™^ÉÛ‚ÙXNÉ©Br—Ò"ÀÐ¢b"Ò»	ŽÉˆ«¸ª^ÈK¢¶6Æ—÷FW‡B†—FVÒævWB‚w&–6VEö–âr’÷"~¸*îÉØÇîÊI«BrÂC—Ò"ÀÐ¢b"Ò»	Ž¸È«{Î«¢¶6Æ—÷FW‡B†—FVÒævWB‚v6÷VçFW"r’÷"~ÈKŽ»hÊ«BÙ™^ÉÛ‚ÊN«˜ÎÊxÊxÊ	ÈºNÊÉ{«+ÉØÊ	ÎÙYÎÊÉè^¸¸Ž¸ºBârÂc—Ò"ÀÐ¢b"ÒÈºNØÊ‚ÈºÙ‹ƒ¢¶6Æ—÷FW‡B†—FVÒævWB‚vf–ÇW&U÷6–væÂr’÷"~Ù¸NÈhÒÈ¹ÎÙhžÉÛÌ+~ÉˆŽÈ++~«8NÉ[Ü+~È‰Ž«ˆ’»	ŽÉÙÉÛBÉxnÉËÎº›B¸ºŽ»	ÎÈKÊ	^ËRÉÛNÈ¨ŽºÂ¸Þ¸*ž¸¸Ž¸ºBârÂc—Ò"ÀÐ¢ÐÐ Ð Ð¦FVb÷&uöW‡ÆæF–öåöÆ–æW2†—FVÓ¢F–7B’ÓâÆ—7E·7G%Ó Ð¢Vç7W&UöW‡Æ–æVB†—FVÒÐ¢–×7EöÆ&VÇ2ÒF—7Æ•öFV6—6–öåö–×7G2†—FVÒævWB‚&–×7G2"’Ð¢&WGW&â°Ð¢b"ÒØÉ¸º‚ÊxŽºËƒ¢¶—FVÒævWB‚vFV6—6–öå÷VW7F–öâr’÷"DT4•4”ôåõTU5D”ôçÒ"ÀÐ¢b"ÒÉˆÙjR»hNºYƒ¢¶—FVÒævWB‚vFV6—6–öåö6Æ76–f–6F–öâr’÷"FV6—6–öåö6Æ76–f–6F–öå÷FW‡B†—FVÒævWB‚v–×7G2r’—Ò"ÀÐ¢b"Ò»hNºY‚ºzNØ«ŽºjÞÈªC¢¶FV6—6–öåöÖG&—…÷FW‡B†—FVÒævWB‚v–×7G2r’—Ò"ÀÐ¢b"ÒÙ[^ÈºÂ¸+NÉª“¢¶—FVÒævWB‚wöÆ–7•÷Æ–å÷7VÖÖ'’r’÷"~Ê	^ËRÈKŽ»h¸+NÉª’Ù™^ÉÛ‚ÙXNÉ©BwÒ"ÀÐ¢b"ÒØŠÎÉé«HÊ	¢¶—FVÒævWB‚v–çfW7FÖVçE÷f–Wrr’÷"~ÈºNÊ+~ÙZÉÛŽÉÊŒ+~È‰Ž«ˆœ+~È¹Î«NÙÂ»8Ù™BÉzÎ»hÙ™^ÉÛ‚ÙXNÉ©BwÒ"ÀÐ¢b"ÒÙYÎ«ZÞÉêRÉˆÙjS¢¶—FVÒævWB‚v¶÷&VöÖ&¶WEö–×7Br’÷"~ÙYÎ«ZÞÉêRÊxÊ	ÉˆÙjRÙ™^ÉÛ‚ÙXNÉ©BwÒ"ÀÐ¢b"ÒÙYÎ«ZÒ»ŽºYŽË+NÉÛƒ¢²rÂræ¦ö–â†5öÆ—7B†—FVÒævWB‚v¶÷&V÷fÇVUö6†–âr’’÷"²~ÊxÊ	É{«+Éx^Ê(RÙ™^ÉÛ‚ÙXNÉ©BuÒ—Ò"ÀÐ¢b"ÒÉÙŽÈ*Î«+Ê	RÉˆÙjS¢²rÂræ¦ö–â†–×7EöÆ&VÇ2÷"´Ä”Ô•DTEô”Õ5EÒ—Ò"ÀÐ¢b"ÒÉˆÙjR«+ÞºÃ¢²rÂræ¦ö–â†5öÆ—7B†—FVÒævWB‚wF‡2r’’÷"²~Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚uÒ—Ò"ÀÐ¢b"ÒÉˆÙjRÈKžØK¢²rÂræ¦ö–â†5öÆ—7B†—FVÒævWB‚w6V7F÷'2r’’÷"²~Ê	^ËRþ«yÎÊ	ÂÉÛÎ»	‚uÒ—Ò"ÀÐ¢b"ÒÉÛNºû‚Ê;Î«Éy»	ŽÉˆ¹	ÉØB«¸ª^ÈK¢¶—FVÒævWB‚w&–6VEö–âr’÷"~¸*îÉØÇîÊI«BwÒ"ÀÐ¢b"Ò»	Ž¸È«{Î«¢¶—FVÒævWB‚v6÷VçFW"r’÷"~ÈKŽ»hÊ«BÙ™^ÉÛ‚ÊN«˜ÎÊxÊxÊ	ÈºNÊÉ{«+ÉØÊ	ÎÙYÎÊÉè^¸¸Ž¸ºBâwÒ"ÀÐ¢b"ÒÈºNØÊ‚ÈºÙ‹ƒ¢¶—FVÒævWB‚vf–ÇW&U÷6–væÂr’÷"~Ù¸NÈhÒÈ¹ÎÙhžÉÛÌ+~ÉˆŽÈ++~«8NÉ[Ü+~È‰Ž«ˆ’»	ŽÉÙÉÛBÉxnÉËÎº›B¸ºŽ»	ÎÈKÊ	^ËR¸›NÈªNºÂ¸Þ¸*ž¸¸Ž¸ºBâwÒ"ÀÐ¢ÐÐ 