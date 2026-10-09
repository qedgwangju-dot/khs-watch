#!/usr/bin/env python3
import datetime as dt
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from global_rates_watch import fetch_ust_curve

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "treasury_positioning_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
STATE.parent.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

CFTC_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CFTC_HTML_URL = "https://www.cftc.gov/dea/futures/financial_lf.htm"
OFR_URL = "https://data.financialresearch.gov/v1/series/full"
OFR_TIMESERIES_URL = "https://data.financialresearch.gov/v1/series/timeseries"
NYFED_SOFR_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/10.json"
NYFED_TGCR_URL = "https://markets.newyorkfed.org/api/rates/secured/tgcr/last/10.json"

CONTRACTS = {
    "2년": {"code": "042601", "name": "UST 2Y NOTE"},
    "5년": {"code": "044601", "name": "UST 5Y NOTE"},
    "10년": {"code": "043602", "name": "UST 10Y NOTE"},
    "30년": {"code": "020601", "name": "UST BOND"},
}


def load_state():
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _ints(text):
    return [int(x.replace(",", "")) for x in re.findall(r"[-+]?\d[\d,]*", text or "")]


def ensure_recent_date(label, raw_date, max_days):
    try:
        d = dt.date.fromisoformat(str(raw_date)[:10])
    except Exception as exc:
        raise RuntimeError(f"{label} date invalid: {raw_date}") from exc
    age = (dt.datetime.now(KST).date() - d).days
    if age < 0 or age > max_days:
        raise RuntimeError(f"{label} stale: {raw_date} ({age} days)")
    return age


def nyfed_rate(url, expected_type):
    r = requests.get(url, headers=HEADERS, timeout=(8, 30))
    r.raise_for_status()
    rows = (r.json() or {}).get("refRates") or []
    rows = [x for x in rows if str(x.get("type") or "").upper() == expected_type.upper()]
    if not rows:
        raise RuntimeError(f"NY Fed {expected_type} data unavailable")
    rows.sort(key=lambda x: str(x.get("effectiveDate") or ""))
    row = rows[-1]
    return {
        "date": str(row.get("effectiveDate") or "")[:10],
        "rate": float(row.get("percentRate")),
        "revision": str(row.get("revisionIndicator") or ""),
        "source": url,
    }


def get_cftc_official_html():
    r = requests.get(CFTC_HTML_URL, headers=HEADERS, timeout=(8, 45))
    r.raise_for_status()
    plain = BeautifulSoup(r.text, "html.parser").get_text("\n")
    report_m = re.search(
        r"Traders in Financial Futures\s*-\s*Futures Only Positions as of\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
        plain,
        re.I,
    )
    if not report_m:
        raise RuntimeError("CFTC official HTML report date unavailable")
    report_date = dt.datetime.strptime(report_m.group(1), "%B %d, %Y").date().isoformat()

    out = {}
    for label, meta in CONTRACTS.items():
        pattern = re.escape(meta["name"]) + r"\s*-\s*CHICAGO BOARD OF TRADE"
        m = re.search(pattern, plain, re.I)
        if not m:
            raise RuntimeError(f"CFTC official HTML contract missing: {label}")
        block = plain[m.start():m.start() + 4500]
        oi_m = re.search(r"Open Interest is\s*([\d,]+)", block, re.I)
        pos_m = re.search(r"Positions\s+([\s\S]*?)\s+Changes from:", block, re.I)
        if not oi_m or not pos_m:
            raise RuntimeError(f"CFTC official HTML fields missing: {label}")
        vals = _ints(pos_m.group(1))
        if len(vals) < 14:
            raise RuntimeError(f"CFTC official HTML positions parse failed: {label}")
        out[label] = {
            "oi": int(oi_m.group(1).replace(",", "")),
            "long": vals[6],
            "short": vals[7],
        }
    return report_date, out


def validate_cftc_crosscheck(latest, rows, html_latest, html_rows):
    if html_latest != latest:
        raise RuntimeError(f"CFTC source date mismatch: API={latest}, HTML={html_latest}")
    for label in CONTRACTS:
        a = rows[label]
        b = html_rows.get(label) or {}
        for key in ("oi", "long", "short"):
            if int(round(float(a.get(key) or 0))) != int(b.get(key) or 0):
                raise RuntimeError(
                    f"CFTC source mismatch {label} {key}: API={a.get(key)} HTML={b.get(key)}"
                )
    return True


