#!/usr/bin/env python3
"""Watch official Treasury long-end buyback policy and special announcements.

Alerts only on material policy changes affecting the 10Y-20Y or 20Y-30Y
nominal liquidity-support buyback program. It watches both the quarterly
schedule and TreasuryDirect SPL special-announcement PDFs so an intra-quarter
change is not missed while the tentative schedule still shows its old values.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pypdf import PdfReader

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE = DATA / "treasury_buyback_policy_state.json"
NEXT_STATE = DATA / "treasury_buyback_policy_state_next.json"
ALERT = OUT / "treasury_buyback_policy_alert.html"
TITLE = OUT / "treasury_buyback_policy_title.txt"
DETAIL = OUT / "treasury_buyback_policy_detail.json"
STATUS = OUT / "treasury_buyback_policy_status.md"

BUYBACK_PAGE = "https://treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
SCHEDULE_PDF = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.pdf"
FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
FRED_FX = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"
SPECIAL_TEMPLATE = "https://www.treasurydirect.gov/instit/annceresult/press/preanre/{year}/SPL_{ymd}_{n}.pdf"

BUCKETS = ("10Y to 20Y", "20Y to 30Y")
DEFAULT_BASELINE_BN = 2.0


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/1.1"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def maybe_fetch(url: str) -> bytes | None:
    try:
        return fetch_bytes(url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_bucket_maxima(text: str) -> dict[str, list[float]]:
    clean = re.sub(r"\s+", " ", text)
    out: dict[str, list[float]] = {bucket: [] for bucket in BUCKETS}
    for bucket in BUCKETS:
        for m in re.finditer(re.escape(bucket), clean, flags=re.I):
            window = clean[m.end() : m.end() + 280]
            amount = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*billion", window, flags=re.I)
            if amount:
                out[bucket].append(float(amount.group(1)))
    return out


def latest_fx() -> tuple[float, str]:
    try:
        text = fetch_bytes(FRED_FX).decode("utf-8", errors="replace")
        rows = [line.strip().split(",") for line in text.splitlines()[1:] if "," in line]
        for date, value, *_ in reversed(rows):
            if value and value != ".":
                return float(value), date
    except Exception:
        pass
    return 1392.0, "fallback"


def fmt_krw(usd_bn: float, fx: float) -> str:
    trillion = usd_bn * fx / 1000.0
    return f"약 {trillion:,.2f}조원" if trillion >= 1 else f"약 {trillion * 10000:,.0f}억원"


def is_long_end_buyback_special(text: str) -> bool:
    clean = re.sub(r"\s+", " ", text).lower()
    if "buyback" not in clean:
        return False
    long_terms = (
        "10-year to 20-year",
        "10 year to 20 year",
        "10y to 20y",
        "20-year to 30-year",
        "20 year to 30 year",
        "20y to 30y",
        "long-end",
        "long end",
    )
    policy_terms = ("increase", "decrease", "double", "maximum", "liquidity support", "size")
    return any(x in clean for x in long_terms) and any(x in clean for x in policy_terms)


def special_amounts(text: str) -> list[float]:
    clean = re.sub(r"\s+", " ", text)
    vals: list[float] = []
    for raw in re.findall(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(billion|million)?", clean, flags=re.I):
        num = float(raw[0].replace(",", ""))
        unit = raw[1].lower()
        if unit == "million":
            num /= 1000.0
        elif unit == "":
            # Most special releases use full dollar values; convert if clearly > 1m.
            if num >= 1_000_000:
                num /= 1_000_000_000.0
            else:
                continue
        if 0.1 <= num <= 100:
            vals.append(num)
    return vals


def find_new_specials(state: dict) -> list[dict]:
    seen = set(state.get("seen_long_end_special_shas", []))
    found: list[dict] = []
    now_et = datetime.now(ET)
    # Treasury special releases are dated in ET. Scan today and the two prior
    # business/calendar days because indexing and workflow timing can lag.
    for delta in range(0, 3):
        day = now_et.date() - timedelta(days=delta)
        ymd = day.strftime("%Y%m%d")
        for n in range(1, 13):
            url = SPECIAL_TEMPLATE.format(year=day.year, ymd=ymd, n=n)
            raw = maybe_fetch(url)
            if not raw or not raw.startswith(b"%PDF"):
                continue
            sha = hashlib.sha256(raw).hexdigest()
            if sha in seen:
                continue
            try:
                text = pdf_text(raw)
            except Exception:
                continue
            if is_long_end_buyback_special(text):
                found.append({
                    "url": url,
                    "sha256": sha,
                    "date": day.isoformat(),
                    "text": re.sub(r"\s+", " ", text).strip(),
                    "amounts_bn": special_amounts(text),
                })
    return found


def build_common_body(fx: float, fx_date: str, source_url: str, change_lines: list[str], verdict: str) -> str:
    return "\n".join([
        "<b>쉽게 말하면</b>",
        f"🟢 {verdict}",
        "",
        "<b>무엇이 바뀌었나</b>",
        *change_lines,
        "• 대상은 10~20년·20~30년 구간의 <b>off-the-run 명목 이표채 유동성 지원 바이백</b>입니다.",
        "",
        "<b>금리 해석</b>",
        "• 재무부가 오래된 장기채를 더 많이 사서 소각할 수 있음 → 유통시장 장기채 공급 부담 완화 → 시장 유동성 개선 → 기간 프리미엄·10년/30년 금리 상승 압력을 일부 완화하는 방향입니다.",
        "• 장기금리 급등 국면에서는 장기 듀레이션 채권과 AI·성장주의 할인율에 단기적으로 우호적인 신호입니다.",
        "",
        "<b>중요한 오해 방지</b>",
        "• <b>신규 10년·20년·30년물 발행 확대가 아닙니다.</b> 기존에 유통 중인 비지표물 국채를 재무부가 되사는 조치입니다.",
        "• Fed의 QE가 아닙니다. 재무부의 부채관리 작업이라 은행 준비금을 새로 만드는 통화완화와 다릅니다.",
        "• 금액은 최대 매입 상한입니다. 실제 매입은 제시 물량·가격에 따라 상한보다 작거나 0일 수도 있습니다.",
        "",
        "<b>다음 확인</b>",
        "• 실제 매입액 / 총 제시액 / offer-to-max 비율",
        "• 20년·30년 입찰 꼬리와 간접낙찰 비중",
        "• 10년·30년 명목금리·실질금리가 실제로 내려오는지",
        "",
        f"환율 기준: FRED DEXKOUS {fx_date}, 1달러={fx:,.1f}원",
        f'<a href="{source_url}">원문</a> · <a href="{BUYBACK_PAGE}">바이백 공지·결과</a> · <a href="{FAQ}">바이백 설명</a>',
    ])


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, TITLE, DETAIL):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    state = load_state()
    raw = fetch_bytes(SCHEDULE_PDF)
    text = pdf_text(raw)
    maxima = parse_bucket_maxima(text)
    schedule_sha = hashlib.sha256(raw).hexdigest()
    fx, fx_date = latest_fx()

    current: dict[str, float | None] = {}
    for bucket in BUCKETS:
        vals = maxima.get(bucket) or []
        current[bucket] = max(vals) if vals else None

    previous = state.get("long_end_max_bn") or {bucket: DEFAULT_BASELINE_BN for bucket in BUCKETS}
    schedule_changes: list[dict] = []
    for bucket in BUCKETS:
        cur = current.get(bucket)
        prev = float(previous.get(bucket, DEFAULT_BASELINE_BN))
        if cur is not None and abs(cur - prev) > 1e-9:
            schedule_changes.append({"bucket": bucket, "previous_bn": prev, "current_bn": cur})

    specials = find_new_specials(state)
    checked = datetime.now(KST).isoformat(timespec="seconds")
    next_state = {
        **state,
        "last_checked_kst": checked,
        "schedule_sha256": schedule_sha,
        "long_end_max_bn": {k: (v if v is not None else previous.get(k, DEFAULT_BASELINE_BN)) for k, v in current.items()},
    }

    detail: dict | None = None
    if specials:
        sp = specials[0]
        amounts = sorted(set(sp.get("amounts_bn") or []))
        amount_text = ", ".join(f"${x:g}B" for x in amounts) if amounts else "공식 특별공지 본문 참조"
        change_lines = [
            f"• 미 재무부 TreasuryDirect <b>특별공지</b>에서 장기물 바이백 정책 변경 감지",
            f"• 공지에서 확인된 금액 후보: {amount_text}",
        ]
        # If $2B and >=$4B are both present, explain the doubling explicitly.
        if 2.0 in amounts and any(x >= 4.0 for x in amounts):
            hi = min(x for x in amounts if x >= 4.0)
            change_lines.append(f"• 회당 최대 $2B({fmt_krw(2.0, fx)}) → 최소 ${hi:g}B({fmt_krw(hi, fx)})로 확대")
        body = build_common_body(
            fx,
            fx_date,
            sp["url"],
            change_lines,
            "장기물 바이백 특별공지입니다. 재무부가 신규 장기채를 더 찍는 것이 아니라 기존 장기채를 더 적극적으로 흡수하는 방향이라 장기물 수급에는 우호적입니다.",
        )
        detail = {"type": "special_announcement", "special": sp, "fx": fx, "fx_date": fx_date, "checked_kst": checked}
        next_state["pending_special_sha"] = sp["sha256"]
    elif schedule_changes:
        increases = [c for c in schedule_changes if c["current_bn"] > c["previous_bn"]]
        verdict = (
            "장기물 바이백 상한 확대입니다. 신규 장기채 발행 확대가 아니라 기존 장기채 흡수가 늘어나는 방향이라 장기물 수급에 우호적입니다."
            if increases else
            "장기물 바이백 상한 축소입니다. 재무부의 유동성 지원이 줄어드는 방향이라 장기물 수급에는 부담입니다."
        )
        change_lines = []
        for c in schedule_changes:
            change_lines.append(
                f"• {c['bucket']}: 회당 최대 ${c['previous_bn']:g}B → ${c['current_bn']:g}B "
                f"({fmt_krw(c['previous_bn'], fx)} → {fmt_krw(c['current_bn'], fx)})"
            )
        body = build_common_body(fx, fx_date, SCHEDULE_PDF, change_lines, verdict)
        detail = {"type": "schedule_change", "changes": schedule_changes, "fx": fx, "fx_date": fx_date, "checked_kst": checked}
        next_state["pending_schedule_change"] = schedule_changes

    if detail is not None:
        TITLE.write_text("🇺🇸 미 재무부 장기채 바이백 정책 변경\n", encoding="utf-8")
        ALERT.write_text(body[:4096].rstrip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# 미 재무부 장기채 바이백 정책 점검\n\n"
        f"- 조회시각: {checked}\n"
        f"- 10Y~20Y 일정상 최대: {current.get('10Y to 20Y')}B\n"
        f"- 20Y~30Y 일정상 최대: {current.get('20Y to 30Y')}B\n"
        f"- 신규 장기물 특별공지: {'예' if specials else '아니오'}\n"
        f"- 일정 자체 변경: {'예' if schedule_changes else '아니오'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
