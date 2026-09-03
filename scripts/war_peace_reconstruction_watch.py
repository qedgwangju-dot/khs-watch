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


def h(s):
    return html.escape(str(s or ""), quote=True)


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


def topic_label(x):
    text = (x["title"] + " " + x["description"]).lower()
    parts = []
    if any(k in text for k in ["iran", "hormuz", "tehran", "이란", "호르무즈", "테헤란"]):
        parts.append("이란·호르무즈")
    if any(k in text for k in ["ukraine", "russia", "putin", "zelensky", "우크라이나", "러시아", "푸틴", "젤렌스키"]):
        parts.append("우크라이나·러시아")
    if "재건" in x.get("tags", []) or any(k in text for k in ["reconstruction", "rebuilding", "재건", "복구"]):
        parts.append("재건")
    return " · ".join(parts) or "전쟁·외교"


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
                arrow = "▲" if pct > 0 else "▼" if pct < 0 else "－"
                rows.append({"name": name, "price": px, "pct": pct, "arrow": arrow})
        except Exception:
            pass
    return rows


def load_state():
    if not STATE.exists():
        return {"seen": [], "updated_at": None}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": [], "updated_at": None}


def build_alert(items, markets, now):
    peace = any("종전·협상" in x["tags"] for x in items)
    escalation = any("확전" in x["tags"] for x in items)
    rebuild = any("재건" in x["tags"] for x in items)

    lines = [
        "🚨 <b>전쟁·종전·재건 웹감시</b>",
        f"🕒 {now:%Y-%m-%d %H:%M} KST",
        "",
        "⚡ <b>핵심 변화</b>",
    ]

    # 가독성 원칙: 가장 중요한 5~8개 문장을 최상단에서 먼저 읽히게 한다.
    for idx, x in enumerate(items[:8], 1):
        tags = " · ".join(x["tags"]) or "전쟁"
        lines.append(f"<b>{idx}. [{h(topic_label(x))}]</b> {h(x['title'])}")
        lines.append(f"   └ {h(tags)} · {h(x['source'] or '출처미상')}")

    if markets:
        lines += ["", "📊 <b>시장 반응</b>"]
        for m in markets:
            lines.append(f"• {h(m['name'])} <b>{m['price']:,.2f}</b> {m['arrow']} {m['pct']:+.2f}%")

    lines += ["", "🎯 <b>투자 판정</b>"]
    if peace:
        lines.append("• <b>할인율:</b> 종전·휴전 진전이면 유가·전쟁 위험프리미엄 완화 가능")
        lines.append("• <b>수급:</b> 달러·금리 안정이 동반되면 나스닥·신흥국 위험선호에 우호적")
        lines.append("• <b>시간표:</b> 공식 휴전문·정상회담·제재해제·병력철수 여부가 다음 확인점")
    if rebuild:
        lines.append("• <b>돈 버는 능력:</b> 재건 기대보다 기금 → 입찰 → 본계약 → 수주 → 매출인식 순서 확인")
        lines.append("• <b>한국기업:</b> 실명·계약금액·발주처가 공식 확인되기 전에는 후보 단계")
    if escalation:
        lines += ["", "⚠️ <b>반대 신호</b>", "• 공습·미사일·봉쇄·병력증강이 함께 잡힘 — 종전 기대와 확전 위험이 동시에 존재"]

    lines += ["", "🔎 <b>다음 확인</b>"]
    checkpoints = []
    if peace:
        checkpoints.extend(["공식 합의문/공동성명", "실제 교전 중단", "후속 정상·실무회담 일정"])
    if rebuild:
        checkpoints.extend(["재건기금 운용주체", "한국 기업 실명", "입찰·MOU·본계약 구분"])
    if escalation:
        checkpoints.extend(["추가 공습 여부", "호르무즈 통항량·보험료"])
    for cp in list(dict.fromkeys(checkpoints))[:6]:
        lines.append(f"• {h(cp)}")

    lines += ["", "🔗 <b>원문</b>"]
    for idx, x in enumerate(items[:8], 1):
        src = h(x["source"] or "출처미상")
        url = h(x["link"])
        lines.append(f"{idx}. {src} · <a href=\"{url}\">기사 열기</a>")

    text = "\n".join(lines)
    return text[:4000] + "\n"


def run(test=False):
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, PENDING):
        if p.exists():
            p.unlink()
    now = dt.datetime.now(KST)
    if test:
        ALERT.write_text(
            "🚨 <b>전쟁·종전·재건 웹감시 테스트</b>\n"
            f"🕒 {now:%Y-%m-%d %H:%M} KST\n\n"
            "⚡ <b>핵심 변화</b>\n"
            "<b>1. [이란·호르무즈]</b> Telegram 연결 및 가독성 형식 점검\n"
            "   └ 종전·협상 · 테스트\n\n"
            "📊 <b>시장 반응</b>\n"
            "• 실제 알림에서는 나스닥100 선물·WTI·Brent·달러지수를 줄별로 표시\n\n"
            "🎯 <b>투자 판정</b>\n"
            "• 할인율·수급·시간표·재건 매출 연결을 분리 표시\n\n"
            "🔎 <b>다음 확인</b>\n"
            "• 공식 합의문 · 실제 교전 중단 · 본계약/수주\n\n"
            "✅ 연결 테스트 메시지입니다.\n",
            encoding="utf-8",
        )
        PENDING.write_text(json.dumps({"ids": []}, ensure_ascii=False), encoding="utf-8")
        return

    state = load_state()
    seen = set(state.get("seen", []))
    gathered, errors = [], []
    for q in QUERIES:
        items, err = google_news(q)
        if err:
            errors.append(err)
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
    markets = market_snapshot()

    if items:
        ALERT.write_text(build_alert(items, markets, now), encoding="utf-8")
        PENDING.write_text(json.dumps({"ids": [x["id"] for x in items]}, ensure_ascii=False), encoding="utf-8")

    summary = [
        "# 전쟁·종전·재건 웹감시 상태",
        "",
        f"- 조회: {now.isoformat(timespec='seconds')}",
        f"- 수집: {len(gathered)}건",
        f"- 신규 강한 신호: {len(items)}건",
        "- Telegram 형식: HTML · 핵심변화 → 시장반응 → 투자판정 → 다음확인 → 원문",
    ]
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