def select_week_reference(points):
    if len(points) < 2:
        raise RuntimeError("weekly comparison history insufficient")
    latest_date, latest_value = points[-1]
    target = dt.date.fromisoformat(latest_date) - dt.timedelta(days=7)
    eligible = [(d, v) for d, v in points[:-1] if dt.date.fromisoformat(d) <= target]
    if not eligible:
        raise RuntimeError("weekly comparison anchor unavailable")
    old_date, old_value = eligible[-1]
    return latest_date, latest_value, old_date, old_value


def get_cftc_positions():
    r = requests.get(
        CFTC_URL,
        params={"$order": "report_date_as_yyyy_mm_dd DESC", "$limit": 2000},
        headers=HEADERS,
        timeout=(8, 45),
    )
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("CFTC TFF data unavailable")

    by_code = {v["code"]: [] for v in CONTRACTS.values()}
    for row in rows:
        code = str(row.get("cftc_contract_market_code") or "")
        if code not in by_code:
            continue
        date = str(row.get("report_date_as_yyyy_mm_dd") or "")[:10]
        if not date:
            continue
        long_pos = num(row.get("lev_money_positions_long"))
        short_pos = num(row.get("lev_money_positions_short"))
        oi = num(row.get("open_interest_all"))
        by_code[code].append({
            "date": date,
            "long": long_pos,
            "short": short_pos,
            "net": long_pos - short_pos,
            "oi": oi,
            "net_oi_pct": ((long_pos - short_pos) / oi * 100.0) if oi else None,
        })

    common_dates = None
    for meta in CONTRACTS.values():
        vals = sorted(by_code[meta["code"]], key=lambda x: x["date"], reverse=True)
        if len(vals) < 2:
            raise RuntimeError("CFTC history insufficient")
        dates = {x["date"] for x in vals}
        common_dates = dates if common_dates is None else common_dates & dates

    common_dates = sorted(common_dates or [], reverse=True)
    if len(common_dates) < 2:
        raise RuntimeError("CFTC common report dates insufficient")
    latest, prev = common_dates[0], common_dates[1]

    result = {}
    for label, meta in CONTRACTS.items():
        vals = {x["date"]: x for x in by_code[meta["code"]]}
        cur, old = vals[latest], vals[prev]
        result[label] = {
            **cur,
            "previous_net": old["net"],
            "net_change": cur["net"] - old["net"],
            "long_change": cur["long"] - old["long"],
            "short_change": cur["short"] - old["short"],
        }

    if dt.date.fromisoformat(latest).weekday() != 1:
        raise RuntimeError(f"CFTC latest report is not Tuesday: {latest}")
    ensure_recent_date("CFTC", latest, 10)
    html_latest, html_rows = get_cftc_official_html()
    validate_cftc_crosscheck(latest, result, html_latest, html_rows)
    return latest, prev, result


def extract_points(payload):
    found = []

    def walk(obj):
        if isinstance(obj, list):
            if obj and all(
                isinstance(x, list)
                and len(x) >= 2
                and isinstance(x[0], str)
                and len(x[0]) >= 10
                and x[0][4:5] == "-"
                for x in obj
            ):
                for x in obj:
                    try:
                        found.append((x[0][:10], float(x[1])))
                    except Exception:
                        pass
            else:
                for x in obj:
                    walk(x)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)

    walk(payload)
    if not found:
        raise RuntimeError("OFR series data not found")
    dedup = {}
    for d, v in found:
        dedup[d] = v
    return sorted(dedup.items())


def ofr_series(mnemonic, days=45, endpoint=OFR_URL):
    start = (dt.datetime.now(KST).date() - dt.timedelta(days=days)).isoformat()
    r = requests.get(
        endpoint,
        params={"mnemonic": mnemonic, "start_date": start},
        headers=HEADERS,
        timeout=(8, 30),
    )
    r.raise_for_status()
    return extract_points(r.json())


