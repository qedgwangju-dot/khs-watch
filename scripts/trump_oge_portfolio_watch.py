#!/usr/bin/env python3
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
from html import unescape

from pypdf import PdfReader

STATE_PATH = pathlib.Path("data/trump_oge_portfolio_watch_state.json")
EXPECTED_BOT_USERNAME = "khs887988798879_bot"
OGE_INDEX_URLS = [
    "https://extapps2.oge.gov/201/Presiden.nsf/PAS%20Filings%20by%20Date?OpenView&Start=1&Count=250",
    "https://extapps2.oge.gov/201/Presiden.nsf/PAS%20IndexA?OpenView&Start=1&Count=1000&Expand=1&RestrictToCategory=T",
]
# 2026-08-22 공개분. 첫 실행 때도 이 신고를 놓치지 않도록 시드로 유지한다.
SEED_CURRENT_URL = "https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/2BF91F890F718ACB85258E5B002DE16B/$FILE/Donald-J-Trump-08.12.2026-278T.pdf"

# 현행 OGE 거래금액 구간. 총 보유액이 아니라 '각 거래'의 신고 범위다.
AMOUNT_BANDS = [
    (1_001, 15_000),
    (15_001, 50_000),
    (50_001, 100_000),
    (100_001, 250_000),
    (250_001, 500_000),
    (500_001, 1_000_000),
    (1_000_001, 5_000_000),
    (5_000_001, 25_000_000),
    (25_000_001, 50_000_000),
]

COMMON_NAME_KR = {
    "VANGUARD DIVIDEND APPRECIATION": "뱅가드 배당성장 ETF(VIG)",
    "META PLATFORMS": "메타(META)",
    "MOTOROLA SOLUTIONS": "모토로라 솔루션즈(MSI)",
    "BERKSHIRE HATHAWAY": "버크셔 해서웨이(BRK.B)",
    "CINTAS": "신타스(CTAS)",
    "VISA": "비자(V)",
    "MASTERCARD": "마스터카드(MA)",
    "HOME DEPOT": "홈디포(HD)",
    "FIDELITY NATIONAL INFORMATION": "피델리티 내셔널 인포메이션 서비스(FIS)",
    "PALANTIR": "팔란티어(PLTR)",
    "RTX": "RTX(RTX)",
    "NORTHROP GRUMMAN": "노스럽그러먼(NOC)",
    "COINBASE": "코인베이스(COIN)",
    "ISHARES U.S. TREASURY": "아이셰어즈 미국 국채 ETF",
    "TECHNOLOGY SELECT SECTOR SPDR": "기술주 섹터 ETF(XLK)",
    "ISHARES GSCI COMMODITY": "아이셰어즈 원자재 ETF",
    "VANGUARD SHORT-TERM BOND": "뱅가드 단기채 ETF",
    "CONSUMER DISCRETIONARY SELECT SECTOR": "경기소비재 섹터 ETF(XLY)",
    "VANGUARD FTSE EUROPE": "뱅가드 유럽 ETF(VGK)",
}


