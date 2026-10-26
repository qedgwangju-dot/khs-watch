#!/usr/bin/env python3
"""Monitor iPhone Duo preorder allocation and per-market shipping lead times.

Shipping backlogs are a supply-demand balance, NOT a measured sales volume.
The launch date is distinct from the promised date for new online orders.
Keep a stable source-verified first-day chronology (2026-10-16), and alert again
only for a fresh material ETA extension in the SAME market. Do not infer
country/colour/capacity absent an explicit claim. No new Telegram route.
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
STATE_PATH = ROOT / "data" / "apple_duo_preorder_delivery_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
PENDING = OUT / "apple_duo_preorder_delivery_pending_state.json"
STATUS = OUT / "apple_duo_preorder_delivery_status.md"
FRAGMENT = OUT / "apple_duo_preorder_delivery_alert.html"
TELEGRAM = OUT / "apple_duo_supply_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")
PREORDER = dt.datetime(2026, 10, 16, 21, tzinfo=KST)
LAUNCH = dt.date(2026, 10, 23)
APPLE = "https://www.apple.com/kr/newsroom/2026/10/open-up-to-new-possibilities-with-iphone-duo/"
AI = "https://appleinsider.com/articles/26/10/16/iphone-duo-sells-out-moments-after-pre-orders-begin"
MR = "https://www.macrumors.com/2026/10/16/iphone-duo-preorder-shipping-wait-times/"
VERGE = "https://www.theverge.com/tech/1012805/apple-iphone-duo-preorder-delay"
OCT19_IMPROVEMENT = "https://www.macrumors.com/2026/10/19/apple-starts-moving-up-iphone-duo-delivery-dates/"
OCT19_ALTERNATIVE = "https://9to5mac.com/2026/10/19/some-iphone-duo-orders-getting-moved-up-to-earlier-dates/"
RETAIL_LAUNCH_BENCHMARK = {
    "as_of": "2026-10-23",
    "market": "미국",
    "mean_online_wait_days_reported": 92,
    "mean_wait_source_kind": "Navi 조사·WSJ/연합뉴스 재인용, Apple 공식 납기 아님",
    "us_store_initial_allocation_units_reported": [50, 200],
    "allocation_source_kind": "연합뉴스가 인용한 출시 첫날 미국 매장별 배정 보도",
    "source": "https://www.yna.co.kr/view/AKR20261024007600075",
    "confirmed_total_sales_units": None,
    "sku_specific_delivery_date": None,
}

QUERY = [
    ("ko", '"아이폰 듀오" 사전 예약 품절 배송 예정일'),
    ("ko", '"아이폰 듀오" 배송 지연 11월 12월 2027년'),
    ("en", '"iPhone Duo" preorders delivery estimated November December January'),
    ("en", '"iPhone Duo" shipping dates backorder 2027'),
    ("en", '"iPhone Duo" preorder sold out production supply shortage'),
]
FEEDS = [
    ("MacRumors", "https://feeds.macrumors.com/MacRumors-All"),
    ("AppleInsider", "https://appleinsider.com/rss/news/"),
    ("9to5Mac", "https://9to5mac.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
]
HIGH = ("reuters", "bloomberg", "the verge", "financial times", "nikkei", "apple newsroom")
MID = ("appleinsider", "macrumors", "9to5mac", "the elec", "연합뉴스", "zdnet", "전자신문")
UA = "Mozilla/5.0 (compatible; khs-iphone-duo-delivery-watch/1.0)"

BASELINE = {
    "2026-10-16_initial_stock_out": {
        "status": "초기 10월23일 배송분 소진 보도·총주문 마감 아님",
        "source": AI,
    },
    "US": {
        "latest_reported_delivery": "2027-01",
        "precision": "1월 말(일자 미확정)",
        "source": VERGE,
        "source_quality": "독립 보도, Apple 공식 동적 배송 견적 미열람",
        "first_retail_date": LAUNCH.isoformat(),
    },
    "KR": {"latest_reported_delivery": None, "precision": "확인 불가"},
}

def _clean(v: str | None) -> str:
    s = re.sub(r"<[^>]*>", " ", v or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def _rank(v: str) -> int:
    s = _clean(v).lower()
    if any(x in s for x in HIGH):
        return 3
    if any(x in s for x in MID):
        return 2
    return 0

def _fingerprint(v: dict) -> str:
    key = f"{v.get('title','')}|{v.get('source','')}|{v.get('published_at_kst','')}".lower()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]

def _date(v: str | None) -> dt.datetime | None:
    try:
        t = parsedate_to_datetime(v or "")
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t.astimezone(KST)
    except Exception:
        return None

_MONTH_NAMES = (
    "october|oct|november|nov|december|dec|january|jan|february|feb|"
    "march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep"
)
_DATE_MENTION_RE = re.compile(
    r"(?:20\d{2}\s*년\s*\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?|"
    r"\d{1,2}\s*월(?:\s*\d{1,2}\s*(?:-|–|—|~)\s*\d{1,2}\s*일|\s*\d{1,2}\s*일)?|"
    r"(?:early|mid|late)\s+(?:" + _MONTH_NAMES + r")(?:\s+20\d{2})?|"
    r"(?:" + _MONTH_NAMES + r")\s+(?:\d{1,2}\s*(?:-|–|—|to|through|~)\s*\d{1,2}"
    r"|\d{1,2})(?:\s*,?\s*20\d{2})?|"
    r"(?:" + _MONTH_NAMES + r")\s+20\d{2})",
    re.I,
)
_ETA_WORD_RE = re.compile(
    r"shipping|delivery|delivered|ships?\b|backorders?|wait\s+times?|"
    r"배송|출고|납기|대기\s*기간",
    re.I,
)
_NOND_ELIVERY_WORD_RE = re.compile(
    r"production|produced|manufactur|assembl|fabricat|"
    r"pickup|pick-up|walk-in|매장\s*수령|픽업|생산|제조|조립",
    re.I,
)


def _month_and_day(phrase: str, pub: dt.datetime, allow_launch: bool = False) -> tuple[str, str, str | None] | None:
    s = phrase.lower()
    names = {
        "october":10, "oct":10, "november":11, "nov":11,
        "december":12, "dec":12, "january":1, "jan":1,
        "february":2, "feb":2, "march":3, "mar":3,
        "april":4, "apr":4, "may":5, "june":6, "jun":6,
        "july":7, "jul":7, "august":8, "aug":8, "september":9, "sep":9,
    }
    matching_month = re.search(r"\b(?:" + _MONTH_NAMES + r")\b", s, re.I)
    korean = re.search(r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월", s)
    if matching_month:
        mo = names[matching_month.group(0).lower()]
        rest = s[matching_month.end():]
        range_match = re.search(r"^\s*(\d{1,2})\s*(?:-|–|—|to|through|~)\s*(\d{1,2})", rest)
        date_match = re.search(r"^\s*(\d{1,2})(?:\D|$)", rest)
        day = int(range_match.group(2)) if range_match else (int(date_match.group(1)) if date_match else None)
    elif korean:
        mo = int(korean.group(2))
        rest = s[korean.end():]
        range_match = re.search(r"^\s*(\d{1,2})\s*(?:-|–|—|~)\s*(\d{1,2})\s*일", rest)
        date_match = re.search(r"^\s*(\d{1,2})\s*일", rest)
        day = int(range_match.group(2)) if range_match else (int(date_match.group(1)) if date_match else None)
    else:
        return None
    if not 1 <= mo <= 12 or (day is not None and not 1 <= day <= 31):
        return None

    years = re.findall(r"\b20(?:26|27|28|29)\b|20(?:26|27|28|29)\s*년", s)
    if korean and korean.group(1):
        year = int(korean.group(1))
    elif years:
        year = int(re.search(r"20\d{2}", years[0]).group(0))
    elif mo >= pub.month:
        year = pub.year
    elif pub.month >= 9 and mo <= 3:
        # January following an October preorder is Jan 2027. "late August"
        # in an October retrospective is NOT automatically August 2027.
        year = pub.year + 1
    else:
        return None
    try:
        d = dt.date(year, mo, day or 1)
    except ValueError:
        return None
    if d < LAUNCH or (d == LAUNCH and not allow_launch):
        return None
    if (d - pub.date()).days > 180:
        return None
    label = (
        f"{year}년 {mo}월 {day}일"
        if day is not None
        else f"{year}년 {mo}월 말(정확한 일자 확인 불가)"
        if re.search(r"\blate\b|말", s)
        else f"{year}년 {mo}월(정확한 일자 확인 불가)"
    )
    exact = d.isoformat() if day is not None else None
    return f"{year:04d}-{mo:02d}", label, exact


def _shipping_event(blob: str, published: dt.datetime) -> dict | None:
    if published < PREORDER:
        return None
    low = blob.lower()
    if not ("iphone duo" in low or "아이폰 듀오" in low):
        return None
    candidates = []
    for match in _DATE_MENTION_RE.finditer(blob):
        # Associate each calendar expression with the shipping/delivery phrase
        # in the SAME local clause. Never choose the largest month in an entire
        # syndicated article with production history, retail pickup, and launch.
        before = blob[max(0, match.start() - 115):match.start()]
        after = blob[match.end():min(len(blob), match.end() + 85)]
        left = re.split(r"[.!?;\n。]+", before)[-1]
        right = re.split(r"[.!?;\n。]+", after)[0]
        eta_positions = []
        for m in _ETA_WORD_RE.finditer(left):
            eta_positions.append(("before", len(left) - m.end()))
        for m in _ETA_WORD_RE.finditer(right):
            eta_positions.append(("after", m.start()))
        if not eta_positions:
            continue
        direction, distance = min(eta_positions, key=lambda x: x[1])
        if distance > (85 if direction == "before" else 48):
            continue
        context = (left[-95:] + " " + match.group(0) + " " + right[:65]).strip()
        # The nearest semantic cue must refer to delivery, not production or
        # pickup availability. A speculative article can mention all three.
        competing = []
        for m in _NOND_ELIVERY_WORD_RE.finditer(left):
            competing.append(len(left) - m.end())
        for m in _NOND_ELIVERY_WORD_RE.finditer(right):
            competing.append(m.start())
        if competing and min(competing) < distance:
            continue
        info = _month_and_day(match.group(0), published)
        if info is not None:
            candidates.append((info, context))
    if not candidates:
        return None
    # Multiple genuine shipment-date milestones in one article are allowed;
    # only DATE-CONSTRAINED quotations participate in the latest-date choice.
    info, evidence = max(candidates, key=lambda x: (x[0][0], x[0][2] or ""))
    if re.search(r"\b(?:u\.s\.?(?=\W|$)|united states|usa|us apple store)\b", low):
        has_us = True
    else:
        has_us = False
    has_kr = bool(re.search(r"\b(?:south korea|korea|한국|국내|대한민국)\b", low))
    market = "미국" if has_us and not has_kr else ("한국" if has_kr and not has_us else "지역 미확인")
    # Model variants in price lists elsewhere in the article never assign an
    # unknown general delivery ETA to 256GB/2TB or a particular color.
    local = evidence.lower()
    if "all configurations" in local or "모든 구성" in local:
        local = re.sub(r"\b(?:256|512)\s*gb\b|\b[12]\s*tb\b", "", local)
    sizes = set(re.findall(r"\b(?:256|512)\s*gb\b|\b(?:1|2)\s*tb\b", local))
    colors = {x for x in ("star white", "night sky", "스타 화이트", "나이트 스카이") if x in local}
    storage = next(iter(sizes)).replace(" ", "").upper() if len(sizes) == 1 else "구성 미확인"
    color = next(iter(colors)) if len(colors) == 1 else "색상 미확인"
    return {
        "market": market, "month": info[0], "label": info[1],
        "exact_date": info[2], "capacity": storage, "colour": color,
        "eta_evidence": re.sub(r"\s+", " ", evidence)[:175],
    }


def _direct_publisher_link(row: dict) -> bool:
    # Search snippets behind a Google News redirect are discovery only.
    host = (urlparse(row.get("link") or "").hostname or "").lower().removeprefix("www.")
    source = (row.get("source") or "").lower()
    hosts = {
        "macrumors": "macrumors.com",
        "9to5mac": "9to5mac.com",
        "appleinsider": "appleinsider.com",
        "the verge": "theverge.com",
        "reuters": "reuters.com",
        "financial times": "ft.com",
        "nikkei": "asia.nikkei.com",
        "bloomberg": "bloomberg.com",
        "연합뉴스": "yna.co.kr",
    }
    for src, expected in hosts.items():
        if src in source:
            return host == expected or host.endswith("." + expected)
    return False


# An existing pre-order brought forward is NOT a new-order shipping delay.
_ADVANCE_TITLE_RE = re.compile(
    r"moving up|moved up|bump(?:ed|ing|s)? up|earlier deliver|"
    r"delivery dates? (?:improv|advanc)|배송.{0,15}앞당|배송.{0,15}단축|앞당겨", re.I)
_ADVANCE_DATE_RE = re.compile(
    r"\b(?:" + _MONTH_NAMES + r")\b(?:\s+\d{1,2})?(?:,?\s*20\d{2})?", re.I)
_ADVANCE_OLD_RE = re.compile(
    r"\b(?:initial(?:ly)?|original(?:ly)?|previous(?:ly)?|used\s+to|before)\b|"
    r"당초|기존|이전|처음", re.I)
_ADVANCE_NEW_RE = re.compile(
    r"\b(?:now|currently|earlier|moved\s+up|bumped\s+up)\b|앞당|현재|지금|변경", re.I)
_ADVANCE_MARKET_SPLIT_RE = re.compile(
    r"(?=(?:In the U\.S\.,|In the United States,|In Japan,|In South Korea,|"
    r"미국에서는|일본에서는|한국에서는))", re.I)


def _is_preorder_improvement_article(row: dict) -> bool:
    title = str(row.get("title") or "")
    return bool(("iphone duo" in title.lower() or "아이폰 듀오" in title)
                and _ADVANCE_TITLE_RE.search(title))


def _new_preorder_improvements(rows: list[dict], state: dict) -> list[dict]:
    """Require a direct publisher plus old/new dates of one existing customer.

    Historic seen_ids are scan receipts, not proof that an improvement was sent.
    """
    known = set(state.get("seen_improvement_fact_keys") or [])
    changes: list[dict] = []
    for row in rows:
        if not _is_preorder_improvement_article(row):
            continue
        if row.get("publisher_direct") is not True or _rank(row.get("source") or "") < 2:
            continue
        try:
            pub = dt.datetime.fromisoformat(row["published_at_kst"])
        except (KeyError, TypeError, ValueError):
            continue
        whole = f"{row.get('title') or ''}. {row.get('description') or ''}"
        for part in _ADVANCE_MARKET_SPLIT_RE.split(whole):
            header = part[:55].lower()
            if re.match(r"in the u\.s\.,|in the united states,|미국에서는", header):
                market = "미국"
            elif re.match(r"in japan,|일본에서는", header):
                market = "일본"
            elif re.match(r"in south korea,|한국에서는", header):
                market = "한국"
            else:
                continue
            tokens: list[dict] = []
            for match in _ADVANCE_DATE_RE.finditer(part):
                info = _month_and_day(match.group(0), pub, allow_launch=True)
                if info is None:
                    continue
                nearby = part[max(0,match.start()-65):match.end()+30].lower()
                if (re.search(r"\bpick.?up\b|\bwalk.?in\b|매장\s*수령|픽업", nearby)
                        and not re.search(r"deliver|ship|배송|배달", nearby)):
                    continue
                preceding = part[max(0,match.start()-105):match.start()]
                cues = ([(m.end(),"old") for m in _ADVANCE_OLD_RE.finditer(preceding)]
                        + [(m.end(),"new") for m in _ADVANCE_NEW_RE.finditer(preceding)])
                if not cues:
                    continue
                role = max(cues,key=lambda a:a[0])[1]
                year,month = (int(n) for n in info[0].split("-"))
                d = dt.date.fromisoformat(info[2] or f"{year:04d}-{month:02d}-01")
                tokens.append({
                    "start":match.start(),"end":match.end(),"month":info[0],"date":d,
                    "role":role,"first_day":d.day if info[2] else None,
                    "last_day":d.day if info[2] else None,"label":info[1],
                })
            merged: list[dict] = []
            for tok in tokens:
                if (merged and tok["month"]==merged[-1]["month"]
                        and tok["role"]==merged[-1]["role"]
                        and merged[-1]["last_day"] is not None
                        and tok["last_day"] is not None
                        and re.fullmatch(r"\s*(?:(?:to|through|and)|[-–—~])\s*",
                                         part[merged[-1]["end"]:tok["start"]],re.I)):
                    p=merged[-1]
                    p["end"]=tok["end"]
                    p["date"]=tok["date"]
                    p["last_day"]=tok["last_day"]
                    year,month=(int(n) for n in p["month"].split("-"))
                    p["label"]=f"{year}년 {month}월 {p['first_day']}~{p['last_day']}일"
                else:
                    merged.append(dict(tok))
            pairs=[]
            for old in merged:
                if old["role"]!="old":
                    continue
                for new in merged:
                    if new["role"]!="new":
                        continue
                    distance=abs(old["start"]-new["start"])
                    if distance>240 or new["date"]>=old["date"]:
                        continue
                    if (old["month"]==new["month"]
                            and (old["date"]-new["date"]).days<7):
                        continue
                    pairs.append((distance,old,new))
            pairs.sort(key=lambda p:p[0])
            used_old,used_new=set(),set()
            for _,old,new in pairs:
                if old["start"] in used_old or new["start"] in used_new:
                    continue
                used_old.add(old["start"]);used_new.add(new["start"])
                key=f"advance:{market}:{old['label']}->{new['label']}"
                if key in known:
                    continue
                known.add(key)
                excerpt=part[max(0,min(old["start"],new["start"])-65):
                             min(len(part),max(old["end"],new["end"])+50)]
                changes.append({
                    "market":market,"old":old["label"],"new":new["label"],
                    "item":row,"fact_key":key,"change_type":"기존 예약 배송 앞당김",
                    "eta_evidence":re.sub(r"\s+"," ",excerpt).strip()[:245],
                })
    state["seen_improvement_fact_keys"]=sorted(known)[-400:]
    return changes


def _preorder_improvement_alert(changes: list[dict]) -> str:
    lines=[
        "📦 <b>[iPhone Duo 기존 예약 배송 앞당김 | 언론 보도]</b>",
        "━━━━━━━━━━━━━━━━",
        "• 신규 주문이 아닌 일부 기존 예약자의 개별 배송 예상일 변화입니다.",
    ]
    if any(ch["item"].get("historical_recovery") for ch in changes):
        lines.append("• 2026년 10월 19일 기보도 내용을 누락 복구한 것으로, 오늘 새로 발생한 배송 변경이 아닙니다.")
    for ch in changes:
        row=ch["item"]
        lines.extend([
            f"• {html.escape(ch['market'])} / 구성·색상 별도 확인 필요: "
            f"{html.escape(ch['old'])} → {html.escape(ch['new'])}",
            f"  └ {html.escape(row.get('source') or '')} · "
            f"{html.escape(row.get('published_at_kst') or '')}",
            f"  └ 근거: {html.escape(ch['eta_evidence'])}",
            f'<a href="{html.escape(row.get("link") or "",quote=True)}">배송 앞당김 원문</a>',
        ])
    lines.extend([
        "• 다른 고객, 국가, 색상, 저장용량 또는 신규 주문 배송일로 일반화할 수 없습니다.",
        "• Apple 개별 주문의 실시간 배송일과 실제 출고·수령은 별도 확인 대상입니다.",
    ])
    return "\n".join(lines)+"\n"



_FUTURE_ETA_RE = re.compile(
    r"(?:new(?:ly)?\s+(?:online\s+)?orders?|신규\s*(?:온라인\s*)?주문)"
    r"[^.!?\n]{0,85}?(?:shipping|delivery|ships?|배송|출고)"
    r"[^.!?\n]{0,40}?"
    r"(?P<month>october|november|december|january|february|march|april|may|june|july|august|september)"
    r"\s+(?:(?P<day>\d{1,2}),?\s+)?(?P<year>20\d{2})\b", re.I
)


def _explicit_far_future_eta(blob: str, published: dt.datetime) -> dict | None:
    """Read only a dated future NEW-online-order delivery claim."""
    if not ("iphone duo" in blob.lower() or "아이폰 듀오" in blob):
        return None
    hit = _FUTURE_ETA_RE.search(blob)
    if hit is None:
        return None
    names = {month:idx for idx,month in enumerate((
        "january","february","march","april","may","june","july","august",
        "september","october","november","december"),1)}
    year = int(hit.group("year"))
    month = names[hit.group("month").lower()]
    day = int(hit.group("day")) if hit.group("day") else None
    try:
        when = dt.date(year,month,day or 1)
    except ValueError:
        return None
    if (when-published.date()).days <= 180 or (when-published.date()).days > 500:
        return None
    text = blob.lower()
    has_us = bool(re.search(r"(?:\bu\.s\.(?=\W|$)|\bunited states\b|\busa\b)",text))
    has_korea = bool(re.search(r"\b(?:korea|한국|대한민국)\b",text))
    market = "미국" if has_us and not has_korea else ("한국" if has_korea and not has_us else None)
    if not market:
        return None
    label = (f"{year}년 {month}월 {day}일" if day else
             f"{year}년 {month}월(정확한 일자 확인 불가)")
    return {
        "market":market,"month":f"{year:04d}-{month:02d}",
        "exact_date":when.isoformat() if day else None,
        "label":label,"capacity":"구성 미확인","colour":"색상 미확인",
        "eta_evidence":re.sub(r"\s+"," ",hit.group(0))[:175],
    }


def _needs_august_correction(state: dict) -> bool:
    return (
        not bool(state.get("false_august_correction_sent"))
        and any(
            entry.get("reported_month") == "2027-08"
            for entry in state.get("quarantined_delivery_claims") or []
        )
    )


def _august_correction_alert() -> str:
    return "\n".join([
        "📦 <b>[정정 | iPhone Duo 배송 예정일]</b>",
        "━━━━━━━━━━━━━━━━",
        "• 앞서 발송한 <b>'2027년 1월 → 2027년 8월 말'</b> 알림은 잘못된 날짜 추출이므로 취소합니다.",
        "• 해당 MacRumors 10월 17일 보도가 확인한 미국 온라인 신규 주문 배송 예정일은 "
        "<b>2027년 1월 25일</b>입니다.",
        "• 기사 속 <b>'지난 8월'</b>은 초기 생산량을 설명한 과거 시점이며 배송 예정일이 아닙니다.",
        "• <b>10월 24일</b>은 매장 수령 재고 확인 안내일로, 배송 지연 날짜가 아닙니다.",
        "• Apple 공식 출시일 <b>2026년 10월 23일</b>과 온라인 신규 주문 배송일을 분리합니다.",
        "• 1월 25일도 당시 미국 온라인 스토어에 관한 언론 보도이며,"
        " 한국 전 구성의 현재 배송일이나 실제 예약 대수로 일반화할 수 없습니다.",
        "",
        '<a href="https://www.macrumors.com/2026/10/17/staff-warn-against-iphone-duo-walk-ins/">'
        "MacRumors 원문</a>",
        f'<a href="{APPLE}">Apple 공식 출시 일정</a>',
    ]) + "\n"


def _initial_alert() -> str:
    return "\n".join([
        "📦 <b>[iPhone Duo 초기 예약·배송 지연 | 첫 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[공식 일정과 실시간 배송 추정치를 분리]</b>",
        "• Apple 공식: 2026년 10월 16일 21:00 KST 사전주문 시작, 10월 23일 정식 출시.",
        "• AppleInsider(21:07 KST): 초기 10월23일 수령분 소진, 주문 배송 예정일 11월16일→23일로 이동 보도.",
        "• MacRumors(21:22 KST): 미국 온라인 2색상×4저장용량(8개 구성)의 신규 주문 배송 견적 12월15~22일.",
        "• The Verge(약 22시 KST): 미국 온라인 신규 주문 배송 전망이 2027년 1월 말까지 이동했다고 보도.",
        "",
        "<b>[판정]</b>",
        "🟠 <b>초기 공급 가능 물량 대비 주문 집중·배송 장기화</b>",
        "• 초기 배송분 소진은 총주문 마감 아님. 신규 사전주문은 계속 가능하지만 배송이 늦어질 수 있습니다.",
        "• 배송 대기 증가 ≠ 실제 판매 대수·예상 대비 수요 증가율 확정.",
        "• Apple의 초기 재고 대수와 일 생산량이 공개되지 않아 수요 강세와 생산 부족의 기여도를 분리할 수 없습니다.",
        "• 위 배송 추정치는 언론사의 미국 온라인 주문 확인 보도이며, Apple 공식 지역별 동적 배송 견적을 직접 확인한 것은 아닙니다.",
        "• 공식 출시일 10월23일 변경과 신규 주문 배송 지연을 혼동하지 않습니다.",
        "",
        "<b>[후속 확인]</b>",
        "• 한국/미국·색상·저장용량·조회시각별 실제 배송일과 매장 픽업 재고",
        "• 7일 이상 추가 배송 지연, 2027년 2월 이후 확장, 배송기간 단축의 공식 확인",
        "• Foxconn 완제품 생산량·최종 조립 수율·힌지 품질·Samsung Display 추가 OLED 발주",
        "",
        f'<a href="{APPLE}">Apple 공식 사전예약·출시 일정</a>',
        f'<a href="{AI}">AppleInsider 초기 11월 배송 전망</a>',
        f'<a href="{MR}">MacRumors 미국 12월15~22일</a>',
        f'<a href="{VERGE}">The Verge 미국 2027년 1월 말</a>',
    ])+"\n"

def _request(url: str) -> bytes:
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/rss+xml,application/atom+xml,application/xml,text/html,*/*"})
    with urllib.request.urlopen(req,timeout=12) as r:
        return r.read(500000)

def _publisher_article_text(link: str, source: str) -> str:
    """Read a direct publisher's main article, never a Google redirect."""
    host=(urlparse(link).hostname or "").lower()
    permitted={
        "macrumors.com":("macrumors.com","www.macrumors.com"),
        "9to5mac":("9to5mac.com","www.9to5mac.com"),
        "appleinsider":("appleinsider.com","www.appleinsider.com"),
        "the verge":("theverge.com","www.theverge.com"),
    }
    prefix=next((name for name in permitted if name in source.lower()),None)
    if not prefix or host not in permitted[prefix]:
        return ""
    try:
        raw=_request(link).decode("utf-8",errors="replace")
    except Exception:
        return ""
    # Some sites use multiple article tags; read the main one only. Do not
    # mistake "related articles" and footer dates for current availability.
    block=re.search(r"<article\b[^>]*>(.*?)</article\s*>",raw,re.I|re.S)
    if not block:
        return ""
    value=re.sub(r"<(?:script|style|nav)[^>]*>.*?</(?:script|style|nav)>"," ",block.group(1),flags=re.I|re.S)
    return _clean(value)[:16000]


