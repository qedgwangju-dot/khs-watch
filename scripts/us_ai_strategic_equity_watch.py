#!/usr/bin/env python3
"""Strict watcher for U.S. government strategic equity stakes in frontier AI companies."""

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
from email.utils import parsedate_to_datetime

STATE_PATH = pathlib.Path("data/us_ai_strategic_equity_watch_state.json")
OUT_DIR = pathlib.Path("out")
OUT_ALERT = OUT_DIR / "us_ai_strategic_equity_alert.html"
OUT_TITLE = OUT_DIR / "us_ai_strategic_equity_title.txt"
OUT_PENDING = OUT_DIR / "us_ai_strategic_equity_pending_state.json"

TIME_TRANSCRIPT = "https://www.aol.com/articles/read-full-transcript-donald-trump-110004000.html"
REUTERS_JUNE = "https://www.reuters.com/business/trump-says-his-team-will-look-into-us-taking-stake-ai-companies-2026-06-05/"
REUTERS_OPENAI = "https://www.reuters.com/business/openai-proposes-handing-trump-administration-5-stake-ft-reports-2026-07-02/"
REUTERS_ANTHROPIC = "https://www.reuters.com/business/trump-administration-anthropic-have-not-discussed-government-taking-stakes-firm-2026-07-02/"
INTEL_OFFICIAL = "https://www.intel.com/content/www/us/en/newsroom/news/corporate/intel-and-trump-administration-reach-historic-agreement.html"

CURRENT_SEED = {
    "id": "time-trump-ai-equity-openai-anthropic-2026-09-28",
    "published": "2026-10-01",
    "source": "TIME 인터뷰 전문 재게시",
    "title": "Trump says he might use an Intel-style government stake model for OpenAI and Anthropic",
    "url": TIME_TRANSCRIPT,
    "kind": "current_baseline",
}

TRUSTED_DOMAINS = {
    "whitehouse.gov": "백악관",
    "commerce.gov": "미 상무부",
    "treasury.gov": "미 재무부",
    "ostp.gov": "백악관 과학기술정책실",
    "sec.gov": "미 증권거래위원회",
    "reuters.com": "Reuters",
    "ft.com": "Financial Times",
    "semafor.com": "Semafor",
    "axios.com": "Axios",
    "apnews.com": "AP",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "x.ai": "xAI",
    "blog.google": "Google",
    "about.fb.com": "Meta",
}

QUERIES = [
    '"government stake" OpenAI Anthropic Trump',
    '"government equity" AI companies Trump',
    '"5% stake" OpenAI government',
    'Trump AI companies equity stake OpenAI Anthropic',
    'site:whitehouse.gov AI stake OpenAI Anthropic equity',
    'site:commerce.gov AI stake OpenAI Anthropic equity',
    'site:treasury.gov AI stake OpenAI Anthropic equity',
    'OpenAI government stake sovereign wealth fund',
    'Anthropic government stake sovereign wealth fund',
]

AI_TARGETS = [
    "openai", "anthropic", "xai", "x.ai", "google", "deepmind",
    "meta", "frontier ai", "frontier lab", "ai company", "ai companies",
    "ai firm", "ai firms", "ai lab", "ai labs",
]
EQUITY_TERMS = [
    "stake", "equity", "shares", "ownership", "warrant", "shareholder",
    "sovereign wealth", "public wealth fund", "government investment",
    "government ownership", "take a stake", "buy shares",
]
MATERIAL_TERMS = [
    "talks", "discussion", "negotiation", "proposal", "offer", "term sheet",
    "agreement", "deal", "approved", "approval", "signed", "purchase",
    "investment", "fund", "appropriation", "congress", "warrant",
    "voting", "board", "governance", "declined", "denied", "rejected",
    "not discussed", "no talks",
]


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "KHS-US-AI-Strategic-Equity-Watch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _rss_urls(query):
    q = urllib.parse.quote_plus(query)
    return [
        f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko",
    ]


def _strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _source_domain(item, link):
    source = item.find("source")
    src_url = ""
    src_name = ""
    if source is not None:
        src_name = _strip(source.text)
        src_url = (source.attrib.get("url") or "").strip()
    candidates = [src_url, link]
    for raw in candidates:
        try:
            host = (urllib.parse.urlparse(raw).hostname or "").lower().removeprefix("www.")
            for domain, label in TRUSTED_DOMAINS.items():
                if host == domain or host.endswith("." + domain):
                    return domain, label
        except Exception:
            pass
    # Feed source name is not enough to qualify as trusted unless mapped.
    low = src_name.lower()
    for domain, label in TRUSTED_DOMAINS.items():
        if domain.split(".")[0] in low:
            return domain, label
    return "", src_name or "웹 검색"


