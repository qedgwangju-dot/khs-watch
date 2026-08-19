#!/usr/bin/env python3
"""Watch official Treasury buyback policy/schedule for material long-end changes.

This watcher is intentionally different from the normal per-operation buyback feed.
It alerts only when the 10Y-20Y or 20Y-30Y nominal liquidity-support maximum
changes versus the prior official schedule/baseline, because that changes long-end
secondary-market supply/liquidity and can matter for term premium.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pypdf import PdfReader

KST = ZoneInfo("Asia/Seoul")
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

BUCKETS = ("10Y to 20Y", "20Y to 30Y")
DEFAULT_BASELINE_BN = 2.0


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_bucket_maxima(text: str) -> dict[str, list[float]]:
    # pypdf generally extracts each schedule row in reading order. Allow enough
    # room for date/maturity fields but stop before a later table row.
    clean = re.sub(r"\s+", " ", text)
    out: dict[str, list[float]] = {bucket: [] for bucket in BUCKETS}
    for bucket in BUCKETS:
        for m in re.finditer(re.escape(bucket), clean, flags=re.I):
            window = clean[m.end() : m.end() + 260]
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
    return 1418.0, "fallback"


def krw_trillion(usd_bn: float, fx: float) -> float:
    # $1bn * KRW/USD -> KRW billion; divide by 1000 for KRW trillion.
    return usd_bn * fx / 1000.0


def fmt_krw(usd_bn: float, fx: float) -> str:
    v = krw_trillion(usd_bn, fx)
    if v >= 1:
        return f"약 {v:,.2f}조원"
    return f"약 {v * 10000:,.0f}억원"


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
    sha = hashlib.sha256(raw).hexdigest()
    fx, fx_date = latest_fx()

    current: dict[str, float | None] = {}
    for bucket in BUCKETS:
        vals = maxima.get(bucket) or []
        current[bucket] = max(vals) if vals else None

    previous = state.get("long_end_max_bn") or {bucket: DEFAULT_BASELINE_BN for bucket in BUCKETS}
    changes: list[dict] = []
    for bucket in BUCKETS:
        cur = current.get(bucket)
        prev = float(previous.get(bucket, DEFAULT_BASELINE_BN))
        if cur is not None and abs(cur - prev) > 1e-9:
            changes.append({"bucket": bucket, "previous_bn": prev, "current_bn": cur})

    checked = datetime.now(KST).isoformat(timespec="seconds")
    next_state = {
        **state,
        "last_checked_kst": checked,
        "schedule_sha256": sha,
        "long_end_max_bn": {k: (v if v is not None else previous.get(k, DEFAULT_BASELINE_BN)) for k, v in current.items()},
    }

    if changes:
        increases = [c for c in changes if c["current_bn"] > c["previous_bn"]]
        if increases:
            badge = "🟢"
            verdict = "장기물 수급에 우호적 — 신규 장기채 발행 확대가 아니라, 기존 장기채를 더 많이 흡수하는 바이백 상한 확대입니다."
        else:
            badge = "🔴"
            verdict = "장기물 수급에 부담 — 재무부의 장기물 유동성 지원 바이백 상한이 축소됐습니다."

        change_lines = []
        incremental_bn = 0.0
        for c in changes:
            delta = c["current_bn"] - c["previous_bn"]
            incremental_bn += max(delta, 0.0)
            change_lines.append(
                f"• {c['bucket']}: 회당 최대 ${c['previous_bn']:g}B → ${c['current_bn']:g}B "
                f"({fmt_krw(c['previous_bn'], fx)} → {fmt_krw(c['current_bn'], fx)})"
            )

        body = [
            "<b>쉽게 말하면</b>",
            f"{badge} {verdict}",
            "",
            "<b>무엇이 바뀌었나</b>",
            *change_lines,
            "• 대상은 10~20년·20~30년 구간의 <b>off-the-run 명목 이표채 유동성 지원 바이백</b>입니다.",
            "",
            "<b>금리 해석</b>",
            "• 재무부가 오래된 장기채를 더 많이 사서 소각할 수 있음 → 유통시장 장기채 공급 부담 완화 → 시장 유동성 개선 → 기간 프리미엄·10년/30년 금리의 상승 압력을 일부 완화하는 방향입니다.",
            "• 특히 장기채 금리가 급등하고 off-the-run 유동성이 약해진 국면에서는 단기적으로 장기 듀레이션 자산과 AI·성장주 할인율에 우호적인 신호입니다.",
            "",
            "<b>중요한 오해 방지</b>",
            "• 이것은 <b>신규 10년·20년·30년물 발행 규모 확대가 아닙니다.</b> 기존에 유통 중인 비지표물 국채를 재무부가 되사는 정책입니다.",
            "• Fed의 QE도 아닙니다. 재무부 부채관리 작업이며 은행 준비금을 새로 만드는 통화완화와는 다릅니다.",
            "• 발표 금액은 <b>최대 매입 상한</b>입니다. 실제 매입액은 제시 물량·가격에 따라 상한보다 작거나 0일 수도 있습니다.",
            "",
            "<b>다음 확인</b>",
            "• 실제 회당 매입액 / 총 제시액 / offer-to-max 비율",
            "• 20년·30년 입찰 꼬리와 간접낙찰 비중",
            "• 10년·30년 명목금리와 실질금리가 실제로 꺾이는지",
            "",
            f"환율 기준: FRED DEXKOUS {fx_date}, 1달러={fx:,.1f}원",
            f'<a href="{SCHEDULE_PDF}">원문</a> · <a href="{BUYBACK_PAGE}">바이백 공지·결과</a> · <a href="{FAQ}">바이백 설명</a>',
        ]
        title = "🇺🇸 미 재무부 장기채 바이백 정책 변경"
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text("\n".join(body)[:4096] + "\n", encoding="utf-8")
        DETAIL.write_text(
            json.dumps(
                {
                    "type": "treasury_buyback_policy_change",
                    "changes": changes,
                    "fx": fx,
                    "fx_date": fx_date,
                    "schedule_sha256": sha,
                    "checked_kst": checked,
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        # Mark as pending; workflow commits only after Telegram confirmation.
        next_state["pending_change"] = changes

    NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# 미 재무부 장기채 바이백 정책 점검\n\n"
        f"- 조회시각: {checked}\n"
        f"- 10Y~20Y 최대: {current.get('10Y to 20Y')}B\n"
        f"- 20Y~30Y 최대: {current.get('20Y to 30Y')}B\n"
        f"- 정책 변경 감지: {'예' if changes else '아니오'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