def _recover_verified_oct19_advance(rows: list[dict], errors: list[str]) -> list[dict]:
    """Read original publisher pages. No unverified aggregator snippets."""
    sources = (
        ("MacRumors", OCT19_IMPROVEMENT,
         "Apple Starts Moving Up iPhone Duo Delivery Dates", "2026-10-20T04:31:00+09:00"),
        ("9to5Mac", OCT19_ALTERNATIVE,
         "Some iPhone Duo orders getting moved up to earlier dates", "2026-10-19T22:19:00+09:00"),
    )
    recovered=0
    for publisher,url,title,published in sources:
        full=_publisher_article_text(url,publisher)
        if not full:
            continue
        low=full.lower()
        if not ("iphone duo" in low and "delivery" in low):
            continue
        if publisher=="MacRumors" and "in the u.s." not in low:
            continue
        if publisher=="9to5Mac" and not ("japan" in low and "december" in low
                                         and "october 23" in low and "moved up" in low):
            continue
        rows.append({
            "title":title,"description":full,"source":publisher,"link":url,
            "published_at_kst":published,"publisher_direct":True,
            "historical_recovery":True,
        })
        recovered+=1
    if not recovered:
        errors.append("2026-10-19 preorder improvement original publisher texts unavailable")
    return rows


def _collect() -> tuple[list[dict],list[str]]:
    now=dt.datetime.now(KST)
    results:dict[str,dict]={}
    errors:list[str]=[]
    sources=[]
    for name,url in FEEDS:
        sources.append((name,url))
    for lang,q in QUERY:
        p={"q":q,"hl":"ko" if lang=="ko" else "en-US",
           "gl":"KR" if lang=="ko" else "US",
           "ceid":"KR:ko" if lang=="ko" else "US:en"}
        sources.append(("", "https://news.google.com/rss/search?"+urllib.parse.urlencode(p)))
    article_fetches=0
    for source_name,url in sources:
        try:
            root=ET.fromstring(_request(url))
        except Exception as e:
            errors.append(f"{source_name or '검색'}: {type(e).__name__}")
            continue
        nodes=root.findall(".//item")
        atom=False
        if not nodes:
            nodes=root.findall(".//{http://www.w3.org/2005/Atom}entry")
            atom=True
        for n in nodes[:60]:
            if atom:
                title=_clean(n.findtext("{http://www.w3.org/2005/Atom}title"))
                desc=_clean(n.findtext("{http://www.w3.org/2005/Atom}summary") or n.findtext("{http://www.w3.org/2005/Atom}content"))
                date_str=n.findtext("{http://www.w3.org/2005/Atom}published") or n.findtext("{http://www.w3.org/2005/Atom}updated")
                try:
                    pub=dt.datetime.fromisoformat((date_str or "").replace("Z","+00:00")).astimezone(KST)
                except Exception:
                    pub=None
                link_node=n.find("{http://www.w3.org/2005/Atom}link")
                link=(link_node.attrib.get("href") or "") if link_node is not None else ""
            else:
                title=_clean(n.findtext("title"))
                desc=_clean(n.findtext("description"))
                # Publisher-owned RSS content is first-party evidence. Ordinary
                # search snippets remain discovery-only and cannot trigger alerts.
                if source_name and _is_preorder_improvement_article({"title":title}):
                    encoded=n.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                    if encoded and ("iphone duo" in encoded.lower() or "아이폰 듀오" in encoded):
                        desc=_clean(encoded)[:16000]
                pub=_date(n.findtext("pubDate"))
                link=_clean(n.findtext("link"))
            source_tag=n.find("source")
            source=source_name or _clean(source_tag.text if source_tag is not None else "")
            if not title or not pub or pub < PREORDER or pub > now+dt.timedelta(minutes=15):
                continue
            if pub < now-dt.timedelta(days=14):
                continue
            blob=f"{title} {desc}".lower()
            if not ("iphone duo" in blob or "아이폰 듀오" in blob):
                continue
            if _rank(source)<2 or not any(k in blob for k in ("preorder","pre-order","shipping","delivery","ship","sold out","backorder","배송","예약","품절","출고")):
                continue
            if (source_name and article_fetches < 5 and
                    (_month_and_day(title+" "+desc,pub) is None
                     or (_is_preorder_improvement_article({"title":title})
                         and len(_ADVANCE_DATE_RE.findall(title+" "+desc)) < 2))):
                article_fetches+=1
                full=_publisher_article_text(link,source_name)
                if full and ("iphone duo" in full.lower() or "아이폰 듀오" in full.lower()):
                    desc=full
            row={"title":title,"description":desc,"source":source,"link":link,
                 "published_at_kst":pub.isoformat(timespec="seconds")}
            row["publisher_direct"] = _direct_publisher_link(row)
            results[_fingerprint(row)]=row
    return sorted(results.values(),key=lambda x:x["published_at_kst"]),errors