def repo_snapshot():
    sofr = dict(ofr_series("FNYR-SOFR-A"))
    tgcr = dict(ofr_series("FNYR-TGCR-A"))
    common = sorted(set(sofr) & set(tgcr))
    if len(common) < 2:
        raise RuntimeError("SOFR/TGCR common dates insufficient")
    d, prev = common[-1], common[-2]
    s, t = sofr[d], tgcr[d]
    spread_bp = (s - t) * 100.0
    move_bp = (s - sofr[prev]) * 100.0

    ny_sofr = nyfed_rate(NYFED_SOFR_URL, "SOFR")
    ny_tgcr = nyfed_rate(NYFED_TGCR_URL, "TGCR")
    if ny_sofr["date"] != d or ny_tgcr["date"] != d:
        raise RuntimeError(
            f"Repo source date mismatch: OFR={d}, NYFed SOFR={ny_sofr['date']}, TGCR={ny_tgcr['date']}"
        )
    if abs(float(ny_sofr["rate"]) - float(s)) > 1e-9 or abs(float(ny_tgcr["rate"]) - float(t)) > 1e-9:
        raise RuntimeError(
            f"Repo source value mismatch: OFR SOFR/TGCR={s}/{t}, NYFed={ny_sofr['rate']}/{ny_tgcr['rate']}"
        )
    ensure_recent_date("Repo", d, 4)

    if spread_bp >= 10 or move_bp >= 10:
        state = "스트레스"
    elif spread_bp >= 5 or move_bp >= 5:
        state = "주의"
    else:
        state = "안정"

    dvp = ofr_series("REPO-DVP_TV_TOT-P", 45)
    dvp_check = ofr_series("REPO-DVP_TV_TOT-P", 45, endpoint=OFR_TIMESERIES_URL)
    dvp_date, dvp_value, old_date, old_value = select_week_reference(dvp)
    check_map = dict(dvp_check)
    if dvp_date not in check_map or abs(float(check_map[dvp_date]) - float(dvp_value)) > 0.01:
        raise RuntimeError(
            f"OFR DVP endpoint mismatch: full={dvp_date}/{dvp_value}, timeseries={check_map.get(dvp_date)}"
        )
    ensure_recent_date("OFR DVP Repo", dvp_date, 4)
    dvp_week_pct = (dvp_value / old_value - 1.0) * 100.0 if old_value else 0.0

    return {
        "state": state,
        "date": d,
        "sofr": s,
        "tgcr": t,
        "spread_bp": spread_bp,
        "move_bp": move_bp,
        "nyfed_verified": True,
        "nyfed_sofr_revision": ny_sofr["revision"],
        "nyfed_tgcr_revision": ny_tgcr["revision"],
        "dvp_date": dvp_date,
        "dvp_value": dvp_value,
        "dvp_old_date": old_date,
        "dvp_old_value": old_value,
        "dvp_week_pct": dvp_week_pct,
        "dvp_crosscheck_verified": True,
    }


def jpm_30y_signal(y30):
    if y30 >= 6.00:
        return "6.00% 이상 → 장기금리 극단 스트레스"
    if y30 >= 5.78:
        return "5.78% 이상 → JPM Equal Swings 약세 목표 구간"
    if y30 >= 5.59:
        return "5.59% 이상 유지 → 채권 약세 수준(신규 돌파 여부는 일별 비교로 별도 판정)"
    if y30 > 5.25:
        return "5.59% 아래·5.25% 위 → 반전 미확인"
    if y30 > 5.15:
        return "5.25% 이하 유지 → 숏커버·CTA 매수전환 후보(신규 돌파 아님)"
    return "5.15% 이하 → 채권 반전 신호 강화"


def technical_positioning(rows, repo, y30):
    reductions = sum(1 for x in rows.values() if x["net"] < 0 and x["net_change"] > 0)
    expansions = sum(1 for x in rows.values() if x["net"] < 0 and x["net_change"] < 0)

    if y30 >= 6.00:
        return "극단 장기금리 스트레스", "30년물 6%대 → 채권·고밸류 성장주 할인율 부담 극대화"
    if y30 >= 5.78:
        return "장기채 약세 2차 목표 구간", f"30년물 {y30:.2f}% + 순숏 확대 {expansions}개 → JPM 5.78% 목표구간 진입"
    if y30 >= 5.59 and expansions >= 2:
        return "기술 약세 + 숏 확대", f"30년물 {y30:.2f}%가 5.59% 위 + 순숏 확대 {expansions}개 → 금리상승 추세 우세"
    if y30 <= 5.15 and reductions >= 2 and repo["state"] == "안정":
        return "채권 반전 신호 강화", f"30년물 {y30:.2f}% ≤ 5.15% + 숏 축소 {reductions}개 + Repo 안정 → CTA·재량 숏커버 동시 가능성"
    if y30 <= 5.25 and reductions >= 2 and repo["state"] == "안정":
        return "숏커버·CTA 전환 후보", f"30년물 {y30:.2f}% ≤ 5.25% + 숏 축소 {reductions}개 + Repo 안정 → 채권 반등 확인 단계"
    if reductions >= 2 and repo["state"] in ("주의", "스트레스"):
        return "강제 디레버리징 경계", f"숏 축소 {reductions}개지만 Repo {repo['state']} → 질서 있는 커버보다 자금조달 압박 가능성 점검"
    return "기술·포지셔닝 혼조", f"30년물 {y30:.2f}% / 숏 확대 {expansions}개·축소 {reductions}개 / Repo {repo['state']}"


