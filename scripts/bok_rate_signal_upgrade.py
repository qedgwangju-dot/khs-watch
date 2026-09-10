#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT, DATA = ROOT / "out", ROOT / "data"
STATE = DATA / "bok_mpc_watch_state.json"
PENDING = OUT / "bok_mpc_pending_state.json"
ALERT = OUT / "bok_mpc_alert.html"
STATUS = OUT / "bok_mpc_status.md"
ERROR = OUT / "bok_mpc_errors.log"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; khs-bok-rate-signal/1.0)", "Accept-Language": "ko-KR,ko;q=0.9"}
FSC_LIST = "https://www.fsc.go.kr/no010101"
FSC_FALLBACK = "https://www.fsc.go.kr/no010101/87675"
CPI_HOME = "https://mods.go.kr/cpi/"
CPI_FALLBACK = "https://www.korea.kr/briefing/policyBriefingView.do?newsId=156777515"
REB_LIST = "https://www.reb.or.kr/reb/na/ntt/selectNttList.do?mi=9565&bbsId=1154"
BOK_SCHEDULE = "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?menuNo=200755&mtgSe=A"
GOOGLE_NEWS = "https://news.google.com/rss/search"
SPEAKERS = ["신현송", "박종우", "황건일", "장용성", "신성환", "유상대", "김종화"]

HAWK = {
    "hike_needed": [r"추가\s*인상", r"인상\s*필요", r"금리\s*인상\s*기조", r"인상\s*가능"],
    "neutral_upper": [r"중립금리[^.]{0,40}(?:상단|상회)", r"중립\s*범위[^.]{0,30}상단", r"긴축적"],
    "inflation_upside": [r"물가\s*상방", r"근원물가[^.]{0,35}(?:높|상승|재가속)", r"물가[^.]{0,30}경계"],
    "middle_east_inflation": [r"중동[^.]{0,80}물가", r"유가[^.]{0,80}(?:물가|수입물가)", r"성장보다\s*물가"],
}
DOVE = {
    "oct_hike_caution": [r"10월[^.]{0,50}인상[^.]{0,30}(?:무리|예단|단정)", r"10월[^.]{0,40}(?:예단|단정)[^.]{0,40}(?:어렵|무리)"],
    "rate_not_only_tool": [r"금리\s*하나만으로[^.]{0,60}(?:어렵|쉽지|부담)", r"금리[^.]{0,50}금융\s*불균형[^.]{0,50}(?:어렵|부담)"],
    "macroprudential_mix": [r"거시건전성", r"대출\s*규제", r"주택\s*공급", r"주택공급"],
}


def norm(s): return re.sub(r"\s+", " ", s or "").strip()
def get(url, timeout=25):
    r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True); r.raise_for_status(); return r

def read_json(path):
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception: return {}

def root_state():
    x = read_json(PENDING); return x if x else read_json(STATE)
def err(s):
    with ERROR.open("a", encoding="utf-8") as f: f.write(s.rstrip() + "\n")
def period(text):
    m = re.search(r"(20\d{2})년\s*(\d{1,2})월", text); return f"{m.group(1)}-{int(m.group(2)):02d}" if m else None
def signed(s):
    if not s: return None
    neg = s.strip().startswith(("-", "△", "▲")); m = re.search(r"[0-9]+(?:\.[0-9]+)?", s.replace(",", ""))
    return (-1 if neg else 1) * float(m.group()) if m else None

