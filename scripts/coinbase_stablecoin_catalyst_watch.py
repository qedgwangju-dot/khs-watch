#!/usr/bin/env python3
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "coinbase_stablecoin_catalyst_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PENDING_PATH = OUT_DIR / "coinbase_stablecoin_catalyst_pending_state.json"
ALERT_PATH = OUT_DIR / "coinbase_stablecoin_catalyst_telegram.txt"
STATUS_PATH = OUT_DIR / "coinbase_stablecoin_catalyst_status.md"

COINBASE_CITI_URL = "https://www.coinbase.com/blog/coinbase-brings-bank-grade-fiat-and-stablecoin-payments-to-businesses-in-collaboration-with-citi"
COINBASE_BLOG_LANDING = "https://www.coinbase.com/blog/landing"
COINBASE_USDC_URL = "https://www.coinbase.com/earn"
CFTC_DCO_URL = "https://www.cftc.gov/IndustryOversight/IndustryFilings/ClearingOrganizations?col=Status&dir=DESC"
CFTC_DCM_URL = "https://www.cftc.gov/IndustryOversight/IndustryFilings/TradingOrganizations?col=Organization&dir=ASC"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KHS-Coinbase-Stablecoin-Catalyst-Watch/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}

STRATEGIC_TITLE_RE = re.compile(
    r"(stablecoin|payments?|bank|clearing|derivatives?|CFTC|USDC|custody|institutional|merchant|"
    r"Citi|Visa|Mastercard|JPMorgan|financial services|settlement)",
    re.I,
)
STRATEGIC_ACTION_RE = re.compile(
    r"(partner|collaborat|launch|approval|approved|register|registration|designat|integrat|accept|"
    r"clearing|settlement|power|enable|bring|expand|acquire)",
    re.I,
)

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


@dataclass(frozen=True)
class Event:
    kind: str
    title: str
    url: str
    date: str
    source: str
    detail: str

    @property
    def key(self):
        raw = "|".join([self.kind, self.title, self.url, self.date, self.detail])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_text(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "ignore")


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_date_from_text(text):
    m = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
        r"(\d{1,2}),\s*(20\d{2})\b",
        text,
        re.I,
    )
    if not m:
        return ""
    month = MONTHS.get(m.group(1).lower())
    if not month:
        return ""
    return dt.date(int(m.group(3)), month, int(m.group(2))).isoformat()


def collect_citi_coinbase(errors):
    try:
        body = clean(BeautifulSoup(fetch_text(COINBASE_CITI_URL), "html.parser").get_text(" ", strip=True))
    except Exception as exc:
        errors.append(f"Coinbase-Citi: {exc}")
        return []
    required = [
        "Citi", "Virtual Account Wallet", "Coinbase Virtual Accounts",
        "Spring by Citi", "automatically convert",
    ]
    if not all(x.lower() in body.lower() for x in required):
        errors.append("Coinbase-Citi: official page opened but required partnership markers were incomplete")
        return []
    reward_note = ""
    try:
        earn = clean(BeautifulSoup(fetch_text(COINBASE_USDC_URL), "html.parser").get_text(" ", strip=True))
        if re.search(r"3\.75\s*%.*USDC|USDC.*3\.75\s*%", earn, re.I):
            reward_note = (
                " Coinbase 공개 Earn 페이지는 현재 USDC 3.75% 보상을 표시하지만, "
                "Citi 연계 기업계정에 동일 조건이 자동 적용되는지는 공식 협업 발표에 명시되지 않았습니다."
            )
    except Exception as exc:
        errors.append(f"Coinbase-USDC reward crosscheck: {exc}")
    date = parse_date_from_text(body) or "2026-09-28"
    detail = (
        "Coinbase가 Citi의 Virtual Account Wallet(가상계좌 지갑)을 Coinbase Virtual Accounts에 연결해 "
        "들어오는 법정화폐를 스테이블코인으로 자동 전환하고, Citi 기관고객은 Spring by Citi에서 "
        "Coinbase 결제 인프라를 통해 스테이블코인 결제를 받을 수 있게 됐습니다." + reward_note
    )
    return [Event(
        "citi_coinbase_stablecoin_payments",
        "Citi·Coinbase, 기업 결제망과 스테이블코인 결제 인프라 직접 연결",
        COINBASE_CITI_URL,
        date,
        "Coinbase 공식 발표",
        detail,
    )]