def position_note(row):
    cur, ch = row["net"], row["net_change"]
    if cur < 0:
        return "숏 축소" if ch > 0 else "숏 확대" if ch < 0 else "변화 없음"
    if cur > 0:
        return "롱 확대" if ch > 0 else "롱 축소" if ch < 0 else "변화 없음"
    return "중립"


def fmt_contracts(v):
    sign = "+" if v > 0 else "" if v < 0 else "±"
    return f"{sign}{v:,.0f}계약"


def classify(rows, repo):
    reductions = sum(1 for x in rows.values() if x["net"] < 0 and x["net_change"] > 0)
    expansions = sum(1 for x in rows.values() if x["net"] < 0 and x["net_change"] < 0)

    if reductions >= 3 and repo["state"] in ("주의", "스트레스"):
        return (
            "강제 디레버리징 경계",
            f"핵심 만기 {reductions}개에서 레버리지 펀드 순숏이 줄고 Repo가 {repo['state']} → 단순 숏커버보다 자금조달 압박 동반 여부 확인",
        )
    if reductions >= 3 and repo["state"] == "안정":
        return (
            "질서 있는 숏·베이시스 축소 가능성",
            f"핵심 만기 {reductions}개 순숏 축소 + Repo 안정 → 강제청산보다 가격 틈 축소에 따른 포지션 정리 가능성 우세",
        )
    if expansions >= 3 and repo["dvp_week_pct"] > 5:
        return (
            "숏·레버리지 확대 가능성",
            f"핵심 만기 {expansions}개 순숏 확대 + DVP Repo 거래량 약 1주 {repo['dvp_week_pct']:+.1f}% → 베이시스·레버리지 확대 여부 점검",
        )
    if expansions >= 3:
        return (
            "국채선물 숏 확대",
            f"핵심 만기 {expansions}개에서 레버리지 펀드 순숏 확대 → 방향성 금리상승 베팅과 베이시스 숏을 Repo와 함께 구분 필요",
        )
    return (
        "혼조·추가 확인",
        "만기별 레버리지 펀드 포지션이 한 방향으로 정렬되지 않음",
    )


def fmt_html(text):
    bold_prefixes = (
        "전체 판정:",
        "기술·포지셔닝:",
        "JPM 30년 기술선:",
        "2년:",
        "5년:",
        "10년:",
        "30년:",
        "Repo:",
        "DVP Repo:",
        "베이시스 해석:",
        "다음 확인:",
    )
    out = []
    for line in text.splitlines():
        e = html.escape(line, quote=False)
        bold = line in ("[미 국채 포지셔닝 Watch]", "[CFTC Leveraged Funds]") or line.startswith(bold_prefixes)
        out.append(f"<b>{e}</b>" if bold else e)
    return "\n".join(out)


def send_telegram(text):
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets missing")

    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": fmt_html(text),
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError("Telegram send failed")
    return (result.get("result") or {}).get("message_id")