def _published_dt(text):
    try:
        d = parsedate_to_datetime(text or "")
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _is_material(title, desc):
    hay = f"{title} {desc}".lower()
    if not any(x in hay for x in AI_TARGETS):
        return False
    if not any(x in hay for x in EQUITY_TERMS):
        return False
    if not any(x in hay for x in MATERIAL_TERMS):
        return False
    # Reject pure market commentary / unrelated stock-price stories.
    noise = ["stock rises", "stock falls", "price target", "options activity", "prediction market"]
    if any(x in hay for x in noise):
        return False
    return True


def _stage(title, desc):
    hay = f"{title} {desc}".lower()
    if any(x in hay for x in ["signed", "agreement", "government buys", "purchase", "acquires", "acquired"]):
        return "계약·취득 확정"
    if any(x in hay for x in ["term sheet", "5% stake", "offer", "proposal", "proposes"]):
        return "구체 조건 제안"
    if any(x in hay for x in ["talks", "discussion", "negotiation", "negotiating"]):
        return "협상·논의"
    if any(x in hay for x in ["not discussed", "no talks", "denied", "rejected", "declined"]):
        return "부인·반대 확인"
    if any(x in hay for x in ["congress", "appropriation", "legislation", "authority"]):
        return "법적·예산 절차"
    return "정책 검토·발언"


def _targets(title, desc):
    hay = f"{title} {desc}".lower()
    out=[]
    mapping=[
        ("openai","OpenAI"),("anthropic","Anthropic"),("xai","xAI"),("x.ai","xAI"),
        ("google","Google"),("deepmind","Google DeepMind"),("meta","Meta"),
    ]
    for key,label in mapping:
        if key in hay and label not in out:
            out.append(label)
    return out or ["미국 최첨단 AI 기업"]


def _event_key(event):
    targets=",".join(sorted(event.get("targets") or []))
    stage=event.get("stage") or ""
    title=re.sub(r"[^0-9a-z가-힣]+"," ",(event.get("title") or "").lower()).strip()
    # Similar headlines about the same targets and stage collapse to one event.
    core=f"{targets}|{stage}|{title[:140]}"
    return hashlib.sha256(core.encode("utf-8")).hexdigest()[:24]


def discover():
    out={CURRENT_SEED["id"]:dict(CURRENT_SEED)}
    now=dt.datetime.now(dt.timezone.utc)
    for query in QUERIES:
        for rss in _rss_urls(query):
            try:
                root=ET.fromstring(_get(rss))
            except Exception as e:
                print(f"WARN RSS failed: {rss}: {e}")
                continue
            for item in root.findall(".//item"):
                title=_strip(item.findtext("title"))
                desc=_strip(item.findtext("description"))
                link=(item.findtext("link") or "").strip()
                pub=_strip(item.findtext("pubDate"))
                if not link or not _is_material(title,desc):
                    continue
                pdt=_published_dt(pub)
                if pdt and now-pdt > dt.timedelta(days=7):
                    continue
                domain,source=_source_domain(item,link)
                if domain not in TRUSTED_DOMAINS:
                    continue
                event={
                    "id":"news:"+hashlib.sha256((title+"|"+source).encode("utf-8")).hexdigest()[:24],
                    "published":pub,
                    "source":source,
                    "title":title,
                    "url":link,
                    "kind":"news",
                    "stage":_stage(title,desc),
                    "targets":_targets(title,desc),
                }
                out[event["id"]]=event
    return list(out.values())