def http_bytes(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 KHS Trump OGE Watch"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_text(url, timeout=30):
    return http_bytes(url, timeout).decode("utf-8", errors="replace")


def discover_trump_278t_urls():
    urls = {SEED_CURRENT_URL}
    for index_url in OGE_INDEX_URLS:
        try:
            html = http_text(index_url)
        except Exception as e:
            print(f"WARN OGE index fetch failed: {index_url}: {e}")
            continue

        # 직접 PDF 링크 우선
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            href = unescape(m.group(1))
            abs_url = urllib.parse.urljoin(index_url, href)
            low = urllib.parse.unquote(abs_url).lower()
            if "trump" in low and "278t" in low and ".pdf" in low:
                urls.add(abs_url)

        # Domino 문서 링크가 먼저 노출되는 경우 주변 문맥에 Trump가 있으면 한 단계 더 열어본다.
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            start = max(0, m.start() - 800)
            end = min(len(html), m.end() + 800)
            ctx = unescape(re.sub(r"<[^>]+>", " ", html[start:end]))
            if "Trump" not in ctx and "Donald J" not in ctx:
                continue
            href = unescape(m.group(1))
            abs_url = urllib.parse.urljoin(index_url, href)
            if ".pdf" in abs_url.lower():
                low = urllib.parse.unquote(abs_url).lower()
                if "278t" in low:
                    urls.add(abs_url)
                continue
            try:
                page = http_text(abs_url, timeout=15)
            except Exception:
                continue
            for pm in re.finditer(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', page, re.I):
                pdf_url = urllib.parse.urljoin(abs_url, unescape(pm.group(1)))
                low = urllib.parse.unquote(pdf_url).lower()
                if "trump" in low and "278t" in low:
                    urls.add(pdf_url)
    return sorted(urls)


def pdf_text(url):
    data = http_bytes(url, timeout=60)
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n".join(pages)


def clean_space(s):
    return re.sub(r"\s+", " ", s).strip()


def parse_money_band(s):
    nums = [int(x.replace(",", "")) for x in re.findall(r"\$?([\d,]+)", s)]
    if len(nums) >= 2:
        return nums[-2], nums[-1]
    return None


def extract_transactions(text):
    """Best-effort OGE 278-T parser. Keeps ranges intact; never invents exact amounts."""
    normalized = text.replace("–", "-").replace("—", "-")
    amount_re = re.compile(r"\$?\s*(1,001|15,001|50,001|100,001|250,001|500,001|1,000,001|5,000,001|25,000,001)\s*-\s*\$?\s*(15,000|50,000|100,000|250,000|500,000|1,000,000|5,000,000|25,000,000|50,000,000)", re.I)
    out = []
    last_end = 0
    for m in amount_re.finditer(normalized):
        chunk = normalized[max(last_end, m.start() - 700):m.end()]
        last_end = m.end()
        low, high = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
        dates = re.findall(r"\b(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/(?:20)?\d{2}\b", chunk)
        date = dates[-1] if dates else ""
        # 날짜 직전의 P/S/B/Sale/Purchase 표기 추정
        action = "거래"
        tail = chunk[-350:]
        if re.search(r"\b(P|Purchase|Buy)\b.{0,80}" + re.escape(date), tail, re.I) if date else re.search(r"\b(Purchase|Buy)\b", tail, re.I):
            action = "매수"
        if re.search(r"\b(S|Sale|Sell)\b.{0,80}" + re.escape(date), tail, re.I) if date else re.search(r"\b(Sale|Sell)\b", tail, re.I):
            action = "매도"
        # 행 앞쪽에서 설명을 추정. 폼 헤더/금액/날짜를 제거한다.
        desc = chunk
        desc = re.sub(r"OGE Form 278-T.*?Transactions", " ", desc, flags=re.I | re.S)
        desc = re.sub(r"\$?[\d,]+\s*-\s*\$?[\d,]+", " ", desc)
        if date:
            desc = desc.replace(date, " ")
        desc = re.sub(r"\b(Purchase|Sale|Buy|Sell|P|S)\b", " ", desc, flags=re.I)
        desc = clean_space(desc)
        # 너무 긴 경우 마지막 180자만 사용
        if len(desc) > 180:
            desc = desc[-180:]
        out.append({"action": action, "date": date, "low": low, "high": high, "description": desc})
    return out


def kr_name(desc):
    u = desc.upper()
    for needle, name in COMMON_NAME_KR.items():
        if needle in u:
            return name
    # ticker-like bracketed identification이 있으면 원문 식별을 보존
    return clean_space(desc)


def fx_rate():
    from fx_api import daily_krw
    q = daily_krw()
    return q.rate, q.basis


def usd_range(low, high):
    def f(v):
        if v >= 1_000_000:
            return f"{v/1_000_000:g}백만달러"
        if v >= 1_000:
            return f"{v/1_000:g}천달러"
        return f"{v:g}달러"
    return f"{f(low)}~{f(high)}"


def krw_range(low, high, rate):
    a, b = low * rate, high * rate
    def f(v):
        if v >= 1_000_000_000_000:
            return f"{v/1_000_000_000_000:,.2f}조원"
        if v >= 100_000_000:
            return f"{v/100_000_000:,.1f}억원"
        return f"{v/10_000:,.0f}만원"
    return f"약 {f(a)}~{f(b)}"


def total_range(txs):
    return sum(x["low"] for x in txs), sum(x["high"] for x in txs)


def curated_seed_message(url, rate, basis):
    # 2026-08-22 공개분은 OGE 신고 + 복수 보도에서 교차확인된 핵심값을 고정한다.
    lines = [
        "📊 [트럼프 OGE 포트폴리오 거래 새 신고]",
        "공시 주체: 도널드 트럼프 미국 대통령",
        "공시 종류: OGE Form 278-T(정기 거래 신고)",
        f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
        "",
        "▶ 2026년 6월 거래 총괄",
        f"• 거래건수: 1,051건",
        f"• 신고 거래총액 범위: 7,810만~2억6,310만달러 ({krw_range(78_100_000, 263_100_000, rate)})",
        "• 주의: 위 금액은 6월 거래액 범위 합계이며 전체 보유자산 규모가 아닙니다.",
        "",
        "▶ 주요 매도",
        f"• 뱅가드 배당성장 ETF(VIG): 500만~2,500만달러 매도 ({krw_range(5_000_000, 25_000_000, rate)}) — 6월 22일, 단일 최대 거래",
        f"• 메타(META): 100만~500만달러 매도 ({krw_range(1_000_000, 5_000_000, rate)}) — 6월 18일",
        f"• 모토로라 솔루션즈(MSI): 100만~500만달러 매도 ({krw_range(1_000_000, 5_000_000, rate)}) — 6월 18일",
        "",
        "▶ 주요 매수",
        f"• 버크셔 해서웨이(BRK.B): 100만~500만달러 매수 ({krw_range(1_000_000, 5_000_000, rate)}) — 6월 18일",
        f"• 신타스(CTAS): 100만~500만달러 매수 ({krw_range(1_000_000, 5_000_000, rate)}) — 6월 18일",
        f"• 비자(V): 100만~500만달러 매수 ({krw_range(1_000_000, 5_000_000, rate)}) — 6월 18일",
        f"• 마스터카드(MA): 100만~500만달러 매수 ({krw_range(1_000_000, 5_000_000, rate)}) — 6월 18일",
        f"• 홈디포(HD)·피델리티 내셔널 인포메이션 서비스(FIS): 6월 22일 각각 100만~500만달러 매수 ({krw_range(1_000_000, 5_000_000, rate)})",
        "",
        "▶ 기타 확인 종목",
        "• 팔란티어(PLTR), RTX(RTX), 노스럽그러먼(NOC), 코인베이스(COIN), 미국 국채·기술주·원자재 ETF, 지방채 등에서 다수 매수·매도",
        "• 일부 종목은 같은 달 안에 매수와 매도가 모두 있어 단순 순매수로 해석하면 안 됩니다.",
        "",
        "▶ 해석 주의",
        "• OGE 278-T는 각 거래액을 정확한 액수가 아니라 법정 범위로 신고합니다.",
        "• 백악관/트럼프 측은 자산이 제3자 운용계좌·신탁 구조로 관리돼 대통령이 개별 거래를 지시하지 않는다는 입장입니다.",
        "• 주요 정책·시장 이벤트와 거래일이 겹쳐도 신고서만으로 인과관계나 내부정보 이용을 단정하지 않습니다.",
        f"OGE 원문: {url}",
    ]
    return "\n".join(lines)


def generic_message(url, txs, rate, basis):
    buys = [x for x in txs if x["action"] == "매수"]
    sells = [x for x in txs if x["action"] == "매도"]
    low, high = total_range(txs) if txs else (0, 0)
    lines = [
        "📊 [트럼프 OGE 포트폴리오 거래 새 신고]",
        "공시 주체: 도널드 트럼프 미국 대통령",
        "공시 종류: OGE Form 278-T(정기 거래 신고)",
        f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
        "",
    ]
    if txs:
        lines += [
            f"• 자동 추출 거래행: {len(txs)}건 (매수 {len(buys)} / 매도 {len(sells)} / 기타 {len(txs)-len(buys)-len(sells)})",
            f"• 자동 합산 신고범위: {usd_range(low, high)} ({krw_range(low, high, rate)})",
            "※ 자동 추출값은 OGE PDF 표 구조에 따라 일부 행이 누락될 수 있어 원문 링크를 함께 제공합니다.",
            "",
            "▶ 금액 상위 거래",
        ]
        top = sorted(txs, key=lambda x: (x["high"], x["low"]), reverse=True)[:12]
        for x in top:
            name = kr_name(x["description"])
            lines.append(f"• {x['date'] or '날짜 미추출'} | {x['action']} | {name} | {usd_range(x['low'], x['high'])} ({krw_range(x['low'], x['high'], rate)})")
    else:
        lines += [
            "• 새 OGE 278-T 신고는 확인했지만 PDF 표 자동 추출에 실패했습니다.",
            "• 거래내용은 원문에서 재확인해야 하며, 자동화는 이 경우 숫자를 추정하지 않습니다.",
        ]
    lines += [
        "",
        "※ 신고 거래액 범위는 전체 보유자산 규모가 아닙니다.",
        "※ 같은 종목의 매수·매도가 반복될 수 있어 개별 거래와 순포지션을 구분합니다.",
        f"OGE 원문: {url}",
    ]
    return "\n".join(lines)


def telegram_api(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode("utf-8") if params is not None else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=25) as r:
        payload = json.load(r)
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload["result"]


def verify_bot(token):
    me = telegram_api(token, "getMe")
    username = me.get("username", "")
    if username.lower() != EXPECTED_BOT_USERNAME.lower():
        raise RuntimeError(f"Telegram bot mismatch: expected @{EXPECTED_BOT_USERNAME}, got @{username or 'unknown'}")
    return username


def send_message(token, chat_id, text):
    current = ""
    chunks = []
    for line in text.splitlines(True):
        if len(current) + len(line) > 3800 and current:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current.strip():
        chunks.append(current.rstrip())
    for chunk in chunks:
        telegram_api(token, "sendMessage", {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"})


def filing_key(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def load_state():
    if not STATE_PATH.exists():
        return {"version": 1, "seen": [], "updated_at": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "seen": [], "updated_at": None}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    token = os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN") or os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID") or os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets missing")
    verify_bot(token)

    state = load_state()
    seen = set(state.get("seen", []))
    urls = discover_trump_278t_urls()
    new_urls = [u for u in urls if filing_key(u) not in seen]
    if not new_urls:
        print("No new Trump OGE 278-T filing; no Telegram message.")
        save_state(state)
        return

    rate, basis = fx_rate()
    for url in new_urls:
        key = filing_key(url)
        if urllib.parse.unquote(url).lower() == urllib.parse.unquote(SEED_CURRENT_URL).lower():
            msg = curated_seed_message(url, rate, basis)
        else:
            try:
                text = pdf_text(url)
                txs = extract_transactions(text)
            except Exception as e:
                print(f"WARN PDF parse failed {url}: {e}")
                txs = []
            msg = generic_message(url, txs, rate, basis)
        send_message(token, chat_id, msg)
        seen.add(key)

    state["seen"] = sorted(seen)
    save_state(state)


if __name__ == "__main__":
    main()