def extract_coinbase_clearing_row(text):
    text = clean(text)
    head = re.search(
        r"Coinbase Clearing LLC\s+(Registered|Pending Registration)\s+(\d{2}/\d{2}/\d{4})\s+",
        text,
        re.I,
    )
    if not head:
        return None
    tail = text[head.end(): head.end() + 900]
    next_row = re.search(
        r"\s+[A-Z][A-Za-z0-9 .,&'()/-]{2,100}\s+"
        r"(?:Registered|Pending Registration|Exempt|Dormant|Vacated)\s+\d{2}/\d{2}/\d{4}\b",
        tail,
        re.I,
    )
    remarks = tail[: next_row.start()] if next_row else tail
    return {
        "status": clean(head.group(1)),
        "date": clean(head.group(2)),
        "remarks": clean(remarks),
    }


def collect_coinbase_dco(errors):
    try:
        body = clean(BeautifulSoup(fetch_text(CFTC_DCO_URL), "html.parser").get_text(" ", strip=True))
    except Exception as exc:
        errors.append(f"CFTC DCO: {exc}")
        return []
    row = extract_coinbase_clearing_row(body)
    if not row:
        errors.append("CFTC DCO: Coinbase Clearing LLC row not found")
        return []
    if row["status"].lower() != "registered":
        return []
    mm, dd, yyyy = map(int, row["date"].split("/"))
    date = dt.date(yyyy, mm, dd).isoformat()
    remarks = row["remarks"]
    if not re.search(r"fully collateralized.*futures.*options.*swaps", remarks, re.I):
        remarks = "CFTC 등록 완료. 완전담보 선물·선물옵션·스왑 청산 허용."
    dcm_context = ""
    try:
        dcm = clean(BeautifulSoup(fetch_text(CFTC_DCM_URL), "html.parser").get_text(" ", strip=True))
        if "Coinbase Derivatives, LLC" in dcm and "Designated" in dcm:
            dcm_context = " Coinbase Derivatives는 이미 DCM(지정계약시장)으로 지정돼 있습니다."
    except Exception as exc:
        errors.append(f"CFTC DCM crosscheck: {exc}")
    detail = (
        "CFTC가 Coinbase Clearing LLC를 DCO(파생상품청산기관)로 등록했습니다. "
        "CFTC 목록상 완전담보 선물, 선물옵션, 스왑을 청산할 수 있습니다."
        + dcm_context
        + " Coinbase Financial Markets의 FCM(선물중개업자) 기능과 함께 거래소·중개·청산의 규제 스택을 더 수직통합할 수 있는 기반입니다."
    )
    return [Event(
        "coinbase_clearing_dco_registered",
        "Coinbase Clearing LLC, CFTC DCO(파생상품청산기관) 등록 완료",
        CFTC_DCO_URL,
        date,
        "CFTC 공식 등록목록",
        detail,
    )]


