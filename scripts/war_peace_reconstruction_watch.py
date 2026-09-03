#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "war_peace_reconstruction_watch_state.json"
OUT = ROOT / "out"
ALERT = OUT / "war_peace_reconstruction_alert.txt"
PENDING = OUT / "war_peace_reconstruction_pending.json"
SUMMARY = OUT / "war_peace_reconstruction_watch.md"
KST = ZoneInfo("Asia/Seoul")

TRUSTED = (
    "Reuters", "Wall Street Journal", "WSJ", "Associated Press", "AP News", "Axios",
    "Financial Times", "Bloomberg", "The Guardian", "BBC", "White House", "U.S. Department of Defense",
    "Kremlin", "President of Ukraine", "연합뉴스", "Yonhap", "Al Arabiya"
)

QUERIES = [
    'site:reuters.com (Iran OR Hormuz) (ceasefire OR peace OR talks OR negotiations OR strike OR Trump) when:2d',
    'site:wsj.com Iran Trump advisers war midterms peace talks when:2d',
    'site:axios.com (Iran OR Ukraine OR Russia) (peace OR ceasefire OR summit OR talks OR Trump OR Ratcliffe) when:3d',
    'site:reuters.com (Ukraine OR Russia OR Putin OR Zelensky) (peace talks OR ceasefire OR summit OR negotiations OR Trump) when:3d',
    'site:apnews.com (Iran OR Ukraine OR Russia) (ceasefire OR peace OR talks OR strikes) when:3d',
    '(Iran OR Ukraine) (reconstruction OR rebuilding OR reconstruction fund OR infrastructure OR South Korea OR Korean companies) when:7d',
    'site:yna.co.kr (이란 OR 우크라이나 OR 러시아) (종전 OR 휴전 OR 평화협상 OR 재건) when:3d',
]

PEACE = [
    "ceasefire", "peace talks", "peace agreement", "end the war", "ending the war", "end war",
    "peace deal", "negotiations", "talks resume", "summit", "trilateral", "withdrawal",
    "constructive peace", "종전", "휴전", "평화협상", "정상회담", "협상 재개", "전쟁 중단",
]
ESCALATION = [
    "strike", "strikes", "attack", "missile", "drone", "deployment", "mobilization", "blockade",
    "hormuz closure", "escalation", "공습", "미사일", "드론", "봉쇄", "확전", "병력 증강",
]
REBUILD = [
    "reconstruction", "rebuilding", "reconstruction fund", "infrastructure", "investment vehicle",
    "korean companies", "south korea", "tender", "epc", "재건", "복구", "재건기금", "한국 기업", "수주",
]
POLITICAL = ["midterm", "election", "republican", "gop", "중간선거", "공화당"]


def req(url, timeout=20):
    headers = {"User-Agent": "Mozilla/5.0 khs-watch/1.0"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read()


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def google_news(query):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(req(url))
    except Exception as e:
        return [], f"{query}: {type(e).__name__}"
    out = []
    for item in root.findall("./channel/item")[:20]:
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        pub = clean(item.findtext("pubDate"))
        source_node = item.find("source")
        source = clean(source_node.text if source_node is not None else "")
        desc = clean(item.findtext("description"))
        out.append({"title": title, "link": link, "published": pub, "source": source, "description": desc})
    return out, None


def score_item(x):
    text = (x["title"] + " " + x["description"]).lower()
    source = x["source"]
    score = 0
    tags = []
    if any(k.lower() in text for k in PEACE):
        score += 4; tags.append("종전·협상")
    if any(k.lower() in text for k in ESCALATION):
        score += 3; tags.append("확전")
    if any(k.lower() in text for k in REBUILD):
        score += 4; tags.append("재건")
    if any(k.lower() in text for k in POLITICAL):
        score += 2; tags.append("정치일정")
    if any(t.lower() in source.lower() for t in TRUSTED):
        score += 3
    if any(k in text for k in ["trump", "putin", "zelensky", "iran", "ukraine", "russia", "hormuz", "트럼프", "푸틴", "젤렌스키", "이란", "우크라이나", "러시아"]):
        score += 1
    return score, sorted(set(tags))


def item_id(x):
    key = re.sub(r"\W+", " ", x["title"].lower()).strip()
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def market_snapshot():
    symbols = {"NQ=F": "나스닥100 선물", "CL=F": "WTI", "BZ=F": "Brent", "DX-Y.NYB": "달러지수"}
    rows = []
    for sym, name in symbols.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=5d&interval=5m"
            data = json.loads(req(url, 15).decode())
            r = data["chart"]["result"][0]
            meta = r["meta"]
            px = float(meta.get("regularMarketPrice") or 0)
            prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0)
            if px and prev:
                pct = (px / prev - 1) * 100
                rows.append(f"{name} {px:,.2f} ({pct:+.2f}%)")
        except Exception:
            pass
    return " · ".join(rows)


