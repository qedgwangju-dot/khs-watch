#!/usr/bin/env python3
"""Keep Treasury alerts Korean and verify Bessent's stated long-yield causal story with public data.

The official Treasury watcher owns policy detection. This layer:
1) keeps user-facing Treasury headlines in Korean,
2) adds the verified Bessent policy boundary (liquidity/volatility support, not yield control),
3) automatically checks Brent -> 10Y breakeven -> 10Y real yield -> 10Y nominal yield,
   with the Kim-Wright 10Y term premium as a lagged confirmation signal,
4) emits only a one-time upgrade or a later material verdict-regime change, avoiding duplicate rate alerts.
"""

from __future__ import annotations

import csv
import html as html_lib
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "treasury_buyback_policy_alert.html"
DETAIL = ROOT / "out" / "treasury_buyback_policy_detail.json"
TITLE = ROOT / "out" / "treasury_buyback_policy_title.txt"
STATE = ROOT / "data" / "treasury_buyback_policy_state.json"
NEXT_STATE = ROOT / "data" / "treasury_buyback_policy_state_next.json"

BESSENT_REUTERS = "https://www.reuters.com/business/bessent-pushes-back-fears-over-us-debt-market-strains-2026-08-31/"
BESSENT_FEVER = "https://news.bgov.com/bloomberg-government-news/bessent-says-buyback-move-aimed-at-quelling-market-fever-1"
BESSENT_OIL_SCENARIO = "https://www.worldoil.com/news/2026/9/4/bessent-sees-oil-falling-as-low-as-40-after-iran-war/"
TREASURY_RELEASE = "https://home.treasury.gov/news/press-releases/sb0607"
BUYBACK_FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
FRED_SERIES_PAGE = "https://fred.stlouisfed.org/series/{series}"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
EIA_BRENT_PAGE = "https://www.eia.gov/dnav/pet/hist/rbrteD.htm"
TREASURY_NOMINAL_XML = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
TREASURY_REAL_XML = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value={year}"
NYFED_TERM_PREMIA = "https://www.newyorkfed.org/research/data_indicators/term-premia-tabs"
NYFED_ACM_XLS = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"

SERIES = {
    "fx": "DEXKOUS",
    "term10": "THREEFYTP10",
}

UPGRADE_MARKER = "<b>정책 목적·경계선</b>"
UPGRADE_REVISION = 7
UA = "Mozilla/5.0 khs-watch-treasury-bessent-verifier/4.0"

EXACT_TITLES = {
    "Treasury Announces Increased Sizes of Nominal Long-End Liquidity Support Buybacks Beginning September 9":
        "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 확대 — 9월 9일 시행",
}


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _url_text(url: str, timeout: int = 12) -> str:
    last_error = None
    for _attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8-sig", errors="replace")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"자료 다운로드 실패: {url} / {type(last_error).__name__}: {last_error}")


