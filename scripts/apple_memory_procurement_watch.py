#!/usr/bin/env python3
"""Apple consumer-device memory procurement / contract-price watch.

Purpose
- Track Apple DRAM/NAND contract-price acceptance, LTAs, supplier allocation and volume commitments.
- Keep consumer-device memory separate from Apple enterprise-server HBM procurement.
- Treat the 2026-09-15 Jiemian report as the first baseline event and send it once.
- Suppress simple republications of the same baseline fact after the first confirmed delivery.

Evidence guardrails
- The Jiemian source reports DRAM ~US$2.0/Gb and NAND ~US$0.33/Gb for 1Q27,
  up 30-40% versus 3Q26; Apple had not responded to its request for comment.
- Gb and GB are not interchangeable. A future source that changes the unit is flagged.
- Supplier pricing reports are not promoted to an Apple official contract unless Apple or
  the named supplier confirms the terms.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_memory_procurement_watch_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
PENDING_PATH = OUT_DIR / "apple_memory_procurement_watch_pending_state.json"
STATUS_PATH = OUT_DIR / "apple_memory_procurement_watch_status.md"
FRAGMENT_PATH = OUT_DIR / "apple_memory_procurement_watch_alert.html"
MAIN_ALERT_PATH = OUT_DIR / "memory_spot_cycle_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")

BASELINE_AT_KST = dt.datetime(2026, 9, 15, 9, 0, tzinfo=KST)
BASELINE_SOURCE = "https://www.jiemian.com/article/15094732.html"
BASELINE_FACT_KEY = "apple_samsung_1q27_dram2.0gb_nand0.33gb_up30_40"
CXMT_APPLE_REFUSAL_BASELINE_KEY = "apple_cxmt_discount_refusal_first_reported_2026_08_05"
BASELINE = {
    "quarter": "2027Q1",
    "supplier": "삼성전자",
    "dram_usd_per_gb": 2.0,
    "nand_usd_per_gb": 0.33,
    "increase_pct_low": 30,
    "increase_pct_high": 40,
    "unit": "Gb",
    "confirmation": "공급망 보도·Apple 공식 미확인",
}

SEARCHES = [
    ("google_ko", '"애플" 삼성전자 DRAM NAND 2027 1분기 가격 2.0 0.33'),
    ("google_ko", '"애플" 메모리 장기계약 LTA 삼성전자 SK하이닉스 마이크론 DRAM NAND'),
    ("google_ko", '"애플" 2027 2분기 DRAM NAND 가격 재협상 공급사'),
    ("google_en", '"Apple" Samsung DRAM NAND 2027 Q1 price 2.0 0.33'),
    ("google_en", '"Apple" memory procurement LTA Samsung SK hynix Micron DRAM NAND'),
    ("google_en", '"Apple" 2027 Q2 DRAM NAND contract price supplier allocation'),
    ("google_ko", '"CXMT" "애플" LPDDR5X 가격 장기계약 공급계약'),
    ("google_en", '"CXMT" "Apple" DRAM LPDDR5X pricing supplier contract'),
    ("bing", '"CXMT" "Apple" DRAM signed supply agreement qualification'),
    ("bing", '"Apple" Samsung DRAM NAND 2027 Q1 2.0 0.33'),
    ("bing", '"Apple" memory procurement LTA Samsung SK hynix Micron'),
    ("bing", '"Apple" 2027 Q2 DRAM NAND contract price'),
]

HIGH_SOURCES = (
    "apple", "samsung", "samsung electronics", "삼성전자", "sk hynix", "sk하이닉스",
    "micron", "reuters", "bloomberg", "financial times", "wall street journal", "wsj",
    "trendforce", "counterpoint", "omdia", "digitimes", "jiemian", "界面新闻", "cxmt",
)
MID_SOURCES = (
    "macrumors", "9to5mac", "the elec", "전자신문", "etnews", "zdnet",
    "businesskorea", "서울경제", "매일경제", "한국경제", "머니투데이",
)
LOW_SOURCES = ("wccftech", "technobezz", "reddit", "note.com", "mexc")

APPLE_MARKERS = ("apple", "애플", "苹果")
MEMORY_MARKERS = ("dram", "nand", "lpddr", "memory", "storage", "메모리", "디램", "낸드", "闪存", "存储")
PROCURE_MARKERS = (
    "price", "quote", "contract", "procurement", "purchase", "lta", "long-term", "allocation",
    "supplier", "order", "volume", "capacity reservation", "negotiat", "agreement",
    "가격", "견적", "계약", "조달", "구매", "장기계약", "배정", "공급사", "발주", "물량",
    "报价", "采购", "合同", "长期协议", "供应商", "订单", "议价",
)
SUPPLIER_MARKERS = {
    "CXMT": ("cxmt", "changxin", "长鑫", "長鑫", "창신메모리"),
    "삼성전자": ("samsung", "삼성전자", "三星"),
    "SK하이닉스": ("sk hynix", "sk하이닉스", "海力士"),
    "Micron": ("micron", "마이크론", "美光"),
    "Kioxia": ("kioxia", "키옥시아", "铠侠"),
}
Q2_MARKERS = ("2027 q2", "2q27", "second quarter 2027", "2027년 2분기", "2027년2분기", "2027年二季度")
Q1_MARKERS = ("2027 q1", "1q27", "first quarter 2027", "2027년 1분기", "2027년1분기", "2027年一季度")

# Same existing consumer-memory scope: Mac configuration changes and retail
# pass-through are distinct from supplier contracts. Source dates are facts,
# not a new schedule; the exact November report is eligible only once.
NEO_REPORT_KEY = "apple_macbook_neo_20261122_feb_march_window_reported"
NEO_OFFICIAL_KEY = "apple_macbook_neo_2_a19pro_12gb_official"
NEO_SPEC_URL = "https://www.apple.com/macbook-neo/specs/"
NEO_REPORT_URL = "https://9to5mac.com/2026/11/22/macbook-neo-2-likely-to-launch-around-march-could-feature-new-colors-report/"
NEO_EARLIER_URL = "https://www.macrumors.com/2026/04/07/macbook-neo-a19-pro-chip-next-year/"
NEO_UDN_URL = "https://money.udn.com/money/story/11162/9897323"

UA = "Mozilla/5.0 (compatible; khs-apple-memory-procurement-watch/1.0)"

def _fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _clean(v: str | None) -> str:
    s = html.unescape(v or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _norm(v: str) -> str:
    s = _clean(v).lower()
    s = re.sub(r"[^0-9a-z가-힣一-龥%.$~+/-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _parse_date(v: str | None) -> dt.datetime | None:
    if not v:
        return None
    try:
        x = parsedate_to_datetime(v)
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(KST)
    except Exception:
        return None

def _source_rank(source: str) -> int:
    s = _norm(source)
    if any(x in s for x in HIGH_SOURCES):
        return 3
    if any(x in s for x in MID_SOURCES):
        return 2
    if any(x in s for x in LOW_SOURCES):
        return 0
    return 1

def _rss_url(kind: str, query: str) -> str:
    q = urllib.parse.quote(query)
    if kind == "google_ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    if kind == "google_en":
        return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    return f"https://www.bing.com/search?format=rss&q={q}"

def _fingerprint(title: str, source: str) -> str:
    return hashlib.sha256(f"{_norm(title)}|{_norm(source)}".encode()).hexdigest()[:24]

def _apple_cxmt_pair(text: str) -> bool:
    low = text.lower()
    return (any(x in low for x in ("cxmt", "changxin", "长鑫", "長鑫", "창신메모리"))
            and any(x in low for x in APPLE_MARKERS))


def _apple_cxmt_discount_reprint(text: str) -> bool:
    """Reject a repeat of the already-reported August 5, 2026 price refusal."""
    low = text.lower()
    if not _apple_cxmt_pair(low):
        return False
    if not any(x in low for x in ("price", "discount", "报价", "采购", "压价", "砍价",
                                  "降价", "单价", "가격", "단가", "할인")):
        return False
    if any(x in low for x in ("has signed with apple", "signed a contract with apple",
                              "与苹果签署", "애플과 공급계약 체결")):
        return False
    return any(x in low for x in ("refuse", "refused", "reject", "rejected",
                                  "won't discount", "no discount", "拒绝", "拒降",
                                  "거절", "퇴짜", "갱신 거부"))


def _verified_apple_cxmt_supply_event(event: dict) -> bool:
    """Require a direct original outlet and specific signed/qualified business."""
    blob = f"{event.get('title','')} {event.get('description','')}"
    if not _apple_cxmt_pair(blob) or _apple_cxmt_discount_reprint(blob):
        return False
    host = (urlparse(event.get("link") or "").hostname or "").lower().removeprefix("www.")
    verified_hosts = {"apple.com", "cxmt.com", "reuters.com", "bloomberg.com"}
    if not any(host == h or host.endswith("." + h) for h in verified_hosts):
        return False
    low = blob.lower()
    a = re.search(
        r"(?:apple|애플|苹果)[^.!?\n]{0,95}(?:cxmt|changxin|长鑫|長鑫|창신메모리)"
        r"[^.!?\n]{0,105}(?:signed|signs|supply agreement|contract signed|approved supplier|"
        r"customer qualified|正式供货|供货协议|签署协议|认证完成|공급계약 체결|양산 공급 확정)",
        low, re.I,
    )
    b = re.search(
        r"(?:cxmt|changxin|长鑫|長鑫|창신메모리)[^.!?\n]{0,100}"
        r"(?:signed|began supplying|approved supplier|供货协议|签署协议|"
        r"正式供货|납품 계약|공급계약 체결)[^.!?\n]{0,75}"
        r"(?:apple|애플|苹果)", low, re.I,
    )
    return bool(a or b)


def _extract_numbers(text: str) -> dict:
    low = text.lower().replace(",", "")
    out: dict[str, object] = {}
    # Preserve unit exactly as reported. Gb and GB differ by 8x.
    dram = re.search(r"dram[^\n.]{0,120}?\$?\s*(\d+(?:\.\d+)?)\s*/?\s*(gb|gigabit|gigabyte)", low, re.I)
    nand = re.search(r"nand[^\n.]{0,120}?\$?\s*(\d+(?:\.\d+)?)\s*/?\s*(gb|gigabit|gigabyte)", low, re.I)
    if dram:
        out["dram"] = float(dram.group(1))
        out["dram_unit_raw"] = dram.group(2)
    if nand:
        out["nand"] = float(nand.group(1))
        out["nand_unit_raw"] = nand.group(2)
    pct_range = re.search(r"(\d{1,3})\s*[-~–—]\s*(\d{1,3})\s*%", low)
    if pct_range:
        out["pct_low"] = int(pct_range.group(1))
        out["pct_high"] = int(pct_range.group(2))
    else:
        pcts = [int(x) for x in re.findall(r"(\d{1,3})\s*%", low) if 0 <= int(x) <= 300]
        if pcts:
            out["pct"] = max(pcts)
    return out

def _unit_flag(text: str) -> str:
    # Baseline source explicitly uses Gb. Flag likely byte/bit transcription risk.
    if re.search(r"(?:2(?:\.0)?|0\.33)\s*(?:usd|dollars?|달러)?\s*/?\s*GB\b", text):
        return "⚠️ 동일 가격을 GB로 표기한 재인용 가능성 — 원출처는 Gb, 8배 차이"
    return ""

def _suppliers(text: str) -> list[str]:
    low = text.lower()
    return [name for name, aliases in SUPPLIER_MARKERS.items() if any(a.lower() in low for a in aliases)]

def _fact_key(text: str, nums: dict) -> str:
    low = text.lower()
    suppliers = "-".join(_suppliers(text)) or "unspecified"
    quarter = "q2_2027" if any(x in low for x in Q2_MARKERS) else ("q1_2027" if any(x in low for x in Q1_MARKERS) else "other")
    if any(x in low for x in ("lta", "long-term agreement", "장기계약", "长期协议")):
        kind = "lta"
    elif any(x in low for x in ("allocation", "capacity reservation", "배정", "产能预订", "공급사")):
        kind = "allocation"
    elif any(x in low for x in ("price", "quote", "가격", "견적", "报价", "议价")):
        kind = "price"
    else:
        kind = "procurement"
    n = f"d{nums.get('dram','x')}_n{nums.get('nand','x')}_p{nums.get('pct_low',nums.get('pct','x'))}_{nums.get('pct_high','x')}"
    return f"apple_{suppliers}_{quarter}_{kind}_{n}".lower().replace(" ", "_")

def _relevant(text: str, source: str) -> bool:
    low = text.lower()
    if _source_rank(source) == 0:
        return False
    return (
        any(x.lower() in low for x in APPLE_MARKERS)
        and any(x.lower() in low for x in MEMORY_MARKERS)
        and any(x.lower() in low for x in PROCURE_MARKERS)
    )

def _collect(diagnostics: dict | None = None) -> list[dict]:
    rows: dict[str, dict] = {}
    health = diagnostics if diagnostics is not None else {}
    health.update({"attempted": len(SEARCHES), "successful": 0, "failed": 0, "errors": []})
    for kind, query in SEARCHES:
        try:
            root = ET.fromstring(_fetch(_rss_url(kind, query)))
            if root.find("./channel") is None:
                raise ValueError("RSS channel missing")
            health["successful"] += 1
        except Exception as exc:
            health["failed"] += 1
            health["errors"].append(f"{kind}: {type(exc).__name__}")
            continue
        for item in root.findall("./channel/item"):
            title = _clean(item.findtext("title"))
            desc = _clean(item.findtext("description"))
            link = _clean(item.findtext("link"))
            pub = _parse_date(_clean(item.findtext("pubDate")))
            source_node = item.find("source")
            source = _clean(source_node.text if source_node is not None and source_node.text else "")
            if kind == "bing" and not source and link:
                source = (urlparse(link).hostname or "").replace("www.", "")
            blob = f"{title} {desc}"
            if not title or not link or not _relevant(blob, source):
                continue
            key = _fingerprint(title, source)
            rows[key] = {
                "id": key,
                "title": title,
                "description": desc,
                "source": source or "출처 미표시",
                "link": link,
                "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
            }
    return sorted(rows.values(), key=lambda x: x.get("published_at_kst") or "")

def _load_state() -> dict:
    if STATE_PATH.exists():
        # Never silently reinitialize a previously delivered event after a
        # damaged state file. Hold the run rather than replay the baseline.
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("Apple memory state is not a JSON object")
        return obj
    return {
        "schema_version": 1,
        "initial_alert_sent": False,
        "seen_ids": [],
        "seen_fact_keys": [BASELINE_FACT_KEY],
        "baseline": BASELINE,
    }

def _write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _append_alert(block: str) -> None:
    existing = MAIN_ALERT_PATH.read_text(encoding="utf-8").strip() if MAIN_ALERT_PATH.exists() else ""
    combined = block.strip() if not existing else existing + "\n\n" + block.strip()
    MAIN_ALERT_PATH.write_text(combined + "\n", encoding="utf-8")

def _initial_block() -> str:
    return "\n".join([
        "🍎 <b>[Apple 메모리 조달가격 | 첫 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[무엇이 달라졌나]</b>",
        "• 界面新闻 공급망 보도: Apple이 삼성전자의 <b>2027년 1분기 메모리 견적을 수용</b>한 것으로 전해졌습니다.",
        "• DRAM <b>약 2.0달러/Gb</b>, NAND <b>약 0.33달러/Gb</b>로, 2026년 3분기 대비 <b>+30~40%</b> 수준입니다.",
        "",
        "<b>[현재 판정]</b>",
        "🟡 <b>가격 수용 보도 단계</b> — Apple·삼성전자 공식 계약 공시는 아직 확인되지 않았습니다.",
        "• 원출처는 Apple에 확인을 요청했지만 보도 시점까지 답변이 없었다고 명시했습니다.",
        "• <b>Gb와 GB는 8배 차이</b>입니다. 현재 기준 단위는 원출처의 <b>Gb</b>로 잠급니다.",
        "",
        "<b>[투자 의미]</b>",
        "• 대형 구매자인 Apple까지 30~40% 높은 견적을 받아들였다는 보도가 사실이면 모바일 DRAM·NAND 계약가격 기준선 상승 신호입니다.",
        "• 삼성전자 직접 수혜 가능성이 가장 먼저 열리며, 이후 SK하이닉스·Micron으로 가격 수용이 확산되는지가 업황 확인 포인트입니다.",
        "",
        "<b>[다음 알림 조건]</b>",
        "• 2027년 1분기 가격·계약조건의 Apple 또는 삼성전자 공식 확인",
        "• 2027년 2분기 재협상 가격 또는 추가 인상·인하",
        "• SK하이닉스·Micron 공급비중·가격 수용·신규 물량 배정",
        "• Apple DRAM/NAND LTA·최소구매물량·용량 예약",
        "• iPhone·iPad·Mac 메모리 사양 축소/확대 또는 제품가격 전가",
        "• Gb↔GB 단위 정정 또는 원출처 수치 수정",
        "",
        f'<a href="{BASELINE_SOURCE}"><b>원출처 | 界面新闻</b></a>',
    ])

def _event_block(event: dict, nums: dict, fact_key: str) -> str:
    blob = f"{event.get('title','')} {event.get('description','')}"
    suppliers = ", ".join(_suppliers(blob)) or "공급사 미확정"
    flag = _unit_flag(blob)
    low = blob.lower()
    if any(x in low for x in Q2_MARKERS):
        stage = "🟠 2027년 2분기 재협상 변화"
    elif any(x in low for x in ("lta", "long-term agreement", "장기계약", "长期协议")):
        stage = "🟠 장기계약·물량확보 변화"
    elif any(x in low for x in ("sk hynix", "sk하이닉스", "micron", "마이크론")):
        stage = "🟠 공급사 확산·배정 변화"
    else:
        stage = "🟡 Apple 메모리 조달가격 변화"

    numbers = []
    if "dram" in nums:
        numbers.append(f"DRAM {nums['dram']} ({nums.get('dram_unit_raw','단위 확인 필요')})")
    if "nand" in nums:
        numbers.append(f"NAND {nums['nand']} ({nums.get('nand_unit_raw','단위 확인 필요')})")
    if "pct_low" in nums:
        numbers.append(f"변화율 {nums['pct_low']}~{nums.get('pct_high', nums['pct_low'])}%")
    elif "pct" in nums:
        numbers.append(f"변화율 {nums['pct']}%")
    number_line = " / ".join(numbers) if numbers else "구체 단가·변화율은 원문 추가 확인 필요"

    lines = [
        f"🍎 <b>[Apple 메모리 조달 | {html.escape(stage)}]</b>",
        "━━━━━━━━━━━━━━━━",
        f"• {html.escape(event.get('title') or '신규 변화')}",
        f"• 공급사: <b>{html.escape(suppliers)}</b>",
        *([("• CXMT: 직접 출처의 신규 계약·고객 검증 변화입니다. "
             "보도와 양측 공식 확인은 구분해야 합니다.")] if _apple_cxmt_pair(blob) else []),
        f"• 숫자: {html.escape(number_line)}",
        f"• 출처: {html.escape(event.get('source') or '출처 미표시')} · {html.escape(event.get('published_at_kst') or '시각 확인 불가')}",
        "",
        "<b>[판정 규칙]</b>",
        "• 공급망 보도와 Apple/공급사 공식 확인을 분리합니다.",
        "• 동일 사실 재인용은 중복 알림하지 않고, 가격·분기·공급사·물량이 바뀔 때만 새 사실로 처리합니다.",
    ]
    if flag:
        lines += ["", html.escape(flag)]
    lines += ["", f'<a href="{html.escape(event.get("link") or BASELINE_SOURCE, quote=True)}"><b>원문</b></a>']
    return "\n".join(lines)

def _neo_page_text(url: str, fetcher=None) -> str:
    fetcher = fetcher or _fetch
    raw = fetcher(url, timeout=12).decode("utf-8", "replace")
    # Drop scripts/styles, so a stray JSON keyword, a navigation link or an
    # embedded ad is not sufficient to classify a new product specification.
    raw = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", raw,
                 flags=re.I | re.S)
    return _clean(raw)


def _neo_current_spec(text: str) -> str:
    if not re.search(r"MacBook\s+Neo", text, re.I):
        return "unverified"
    # Require the chip and unified memory to be visible on the official page.
    # A dual match means the generation cannot be unambiguously assigned.
    a18 = bool(re.search(r"\bA18\s+Pro\b", text, re.I))
    a19 = bool(re.search(r"\bA19\s+Pro\b", text, re.I))
    old_mem = bool(re.search(r"\b8\s*GB\s+unified\s+memory\b", text, re.I))
    new_mem = bool(re.search(r"\b12\s*GB\s+unified\s+memory\b", text, re.I))
    if a18 and old_mem and not a19 and not new_mem:
        return "a18pro_8gb"
    if a19 and new_mem and not a18 and not old_mem:
        return "a19pro_12gb"
    return "unverified"


def _neo_nov22_report_verified(text: str) -> bool:
    # Specific publisher article: confirm the date window, both generations,
    # memory amounts and Bloomberg attribution, not merely a headline/keyword.
    return bool(
        re.search(r"MacBook\s+Neo", text, re.I)
        and re.search(r"\bA18\s+Pro\b", text, re.I)
        and re.search(r"\bA19\s+Pro\b", text, re.I)
        and re.search(r"\b8\s*GB\b", text, re.I)
        and re.search(r"\b12\s*GB\b", text, re.I)
        and re.search(r"\bFebruary\s+(?:and|or|to)\s+March\b|\b(?:around|in|by)\s+March\b", text, re.I)
        and re.search(r"Bloomberg|Mark\s+Gurman", text, re.I)
    )


def _neo_product_context(title: str, desc: str = "") -> bool:
    return bool(re.search(r"\bMacBook\s*Neo\b|맥북\s*네오", title or "", re.I))


def _neo_explicit_supplier_milestone(text: str) -> bool:
    return bool(re.search(
        r"(?i)\b(?:signed|signs|awarded|secured|confirmed)\b.{0,80}"
        r"\b(?:supply\s+agreement|memory\s+contract|purchase\s+order)\b|"
        r"공급계약\s*체결|메모리\s*발주\s*확정|簽署.{0,30}(?:供應|采购|採購)合約",
        text or "",
    ))


def _neo_verified_signal(state: dict, now: dt.datetime, fetcher=None) -> tuple[str | None, str, dict]:
    """A lead report and a later official specification are separate events.

    Failures do not advance event IDs. The report is a dated, directly checked
    Bloomberg-derived forecast, not an Apple announcement or an OLED order.
    The live official spec check continues independently once per KST day.
    """
    prior = dict(state.get("macbook_neo_watch") or {})
    known = set(state.get("seen_fact_keys") or [])
    diag = {"official_source": "not_checked", "report_source": "not_checked"}
    today = now.date().isoformat()
    report_pending = (NEO_REPORT_KEY not in known
                      and dt.date(2026, 11, 22) <= now.date() <= dt.date(2026, 12, 22))
    if prior.get("official_checked_date") == today and not report_pending:
        diag["official_source"] = "verified_today" if prior.get("official_spec") else "unverified_today"
        return None, "", diag
    try:
        spec = _neo_current_spec(_neo_page_text(NEO_SPEC_URL, fetcher))
    except Exception as exc:
        diag["official_source"] = "fetch_failed:" + type(exc).__name__
        return None, "", diag
    diag["official_source"] = spec
    if spec == "unverified":
        return None, "", diag
    diag["official_checked_date"] = today
    if spec == "a19pro_12gb":
        if NEO_OFFICIAL_KEY in known:
            return None, "", diag
        return NEO_OFFICIAL_KEY, "\n".join([
            "<b>[애플 맥북 네오 메모리 사양 공식 변경]</b>",
            "■ 애플 공식 제품 사양에서 A19 Pro 및 12GB 통합 메모리를 직접 확인했습니다.",
            "• 기존 A18 Pro·8GB 대비 메모리 탑재량 50% 확대. 실제 공급사·발주량·판매량은 별도 확인이 필요합니다.",
            "• 디스플레이 사양은 별도 검증 대상이며, 메모리 증량만으로 OLED 전환을 추정하지 않습니다.",
            f'<a href="{NEO_SPEC_URL}">애플 공식 제품 사양</a>',
        ]), diag
    if not report_pending:
        return None, "", diag
    try:
        report = _neo_page_text(NEO_REPORT_URL, fetcher)
    except Exception as exc:
        diag["report_source"] = "fetch_failed:" + type(exc).__name__
        return None, "", diag
    if not _neo_nov22_report_verified(report):
        diag["report_source"] = "content_unverified"
        return None, "", diag
    diag["report_source"] = "direct_article_verified"
    return NEO_REPORT_KEY, "\n".join([
        "<b>[애플 맥북 네오 2세대 — 출시 전망 구체화·메모리 선행지표]</b>",
        "■ 11월 22일 보도: 2027년 상반기 전망에서 2~3월 출시 가능성으로 구체화. 애플 공식 출시일은 미발표.",
        "• 기존 A18 Pro·8GB는 애플 공식 사양 확인. A19 Pro·12GB는 4월부터 나온 공급망 전망이며 이번 신규 확정 사양이 아닙니다.",
        "• 동일 기기 판매량 가정 시 기기당 메모리 탑재량 8→12GB(+50%). 실제 조달단가·공급사·수량·2세대 가격은 미확정.",
        "• 맥북 네오의 OLED 전환 확인 없음. 같은 시기 OLED 아이패드 에어 전망과 구분.",
        "• 이번 보도는 Bloomberg 기자 전망을 인용한 것이며, 재인용은 추가 독립 사실이나 별도 수주가 아닙니다.",
        "• 조기경보: 공식 발표, 실제 판매가격, 제품 판매량과 메모리 조달 물량의 동시 변화.",
        f'<a href="{NEO_SPEC_URL}">애플 현행 공식 사양</a> · <a href="{NEO_REPORT_URL}">11/22 직접 확인 기사</a> · <a href="{NEO_EARLIER_URL}">4월 기존 전망 참고</a> · <a href="{NEO_UDN_URL}">11/24 대만 보도 참고</a>',
    ]), diag


def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    seen_ids = set(state.get("seen_ids") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])
    seen_fact_keys.add(CXMT_APPLE_REFUSAL_BASELINE_KEY)
    health: dict = {}
    events = _collect(health)
    neo_key, neo_block, neo_health = _neo_verified_signal(state, now)

    # Record a genuinely failed source separately from a successful empty feed.
    # Do not stage the old baseline, generic seen IDs or false no-change state
    # after total RSS failure. An independently checked Neo fact may still
    # proceed without acknowledging any failed RSS collection.
    if not health["successful"] and not neo_key:
        PENDING_PATH.unlink(missing_ok=True)
        FRAGMENT_PATH.unlink(missing_ok=True)
        STATUS_PATH.write_text(
            "# Apple 메모리 조달가격 감시\n"
            f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
            f"- source_status: fetch_failed (0/{health['attempted']})\n"
            f"- neo_source_status: {json.dumps(neo_health, ensure_ascii=False)}\n"
            "- state_advanced: false; 신규 발표 없음으로 판정하지 않음\n",
            encoding="utf-8")
        print("apple_memory_source_failed=true state_advanced=false")
        return

    alert_blocks: list[str] = []
    if neo_key and neo_key not in seen_fact_keys and neo_block:
        alert_blocks.append(neo_block)
        seen_fact_keys.add(neo_key)
    initial_was_pending = bool(health["successful"]) and not bool(state.get("initial_alert_sent"))
    if initial_was_pending:
        alert_blocks.append(_initial_block())
        state["initial_alert_sent"] = True
        seen_fact_keys.add(BASELINE_FACT_KEY)

    fresh_candidates = []
    for e in events:
        try:
            pub = dt.datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            pub = None
        if pub and pub < BASELINE_AT_KST:
            seen_ids.add(e["id"])
            continue
        blob = f"{e.get('title','')} {e.get('description','')}"
        nums = _extract_numbers(blob)
        fkey = _fact_key(blob, nums)
        if e["id"] in seen_ids:
            continue
        # Do not turn a product-spec forecast or retail-price article into
        # a new DRAM/NAND procurement contract. The direct Neo lane has its
        # own evidence and semantic key; specific real supplier deals keep
        # their original gate.
        if _neo_product_context(e.get("title", "")) and not _neo_explicit_supplier_milestone(blob):
            continue
        if _apple_cxmt_pair(blob):
            if _apple_cxmt_discount_reprint(blob):
                # The original August refusal cannot become a fresh October deal.
                seen_fact_keys.add(CXMT_APPLE_REFUSAL_BASELINE_KEY)
                continue
            if not _verified_apple_cxmt_supply_event(e):
                # Price discussion, samples and open-to-talk comments are not contracts.
                continue
        # Suppress baseline republications even if title/source differs.
        baseline_like = (
            any(x in blob.lower() for x in Q1_MARKERS)
            and "samsung" in blob.lower()
            and ("2.0" in blob or "$2" in blob)
            and "0.33" in blob
            and ("30" in blob and "40" in blob)
        )
        if baseline_like:
            seen_fact_keys.add(BASELINE_FACT_KEY)
            continue
        if fkey in seen_fact_keys:
            seen_ids.add(e["id"])
            continue
        fresh_candidates.append((e, nums, fkey, _source_rank(e.get("source") or "")))

    # Do not consume candidates beyond the per-run alert cap. Re-check the
    # semantic key within the selected batch to collapse same-fact reprints.
    fresh_candidates.sort(key=lambda x: (x[3], x[0].get("published_at_kst") or ""), reverse=True)
    sent_candidates = 0
    for e, nums, fkey, rank in fresh_candidates:
        if rank < 2:
            continue
        if fkey in seen_fact_keys:
            seen_ids.add(e["id"])
            continue
        if sent_candidates >= 2:
            continue
        alert_blocks.append(_event_block(e, nums, fkey))
        seen_fact_keys.add(fkey)
        seen_ids.add(e["id"])
        sent_candidates += 1

    neo_prior = dict(state.get("macbook_neo_watch") or {})
    if neo_health.get("official_checked_date"):
        neo_prior["official_checked_date"] = neo_health["official_checked_date"]
        neo_prior["official_spec"] = neo_health.get("official_source")
    if neo_key and neo_block:
        neo_prior["last_event_key"] = neo_key
        neo_prior["last_event_source"] = NEO_SPEC_URL if neo_key == NEO_OFFICIAL_KEY else NEO_REPORT_URL
    state["macbook_neo_watch"] = neo_prior

    state.update({
        "source_health": health,
        "source_status": ("complete" if not health["failed"] else
                          "partial" if health["successful"] else "rss_failed_direct_event_only"),
        "neo_source_health": neo_health,
        "schema_version": 1,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "baseline_at_kst": BASELINE_AT_KST.isoformat(timespec="seconds"),
        "baseline_source": BASELINE_SOURCE,
        "baseline": BASELINE,
        "seen_ids": sorted(seen_ids)[-500:],
        "seen_fact_keys": sorted(seen_fact_keys)[-200:],
        "last_scan_count": len(events),
        "last_new_signal_count": max(0, len(alert_blocks) - (1 if initial_was_pending else 0)),
        "alert_generated": bool(alert_blocks),
    })
    _write_json(PENDING_PATH, state)

    if alert_blocks:
        text = "\n\n".join(alert_blocks)
        FRAGMENT_PATH.write_text(text + "\n", encoding="utf-8")
        _append_alert(text)
    elif FRAGMENT_PATH.exists():
        FRAGMENT_PATH.unlink()

    STATUS_PATH.write_text(
        "# Apple 메모리 조달가격 감시\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- scanned_items: {len(events)}\n"
        f"- source_status: {state['source_status']} ({health['successful']}/{health['attempted']})\n"
        f"- neo_source_status: {json.dumps(neo_health, ensure_ascii=False)}\n"
        f"- alert_generated: {str(bool(alert_blocks)).lower()}\n"
        f"- baseline: DRAM US$2.0/Gb, NAND US$0.33/Gb, +30~40%, 2027Q1 Samsung\n"
        f"- source: {BASELINE_SOURCE}\n",
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