def _sanitize_delivery_state(val: dict) -> dict:
    # Quarantine claims unsupported by the publisher's article (2027-08 was
    # incorrectly inferred from a historical "late August" production passage).
    val.setdefault("quarantined_delivery_claims", [])
    cutoff = PREORDER.date() + dt.timedelta(days=180)
    verified=set(val.get("verified_extended_months") or [])
    def impossible_month(month: str,market: str = "") -> bool:
        if market and f"{market}:{month}" in verified:
            return False
        try:
            d=dt.date.fromisoformat(str(month)[:7]+"-01")
        except Exception:
            return False
        return d > cutoff or str(month)=="2027-08"
    latest = val.setdefault("market_latest", {"미국": "2027-01"})
    for key, month in list(latest.items()):
        if month and impossible_month(str(month),key):
            if not any(x.get("market") == key and x.get("reported_month") == month
                       for x in val["quarantined_delivery_claims"]):
                val["quarantined_delivery_claims"].append({
                    "market": key, "reported_month": month,
                    "reason": "No delivery ETA in verified direct publisher article",
                })
            latest[key] = "2027-01" if key == "미국" else None
    for name in ("market_sku_latest",):
        values = val.setdefault(name, {})
        for key, month in list(values.items()):
            if month and impossible_month(str(month),key.split("|")[0]):
                values.pop(key, None)
    for name in ("market_day_latest", "market_sku_day_latest"):
        dates = val.setdefault(name, {})
        for key, date_str in list(dates.items()):
            try:
                date = dt.date.fromisoformat(str(date_str))
            except ValueError:
                dates.pop(key, None)
                continue
            if (date > cutoff and
                    f"{key.split('|')[0]}:{date.strftime('%Y-%m')}" not in verified):
                dates.pop(key, None)
    val["seen_fact_keys"] = [
        key for key in val.get("seen_fact_keys", [])
        if not any(impossible_month(month,str(key).split("|")[0].split(":")[0])
                   for month in re.findall(r"20\d{2}-\d{2}",str(key)))
    ]
    val["schema_version"] = max(int(val.get("schema_version") or 1), 2)
    return val