def load_state():
    if not STATE.exists():
        return {"seen": [], "updated_at": None}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": [], "updated_at": None}


def run(test=False):
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, PENDING):
        if p.exists(): p.unlink()
    now = dt.datetime.now(KST)
    if test:
        ALERT.write_text(
            "[전쟁·종전·재건 웹감시 테스트]\n"
            f"확인시각: {now:%Y-%m-%d %H:%M KST}\n"
            "대상: 이란·호르무즈 / 러시아·우크라이나 / 재건·한국기업\n"
            "상태: Telegram 연결 테스트\n",
            encoding="utf-8",
        )
        PENDING.write_text(json.dumps({"ids": []}, ensure_ascii=False), encoding="utf-8")
        return

    state = load_state(); seen = set(state.get("seen", []))
    gathered, errors = [], []
    for q in QUERIES:
        items, err = google_news(q)
        if err: errors.append(err)
        gathered.extend(items)

    uniq = {}
    for x in gathered:
        iid = item_id(x)
        score, tags = score_item(x)
        if score < 6 or iid in seen:
            continue
        x.update({"id": iid, "score": score, "tags": tags})
        prev = uniq.get(iid)
        if prev is None or score > prev["score"]:
            uniq[iid] = x

    items = sorted(uniq.values(), key=lambda z: z["score"], reverse=True)[:8]
    lines = ["# 전쟁·종전·재건 웹감시", "", f"조회: {now:%Y-%m-%d %H:%M KST}"]
    snap = market_snapshot()
    if snap:
        lines += ["", f"시장: {snap}"]

    if items:
        lines += ["", "핵심 변화"]
        for x in items:
            tag = "/".join(x["tags"]) or "전쟁"
            src = x["source"] or "출처미상"
            lines += [f"• [{tag}] {x['title']}", f"  출처: {src}", f"  링크: {x['link']}"]
        if any("종전·협상" in x["tags"] for x in items):
            lines += ["", "판정: 종전·협상 촉매 감지 — 유가·달러·외국인 위험선호와 재건주 발주 시간표 확인 필요"]
        if any("재건" in x["tags"] for x in items):
            lines += ["재건 체크: 기금·입찰·MOU·수주 공시를 구분하고 한국 기업 실명은 공식 공시 전까지 후보로만 표기"]
        text = "\n".join(lines)
        ALERT.write_text(text[:3900] + "\n", encoding="utf-8")
        PENDING.write_text(json.dumps({"ids": [x["id"] for x in items]}, ensure_ascii=False), encoding="utf-8")

    summary = ["# 전쟁·종전·재건 웹감시 상태", "", f"- 조회: {now.isoformat(timespec='seconds')}", f"- 수집: {len(gathered)}건", f"- 신규 강한 신호: {len(items)}건"]
    if errors:
        summary.append(f"- 소스 오류: {len(errors)}개")
    SUMMARY.write_text("\n".join(summary) + "\n", encoding="utf-8")


def finalize():
    if not PENDING.exists():
        return
    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    state = load_state()
    seen = list(dict.fromkeys(list(state.get("seen", [])) + list(pending.get("ids", []))))[-800:]
    state = {"seen": seen, "updated_at": dt.datetime.now(KST).isoformat(timespec="seconds")}
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    a = ap.parse_args()
    if a.finalize:
        finalize()
    else:
        run(test=a.telegram_test)
