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
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "treasury_buyback_policy_alert.html"
DETAIL = ROOT / "out" / "treasury_buyback_policy_detail.json"
TITLE = ROOT / "out" / "treasury_buyback_policy_title.txt"
STATE = ROOT / "data" / "treasury_buyback_policy_state.json"
NEXT_STATE = ROOT / "data" / "treasury_buyback_policy_state_next.json"

BESSENT_REUTERS = "https://www.reuters.com/business/bessent-pushes-back-fears-over-us-debt-market-strains-2026-08-31/"
TREASURY_RELEASE = "https://home.treasury.gov/news/press-releases/sb0607"
BUYBACK_FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
FRED_SERIES_PAGE = "https://fred.stlouisfed.org/series/{series}"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

SERIES = {
    "fx": "DEXKOUS",
    "brent": "DCOILBRENTEU",
    "bei10": "T10YIE",
    "real10": "DFII10",
    "term10": "THREEFYTP10",
    "nom10": "DGS10",
}

UPGRADE_MARKER = "<b>정책 목적·경계선</b>"
UPGRADE_REVISION = 3
UA = "Mozilla/5.0 khs-watch-treasury-bessent-verifier/3.0"

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


def latest_two(rows: list[tuple[str, float]]) -> tuple[tuple[str, float], tuple[str, float]]:
    return rows[-2], rows[-1]


def latest_fx() -> tuple[float, str]:
    _prev, cur = latest_two(fetch_series(SERIES["fx"], lookback_days=45))
    return cur[1], cur[0]


def fmt_krw(usd_bn: float, fx: float) -> str:
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
    raw = {key: fetch_series(series_id) for key, series_id in SERIES.items() if key != "fx"}

    # Fast verdict uses a truly common date across Brent, BEI, real 10Y and nominal 10Y.
    # The Kim-Wright term premium is intentionally kept as a separate lagged model confirmation.
    fast_keys = ("brent", "bei10", "real10", "nom10")
    maps = {key: dict(raw[key]) for key in fast_keys}
    common_dates = sorted(set.intersection(*(set(maps[key]) for key in fast_keys)))
    if len(common_dates) < 2:
        raise RuntimeError("Brent·BEI·실질금리·명목금리 공통 비교일이 2개 미만입니다.")
    prev_date, cur_date = common_dates[-2], common_dates[-1]

    cur = {key: maps[key][cur_date] for key in fast_keys}
    prev = {key: maps[key][prev_date] for key in fast_keys}
    changes = {
        "brent_pct": pct(cur["brent"], prev["brent"]),
        "bei_bp": bp(cur["bei10"], prev["bei10"]),
        "real_bp": bp(cur["real10"], prev["real10"]),
        "nom_bp": bp(cur["nom10"], prev["nom10"]),
    }

    term_prev, term_cur = latest_two(raw["term10"])
    changes["term_bp"] = bp(term_cur[1], term_prev[1])

    oil_d = direction(changes["brent_pct"], 0.5)
    bei_d = direction(changes["bei_bp"], 1.0)
    real_d = direction(changes["real_bp"], 2.0)
    nom_d = direction(changes["nom_bp"], 2.0)
    term_d = direction(changes["term_bp"], 2.0)

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
        verdict = "⚪ 혼조 — 현재 하루 움직임만으로 에너지·인플레이션 또는 재정·기간프리미엄 단일 원인을 확정하기 어려움"

    latest = {}
    for key, rows in raw.items():
        p, c = latest_two(rows)
        latest[key] = {
            "prev_date": p[0], "prev": p[1], "date": c[0], "value": c[1],
            "change": pct(c[1], p[1]) if key == "brent" else bp(c[1], p[1]),
        }

    return {
        "common_prev_date": prev_date,
        "common_date": cur_date,
        "common_values": cur,
        "common_changes": changes,
        "term_latest": {"prev_date": term_prev[0], "prev": term_prev[1], "date": term_cur[0], "value": term_cur[1], "change_bp": changes["term_bp"]},
        "latest": latest,
        "verdict_key": verdict_key,
        "verdict": verdict,
    }


def causal_block(snapshot: dict) -> str:
    v = snapshot["common_values"]
    c = snapshot["common_changes"]
    t = snapshot["term_latest"]
    return "\n".join([
        "<b>Bessent 금리상승 원인설 자동 검증</b>",
        f"• 공통 비교일: {snapshot['common_prev_date']} → {snapshot['common_date']}",
        f"• Brent: ${v['brent']:.2f}/배럴 ({c['brent_pct']:+.2f}%)",
        f"• 10년 기대인플레이션: {v['bei10']:.2f}% ({c['bei_bp']:+.1f}bp)",
        f"• 10년 실질금리: {v['real10']:.2f}% ({c['real_bp']:+.1f}bp)",
        f"• 10년 명목금리: {v['nom10']:.2f}% ({c['nom_bp']:+.1f}bp)",
        f"• 10년 기간프리미엄(Kim-Wright): {t['value']:.4f}% ({t['change_bp']:+.1f}bp, {t['date']} 기준)",
        f"• 판정: <b>{snapshot['verdict']}</b>",
        "• 기간프리미엄은 모형 추정치라 업데이트 시차가 있어 별도 확인지표로 사용합니다. 실질금리+기대인플레이션과 기간프리미엄을 단순 합산하지 않습니다.",
    ])


