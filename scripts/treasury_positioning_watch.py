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

HFM_BASE = "https://data.financialresearch.gov/hf/v1/series/full"
STFM_BASE = "https://data.financialresearch.gov/v1/series/full"

CORE = {
    "2년": "TFF-LF_TU_NET_POS10YREQV",
    "5년": "TFF-LF_FV_NET_POS10YREQV",
    "10년": "TFF-LF_TY_NET_POS10YREQV",
    "30년": "TFF-LF_US_NET_POS10YREQV",
}
SPONSORED_REPO = "FICC-SPONSORED_REPO_VOL"


def load_state():
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        raise RuntimeError("series data not found")
    dedup = {}
    for date, value in found:
        dedup[date] = value
    return sorted(dedup.items())


def get_series(base, mnemonic, days=90):
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    r = requests.get(
        base,
        params={"mnemonic": mnemonic, "start_date": start},
        headers=HEADERS,
        timeout=(8, 30),
    )
    r.raise_for_status()
    return extract_points(r.json())


def common_weekly_positions():
    series = {label: dict(get_series(HFM_BASE, mnemonic, 120)) for label, mnemonic in CORE.items()}
    common = sorted(set.intersection(*(set(v) for v in series.values())))
    if len(common) < 2:
        raise RuntimeError("CFTC/OFR common weekly dates insufficient")
    latest, prev = common[-1], common[-2]
    rows = {}
    for label, data in series.items():
        cur = data[latest]
        old = data[prev]
        rows[label] = {"current": cur, "previous": old, "change": cur - old}
    return latest, prev, rows


def repo_stress():
    sofr = dict(get_series(STFM_BASE, "FNYR-SOFR-A", 45))
    tgcr = dict(get_series(STFM_BASE, "FNYR-TGCR-A", 45))
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
    return {
        "state": state,
        "date": d,
        "sofr": s,
        "tgcr": t,
        "spread_bp": spread_bp,
        "move_bp": move_bp,
    }


def sponsored_repo():
    pts = get_series(HFM_BASE, SPONSORED_REPO, 45)
    if len(pts) < 2:
        raise RuntimeError("Sponsored repo history insufficient")
    latest_date, latest = pts[-1]
    idx = max(0, len(pts) - 6)
    old_date, old = pts[idx]
    change_pct = (latest / old - 1.0) * 100.0 if old else 0.0
    return {
        "date": latest_date,
        "value": latest,
        "old_date": old_date,
        "old": old,
        "change_pct": change_pct,
    }


def fmt_usd(v):
    av = abs(v)
    sign = "-" if v < 0 else "+" if v > 0 else "±"
    if av >= 1e12:
        return sign + "$" + f"{av/1e12:.2f}T"
    if av >= 1e9:
        return sign + "$" + f"{av/1e9:.0f}B"
    if av >= 1e6:
        return sign + "$" + f"{av/1e6:.0f}M"
    return sign + "$" + f"{av:,.0f}"


def position_note(cur, change):
    if cur < 0:
        return "숏 축소" if change > 0 else "숏 확대" if change < 0 else "변화 없음"
    if cur > 0:
        return "롱 확대" if change > 0 else "롱 축소" if change < 0 else "변화 없음"
    return "중립"


def classify(rows, repo, srepo):
    reduce_count = 0
    expand_count = 0
    for x in rows.values():
        if x["current"] < 0 and x["change"] > 0:
            reduce_count += 1
        elif x["current"] < 0 and x["change"] < 0:
            expand_count += 1

    if reduce_count >= 3 and repo["state"] in ("주의", "스트레스"):
        return (
            "강제 디레버리징 경계",
            f"핵심 만기 {reduce_count}개에서 순숏이 줄고 Repo가 {repo['state']} → 질서 있는 차익축소보다 자금조달 압박 동반 여부 확인",
        )
    if reduce_count >= 3 and repo["state"] == "안정":
        return (
            "질서 있는 숏·베이시스 축소 가능성",
            f"핵심 만기 {reduce_count}개 순숏 축소 + Repo 안정 → 강제청산보다 가격 틈 축소에 따른 포지션 정리 가능성 우세",
        )
    if expand_count >= 3 and srepo["change_pct"] > 5:
        return (
            "베이시스·레버리지 확대 가능성",
            f"핵심 만기 {expand_count}개 순숏 확대 + Sponsored Repo {srepo['change_pct']:+.1f}% → 레버리지 차익거래 확대 가능성 점검",
        )
    return (
        "혼조·추가 확인",
        "CFTC 순포지션과 Repo 지표가 한 방향으로 정렬되지 않음",
    )


def fmt_html(text):
    bold_prefixes = (
        "전체 판정:",
        "2년:",
        "5년:",
        "10년:",
        "30년:",
        "Repo:",
        "Sponsored Repo:",
        "베이시스 해석:",
        "다음 확인:",
    )
    out = []
    for line in text.splitlines():
        e = html.escape(line, quote=False)
        bold = line in ("[미 국채 포지셔닝 Watch]", "[CFTC Leveraged Funds — 10년물 등가]") or line.startswith(bold_prefixes)
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
        raise RuntimeError(f"Telegram send failed: {result}")
    return (result.get("result") or {}).get("message_id")


def main():
    latest, prev, rows = common_weekly_positions()
    repo = repo_stress()
    srepo = sponsored_repo()
    head, reason = classify(rows, repo, srepo)

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
        "[CFTC Leveraged Funds — 10년물 등가]",
    ]
    for label in ("2년", "5년", "10년", "30년"):
        x = rows[label]
        lines.append(
            f"{label}: {fmt_usd(x['current'])} | 전주 {fmt_usd(x['change'])} 변화 → {position_note(x['current'], x['change'])}"
        )

    spread_sign = "+" if repo["spread_bp"] >= 0 else ""
    move_sign = "+" if repo["move_bp"] >= 0 else ""
    lines += [
        "",
        f"Repo: {repo['state']} | SOFR {repo['sofr']:.2f}% / TGCR {repo['tgcr']:.2f}% | 스프레드 {spread_sign}{repo['spread_bp']:.0f}bp | SOFR 전일 {move_sign}{repo['move_bp']:.0f}bp",
        "Sponsored Repo: $" + f"{srepo['value']/1e12:.2f}T | 약 1주 {srepo['change_pct']:+.1f}% | {srepo['date']}",
        "",
        "베이시스 해석: CFTC 선물 숏만으로 금리상승 베팅으로 단정하지 않음",
        "→ 숏↓ + Repo 안정 = 질서 있는 베이시스 축소 가능성",
        "→ 숏↓ + Repo 스트레스 = 강제 디레버리징 경계",
        "→ 숏↑ + Sponsored Repo↑ = 베이시스·레버리지 확대 가능성",
        "",
        "다음 확인: 다음 CFTC TFF 공개 + OFR Repo/Sponsored Repo",
        "출처: CFTC TFF를 집계한 OFR Hedge Fund Monitor · OFR/NY Fed Repo",
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
