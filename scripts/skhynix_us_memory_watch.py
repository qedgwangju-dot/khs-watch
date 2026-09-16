from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "skhynix_us_memory_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
ALERT = OUT / "skhynix_us_memory_alert.html"
STATUS = OUT / "skhynix_us_memory_status.md"

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
FRESH_HOURS = 24

QUERIES = [
    '"SK Hynix" Intel Ohio memory chips manufacture US',
    '"SK Hynix" Intel (lease OR venture OR JV) Ohio memory',
    '"SK Hynix" US memory fab DRAM HBM NAND Intel',
    '"SK하이닉스" 인텔 미국 메모리 오하이오 생산',
]

TRUSTED = (
    "reuters", "sk hynix", "sk하이닉스", "intel", "bloomberg", "financial times",
    "wall street journal", "wsj", "yonhap", "연합뉴스", "the elec", "thelec",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_pub(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def decode_google(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""


def event_id(title: str, source: str) -> str:
    return hashlib.sha256(f"{title}|{source}".encode()).hexdigest()[:24]


def relevant(text: str) -> bool:
    low = text.lower()
    sk = "sk hynix" in low or "sk하이닉스" in low
    intel = "intel" in low or "인텔" in low
    us = any(k in low for k in ("ohio", "united states", "u.s.", " us ", "미국", "오하이오"))
    memory = any(k in low for k in ("memory", "dram", "hbm", "nand", "메모리", "반도체"))
    action = any(k in low for k in ("talk", "deal", "lease", "venture", "jv", "manufactur", "fab", "plant", "생산", "협상", "임대", "합작"))
    return sk and intel and us and memory and action


def read_events() -> list[dict]:
    rows: dict[str, dict] = {}
    for query in QUERIES:
        for lang in ("en", "ko"):
            try:
                root = ET.fromstring(fetch(rss_url(query, lang)))
            except Exception:
                continue
            for item in root.findall("./channel/item"):
                title = clean(item.findtext("title") or "")
                desc = clean(item.findtext("description") or "")
                link = clean(item.findtext("link") or "")
                source_node = item.find("source")
                source = clean(source_node.text if source_node is not None and source_node.text else "")
                pub = parse_pub(clean(item.findtext("pubDate") or ""))
                if not title or not link or not relevant(f"{title} {desc}"):
                    continue
                if not any(k in source.lower() for k in TRUSTED):
                    continue
                direct = decode_google(link)
                if not direct:
                    continue
                key = event_id(title, source)
                rows[key] = {
                    "id": key,
                    "title": title,
                    "description": desc,
                    "source": source or "출처 미표시",
                    "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                    "direct_link": direct,
                }
    return sorted(rows.values(), key=lambda x: x.get("published_at_kst") or "")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_ids": [], "seen_fact_keys": []}


def write_state(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def html_link(url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">원문</a>'


def classify(event: dict) -> tuple[str, str]:
    text = f"{event.get('title','')} {event.get('description','')}".lower()
    if any(k in text for k in ("agreement", "agreed", "signed", "signs", "lease agreement", "joint venture", "mou", "계약 체결", "합의", "양해각서")):
        return "skhynix_intel_us_memory_deal", "계약·합의 단계"
    return "skhynix_intel_us_memory_talks", "협상·검토 단계"


def build_alert(event: dict, stage: str) -> str:
    url = event["direct_link"]
    source = event.get("source") or "Reuters"
    published = event.get("published_at_kst") or "확인 불가"
    return "\n".join([
        "🚨 <b>SK하이닉스·Intel 미국 메모리 생산 협상</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[무엇이 달라졌나]</b>",
        "• Reuters에 따르면 SK하이닉스와 Intel이 <b>미국 내 메모리 칩 생산</b> 방안을 협의 중입니다.",
        "• 성사되면 SK하이닉스가 미국에서 메모리 칩을 <b>전공정 생산하는 첫 사례</b>가 될 수 있습니다.",
        "",
        "<b>[검토 중인 구조]</b>",
        "① SK하이닉스가 Intel의 <b>Ohio 생산시설 일부를 임대</b>",
        "② SK하이닉스·Intel·대형 클라우드사가 <b>합작법인</b>을 구성",
        "",
        "<b>[아직 확정되지 않은 것]</b>",
        "• 어떤 메모리를 생산할지 <b>미정</b> — HBM·DRAM·NAND 중 특정 제품은 아직 확인되지 않았습니다.",
        "• SK하이닉스는 추가 생산기지 방안을 검토 중이지만 <b>결정된 사항은 없다고</b> Reuters에 밝혔습니다.",
        "• Intel도 협상설에는 논평하지 않았고 Ohio 투자는 계속 진행한다고 밝혔습니다.",
        "",
        "<b>[왜 중요한가]</b>",
        "• Indiana: HBM <b>첨단 패키징·검사</b> 거점",
        "• Ohio 협상: 메모리 웨이퍼를 만드는 <b>전공정 생산기지</b> 가능성",
        "→ 같은 미국 투자라도 산업적 의미가 완전히 다릅니다.",
        "• HBM·첨단 DRAM처럼 국가핵심기술이 포함되면 한국 산업기술보호법상 정부 심사가 필요할 수 있습니다.",
        "",
        "<b>[현재 판정]</b>",
        f"🟡 <b>{stage}</b> — 전략적으로 큰 변화지만 아직 수주·설비투자·생산능력 확정 단계는 아닙니다.",
        "",
        "<b>[다음 알림 조건]</b>",
        "• 임대계약·합작법인·양해각서 체결",
        "• HBM/DRAM/NAND 등 <b>생산 제품 확정</b>",
        "• 투자금액·웨이퍼 생산능력·장비 반입·가동시점 공개",
        "• 참여 클라우드 고객 실명 공개",
        "• 한국 정부 국가핵심기술 심사·승인",
        "• 미국 보조금·관세 조건과 연결",
        "",
        f"<b>출처</b>: {html.escape(source)} · 공개 {html.escape(published)}",
        html_link(url),
    ]) + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_state()
    seen_ids = set(state.get("seen_ids") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])

    events = read_events()
    cutoff = now - timedelta(hours=FRESH_HOURS)
    fresh = []
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if cutoff <= dt <= now + timedelta(minutes=10):
            fresh.append(e)

    new_event = None
    new_fact_key = ""
    stage = ""
    for e in reversed(fresh):
        fact_key, fact_stage = classify(e)
        if e["id"] in seen_ids or fact_key in seen_fact_keys:
            continue
        new_event = e
        new_fact_key = fact_key
        stage = fact_stage
        break

    # Always record current search results. If Telegram sending fails, the workflow fails before commit,
    # so this state is not persisted and the alert will retry next run.
    seen_ids.update(e["id"] for e in events)
    if new_fact_key:
        seen_fact_keys.add(new_fact_key)
    state = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted(seen_ids)[-500:],
        "seen_fact_keys": sorted(seen_fact_keys)[-100:],
        "last_event_count": len(events),
        "last_fresh_count": len(fresh),
        "alert_generated": bool(new_event),
    }
    write_state(state)

    if new_event:
        ALERT.write_text(build_alert(new_event, stage), encoding="utf-8")
    elif ALERT.exists():
        ALERT.unlink()

    STATUS.write_text(
        "# SK hynix US memory strategic watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- events: {len(events)}\n"
        f"- fresh: {len(fresh)}\n"
        f"- alert_generated: {str(bool(new_event)).lower()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
