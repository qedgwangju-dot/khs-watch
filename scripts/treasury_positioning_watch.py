#!/usr/bin/env python3
import datetime as dt
import html
import json
import os
import pathlib
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import requests

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
OFR_URL = "https://data.financialresearch.gov/v1/series/full"

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


def ofr_series(mnemonic, days=45):
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    r = requests.get(
        OFR_URL,
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

    if spread_bp >= 10 or move_bp >= 10:
        state = "스트레스"
    elif spread_bp >= 5 or move_bp >= 5:
        state = "주의"
    else:
        state = "안정"

    dvp = ofr_series("REPO-DVP_TV_TOT-P", 30)
    dvp_date, dvp_value = dvp[-1]
    old_idx = max(0, len(dvp) - 6)
    old_date, old_value = dvp[old_idx]
    dvp_week_pct = (dvp_value / old_value - 1.0) * 100.0 if old_value else 0.0

    return {
        "state": state,
        "date": d,
        "sofr": s,
        "tgcr": t,
        "spread_bp": spread_bp,
        "move_bp": move_bp,
        "dvp_date": dvp_date,
        "dvp_value": dvp_value,
        "dvp_old_date": old_date,
        "dvp_week_pct": dvp_week_pct,
    }


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

    state = load_state()
    force = (os.getenv("FORCE_SEND") or "").lower() in ("1", "true", "yes")
    if not force and state.get("last_sent_cftc_date") == latest:
        print(f"no_new_cftc_data=true date={latest}")
        return

    lines = [
        "[미 국채 포지셔닝 Watch]",
        f"기준: CFTC TFF {latest} (직전 {prev}) | Repo {repo['date']}",
        "",
        f"전체 판정: {head}",
        f"→ {reason}",
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
        "DVP Repo: $" + f"{repo['dvp_value']/1e12:.2f}T | 약 1주 {repo['dvp_week_pct']:+.1f}% | {repo['dvp_date']}",
        "",
        "베이시스 해석: CFTC 선물 숏만으로 금리상승 베팅으로 단정하지 않음",
        "→ 숏↓ + Repo 안정 = 질서 있는 베이시스 축소 가능성",
        "→ 숏↓ + Repo 스트레스 = 강제 디레버리징 경계",
        "→ 숏↑ + Repo 거래량↑ = 레버리지 확대 가능성 보조 신호",
        "",
        "다음 확인: 다음 CFTC TFF 공개 + SOFR/TGCR + OFR DVP Repo",
        "출처: CFTC TFF Futures Only · OFR/NY Fed Repo",
    ]
    text = "\n".join(lines)

    OUT.joinpath("treasury_positioning_watch.txt").write_text(text + "\n", encoding="utf-8")
    mid = send_telegram(text)
    state.update({
        "last_sent_cftc_date": latest,
        "last_message_id": mid,
        "updated_at_kst": dt.datetime.now(KST).isoformat(),
    })
    save_state(state)
    print(f"telegram_delivery_confirmed=true message_id={mid} cftc_date={latest} classification={head}")


if __name__ == "__main__":
    main()