def _merge_delivery_state(remote: dict, local: dict) -> dict:
    newer = local if str(local.get("updated_at_kst") or "") >= str(remote.get("updated_at_kst") or "") else remote
    older = remote if newer is local else local
    merged = dict(older)
    merged.update(newer)
    merged["initial_alert_sent"] = bool(remote.get("initial_alert_sent") or local.get("initial_alert_sent"))
    merged["false_august_correction_sent"] = bool(
        remote.get("false_august_correction_sent") or local.get("false_august_correction_sent")
    )
    for key in ("seen_ids", "seen_fact_keys", "seen_improvement_fact_keys", "verified_extended_months"):
        merged[key] = sorted(set(remote.get(key) or []) | set(local.get(key) or []))[-1800:]
    # Preserve quarantine and audit history across concurrent scan commits.
    audit = list(remote.get("quarantined_delivery_claims") or [])
    for entry in local.get("quarantined_delivery_claims") or []:
        if entry not in audit:
            audit.append(entry)
    merged["quarantined_delivery_claims"] = audit[-25:]
    return _sanitize_delivery_state(merged)


def _load() -> dict:
    if not STATE_PATH.exists():
        return {"schema_version":1,"initial_alert_sent":False,
                "seen_ids":[],"seen_fact_keys":[],"baseline":BASELINE,
                "market_latest":{"미국":"2027-01"}}
    try:
        val=json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError("Preorder delivery state corrupt; fail closed to prevent duplicate alert") from e
    if not isinstance(val,dict):
        raise RuntimeError("Preorder delivery state invalid; fail closed")
    val.setdefault("seen_ids",[])
    val.setdefault("seen_fact_keys",[])
    val.setdefault("seen_improvement_fact_keys", [])
    val.setdefault("market_latest",{"미국":"2027-01"})
    val.setdefault("market_day_latest",{})
    val.setdefault("market_sku_day_latest",{})
    return _sanitize_delivery_state(val)