def _load_state():
    if not STATE_PATH.exists():
        return {"version":1,"seen_events":[],"updated_at":None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version":1,"seen_events":[],"updated_at":None}


def _save_pending(state):
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    state["updated_at"]=dt.datetime.now(dt.timezone.utc).isoformat()
    OUT_PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def _fx():
    try:
        from fx_api import daily_krw
        q=daily_krw()
        return float(q.rate), str(q.basis)
    except Exception:
        return None, "환율 조회 실패"


def _krw(usd,rate):
    if rate is None:
        return "원화 확인 불가"
    won=usd*rate
    if won>=1_000_000_000_000:
        return f"약 {won/1_000_000_000_000:,.2f}조원"
    if won>=100_000_000:
        return f"약 {won/100_000_000:,.1f}억원"
    return f"약 {won/10_000:,.0f}만원"


def _link(label,url):
    return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'


def build_seed(rate,basis):
    r89=_krw(8_900_000_000,rate)
    r57=_krw(5_700_000_000,rate)
    r32=_krw(3_200_000_000,rate)
    r111=_krw(11_100_000_000,rate)
    lines=[
        "🏛 <b>미국 정부 전략지분·AI 산업정책 Watch</b>",
        "<b>판정  🟡 정책 가능성 재확인 · OpenAI·Anthropic 지분 취득 확정 아님</b>",
        "",
        "<b>한눈에 보기</b>",
        "• 트럼프 대통령은 TIME 인터뷰에서 OpenAI·Anthropic에 Intel식 정부 지분 모델을 적용할 수 있다는 가능성을 다시 열어뒀습니다.",
        "• 국유화 여부에는 부정적으로 답해, 현재 단계는 <b>지분 취득 가능성</b>이지 국유화나 계약 확정이 아닙니다.",
        "• 6월에는 미국 정부가 주요 AI 기업 지분 취득을 검토하겠다고 밝혔고, 7월에는 OpenAI 5% 지분안이 보도됐지만 Reuters는 이를 독립 확인하지 못했다고 명시했습니다.",
        "• Anthropic은 7월 2일 기준 미 정부와 지분 협의를 하지 않았다는 반대 확인이 있습니다.",
        "",
        "<b>Intel 선례 — 공식 확정</b>",
        f"• 미국 정부 투자: 89억달러 ({r89}) → Intel <b>9.9%</b>",
        "• 취득: 4억3,330만주 · 주당 20.47달러",
        f"• 재원: CHIPS 잔여보조금 57억달러 ({r57}) + Secure Enclave 32억달러 ({r32})",
        f"• 기존 지급분 포함 총 정부 지원·투자: 111억달러 ({r111})",
        "• 지배구조: 이사회석·정보권 없는 수동적 지분",
        "• 추가 조건: Intel이 foundry 지분 51% 미만으로 내려갈 때만 행사 가능한 5년 만기 5% 추가 워런트",
        "",
        "<b>앞으로 알림하는 변화</b>",
        "• 실제 협상 개시 · 회사 공식 확인/부인",
        "• 지분율·취득금액·기업가치·신주/구주·워런트 조건 공개",
        "• 재원(CHIPS·국부펀드·Trump Accounts·별도 예산) 확정",
        "• 의결권·이사회석·정보권·거부권 등 지배구조 조건",
        "• 의회 승인·예산·법적 권한 변화",
        "• 최종 계약 체결·철회·무산",
        "",
        "<b>정확도 원칙</b>",
        "• 단순 정치 발언·반복 기사·주가 반응만으로는 재알림하지 않습니다.",
        "• 공식자료 또는 Reuters·FT·AP 등 신뢰자료에서 <b>새 조건이 확인될 때만</b> 보냅니다.",
        "• 보도와 공식 확정은 반드시 분리합니다.",
        "",
        f"환율 기준: {basis}" if rate is not None else "환율: 확인 불가",
        f"{_link('TIME 인터뷰 전문 재게시',TIME_TRANSCRIPT)}  |  {_link('Reuters 6월',REUTERS_JUNE)}",
        f"{_link('Reuters OpenAI 5% 보도',REUTERS_OPENAI)}  |  {_link('Reuters Anthropic 부인',REUTERS_ANTHROPIC)}",
        _link("Intel 공식 계약",INTEL_OFFICIAL),
    ]
    return "\n".join(lines)


def build_news(event):
    targets="·".join(event.get("targets") or ["AI 기업"])
    lines=[
        "🏛 <b>미국 정부 전략지분·AI 산업정책 — 새 변화</b>",
        f"<b>단계  {html.escape(event.get('stage') or '확인 필요')}</b>",
        f"대상: <b>{html.escape(targets)}</b>",
        f"출처: {html.escape(event.get('source') or '신뢰 출처')}",
        "",
        "<b>무엇이 달라졌나</b>",
        f"• {html.escape(event.get('title') or '정부 지분 관련 새 보도')}",
        "• 기존 발언을 반복한 기사인지, 실제 조건·협상·계약 단계가 바뀐 것인지 후속 공식자료에서 재확인합니다.",
        "",
        _link("원문",event.get("url") or ""),
    ]
    return "\n".join(lines)


def main():
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    for p in [OUT_ALERT,OUT_TITLE,OUT_PENDING]:
        if p.exists():
            p.unlink()

    state=_load_state()
    seen=set(state.get("seen_events",[]))
    events=discover()

    # Bootstrap: deliver the verified current baseline exactly once and suppress historical backfill.
    seed_key="baseline:time-openai-anthropic-intel"
    if seed_key not in seen:
        rate,basis=_fx()
        OUT_TITLE.write_text("🏛 미국 정부 전략지분·AI 산업정책\n",encoding="utf-8")
        OUT_ALERT.write_text(build_seed(rate,basis)+"\n",encoding="utf-8")
        seen.add(seed_key)
        for e in events:
            if e.get("kind")=="news":
                seen.add("event:"+_event_key(e))
        print("alert_ready=true type=baseline")
    else:
        new_events=[]
        used=set()
        for e in events:
            if e.get("kind")!="news":
                continue
            key="event:"+_event_key(e)
            if key in seen or key in used:
                continue
            used.add(key)
            new_events.append((key,e))

        selected=new_events[:5]
        if selected:
            body="\n\n────────\n\n".join(build_news(e) for _,e in selected)
            OUT_TITLE.write_text("🏛 미국 정부 전략지분·AI 산업정책 — 새 변화\n",encoding="utf-8")
            OUT_ALERT.write_text(body+"\n",encoding="utf-8")
            for key,_ in selected:
                seen.add(key)
            print(f"alert_ready=true count={len(selected)}")
        else:
            print("No material new US AI strategic-equity event.")

    state["seen_events"]=sorted(seen)
    _save_pending(state)


if __name__=="__main__":
    main()