def main():
    latest, prev, rows = get_cftc_positions()
    repo = repo_snapshot()
    head, reason = classify(rows, repo)
    curve = fetch_ust_curve()
    y30 = curve["ust30"].value
    y30_date = curve["ust30"].date
    ensure_recent_date("U.S. Treasury 30Y", y30_date, 4)
    jpm_signal = jpm_30y_signal(y30)
    tech_head, tech_reason = technical_positioning(rows, repo, y30)

    lines = [
        "[미 국채 포지셔닝 Watch]",
        f"기준: CFTC TFF {latest} (직전 {prev}) | Repo {repo['date']}",
        "",
        f"전체 판정: {head}",
        f"→ {reason}",
        f"기술·포지셔닝: {tech_head}",
        f"→ {tech_reason}",
        f"JPM 30년 기술선: 현재 {y30:.2f}% ({y30_date}) | {jpm_signal} | 상단 5.59→5.78→6.00 / 하단 5.25→5.15",
        "",
        "[CFTC Leveraged Funds]",
    ]
    for label in ("2년", "5년", "10년", "30년"):
        x = rows[label]
        pct = f"{x['net_oi_pct']:+.1f}%" if x["net_oi_pct"] is not None else "확인 대기"
        lines.append(
            f"{label}: 순포지션 {fmt_contracts(x['net'])} | OI 대비 {pct} | 전주 {fmt_contracts(x['net_change'])} 변화 → {position_note(x)}"
        )

    spread_sign = "+" if repo["spread_bp"] >= 0 else ""
    move_sign = "+" if repo["move_bp"] >= 0 else ""
    lines += [
        "",
        f"Repo: {repo['state']} | SOFR {repo['sofr']:.2f}% / TGCR {repo['tgcr']:.2f}% | 스프레드 {spread_sign}{repo['spread_bp']:.0f}bp | SOFR 전일 {move_sign}{repo['move_bp']:.0f}bp",
        "DVP Repo: $" + f"{repo['dvp_value']/1e12:.2f}T | 약 1주 {repo['dvp_week_pct']:+.1f}% ({repo['dvp_old_date']}→{repo['dvp_date']}) | {repo['dvp_date']}",
        "",
        "베이시스 해석: CFTC 선물 숏만으로 금리상승 베팅으로 단정하지 않음",
        "→ 숏↓ + Repo 안정 = 질서 있는 베이시스 축소 가능성",
        "→ 숏↓ + Repo 스트레스 = 강제 디레버리징 경계",
        "→ 숏↑ + Repo 거래량↑ = 레버리지 확대 가능성 보조 신호",
        "",
        "다음 확인: 다음 CFTC TFF 공개 + SOFR/TGCR + OFR DVP Repo + 30년 5.59/5.78/6.00·5.25/5.15",
        "출처: CFTC TFF Futures Only · OFR/NY Fed Repo · U.S. Treasury · JPM 기술기준(사용자 제공 2026-09-29 자료)",
    ]
    text = "\n".join(lines)

    verification = {
        "checked_at_kst": dt.datetime.now(KST).isoformat(),
        "cftc": {
            "latest": latest,
            "previous": prev,
            "official_api_html_crosscheck": True,
            "rows": rows,
        },
        "repo": repo,
        "treasury_30y": {
            "date": y30_date,
            "yield": y30,
            "source": curve["ust30"].source,
        },
        "classification": {
            "overall": head,
            "reason": reason,
            "technical": tech_head,
            "technical_reason": tech_reason,
        },
    }
    OUT.joinpath("treasury_positioning_watch.txt").write_text(text + "\n", encoding="utf-8")
    OUT.joinpath("treasury_positioning_verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    audit_only = (os.getenv("AUDIT_ONLY") or "").lower() in ("1", "true", "yes")
    if audit_only:
        print(
            f"audit_only=true cftc={latest} repo={repo['date']} dvp={repo['dvp_date']} "
            f"dvp_week={repo['dvp_week_pct']:+.2f}% y30={y30:.2f}@{y30_date} classification={head}"
        )
        return

    state = load_state()
    force = (os.getenv("FORCE_SEND") or "").lower() in ("1", "true", "yes")
    if not force and state.get("last_sent_cftc_date") == latest:
        print(f"no_new_cftc_data=true date={latest}")
        return

    mid = send_telegram(text)
    delivery = {
        "message_id": mid,
        "cftc_date": latest,
        "confirmed_at_kst": dt.datetime.now(KST).isoformat(),
    }
    OUT.joinpath("treasury_positioning_delivery.json").write_text(
        json.dumps(delivery, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    state.update({
        "last_sent_cftc_date": latest,
        "last_message_id": mid,
        "updated_at_kst": delivery["confirmed_at_kst"],
    })
    save_state(state)
    print(f"telegram_delivery_confirmed=true message_id={mid} cftc_date={latest} classification={head}")


if __name__ == "__main__":
    main()