def collect_recent_coinbase_blog(errors, today):
    events = []
    try:
        soup = BeautifulSoup(fetch_text(COINBASE_BLOG_LANDING), "html.parser")
    except Exception as exc:
        errors.append(f"Coinbase blog landing: {exc}")
        return events
    seen = set()
    for a in soup.find_all("a", href=True):
        title = clean(a.get_text(" ", strip=True))
        if len(title) < 12 or not STRATEGIC_TITLE_RE.search(title) or not STRATEGIC_ACTION_RE.search(title):
            continue
        href = urllib.parse.urljoin(COINBASE_BLOG_LANDING, a.get("href"))
        if "/blog/" not in href or href in seen or href == COINBASE_CITI_URL:
            continue
        seen.add(href)
        try:
            body = clean(BeautifulSoup(fetch_text(href), "html.parser").get_text(" ", strip=True))
        except Exception:
            continue
        date = parse_date_from_text(body)
        if not date:
            continue
        d = dt.date.fromisoformat(date)
        if (today - d).days < 0 or (today - d).days > 7:
            continue
        signal = f"{title} {body[:3000]}"
        if not (STRATEGIC_TITLE_RE.search(signal) and STRATEGIC_ACTION_RE.search(signal)):
            continue
        detail = clean(body[:900])
        events.append(Event(
            "coinbase_strategic_business_update",
            title,
            href,
            date,
            "Coinbase 공식 블로그",
            detail,
        ))
    return events


def event_summary(event):
    if event.kind == "citi_coinbase_stablecoin_payments":
        return (
            "한마디로: 스테이블코인이 거래소 안의 자산을 넘어 Citi의 기업 결제망과 직접 연결된 상용화 단계입니다. "
            "Coinbase에는 결제 인프라·법정화폐↔스테이블코인 전환·기업고객 관계라는 반복 수익 경로가 넓어질 수 있고, "
            "Circle에는 실제 결제에 USDC가 얼마나 쓰이는지가 핵심입니다."
        )
    if event.kind == "coinbase_clearing_dco_registered":
        return (
            "한마디로: Coinbase가 파생상품 거래를 연결하는 중개 기능뿐 아니라 거래소와 청산까지 CFTC 규제권 안에서 직접 통제할 수 있는 기반을 갖춘 것입니다. "
            "청산은 거래가 끝난 뒤 돈·담보·포지션을 실제로 맞춰주는 핵심 인프라라, 제3자 청산 의존도를 낮추고 상품 출시·담보·결제 구조를 더 직접 설계할 수 있게 됩니다."
        )
    return (
        "한마디로: Coinbase의 규제 인프라·결제·기관사업이 실제 상용화 단계에서 넓어진 변화입니다. "
        "현재 매출 발생 여부와 반복 수익 구조를 다음 실적에서 확인해야 합니다."
    )


def investment_lines(event):
    if event.kind == "citi_coinbase_stablecoin_payments":
        return [
            "돈 버는 능력: Coinbase의 거래수수료 외 수익원인 결제·전환·기업 인프라 사용량이 늘어날 수 있습니다.",
            "Circle/USDC: 공식 발표는 특정 스테이블코인을 고정하지 않았으므로 USDC 직접 수혜는 아직 확정이 아닙니다. 실제 결제·보관 잔액에서 USDC 비중을 확인해야 합니다.",
            "시간표: 미국에서 먼저 출시하며 추가 기능을 앞으로 수개월 동안 확대한다고 양사가 밝혔습니다.",
            "실패 경로: 기업 고객 채택이 느리거나 보상률·규제·회계·세무 부담 때문에 스테이블코인 잔액이 실제로 늘지 않으면 매출 효과가 제한됩니다.",
        ]
    if event.kind == "coinbase_clearing_dco_registered":
        return [
            "돈 버는 능력: 거래소(DCM)·중개(FCM)·청산(DCO)을 한 그룹 안에서 연결하면 외부 청산 의존도를 줄이고 파생상품 거래량에서 더 많은 경제성을 내부화할 가능성이 생깁니다.",
            "시간표: DCO 등록은 2026년 9월 28일 완료됐지만, 실제 Coinbase 상품이 새 청산소로 이전되는 시점과 상품별 승인은 별도로 확인해야 합니다.",
            "USDC: 사용자 제공 보도에는 USDC 담보·24/7 결제가 언급됐지만 CFTC 등록목록 요약 자체는 이를 확인하지 않습니다. 공식 규정·회사 원문을 추가 확인해야 합니다.",
            "실패 경로: 청산소 등록만 있고 거래량 이전·신상품·담보 효율 개선이 늦으면 단기 실적 기여는 작을 수 있습니다.",
        ]
    return [
        "돈 버는 능력: 실제 고객·거래량·잔액·수수료가 늘어나는지 확인합니다.",
        "시간표: 발표와 실제 출시·매출 인식을 분리합니다.",
        "실패 경로: 발표만 있고 고객 채택·거래량이 따라오지 않는 경우입니다.",
    ]