def _new_delivery_signals(rows: list[dict], state: dict) -> tuple[list[dict],set[str]]:
    seen=set(state.get("seen_ids") or [])
    known=set(state.get("seen_fact_keys") or [])
    latest=dict(state.get("market_latest") or {})
    sku_latest=dict(state.get("market_sku_latest") or {})
    sku_dates=dict(state.get("market_sku_day_latest") or {})
    market_dates=dict(state.get("market_day_latest") or {})
    new=[]

    # A very distant shipment report must be tied to two different direct
    # publisher domains. Identical RSS reposts do not count as corroboration.
    future_sources: dict[tuple[str,str],set[str]]={}
    for report in rows:
        if (report.get("publisher_direct") is not True
                or _rank(report.get("source") or "") < 2
                or _is_preorder_improvement_article(report)):
            continue
        try:
            published=dt.datetime.fromisoformat(report["published_at_kst"])
        except (KeyError,TypeError,ValueError):
            continue
        body=f"{report.get('title') or ''}. {report.get('description') or ''}"
        candidate=_explicit_far_future_eta(body,published)
        if candidate:
            domain=(urlparse(report.get("link") or "").hostname or "").lower().removeprefix("www.")
            if domain:
                future_sources.setdefault((candidate["market"],candidate["month"]),set()).add(domain)
    for row in rows:
        if _is_preorder_improvement_article(row):
            seen.add(_fingerprint(row))
            continue
        fp=_fingerprint(row)
        if fp in seen:
            continue
        seen.add(fp)
        # Publisher's direct first-party feed or article link is mandatory.
        # RSS snippets behind Google News redirects are search context only.
        if row.get("publisher_direct") is False:
            continue
        body=f"{row['title']}. {row.get('description','')}"
        pub=dt.datetime.fromisoformat(row["published_at_kst"])
        info=_shipping_event(body,pub)
        if info is None and row.get("publisher_direct") is True:
            far=_explicit_far_future_eta(body,pub)
            if far and len(future_sources.get((far["market"],far["month"]),set()))>=2:
                info=far
                confirmed=set(state.get("verified_extended_months") or [])
                confirmed.add(f"{far['market']}:{far['month']}")
                state["verified_extended_months"]=sorted(confirmed)
        if info is None:
            continue
        market=info["market"]
        # Unspecified region cannot be used to upgrade a US or KR delivery ETA.
        if market=="지역 미확인":
            continue
        scope=f"{market}|{info['capacity']}|{info['colour']}"
        fingerprint=f"{scope}:{info['exact_date'] or info['month']}"
        if fingerprint in known:
            continue
        sku_specific=info["capacity"]!="구성 미확인"
        prior=sku_latest.get(scope) if sku_specific else latest.get(market)
        if prior is None and sku_specific:
            prior=latest.get(market)
        previous_date=sku_dates.get(scope) if sku_specific else market_dates.get(market)
        current_date=info["exact_date"]
        # Prior later-month report is not invalidated by an earlier ETA from
        # another colour or capacity variant. This is a *later* ETA watch.
        advanced_month=prior is None or info["month"]>prior
        advanced_day=False
        if prior==info["month"] and current_date and previous_date:
            try:
                diff=(dt.date.fromisoformat(current_date)-dt.date.fromisoformat(previous_date)).days
                advanced_day=diff>=7
            except ValueError:
                advanced_day=False
        if not advanced_month and not advanced_day:
            continue
        if _rank(row.get("source") or "")<2:
            continue
        info.update({"item":row,"previous_month":prior,"previous_date":previous_date,
                     "fact_key":fingerprint,"change_type":"추가 배송 지연"})
        new.append(info)
        known.add(fingerprint)
        if latest.get(market) is None or info["month"]>latest[market]:
            latest[market]=info["month"]
        if sku_specific:
            sku_latest[scope]=info["month"]
            if current_date:
                sku_dates[scope]=current_date
            else:
                sku_dates.pop(scope,None)
        else:
            if current_date:
                market_dates[market]=current_date
            else:
                market_dates.pop(market,None)
    state["market_latest"]=latest
    state["market_sku_latest"]=sku_latest
    state["market_day_latest"]=market_dates
    state["market_sku_day_latest"]=sku_dates
    state["seen_fact_keys"]=sorted(known)[-400:]
    return new,seen