def _parse_fred_txt(text: str, start: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    data_started = False
    for line in text.splitlines():
        stripped = line.strip()
        if not data_started:
            if re.match(r"^DATE\s+VALUE$", stripped):
                data_started = True
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        d, raw = parts[0], parts[1]
        if d < start or raw == ".":
            continue
        try:
            out.append((d, float(raw)))
        except ValueError:
            continue
    return out


def _parse_fred_csv(text: str) -> list[tuple[str, float]]:
    rows = list(csv.reader(io.StringIO(text)))
    out: list[tuple[str, float]] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        d, raw = row[0].strip(), row[1].strip()
        if not d or not raw or raw == ".":
            continue
        try:
            out.append((d, float(raw)))
        except ValueError:
            continue
    return out


def fetch_series(series_id: str, lookback_days: int = 120) -> list[tuple[str, float]]:
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    errors = []

    # Static FRED text files are materially faster/more reliable on GitHub-hosted runners.
    try:
        text = _url_text(f"https://fred.stlouisfed.org/data/{series_id}.txt", timeout=12)
        out = _parse_fred_txt(text, start)
        if len(out) >= 2:
            return out
        errors.append("txt: 유효 관측치 부족")
    except Exception as exc:
        errors.append(f"txt: {type(exc).__name__}: {exc}")

    # Fallback to graph CSV, but do not let one slow FRED endpoint hang the whole watcher.
    try:
        query = urllib.parse.urlencode({"id": series_id, "cosd": start})
        text = _url_text(f"{FRED_CSV}?{query}", timeout=12)
        out = _parse_fred_csv(text)
        if len(out) >= 2:
            return out
        errors.append("csv: 유효 관측치 부족")
    except Exception as exc:
        errors.append(f"csv: {type(exc).__name__}: {exc}")

    raise RuntimeError(f"FRED {series_id} 조회 실패: {' | '.join(errors)}")


class _EiaTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", html_lib.unescape(" ".join(self._cell))).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def fetch_eia_brent_rows() -> list[tuple[str, float]]:
    """Parse EIA's static daily Brent history table without an API key.

    Each history-table row is one Monday-Friday week, for example:
    "2026 Sep-28 to Oct- 2 | 119.97 | 113.96 | ...".
    Blank holiday cells are ignored. This endpoint is static HTML and is more
    reliable on GitHub runners than the FRED mirror that previously timed out.
    """
    raw = _url_text(EIA_BRENT_PAGE, timeout=15)
    parser = _EiaTableParser()
    parser.feed(raw)

    months = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    out: list[tuple[str, float]] = []
    pattern = re.compile(
        r"^(\d{4})\s+([A-Za-z]{3})-\s*(\d{1,2})\s+to\s+([A-Za-z]{3})-\s*(\d{1,2})$"
    )

    for row in parser.rows:
        if len(row) < 2:
            continue
        label = re.sub(r"\s+", " ", row[0]).strip()
        m = pattern.match(label)
        if not m:
            continue
        year = int(m.group(1))
        month = months.get(m.group(2).title())
        if month is None:
            continue
        try:
            monday = date(year, month, int(m.group(3)))
        except ValueError:
            continue

        for offset, cell in enumerate(row[1:6]):
            raw_value = cell.replace(",", "").strip()
            if not raw_value or raw_value in ("-", "--", "NA", "W"):
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue
            observed = monday + timedelta(days=offset)
            out.append((observed.isoformat(), value))

    out.sort(key=lambda x: x[0])
    if len(out) < 2:
        raise RuntimeError("EIA Brent 일일 역사표 파싱 실패")
    return out


def fetch_treasury_10y_rows(real: bool = False) -> list[tuple[str, float]]:
    year = date.today().year
    url = (TREASURY_REAL_XML if real else TREASURY_NOMINAL_XML).format(year=year)
    raw = _url_text(url, timeout=15)
    out: list[tuple[str, float]] = []
    for entry in re.findall(r"<entry>(.*?)</entry>", raw, flags=re.I | re.S):
        dm = re.search(r"<d:NEW_DATE[^>]*>([^<]+)</d:NEW_DATE>", entry, flags=re.I)
        field = "TC_10YEAR" if real else "BC_10YEAR"
        ym = re.search(rf"<d:{field}[^>]*>([^<]+)</d:{field}>", entry, flags=re.I)
        if not dm or not ym:
            continue
        try:
            out.append((dm.group(1)[:10], float(ym.group(1))))
        except ValueError:
            continue
    out.sort(key=lambda x: x[0])
    if len(out) < 2:
        raise RuntimeError(f"미 재무부 {'실질' if real else '명목'} 10년물 XML 파싱 실패")
    return out


def fetch_nyfed_term_premium_rows() -> list[tuple[str, float]]:
    """Read the NY Fed ACM daily 10-year term-premium series from its primary XLS."""
    import xlrd

    raw = _url_bytes(NYFED_ACM_XLS, timeout=20)
    book = xlrd.open_workbook(file_contents=raw)
    sheet = None
    for name in book.sheet_names():
        if "daily" in name.lower():
            sheet = book.sheet_by_name(name)
            break
    if sheet is None:
        raise RuntimeError("NY Fed ACM 일별 시트를 찾지 못했습니다.")

    header_row = None
    date_col = None
    tp_col = None
    for r in range(min(sheet.nrows, 20)):
        headers = [str(sheet.cell_value(r, col)).strip() for col in range(sheet.ncols)]
        upper = [h.upper() for h in headers]
        if "DATE" in upper and "ACMTP10" in upper:
            header_row = r
            date_col = upper.index("DATE")
            tp_col = upper.index("ACMTP10")
            break
    if header_row is None or date_col is None or tp_col is None:
        raise RuntimeError("NY Fed ACM DATE/ACMTP10 열을 찾지 못했습니다.")

    rows: list[tuple[str, float]] = []
    for r in range(header_row + 1, sheet.nrows):
        dv = sheet.cell_value(r, date_col)
        tv = sheet.cell_value(r, tp_col)
        if tv in ("", None):
            continue
        try:
            value = float(tv)
        except Exception:
            continue

        d: date | None = None
        if isinstance(dv, (int, float)) and dv:
            try:
                d = xlrd.xldate_as_datetime(float(dv), book.datemode).date()
            except Exception:
                d = None
        else:
            s = str(dv).strip()
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    d = datetime.strptime(s, fmt).date()
                    break
                except ValueError:
                    continue
        if d is not None:
            rows.append((d.isoformat(), value))

    rows.sort(key=lambda x: x[0])
    if len(rows) < 2:
        raise RuntimeError("NY Fed ACM 일별 10년 기간프리미엄 관측치 부족")
    return rows


def latest_two(rows: list[tuple[str, float]]) -> tuple[tuple[str, float], tuple[str, float]]:
    return rows[-2], rows[-1]


def latest_fx():
    """Do not suppress the policy alert only because KRW sources disagree."""
    errors: list[str] = []
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return q.rate, q.basis
    except Exception as exc:
        errors.append(f"교차검증 API 실패: {type(exc).__name__}: {exc}")

    try:
        rows = fetch_series(SERIES["fx"], lookback_days=14)
        day, rate = rows[-1]
        if rate > 0:
            return rate, f"{day} FRED DEXKOUS 독립 공식 fallback · 원 API 교차검증 실패"
    except Exception as exc:
        errors.append(f"FRED DEXKOUS 실패: {type(exc).__name__}: {exc}")

    return None, "환율 검증 실패 — 원화 환산 보류 · " + " | ".join(errors)


def fmt_krw(usd_bn: float, fx: float | None) -> str:
    if fx is None:
        return "원화 환산 보류"
    won = usd_bn * 1_000_000_000 * fx
    jo = int(won // 1_000_000_000_000)
    eok = int(round((won - jo * 1_000_000_000_000) / 100_000_000))
    if eok >= 10000:
        jo += 1
        eok -= 10000
    if jo and eok:
        return f"약 {jo:,}조{eok:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {eok:,}억원"


def fx_basis_line(fx: float | None, fx_date: str) -> str:
    if fx is None:
        return f"환율 기준: {fx_date}"
    return f"환율 기준: {fx_date}, 1달러={fx:,.2f}원"


def bp(new: float, old: float) -> float:
    return (new - old) * 100.0


def pct(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0


def direction(value: float, threshold: float) -> int:
    if value >= threshold:
        return 1
    if value <= -threshold:
        return -1
    return 0


def translate_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    if title in EXACT_TITLES:
        return EXACT_TITLES[title]
    low = title.lower()
    if "buyback" in low and ("long-end" in low or "long end" in low):
        if "increase" in low or "increased" in low or "expand" in low:
            return "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 확대"
        if "decrease" in low or "reduce" in low:
            return "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 축소"
        return "미 재무부, 장기 명목국채 유동성 지원 바이백 정책 변경"
    if "quarterly refunding" in low or "refunding" in low:
        return "미 재무부 분기 차환·자금조달 계획 발표"
    if "treasury" in low:
        return "미 재무부 공식 발표"
    return title


def build_causal_snapshot() -> dict:
    # Fast causal verdict uses first-party sources that are reliable on GitHub runners:
    # EIA Brent + U.S. Treasury nominal/real 10Y. The inflation component is the
    # same-day nominal-minus-real Treasury curve spread, used as a transparent proxy.
    brent_rows = fetch_eia_brent_rows()
    nom_rows = fetch_treasury_10y_rows(real=False)
    real_rows = fetch_treasury_10y_rows(real=True)

    maps = {
        "brent": dict(brent_rows),
        "nom10": dict(nom_rows),
        "real10": dict(real_rows),
    }
    common_dates = sorted(set(maps["brent"]) & set(maps["nom10"]) & set(maps["real10"]))
    if len(common_dates) < 2:
        raise RuntimeError("EIA Brent·미 재무부 명목/실질 10년물 공통 비교일이 2개 미만입니다.")
    prev_date, cur_date = common_dates[-2], common_dates[-1]

    prev = {
        "brent": maps["brent"][prev_date],
        "nom10": maps["nom10"][prev_date],
        "real10": maps["real10"][prev_date],
    }
    cur = {
        "brent": maps["brent"][cur_date],
        "nom10": maps["nom10"][cur_date],
        "real10": maps["real10"][cur_date],
    }
    prev["bei10"] = prev["nom10"] - prev["real10"]
    cur["bei10"] = cur["nom10"] - cur["real10"]

    changes = {
        "brent_pct": pct(cur["brent"], prev["brent"]),
        "bei_bp": bp(cur["bei10"], prev["bei10"]),
        "real_bp": bp(cur["real10"], prev["real10"]),
        "nom_bp": bp(cur["nom10"], prev["nom10"]),
        "term_bp": None,
    }

    # One-day moves are noisy. Use a five-common-trading-day window as the
    # primary causal regime when available, while retaining 1-day changes for
    # transparency. This prevents flip-flopping alerts on a single session.
    changes_5d = None
    if len(common_dates) >= 6:
        base5_date = common_dates[-6]
        base5 = {
            "brent": maps["brent"][base5_date],
            "nom10": maps["nom10"][base5_date],
            "real10": maps["real10"][base5_date],
        }
        base5["bei10"] = base5["nom10"] - base5["real10"]
        changes_5d = {
            "start_date": base5_date,
            "brent_pct": pct(cur["brent"], base5["brent"]),
            "bei_bp": bp(cur["bei10"], base5["bei10"]),
            "real_bp": bp(cur["real10"], base5["real10"]),
            "nom_bp": bp(cur["nom10"], base5["nom10"]),
        }

    term_latest = {
        "available": False,
        "prev_date": None,
        "prev": None,
        "date": None,
        "value": None,
        "change_bp": None,
        "source": NYFED_TERM_PREMIA,
    }
    try:
        try:
            term_rows = fetch_nyfed_term_premium_rows()
            term_source = "NY Fed ACM primary XLS"
        except Exception as primary_exc:
            term_rows = fetch_series(SERIES["term10"])
            term_source = f"FRED Kim-Wright fallback; NY Fed ACM failed: {type(primary_exc).__name__}"
        term_prev, term_cur = latest_two(term_rows)
        changes["term_bp"] = bp(term_cur[1], term_prev[1])
        term_latest.update({
            "available": True,
            "prev_date": term_prev[0],
            "prev": term_prev[1],
            "date": term_cur[0],
            "value": term_cur[1],
            "change_bp": changes["term_bp"],
            "data_source": term_source,
        })
    except Exception as exc:
        term_latest["error"] = f"{type(exc).__name__}: {exc}"

    regime_changes = changes_5d or changes
    oil_d = direction(regime_changes["brent_pct"], 0.5)
    bei_d = direction(regime_changes["bei_bp"], 1.0)
    real_d = direction(regime_changes["real_bp"], 2.0)
    nom_d = direction(regime_changes["nom_bp"], 2.0)
    term_d = direction(changes["term_bp"], 2.0) if changes["term_bp"] is not None else 0

    if oil_d < 0 and bei_d < 0 and nom_d < 0:
        verdict_key = "energy_disinflation_support"
        verdict = "🟢 Bessent 설명 지지 — 에너지·기대인플레이션 완화가 장기금리 하락과 같은 방향"
    elif oil_d > 0 and bei_d > 0 and nom_d > 0:
        verdict_key = "energy_inflation_pressure_support"
        verdict = "🟠 Bessent 설명과 부합 — 에너지·기대인플레이션 압력이 장기금리 상승과 같은 방향"
    elif oil_d < 0 and bei_d < 0 and nom_d >= 0 and (real_d > 0 or term_d > 0):
        verdict_key = "fiscal_real_dominant"
        verdict = "🔴 Bessent 설명 약화 — 에너지·기대인플레이션은 내려가는데 실질금리·기간프리미엄이 장기금리를 떠받침"
    elif nom_d > 0 and bei_d <= 0 and (real_d > 0 or term_d > 0):
        verdict_key = "noninflation_component_dominant"
        verdict = "🔴 비인플레이션 요인 우세 — 실질금리·기간프리미엄 쪽 상승 압력이 더 강함"
    else:
        verdict_key = "mixed"
        verdict = "⚪ 혼조 — 현재 다중거래일 흐름만으로 에너지·인플레이션 또는 재정·기간프리미엄 단일 원인을 확정하기 어려움"

    latest = {
        "brent": {"date": brent_rows[-1][0], "value": brent_rows[-1][1]},
        "nom10": {"date": nom_rows[-1][0], "value": nom_rows[-1][1]},
        "real10": {"date": real_rows[-1][0], "value": real_rows[-1][1]},
    }

    return {
        "common_prev_date": prev_date,
        "common_date": cur_date,
        "common_values": cur,
        "common_changes": changes,
        "changes_5d": changes_5d,
        "verdict_basis": "5거래일 공통창" if changes_5d else "1거래일 공통창",
        "term_latest": term_latest,
        "latest": latest,
        "verdict_key": verdict_key,
        "verdict": verdict,
        "sources": {
            "brent": "EIA Brent Europe spot price",
            "nominal10": "U.S. Treasury Daily Par Yield Curve",
            "real10": "U.S. Treasury Daily Real Par Yield Curve",
            "bei10": "U.S. Treasury nominal-real 10Y spread proxy",
            "term10": "New York Fed term premium page / FRED mirror when available",
        },
    }

def causal_block(snapshot: dict) -> str:
    if not snapshot.get("available", True):
        return "\n".join([
            "<b>Bessent 금리상승 원인설 자동 검증</b>",
            "• 최신 원자료 일부가 지연·실패해 이번 실행의 원인분해 숫자는 <b>확인 보류</b>합니다.",
            f"• 실패 사유: {snapshot.get('error') or '자료 조회 실패'}",
            "• 정책 사실·바이백 실제 집행 감시는 계속하며, 원인분해 실패만으로 정책 알림을 막지 않습니다.",
        ])
    v = snapshot["common_values"]
    c = snapshot["common_changes"]
    t = snapshot.get("term_latest") or {}
    if t.get("available") and t.get("value") is not None:
        term_line = f"• 10년 기간프리미엄(보조): {t['value']:.4f}% ({t['change_bp']:+.1f}bp, {t['date']} 기준 · {t.get('data_source','NY Fed ACM')})"
    else:
        term_line = "• 10년 기간프리미엄(보조): 이번 실행 확인 보류 — 핵심 판정은 EIA·미 재무부 원자료로 계속"
    return "\n".join([
        "<b>Bessent 금리상승 원인설 자동 검증</b>",
        f"• 공통 비교일: {snapshot['common_prev_date']} → {snapshot['common_date']}",
        f"• Brent(EIA): ${v['brent']:.2f}/배럴 ({c['brent_pct']:+.2f}%)",
        f"• 10년 기대인플레이션 프록시(미 재무부 명목-실질): {v['bei10']:.2f}% ({c['bei_bp']:+.1f}bp)",
        f"• 10년 실질금리(미 재무부): {v['real10']:.2f}% ({c['real_bp']:+.1f}bp)",
        f"• 10년 명목금리(미 재무부): {v['nom10']:.2f}% ({c['nom_bp']:+.1f}bp)",
        (
            f"• 5거래일 검증: Brent {snapshot['changes_5d']['brent_pct']:+.1f}% · "
            f"기대인플레 {snapshot['changes_5d']['bei_bp']:+.1f}bp · "
            f"실질금리 {snapshot['changes_5d']['real_bp']:+.1f}bp · "
            f"명목10Y {snapshot['changes_5d']['nom_bp']:+.1f}bp"
            if snapshot.get("changes_5d") else
            "• 5거래일 검증: 공통 관측치 부족 — 1일 판정만 사용"
        ),
        term_line,
        f"• 판정 기준: {snapshot.get('verdict_basis','확인 불가')}",
        f"• 판정: <b>{snapshot['verdict']}</b>",
        "• 기대인플레이션 프록시는 같은 날짜의 미 재무부 명목 10년물-실질 10년물 차이입니다. 기간프리미엄은 모형 추정치라 보조 확인에만 사용합니다.",
    ])

def stock_market_block(snapshot: dict) -> str:
    if not snapshot.get("available", True):
        return "\n".join([
            "",
            "<b>주식시장 영향</b>",
            "• 현재 판정: <b>⚪ 자동판정 보류</b>",
            "• 명목·실질금리 원자료가 같은 실행에서 완성되지 않아 성장주 할인율 방향을 추정하지 않습니다.",
            "• 정책·집행 사실은 유지하고 다음 정상 원자료 실행에서 Nasdaq·AI·반도체·소프트웨어 영향을 다시 판정합니다.",
        ])
    # Equity interpretation must use the same primary horizon as the causal
    # regime verdict; otherwise a one-day reversal can contradict a five-day cause test.
    c = snapshot.get("changes_5d") or snapshot["common_changes"]
    v = snapshot["common_values"]
    nom = c["nom_bp"]
    real = c["real_bp"]
    bei = c["bei_bp"]

    if nom <= -2.0 and real <= -2.0:
        verdict = "🟢 성장주 할인율 우호 강화"
        reason = "10년 명목·실질금리가 함께 하락해 Nasdaq·AI·반도체·소프트웨어의 할인율 부담이 실제로 완화되는 방향입니다."
    elif nom >= 2.0 and real >= 2.0:
        verdict = "🔴 성장주 할인율 부담 확대"
        reason = "10년 명목·실질금리가 함께 올라 바이백의 수급 완충보다 높은 실질 할인율 부담이 더 강한 상태입니다."
    elif nom < 0 and real >= 0 and bei < 0:
        verdict = "🟡 물가 완화는 우호적이나 실질금리 부담 잔존"
        reason = "기대인플레이션은 내려가도 실질금리가 버티면 성장주 밸류에이션 개선은 제한적입니다."
    else:
        verdict = "⚪ 주식시장 영향 혼조"
        reason = "채권 수급 개선이 주식 할인율 개선으로 이어졌다고 보기엔 명목·실질금리 방향이 충분히 정렬되지 않았습니다."

    return "\n".join([
        "",
        "<b>주식시장 영향</b>",
        f"• 현재 판정: <b>{verdict}</b>",
        f"• {reason}",
        f"• 10년 명목 {v['nom10']:.2f}% ({nom:+.1f}bp) / 실질 {v['real10']:.2f}% ({real:+.1f}bp) / 기대인플레이션 {v['bei10']:.2f}% ({bei:+.1f}bp)",
        "• 금리 하락이 경기침체·실적악화 때문이면 성장주 호재로 자동 판정하지 않습니다. 여기서는 바이백·수급과 실질 할인율 경로를 분리해 봅니다.",
    ])


def oil_scenario_block(snapshot: dict) -> str:
    if not snapshot.get("available", True):
        return "\n".join([
            "<b>Bessent 원유 40~50달러 조건부 시나리오</b>",
            "• EIA Brent 최신값 확인 실패로 가격 경로 판정을 보류합니다.",
            "• 40~50달러는 공식 유가 목표가 아니라 <b>이란 분쟁 종료 후 공급과잉이 생긴다는 조건부 전망</b>입니다.",
        ])
    latest = snapshot.get("latest") or {}
    brent = ((latest.get("brent") or {}).get("value"))
    brent_date = str((latest.get("brent") or {}).get("date") or "확인 불가")
    if brent is None:
        return "<b>Bessent 원유 40~50달러 조건부 시나리오</b>\n• Brent 최신값 확인 불가"
    brent = float(brent)
    to50 = (50.0 / brent - 1.0) * 100.0
    to40 = (40.0 / brent - 1.0) * 100.0
    if brent >= 100:
        label = "🔴 현재는 시나리오와 역방향 — 에너지·인플레이션 압력 고조"
    elif brent >= 80:
        label = "🟠 아직 매우 멂 — 전쟁·공급차질 해소가 먼저 필요"
    elif brent >= 60:
        label = "🟡 하락 경로 진입 가능성은 커졌지만 40~50달러는 미도달"
    elif brent > 50:
        label = "🟡 50달러 시나리오 접근"
    else:
        label = "🟢 50달러 이하 진입 — 40달러 꼬리 시나리오 검증 구간"
    return "\n".join([
        "<b>Bessent 원유 40~50달러 조건부 시나리오</b>",
        f"• Brent(EIA) 최신: <b>${brent:.2f}/배럴</b> ({brent_date}) · 50달러까지 {to50:+.1f}% · 40달러까지 {to40:+.1f}%",
        f"• 현재 판정: <b>{label}</b>",
        "• 조건 분리: 40~50달러는 <b>이란 분쟁 종료 + 공급과잉</b>을 전제로 한 Bessent의 조건부 전망이며 재무부의 공식 가격목표가 아닙니다.",
        "• 검증 경로: Brent↓ → 기대인플레↓ → 실질금리↓/기간프리미엄 안정 → 10년물↓. 유가만 내려가고 10년물이 버티면 재정·실질금리 요인이 더 강한 것으로 판정합니다.",
    ])

def policy_block(snapshot: dict) -> str:
    return "\n".join([
        "",
        "<b>정책 목적·경계선</b>",
        "• Bessent는 9월 8일 ‘시장을 균형 쪽으로 되돌리는 것이 내 일’이라면서도 <b>균형가격 자체를 바꿀 수 있다고 보지는 않는다</b>고 설명했고, 당시 장기채 시장에 ‘fever(과열)’가 쌓이고 있었다고 표현했습니다.",
        "• 따라서 현재 공식 정책선은 <b>특정 수익률·채권가격 통제</b>가 아니라 <b>시장 기능·유동성·변동성의 과속 완화</b>입니다.",
        "• Bessent는 이를 QE가 아니라고 선을 긋고 과거 Operation Twist와 유사한 부채관리 접근으로 설명했습니다. 재무부 바이백을 Fed의 준비금 창출형 자산매입과 동일시하지 않습니다.",
        "• 정책 충격 뒤 CTA·모멘텀 숏커버가 자기증폭될 수는 있지만, 이는 <b>시장 결과</b>이지 Bessent가 공식적으로 선언한 CTA 스퀴즈 목표로 단정하지 않습니다.",
        "• 시장 기능이 정상인데도 특정 금리 수준에 맞춰 바이백·발행구조를 반복 조정하면 ‘유동성 지원 → 사실상 금리관리’로 정책선 이탈 경보를 올립니다.",
        "",
        causal_block(snapshot),
        oil_scenario_block(snapshot),
        stock_market_block(snapshot),
        "",
        "<b>실행 확인</b>",
        "• 정책 변경 효력은 9월 9일, Bessent가 밝힌 확대 운영 시작은 9월 10일입니다.",
        "• 실제 매입액·총 제시액·상한 소진율 → +1일·+3일·+5일 10년·30년 명목·실질금리 → CTA 숏커버 순서로 확인합니다.",
        "• 바이백에도 장기금리가 오르면 재정·인플레이션·기간프리미엄이 유동성 지원보다 강한 것으로 판정합니다.",
    ])


def source_links() -> str:
    return " · ".join([
        f'<a href="{BESSENT_REUTERS}">Bessent Reuters 인터뷰</a>',
        f'<a href="{BESSENT_FEVER}">Bessent ‘market fever’ 발언</a>',
        f'<a href="{BESSENT_OIL_SCENARIO}">Bessent 원유 40~50달러 조건부 전망</a>',
        f'<a href="{TREASURY_RELEASE}">미 재무부 공식 발표</a>',
        f'<a href="{BUYBACK_FAQ}">바이백 공식 설명</a>',
        f'<a href="{EIA_BRENT_PAGE}">EIA Brent</a>',
        f'<a href="{TREASURY_NOMINAL_XML.format(year=date.today().year)}">미 재무부 명목금리</a>',
        f'<a href="{TREASURY_REAL_XML.format(year=date.today().year)}">미 재무부 실질금리</a>',
        f'<a href="{NYFED_TERM_PREMIA}">뉴욕연은 기간프리미엄</a>',
    ])

def one_time_alert(fx: float, fx_date: str, snapshot: dict) -> str:
    return "\n".join([
        "<b>핵심 판단</b>",
        "🟢 Bessent가 장기물 바이백의 정책 목적을 명확히 했습니다. 공식선은 특정 수익률 통제가 아니라 유동성·변동성 완화이며, 이제 이 설명을 실제 시장 데이터로 자동 검증합니다.",
        "",
        "<b>확정 사실</b>",
        f"• 장기 비지표물 바이백: 회당 최대 20억달러({fmt_krw(2.0, fx)}) → 최소 40억달러({fmt_krw(4.0, fx)}). 공식 효력일은 9월 9일입니다.",
        "• 9월 초 당시 확대 운영은 9월 10일부터 시작됐으며, 현재 평가는 발표 당시 설명이 아니라 실제 집행·후속 금리 경로로 판정합니다.",
        policy_block(snapshot),
        "",
        "<b>한 줄 결론</b>",
        "공식 정책선과 시장 결과를 분리합니다. 원유 40~50달러는 이란 분쟁 종료·공급과잉을 전제로 한 조건부 전망으로만 추적하고, Brent·기대인플레이션·실질금리·10년물을 5거래일 중심으로 연결해 바이백과 성장주 할인율 효과가 실제로 지속되는지 판정합니다.",
        "",
        fx_basis_line(fx, fx_date),
        source_links(),
    ])


def verdict_change_alert(snapshot: dict) -> str:
    return "\n".join([
        "<b>핵심 판단</b>",
        "Bessent의 장기금리 상승 원인 설명에 대한 데이터 판정이 이전 감시 대비 바뀌었습니다.",
        "",
        causal_block(snapshot),
        "",
        "<b>정확한 의미</b>",
        "• 이 알림은 10년물 단독 움직임이 아니라 Brent·기대인플레이션·실질금리·명목금리의 공통일 변화와 기간프리미엄 보조확인을 묶은 판정입니다.",
        "• 일반 금리 알림과 중복되지 않도록 <b>원인 판정 레짐이 바뀔 때만</b> 보냅니다.",
        "",
        source_links(),
    ])


def write_next_state(snapshot: dict) -> None:
    state = load_json(NEXT_STATE) or load_json(STATE)
    state["bessent_policy_boundary_revision"] = UPGRADE_REVISION
    if snapshot.get("available", True):
        state["bessent_causal_verdict_key"] = snapshot["verdict_key"]
        state["bessent_causal_verdict"] = snapshot["verdict"]
        state["bessent_causal_snapshot"] = snapshot
        state.pop("bessent_causal_last_error", None)
    else:
        state["bessent_causal_last_error"] = snapshot.get("error")
    NEXT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    state = load_json(STATE)
    revision = int(state.get("bessent_policy_boundary_revision", 0) or 0)
    old_verdict_key = str(state.get("bessent_causal_verdict_key") or "")
    try:
        snapshot = build_causal_snapshot()
        snapshot["available"] = True
    except Exception as exc:
        snapshot = {
            "available": False,
            "verdict_key": "unavailable",
            "verdict": "⚪ 원인분해 데이터 확인 보류",
            "error": f"{type(exc).__name__}: {exc}",
        }

    official_alert_exists = ALERT.exists()

    if not official_alert_exists:
        if revision < UPGRADE_REVISION:
            fx, fx_date = latest_fx()
            TITLE.write_text(
                "🇺🇸 미 재무부 장기물 바이백 — 정책선·원유 40~50달러 시나리오·금리원인 통합검증\n",
                encoding="utf-8",
            )
            body = one_time_alert(fx, fx_date, snapshot)
            if len(body) > 3900:
                raise RuntimeError(f"업그레이드 재무부 알림 본문이 너무 깁니다: {len(body)}")
            ALERT.write_text(body + "\n", encoding="utf-8")
            DETAIL.write_text(json.dumps({
                "type": "bessent_policy_and_causal_verifier_upgrade",
                "source": {"url": BESSENT_REUTERS, "title": "Bessent Reuters 인터뷰", "date": "2026-08-31"},
                "fx": fx,
                "fx_date": fx_date,
                "revision": UPGRADE_REVISION,
                "causal_snapshot": snapshot,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif snapshot.get("available", True) and old_verdict_key and snapshot["verdict_key"] != old_verdict_key:
            TITLE.write_text(
                "🇺🇸 미 국채 장기금리 — Bessent 원인설 데이터 판정 변화\n",
                encoding="utf-8",
            )
            body = verdict_change_alert(snapshot)
            if len(body) > 3900:
                raise RuntimeError(f"Bessent 원인설 판정 변화 알림이 너무 깁니다: {len(body)}")
            ALERT.write_text(body + "\n", encoding="utf-8")
            DETAIL.write_text(json.dumps({
                "type": "bessent_causal_verdict_change",
                "source": {"url": BESSENT_REUTERS, "title": "Bessent Reuters 인터뷰", "date": "2026-08-31"},
                "previous_verdict_key": old_verdict_key,
                "causal_snapshot": snapshot,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_next_state(snapshot)
        return 0

    text = ALERT.read_text(encoding="utf-8")
    detail = load_json(DETAIL)
    source = detail.get("source") or {}
    original_title = source.get("title")
    source_url = str(source.get("url") or "")

    if original_title:
        translated = translate_title(str(original_title))
        text = text.replace(
            f"• 공식 출처: <b>{original_title}</b>",
            f"• 공식 출처: <b>{translated}</b>",
        )

    pattern = re.compile(r"(• 공식 출처: <b>)([^<]+)(</b>)")
    def repl(match: re.Match[str]) -> str:
        shown = match.group(2).strip()
        if re.search(r"[A-Za-z]{4,}", shown):
            shown = translate_title(shown)
            if re.search(r"[A-Za-z]{4,}", shown):
                shown = "미 재무부 공식 발표"
        return match.group(1) + shown + match.group(3)
    text = pattern.sub(repl, text)

    if UPGRADE_MARKER not in text:
        text = text.rstrip() + "\n" + policy_block(snapshot) + "\n"

    if source_url.rstrip("/") == TREASURY_RELEASE.rstrip("/") and TITLE.exists():
        TITLE.write_text(
            "🇺🇸 미 재무부 장기물 바이백 — 정책 변화 + Bessent 원인설 자동검증\n",
            encoding="utf-8",
        )

    if re.search(r"• 공식 출처: <b>[^<]*\b(Treasury|Buyback|Refunding)\b", text, re.I):
        raise RuntimeError("공식 출처 제목의 한국어 변환이 완료되지 않았습니다.")
    if len(text) > 3900:
        raise RuntimeError(f"업그레이드된 재무부 알림 본문이 너무 깁니다: {len(text)}")

    ALERT.write_text(text, encoding="utf-8")
    if snapshot.get("available", True):
        detail["bessent_causal_snapshot"] = snapshot
        detail["bessent_causal_verdict"] = snapshot["verdict"]
        detail.pop("bessent_causal_error", None)
    else:
        detail["bessent_causal_error"] = snapshot.get("error")
    DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_next_state(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