def list_link(url, key, domain):
    p = get(url); soup = BeautifulSoup(p.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if key in norm(a.get_text(" ", strip=True)):
            u = urllib.parse.urljoin(p.url, a["href"])
            if domain in urllib.parse.urlparse(u).netloc: return u
    return None


def household():
    try: u = list_link(FSC_LIST, "가계대출 동향", "fsc.go.kr")
    except Exception: u = None
    p = get(u or FSC_FALLBACK); t = norm(BeautifulSoup(p.text, "html.parser").get_text(" ", strip=True))
    mt = re.search(r"(?:全|전)\s*금융권\s*가계대출.{0,180}?([+△▲-]?\s*[0-9.]+)\s*조원\s*증가", t)
    mm = re.search(r"주택담보대출.{0,140}?([+△▲-]?\s*[0-9.]+)\s*조원\s*증가.{0,120}?전월\s*\(\s*([+△▲-]?\s*[0-9.]+)\s*조원", t)
    if not mt or not mm: raise RuntimeError("금융위원회 가계대출 핵심 수치 파싱 실패")
    total, mort, prev = signed(mt.group(1)), signed(mm.group(1)), signed(mm.group(2))
    return {"period": period(t), "total_trn": total, "mortgage_trn": mort, "mortgage_prev_trn": prev,
            "mortgage_reaccelerating": prev is not None and mort > prev, "source": p.url, "source_tier": "공식"}


def parse_cpi(u):
    p = get(u); t = norm(BeautifulSoup(p.text, "html.parser").get_text(" ", strip=True))
    h = re.search(r"소비자물가지수.{0,200}?전년동월대비\s*([0-9.]+)%\s*상승", t)
    c = re.search(r"식료품\s*및\s*에너지제외지수.{0,180}?전년동월대비\s*([0-9.]+)%", t)
    if not h or not c: raise RuntimeError("소비자물가 핵심 수치 파싱 실패")
    return {"period": period(t), "headline_yoy": float(h.group(1)), "core_yoy": float(c.group(1)), "source": p.url, "source_tier": "공식"}

def inflation():
    urls = []
    try:
        p = get(CPI_HOME); soup = BeautifulSoup(p.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if re.search(r"20\d{2}년\s*\d{1,2}월\s*소비자물가동향", norm(a.get_text(" ", strip=True))):
                u = urllib.parse.urljoin(p.url, a["href"])
                if u not in urls: urls.append(u)
                if len(urls) >= 3: break
    except Exception: pass
    if CPI_FALLBACK not in urls: urls.append(CPI_FALLBACK)
    rows = []
    for u in urls[:4]:
        try:
            x = parse_cpi(u)
            if x["period"] and all(r["period"] != x["period"] for r in rows): rows.append(x)
        except Exception: pass
    if not rows: raise RuntimeError("최신 소비자물가 공식자료 조회 실패")
    rows.sort(key=lambda x: x["period"], reverse=True); cur = rows[0]; prev = rows[1] if len(rows) > 1 else None
    cur["prev_headline_yoy"] = prev.get("headline_yoy") if prev else None; cur["prev_core_yoy"] = prev.get("core_yoy") if prev else None
    cur["headline_reaccelerating"] = bool(prev and cur["headline_yoy"] >= prev["headline_yoy"] + 0.1)
    cur["core_reaccelerating"] = bool(prev and cur["core_yoy"] >= prev["core_yoy"] + 0.1)
    return cur


def rate_after(text, label):
    m = re.search(rf"{label}\s*[:：]?\s*([+-]?[0-9]+(?:\.[0-9]+)?)%", text); return float(m.group(1)) if m else None

def housing():
    p = get(REB_LIST); soup = BeautifulSoup(p.text, "html.parser"); link = None; title = ""
    for a in soup.find_all("a", href=True):
        x = norm(a.get_text(" ", strip=True))
        if "주간 아파트가격 동향" in x: title, link = x, urllib.parse.urljoin(p.url, a["href"]); break
    if not link: raise RuntimeError("한국부동산원 최신 주간자료 링크 조회 실패")
    d = get(link); t = norm(BeautifulSoup(d.text, "html.parser").get_text(" ", strip=True)); m = re.search(r"(20\d{2})년\s*(\d{1,2})월\s*(\d+)주", title + " " + t)
    vals = {"seoul_wow": rate_after(t, "서울"), "gangbuk_wow": rate_after(t, r"강북\s*14개구"),
            "gangnam_wow": rate_after(t, r"강남\s*11개구"), "gyeonggi_wow": rate_after(t, "경기"), "capital_wow": rate_after(t, "수도권")}
    pos = sum(1 for k in ("gangbuk_wow", "gangnam_wow", "gyeonggi_wow") if vals[k] is not None and vals[k] > 0)
    return {"period": f"{m.group(1)}-{int(m.group(2)):02d}-{m.group(3)}주" if m else None, **vals, "positive_axes": pos,
            "broad_diffusion": bool((vals["seoul_wow"] or 0) > 0 and pos >= 2), "source": d.url, "source_tier": "공식"}


def oil():
    u = "https://query1.finance.yahoo.com/v8/finance/chart/BZ%3DF?range=10d&interval=1d&includePrePost=false"; j = get(u).json(); r = ((j.get("chart") or {}).get("result") or [None])[0]
    if not r: raise RuntimeError("브렌트유 시계열 없음")
    ts = r.get("timestamp") or []; cl = (((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    z = [(a, float(b)) for a, b in zip(ts, cl) if b is not None]
    if len(z) < 2: raise RuntimeError("브렌트유 유효 종가 부족")
    base = z[-6][1] if len(z) >= 6 else z[0][1]; change = (z[-1][1] / base - 1) * 100
    return {"date": dt.datetime.fromtimestamp(z[-1][0], dt.timezone.utc).date().isoformat(), "brent_usd": round(z[-1][1], 2), "change_5d_pct": round(change, 2), "source": "Yahoo Finance BZ=F", "source_tier": "시장자료"}


def news(q, limit=25):
    u = GOOGLE_NEWS + "?" + urllib.parse.urlencode({"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}); root = ET.fromstring(get(u).content); out = []
    for item in root.findall(".//item")[:limit]:
        try:
            d = parsedate_to_datetime(norm(item.findtext("pubDate") or "")); d = (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).astimezone(KST)
        except Exception: d = None
        src = item.find("source")
        out.append({"title": norm(item.findtext("title") or ""), "description": norm(BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)), "link": norm(item.findtext("link") or ""), "published": d, "source_name": norm(src.text if src is not None and src.text else "")})
    return out

def flags(blob):
    x = {}; [x.__setitem__(k, any(re.search(p, blob) for p in ps)) for k, ps in HAWK.items()]; [x.__setitem__(k, any(re.search(p, blob) for p in ps)) for k, ps in DOVE.items()]; return x
def rhetoric_score(f):
    h = (2 if f.get("hike_needed") else 0) + (1 if f.get("neutral_upper") else 0) + (1 if f.get("inflation_upside") else 0) + (1 if f.get("middle_east_inflation") else 0)
    d = (2 if f.get("oct_hike_caution") else 0) + (1 if f.get("rate_not_only_tool") else 0) + (1 if f.get("macroprudential_mix") else 0)
    return max(-2, min(2, h - d))
def rhetoric(now):
    rows = []; cutoff = now - dt.timedelta(days=4)
    for q in ("한국은행 박종우 기준금리 인상 중립금리 물가 중동", "한국은행 신현송 기준금리 추가 인상 근원물가 금융안정", "한국은행 금통위원 기준금리 인상 금융안정 주택 가계부채"):
        try: rows += news(q)
        except Exception as e: err(f"한은 발언 뉴스 조회 일부 실패: {type(e).__name__}: {e}")
    out = {}
    for r in rows:
        if not r["published"] or r["published"] < cutoff: continue
        blob = norm(r["title"] + " " + r["description"]); sp = next((s for s in SPEAKERS if s in blob), None)
        if not sp: continue
        f = flags(blob)
        if not any(f.values()): continue
        semantic = {"date": r["published"].date().isoformat(), "speaker": sp, "flags": {k: v for k, v in sorted(f.items()) if v}}
        eh = hashlib.sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        ev = {**semantic, "event_hash": eh, "score": rhetoric_score(f), "title": r["title"], "link": r["link"], "source_name": r["source_name"], "published_at_kst": r["published"].isoformat(timespec="minutes")}
        rank = 0 if "한국은행" in ev["source_name"] else 1 if "연합뉴스" in ev["source_name"] else 2; old = out.get(eh); oldrank = 9 if not old else (0 if "한국은행" in old["source_name"] else 1 if "연합뉴스" in old["source_name"] else 2)
        if not old or rank < oldrank: out[eh] = ev
    return sorted(out.values(), key=lambda x: x["published_at_kst"], reverse=True)


def next_mpc(now):
    p = get(BOK_SCHEDULE); t = norm(BeautifulSoup(p.text, "html.parser").get_text(" ", strip=True)); ds = []
    for m in re.finditer(r"(\d{2})월\s*(\d{2})일", t):
        try:
            d = dt.date(now.year, int(m.group(1)), int(m.group(2)))
            if d >= now.date(): ds.append(d)
        except Exception: pass
    if not ds: raise RuntimeError("다음 금통위 일정 파싱 실패")
    return {"date": min(ds).isoformat(), "source": p.url}

def ip(x):
    if not x: return 0
    p = 2 if x.get("core_yoy", 0) >= 3 else 1 if x.get("core_yoy", 0) >= 2.5 else 0
    return p + (1 if x.get("core_reaccelerating") or x.get("headline_reaccelerating") else 0)
def hp(x): return (1 if x and x.get("mortgage_trn", 0) >= 4 else 0) + (1 if x and x.get("mortgage_reaccelerating") else 0)
def rp(x): return 2 if x and x.get("broad_diffusion") else 1 if x and x.get("seoul_wow", 0) > 0 else -1 if x else 0
def op(x):
    ch = x.get("change_5d_pct") if x else None
    return 2 if ch is not None and ch >= 10 else 1 if ch is not None and ch >= 5 else -1 if ch is not None and ch <= -5 else 0
def grade(score, inf, hh, oilx, rhet):
    financial = bool(hh and hh.get("mortgage_reaccelerating") and hh.get("mortgage_trn", 0) >= 4); core = bool(inf and inf.get("core_reaccelerating")); oup = bool(oilx and oilx.get("change_5d_pct", 0) >= 5)
    if rhet >= 1 and core and oup and financial: return "🔴", "다음 회의 인상 경보"
    if score >= 5: return "🟠", "인상 압력 확대"
    if score >= 1 or financial or (inf and inf.get("core_yoy", 0) >= 2.5): return "🟡", "추가인상 살아있음"
    return "🟢", "동결 우세"
def safe(new, old):
    if new: return {**new, "stale": False}
    return {**old, "stale": True} if old else None
def same(a, b, ks): return bool(a and b and all(a.get(k) == b.get(k) for k in ks))
def arrow(n): return "↑" if n > 0 else "↓" if n < 0 else "→"


def message(s, reasons, newr):
    c = s["components"]; inf, hh, hs, oi = c.get("inflation"), c.get("household"), c.get("housing"), c.get("oil"); fin, price = hp(hh) + rp(hs), ip(inf) + op(oi)
    lines = [f"🚨 <b>한국은행 추가인상 위험 변화 — 금융안정 압력 {arrow(fin)} / 물가 압력 {arrow(price)}</b>", "", f"• 위험등급: <b>{s['grade_emoji']} {s['grade_label']}</b> (위험점수 {s['risk_score']})"]
    if s.get("next_mpc_date"):
        d = dt.date.fromisoformat(s["next_mpc_date"]); lines.append(f"• 다음 금통위: <b>{d.month}월 {d.day}일</b>")
    lines.append("• 위험점수는 통계적 인상확률이 아니라 <b>정책 조건 판정값</b>입니다.")
    if reasons: lines += ["", "<b>이번에 달라진 점</b>"] + ["• " + html.escape(x) for x in reasons[:6]]
    lines += ["", "<b>① 물가·중동 유가</b>"]
    if inf:
        pc = f" (직전 {inf['prev_core_yoy']:.1f}%)" if isinstance(inf.get("prev_core_yoy"), (int, float)) else ""; lines.append(f"• 소비자물가 <b>{inf['headline_yoy']:.1f}%</b> / 식료품·에너지 제외 근원 <b>{inf['core_yoy']:.1f}%{pc}</b>")
    else: lines.append("• 소비자물가: 확인 불가")
    lines.append(f"• 브렌트유 <b>${oi['brent_usd']:.2f}</b> / 최근 5거래일 <b>{oi['change_5d_pct']:+.1f}%</b>" if oi else "• 브렌트유: 확인 불가")
    lines += ["", "<b>② 가계부채·주택 확산</b>"]
    if hh:
        tag = " <b>→ 주담대 재가속 경보</b>" if hh.get("mortgage_reaccelerating") else ""; lines.append(f"• 전 금융권 가계대출 <b>{hh['total_trn']:+.1f}조원</b>"); lines.append(f"• 주택담보대출 <b>{hh['mortgage_trn']:+.1f}조원</b> / 직전 <b>{hh['mortgage_prev_trn']:+.1f}조원</b>{tag}")
    else: lines.append("• 가계대출: 확인 불가")
    if hs:
        vals = [f"{a} {hs[k]:+.2f}%" for a, k in (("서울", "seoul_wow"), ("강북", "gangbuk_wow"), ("강남", "gangnam_wow"), ("경기", "gyeonggi_wow")) if isinstance(hs.get(k), (int, float))]; lines.append("• 주간 아파트 <b>" + " / ".join(vals) + "</b>" if vals else "• 주간 아파트 세부수치 확인 불가"); lines.append("• 확산 판정: <b>" + ("서울 일부가 아니라 주변축까지 확산" if hs.get("broad_diffusion") else "광범위 확산 조건 미충족") + "</b>")
    else: lines.append("• 한국부동산원 확산자료: 확인 불가")
    lines += ["", "<b>③ 한은 발언 변화</b>"]
    if newr:
        for e in newr[:3]:
            f = e["flags"]; p = []
            if f.get("oct_hike_caution"): p.append("다음 회의 즉시 인상 압력 ↓")
            if f.get("rate_not_only_tool") or f.get("macroprudential_mix"): p.append("금융안정의 금리 의존도 ↓")
            if f.get("hike_needed") or f.get("neutral_upper"): p.append("금리 경로 압력 ↑")
            if f.get("inflation_upside") or f.get("middle_east_inflation"): p.append("물가 압력 ↑")
            lines.append(f"• <b>{html.escape(e['speaker'])}</b>: {html.escape(' / '.join(p) or '정책 의미 변화')}"); lines.append("  └ " + html.escape(e["title"][:180]))
    else: lines.append(f"• 새 정책 의미 변화 없음 / 최근 발언 순점수 <b>{s['rhetoric_score']:+d}</b>")
    lines += ["", "<b>최종 판정</b>"]
    verdict = "매파 발언 강화·근원물가 재가속·유가 상승·금융불균형 악화가 동시에 확인돼 다음 회의 인상 경보 조건 충족" if s["grade_emoji"] == "🔴" else "물가 또는 금융불균형이 복수 축에서 동시에 악화돼 인상 압력이 확대된 상태" if s["grade_emoji"] == "🟠" else "즉시 인상을 단정할 단계는 아니지만 근원물가·주담대·유가·한은 발언 중 하나 이상이 추가인상 가능성을 유지" if s["grade_emoji"] == "🟡" else "물가 둔화·주담대 둔화·주택 확산 축소가 함께 확인돼 동결 쪽 조건이 우세"
    lines.append("• <b>" + verdict + "</b>")
    src = [("소비자물가 공식자료", inf), ("가계대출 공식자료", hh), ("한국부동산원 주간자료", hs)]
    links = [(a, x["source"]) for a, x in src if x and x.get("source")]
    if s.get("next_mpc_source"): links.append(("한국은행 금통위 일정", s["next_mpc_source"]))
    links += [(e["speaker"] + " 발언 근거", e["link"]) for e in newr[:2] if e.get("link")]
    if links:
        lines += ["", "<b>원문·근거</b>"]; used = set()
        for a, u in links:
            if u not in used: used.add(u); lines.append(f'<a href="{html.escape(u, quote=True)}">• {html.escape(a)}</a>')
    return "\n".join(lines)


def main():
    OUT.mkdir(parents=True, exist_ok=True); now = dt.datetime.now(KST); root = root_state(); old = root.get("rate_signal_upgrade") if isinstance(root.get("rate_signal_upgrade"), dict) else {}; oc = old.get("components") if isinstance(old.get("components"), dict) else {}; boot = not bool(old); got = {}
    for n, fn in (("inflation", inflation), ("household", household), ("housing", housing), ("oil", oil)):
        try: got[n] = fn()
        except Exception as e: got[n] = None; err(f"추가인상 위험감시 {n} 조회 실패: {type(e).__name__}: {e}")
    c = {n: safe(got[n], oc.get(n)) for n in got}
    try: rhet = rhetoric(now)
    except Exception as e: rhet = []; err(f"추가인상 위험감시 rhetoric 조회 실패: {type(e).__name__}: {e}")
    seen = list(old.get("seen_rhetoric_hashes") or []); ss = set(seen); newr = [e for e in rhet if e["event_hash"] not in ss]
    if boot: newr = []
    for e in rhet:
        if e["event_hash"] not in ss: seen.append(e["event_hash"]); ss.add(e["event_hash"])
    seen = seen[-150:]; rscore = max(-2, min(2, sum(e.get("score", 0) for e in rhet[:5])))
    try: nxt = next_mpc(now)
    except Exception as e: nxt = {"date": old.get("next_mpc_date"), "source": old.get("next_mpc_source")}; err(f"다음 금통위 일정 조회 실패: {type(e).__name__}: {e}")
    score = ip(c.get("inflation")) + hp(c.get("household")) + rp(c.get("housing")) + op(c.get("oil")) + rscore; ge, gl = grade(score, c.get("inflation"), c.get("household"), c.get("oil"), rscore)
    ns = {"version": 1, "updated_at_kst": now.isoformat(timespec="seconds"), "risk_score": score, "grade_emoji": ge, "grade_label": gl, "next_mpc_date": nxt.get("date"), "next_mpc_source": nxt.get("source"), "components": c, "rhetoric_score": rscore, "recent_rhetoric": rhet[:5], "seen_rhetoric_hashes": seen}
    reasons = []
    if not boot:
        if old.get("grade_emoji") != ge or old.get("risk_score") != score: reasons.append(f"위험등급/점수 변화: {old.get('grade_emoji','?')} {old.get('grade_label','')} {old.get('risk_score','?')} → {ge} {gl} {score}")
        if c.get("inflation") and not same(oc.get("inflation"), c["inflation"], ["period", "headline_yoy", "core_yoy"]): reasons.append(f"물가 갱신: CPI {c['inflation']['headline_yoy']:.1f}% / 근원 {c['inflation']['core_yoy']:.1f}%")
        if c.get("household") and not same(oc.get("household"), c["household"], ["period", "total_trn", "mortgage_trn", "mortgage_prev_trn"]): reasons.append(f"가계대출 갱신: 전체 {c['household']['total_trn']:+.1f}조원 / 주담대 {c['household']['mortgage_trn']:+.1f}조원")
        if c.get("housing") and not same(oc.get("housing"), c["housing"], ["period", "seoul_wow", "gangbuk_wow", "gangnam_wow", "gyeonggi_wow", "broad_diffusion"]): reasons.append("주택가격 확산 판정 갱신")
        if c.get("oil") and oc.get("oil") and op(c["oil"]) != op(oc["oil"]): reasons.append(f"브렌트유 압력구간 변화: 5거래일 {c['oil']['change_5d_pct']:+.1f}%")
        if newr: reasons.append(f"한은 발언 정책 의미 변화 {len(newr)}건")
    if reasons or newr:
        msg = message(ns, reasons, newr)
        if ALERT.exists() and ALERT.stat().st_size: ALERT.write_text(ALERT.read_text(encoding="utf-8").rstrip() + "\n\n──────────\n\n" + msg + "\n", encoding="utf-8")
        else: ALERT.write_text(msg + "\n", encoding="utf-8")
    root["rate_signal_upgrade"] = ns; PENDING.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with STATUS.open("a", encoding="utf-8") as f:
        hh = c.get("household") or {}; f.write(f"\n## 추가인상 위험등급\n\n- 위험등급: {ge} {gl}\n- 위험점수: {score} (통계적 확률 아님)\n- 다음 금통위: {ns.get('next_mpc_date') or '확인 불가'}\n- 주담대: {hh.get('mortgage_trn','확인 불가')}조원 / 재가속: {'예' if hh.get('mortgage_reaccelerating') else '아니오'}\n- 새 한은 발언 의미변화: {len(newr)}건\n- 최초 기준선 설정: {'예(알림 미송출)' if boot else '아니오'}\n")
    return 0

if __name__ == "__main__": raise SystemExit(main())