def build_alert(events):
    lines = ["<b>🔔 Coinbase·Stablecoin 사업 촉매</b>", ""]
    for idx, event in enumerate(events, 1):
        lines.extend([
            f"<b>{idx}. {html.escape(event.title)}</b>",
            "",
            f"<b>🧩 한마디로</b>",
            html.escape(event_summary(event)),
            "",
            "<b>✅ 확인된 사실</b>",
            "• " + html.escape(event.detail),
            "",
            "<b>💰 투자 의미</b>",
        ])
        for item in investment_lines(event):
            lines.append("• " + html.escape(item))
        lines.extend([
            "",
            "<b>⏱ 날짜</b>",
            f"• {html.escape(event.date)}",
            "",
            "<b>🔎 근거</b>",
            f"• {html.escape(event.source)}",
            f'• <a href="{html.escape(event.url, quote=True)}">원문</a>',
            "",
        ])
    lines.extend([
        "<b>🎯 핵심 한 줄 요약</b>",
        "Coinbase는 현물거래소 한 곳에서 결제·스테이블코인·파생상품·청산까지 금융 인프라를 넓히고 있으며, "
        "이번 Citi 결제 연결과 CFTC DCO 등록은 실제 사업 범위가 넓어진 사건입니다. 다만 발표·등록 자체와 실제 거래량·USDC 잔액·수수료 매출은 분리해서 확인합니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def main():
    today = dt.datetime.now(ZoneInfo("Asia/Seoul")).date()
    errors = []
    events = []
    events.extend(collect_citi_coinbase(errors))
    events.extend(collect_coinbase_dco(errors))
    events.extend(collect_recent_coinbase_blog(errors, today))
    events = list({e.key: e for e in events}.values())
    events.sort(key=lambda e: (e.date, e.kind, e.title))

    state = load_state()
    seen = set(state.get("seen_event_keys") or [])
    is_first_run = not bool(state)
    if is_first_run:
        cutoff = today - dt.timedelta(days=2)
        new_events = [e for e in events if e.date and dt.date.fromisoformat(e.date) >= cutoff]
    else:
        new_events = [e for e in events if e.key not in seen]

    merged = sorted(seen | {e.key for e in events})
    pending = {
        "initialized": True,
        "last_checked_kst": dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "seen_event_keys": merged[-1000:],
        "event_count": len(events),
        "source_errors": errors,
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if ALERT_PATH.exists():
        ALERT_PATH.unlink()
    if new_events:
        ALERT_PATH.write_text(build_alert(new_events), encoding="utf-8")

    STATUS_PATH.write_text(
        "\n".join([
            "# Coinbase·Stablecoin 사업 촉매 감시",
            "",
            f"- 확인 시각(KST): {pending['last_checked_kst']}",
            f"- 공식 사건 수: {len(events)}",
            f"- 신규 알림 대상: {len(new_events)}",
            f"- 첫 실행 백필: {'예' if is_first_run else '아니오'}",
            f"- 출처 오류: {'없음' if not errors else ' | '.join(errors[:6])}",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"coinbase_stablecoin_catalyst_new={len(new_events)} total={len(events)} first_run={is_first_run}")
    if errors:
        print("source_errors=" + " || ".join(errors[:6]))


if __name__ == "__main__":
    main()