def _update_alert(changes: list[dict]) -> str:
    lines=["📦 <b>[iPhone Duo 사전주문 배송 추정 변경]</b>","━━━━━━━━━━━━━━━━",
           "🟠 <b>기존 배송 예상보다 추가 지연 보도</b>"]
    for ch in changes[:3]:
        row=ch["item"]
        lines += [
            f"• {html.escape(ch['market'])} / {html.escape(ch['capacity'])} / {html.escape(ch['colour'])}: "
            f"{html.escape(ch.get('previous_month') or '이전 수치 없음')} → {html.escape(ch['label'])}",
            f"  └ {html.escape(row['source'])} · {html.escape(row['published_at_kst'])}",
            f"  └ 배송일 관련 근거 문장: {html.escape(ch.get('eta_evidence') or '원문 추가 확인 필요')}",
            f'<a href="{html.escape(row.get("link") or "",quote=True)}">배송 전망 원문</a>',
        ]
    lines += ["","• 배송일은 국가·색상·저장용량·조회시각별로 달라질 수 있습니다.",
              "• 예약 대기 확대는 수요와 초기 공급의 합성 지표로, 실제 예약 대수나 공식 출시 연기를 뜻하지 않습니다.",
              "• Apple 주문 구성별 원문 배송일의 직접 확인 전에는 '언론 보도' 단계입니다."]
    return "\n".join(lines)+"\n"