def policy_block(snapshot: dict) -> str:
    return "\n".join([
        "",
        "<b>정책 목적·경계선</b>",
        "• Bessent는 Reuters 인터뷰에서 시장의 균형가격을 바꾸려는 것이 아니라, 움직임의 속도를 늦춰 시장이 무질서해지는 것을 막는 것이 재무부 역할이라고 설명했습니다.",
        "• 따라서 현재 정책선은 <b>특정 금리·가격 통제</b>가 아니라 <b>유동성·변동성 완화</b>입니다.",
        "• 시장 기능이 정상인데도 특정 금리 수준에 맞춰 바이백·발행구조를 반복 조정하면 ‘유동성 지원 → 사실상 금리관리’로 정책선 이탈 경보를 올립니다.",
        "",
        causal_block(snapshot),
        "",
        "<b>실행 확인</b>",
        "• 정책 변경 효력은 9월 9일, Bessent가 밝힌 확대 운영 시작은 9월 10일입니다.",
        "• 첫 확대 운영의 실제 매입액·총 제시액·상한 소진율과 이후 +1일·+3일·+5일 10년·30년 명목·실질금리 지속성을 확인합니다.",
        "• CTA 숏 스퀴즈가 발생해도 시장 결과로 분리하며 Bessent의 공식 정책목표로 단정하지 않습니다.",
    ])


def source_links() -> str:
    return " · ".join([
        f'<a href="{BESSENT_REUTERS}">Bessent Reuters 인터뷰</a>',
        f'<a href="{TREASURY_RELEASE}">미 재무부 공식 발표</a>',
        f'<a href="{BUYBACK_FAQ}">바이백 공식 설명</a>',
        f'<a href="{FRED_SERIES_PAGE.format(series=SERIES["brent"])}">Brent</a>',
        f'<a href="{FRED_SERIES_PAGE.format(series=SERIES["bei10"])}">10년 기대인플레이션</a>',
        f'<a href="{FRED_SERIES_PAGE.format(series=SERIES["real10"])}">10년 실질금리</a>',
        f'<a href="{FRED_SERIES_PAGE.format(series=SERIES["term10"])}">10년 기간프리미엄</a>',
        f'<a href="{FRED_SERIES_PAGE.format(series=SERIES["nom10"])}">10년 명목금리</a>',
    ])


def one_time_alert(fx: float, fx_date: str, snapshot: dict) -> str:
    return "\n".join([
        "<b>핵심 판단</b>",
        "🟢 Bessent가 장기물 바이백의 정책 목적을 명확히 했습니다. 공식선은 특정 수익률 통제가 아니라 유동성·변동성 완화이며, 이제 이 설명을 실제 시장 데이터로 자동 검증합니다.",
        "",
        "<b>확정 사실</b>",
        f"• 장기 비지표물 바이백: 회당 최대 20억달러({fmt_krw(2.0, fx)}) → 최소 40억달러({fmt_krw(4.0, fx)}). 공식 효력일은 9월 9일입니다.",
        "• Bessent는 Reuters에 확대 운영이 9월 10일부터 시작되며 아직 확대된 바이백은 집행되지 않았다고 설명했습니다.",
        policy_block(snapshot),
        "",
        "<b>한 줄 결론</b>",
        "공식 정책선과 시장 결과를 분리합니다. 앞으로는 ‘유가·기대인플레이션이 내려가면 장기금리도 내려가는가’와 ‘실질금리·기간프리미엄이 이를 상쇄하는가’를 실제 숫자로 판정합니다.",
        "",
        f"환율 기준: FRED DEXKOUS {fx_date}, 1달러={fx:,.2f}원",
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
    state["bessent_causal_verdict_key"] = snapshot["verdict_key"]
    state["bessent_causal_verdict"] = snapshot["verdict"]
    state["bessent_causal_snapshot"] = snapshot
    NEXT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    state = load_json(STATE)
    revision = int(state.get("bessent_policy_boundary_revision", 0) or 0)
    old_verdict_key = str(state.get("bessent_causal_verdict_key") or "")
    snapshot = build_causal_snapshot()

    official_alert_exists = ALERT.exists()

    if not official_alert_exists:
        if revision < UPGRADE_REVISION:
            fx, fx_date = latest_fx()
            TITLE.write_text(
                "🇺🇸 미 재무부 장기물 바이백 — 베센트 정책선 + 금리상승 원인 자동검증 업그레이드\n",
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
        elif old_verdict_key and snapshot["verdict_key"] != old_verdict_key:
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
    detail["bessent_causal_snapshot"] = snapshot
    detail["bessent_causal_verdict"] = snapshot["verdict"]
    DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_next_state(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