def _append(alert: str) -> None:
    text=TELEGRAM.read_text(encoding="utf-8").strip() if TELEGRAM.exists() else ""
    TELEGRAM.write_text((text+"\n\n━━━━━━━━━━━━━━━━\n\n" if text else "")+alert,encoding="utf-8")

def main() -> None:
    now=dt.datetime.now(KST)
    state=_load()
    state.setdefault("retail_launch_benchmark", RETAIL_LAUNCH_BENCHMARK)
    rows,errors=_collect()
    if state.get("initial_alert_sent") and not state.get("seen_improvement_fact_keys"):
        rows=_recover_verified_oct19_advance(rows,errors)
    first=not state.get("initial_alert_sent")
    alerts=[]
    improvements=[]
    if first:
        alerts.append(_initial_alert())
        state["initial_alert_sent"]=True
        state["market_latest"]={"미국":"2027-01"}
        state["market_sku_latest"]={}
        state["market_day_latest"]={}
        state["market_sku_day_latest"]={}
        state["baseline"]=BASELINE
        state["seen_ids"]=sorted(set(state.get("seen_ids") or []) | {_fingerprint(x) for x in rows})[-800:]
        state["seen_fact_keys"]=sorted(set(state.get("seen_fact_keys") or []) | {"미국:2026-11","미국:2026-12","미국:2027-01","initial_launch_allocation"})[-400:]
    else:
        updates,seen=_new_delivery_signals(rows,state)
        state["seen_ids"]=sorted(seen)[-800:]
        improvements=_new_preorder_improvements(rows,state)
        if updates:
            alerts.append(_update_alert(updates))
        if improvements:
            alerts.append(_preorder_improvement_alert(improvements))
    state=_sanitize_delivery_state(state)
    correction_pending = _needs_august_correction(state)
    if correction_pending:
        alerts.append(_august_correction_alert())
        state["false_august_correction_sent"] = True
        state["august_false_alert_corrected_at_kst"] = now.isoformat(timespec="seconds")
    state.update({"schema_version":2,"updated_at_kst":now.isoformat(timespec="seconds"),
                  "last_scan_items":len(rows),"errors":errors[-20:],
                  "last_signal_count":(len(updates)+len(improvements)) if not first else 0,
                  "last_alert":{"at_kst":now.isoformat(timespec="seconds"),
                                "kind":"correction" if correction_pending else ("baseline" if first else
                                          ("delivery_advance" if improvements and not updates else "extension"))}
                                if alerts else state.get("last_alert")})
    PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if alerts:
        txt="\n\n".join(alerts)
        FRAGMENT.write_text(txt,encoding="utf-8")
        _append(txt)
    elif FRAGMENT.exists():
        FRAGMENT.unlink()
    STATUS.write_text("# 아이폰 듀오 예약·배송 추적\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- initial_alert_pending: {str(first).lower()}\n"
        f"- checked_news: {len(rows)}\n"
        f"- new_changes: {len(alerts)-(1 if first else 0)}\n"
        f"- country_shipping_latest: {json.dumps(state.get('market_latest'),ensure_ascii=False)}\n"
        f"- failed_queries: {len(errors)}\n",
        encoding="utf-8")

if __name__=="__main__":
    main()
