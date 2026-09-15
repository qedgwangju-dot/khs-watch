#!/usr/bin/env python3
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "clarity_negotiation_state.json"
PENDING_STATE_PATH = ROOT / "out" / "clarity_negotiation_pending_state.json"
STATUS_PATH = ROOT / "out" / "clarity_negotiation_status.json"
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"
NEWS_RSS = "https://news.google.com/rss/search"

QUERIES = [
    '"CLARITY Act" Democrats counteroffer Republicans',
    '"CLARITY Act" Democratic counterproposal Republicans',
    '"CLARITY Act" counteroffer rejected Republicans',
    '"CLARITY Act" counterproposal rejected GOP',
    '"CLARITY Act" Warner Gallego counteroffer',
]

TIER1 = {
    "reuters": "Reuters",
    "associated press": "Associated Press",
    "ap news": "Associated Press",
    "bloomberg law": "Bloomberg Law",
    "bloomberg tax": "Bloomberg Tax",
    "bloomberg": "Bloomberg",
    "coindesk": "CoinDesk",
    "the block": "The Block",
    "politico": "Politico",
    "punchbowl news": "Punchbowl News",
    "semafor": "Semafor",
    "crypto in america": "Crypto in America",
}

TOPIC_RE = re.compile(r"\b(?:CLARITY\s+(?:Act|Bill)|H\.?\s*R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity)\b", re.I)
COUNTER_RE = re.compile(r"\b(?:counter[- ]?offer|counterproposal|counter[- ]?proposal|counter offer)\b", re.I)
DEM_RE = re.compile(r"\b(?:Democrats?|Democratic|Warner|Gallego|Warnock|Schumer|Gillibrand)\b", re.I)
GOP_RE = re.compile(r"\b(?:Republicans?|Republican|GOP|Lummis|Scott|Boozman|Thune|White House)\b", re.I)
SENT_RE = re.compile(r"\b(?:sent|send|sending|delivered|submitted|handed|provided|transmitted)\b", re.I)
REJECT_RE = re.compile(r"\b(?:reject(?:s|ed|ing)?|declin(?:e|ed|es)|refus(?:e|ed|es)|turn(?:ed|s)?\s+down|dismiss(?:ed|es)?|won['’]?t\s+accept|will\s+not\s+accept|no\s+further\s+concessions|nothing\s+left\s+to\s+give)\b", re.I)
GOP_FINAL_RE = re.compile(r"\b(?:last,?\s+best\s+and\s+final|best\s+and\s+final|final\s+offer|nothing\s+left\s+to\s+give|take\s+yes\s+for\s+an\s+answer)\b", re.I)
DEM_REJECT_GOP_RE = re.compile(r"\b(?:Democrats?|Democratic).{0,120}(?:reject|rejected|oppose|opposed|panning|push\s+back|falls?\s+short)\b|\b(?:reject|rejected|oppose|panning).{0,120}(?:Democrats?|Democratic)\b", re.I | re.S)


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_bytes(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KHS-CLARITY-Negotiation/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def parse_date(value):
    try:
        parsed = email.utils.parsedate_to_datetime(clean(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("UTC"))
    except Exception:
        return None


def source_tier(label):
    low = clean(label).lower()
    for key in sorted(TIER1, key=len, reverse=True):
        if key in low:
            return 1, TIER1[key]
    return 0, clean(label)


def google_news_items(query):
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(fetch_bytes(f"{NEWS_RSS}?{params}"))
    rows = []
    for item in root.findall(".//item")[:60]:
        source_node = item.find("source")
        rows.append({
            "title": clean(item.findtext("title")),
            "description": clean(item.findtext("description")),
            "url": clean(item.findtext("link")),
            "pubDate": clean(item.findtext("pubDate")),
            "source": clean(source_node.text if source_node is not None else ""),
        })
    return rows


def classify_signal(text):
    text = clean(text)
    if not TOPIC_RE.search(text):
        return None
    if COUNTER_RE.search(text) and DEM_RE.search(text) and GOP_RE.search(text) and REJECT_RE.search(text):
        return "gop_rejected_dem_counteroffer"
    if COUNTER_RE.search(text) and DEM_RE.search(text) and SENT_RE.search(text):
        return "dem_counteroffer_sent"
    if DEM_REJECT_GOP_RE.search(text) and GOP_FINAL_RE.search(text):
        return "dem_rejected_gop_final_offer"
    return None


def event_rank(stage):
    return {
        "gop_rejected_dem_counteroffer": 300,
        "dem_counteroffer_sent": 200,
        "dem_rejected_gop_final_offer": 100,
    }.get(stage, 0)


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_event(event):
    existing = []
    if ALERT_JSON.exists():
        try:
            existing = json.loads(ALERT_JSON.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append(event)
    write_json(ALERT_JSON, existing)


def build_event(stage, row, source_label):
    if stage == "gop_rejected_dem_counteroffer":
        title = "공화당, 민주당의 CLARITY 역제안 거부 — 60표 협상 결렬 위험 급등"
        detail = (
            "민주당 협상팀이 CLARITY 법안의 윤리·집행 조항 등에 대한 역제안을 공화당 측에 전달한 뒤, "
            "공화당 협상 측이 이를 받아들이지 않았다는 신뢰매체 보도가 확인됐습니다. "
            "이는 기사 재인용이 아니라 협상 상태가 ‘역제안 전달’에서 ‘수용 실패·결렬 위험 확대’로 바뀐 사건입니다. "
            "한국시간 9월 16일 03:15 예정된 motion to proceed cloture에는 60표가 필요하므로, 표결 직전 초당적 합의 가능성이 낮아지는 직접적인 시간표 악화 신호입니다. "
            "다만 실제 찬성표 숫자는 공식 whip count 또는 roll call 전까지 추정하지 않습니다."
        )
        status = "신뢰매체가 민주당 역제안과 공화당 거부를 함께 확인 / 실제 60표 수치는 미확정"
        event_type = "협상 상태 악화 — 민주당 역제안 공화당 거부"
    elif stage == "dem_counteroffer_sent":
        title = "민주당, CLARITY 역제안 공식 전달 — 표결 직전 협상 재개"
        detail = (
            "민주당 협상팀이 공화당의 ‘최종안’에 대한 역제안을 공화당 협상팀에 실제 전달했다는 신뢰매체 보도가 확인됐습니다. "
            "이는 단순 반대 발언이 아니라 새로운 협상 문안이 상대방에게 넘어간 상태 변화입니다. "
            "핵심 쟁점은 대통령·고위공직자 암호자산 이해관계, State AG 집행권, Office of Government Ethics의 예외 허용 가능성 등으로 보도되고 있습니다. "
            "다음 상태는 공화당의 수용·부분수용·거부 또는 표결 연기 여부이며, 어느 쪽이든 새 사건으로 별도 알림합니다."
        )
        status = "신뢰매체가 역제안 전달 확인 / 구체 문안·공화당 반응은 후속 검증"
        event_type = "협상 상태 변화 — 민주당 역제안 전달"
    else:
        title = "민주당 핵심 협상진, 공화당 CLARITY 최종안 거부 — 역제안 준비"
        detail = (
            "민주당 핵심 협상 의원들이 공화당이 공개한 CLARITY 최종안을 충분하지 않다고 판단하고 역제안을 준비·전달하기로 했다는 보도가 확인됐습니다. "
            "이는 단순 비판보다 한 단계 강한 협상 상태 변화로, 60표 확보 가능성을 낮추는 시간표 역풍입니다."
        )
        status = "신뢰매체가 민주당의 최종안 거부·역제안 움직임 확인"
        event_type = "협상 상태 악화 — 민주당 공화당 최종안 거부"
    return {
        "source": f"{source_label} 협상상태 검증",
        "event_type": event_type,
        "event_subtype": stage,
        "title": title,
        "url": row.get("url", ""),
        "date": row.get("pubDate", ""),
        "detail": detail,
        "verification_status": status,
        "policy_actor": "상원 CLARITY 협상팀",
        "monitoring_unit": "event_state_change",
        "negotiation_stage": stage,
    }


def main():
    now = dt.datetime.now(ZoneInfo("UTC"))
    cutoff = now - dt.timedelta(days=2)
    state = load_state()
    current_stage = str(state.get("negotiation_stage") or "")
    by_key = {}
    errors = []
    for query in QUERIES:
        try:
            for row in google_news_items(query):
                key = (row["title"], row["source"], row["pubDate"])
                by_key.setdefault(key, row)
        except Exception as exc:
            errors.append(f"{query}: {exc}")

    candidates = []
    for row in by_key.values():
        published = parse_date(row.get("pubDate"))
        tier, source_label = source_tier(row.get("source"))
        if tier != 1 or published is None or published < cutoff or published > now + dt.timedelta(hours=2):
            continue
        signal = clean(f"{row.get('title','')} {row.get('description','')}")
        stage = classify_signal(signal)
        if stage:
            candidates.append((event_rank(stage), published, stage, row, source_label))

    chosen = max(candidates, default=None, key=lambda x: (x[0], x[1]))
    new_event = None
    next_stage = current_stage
    if chosen:
        _, _, stage, row, source_label = chosen
        next_stage = stage if event_rank(stage) >= event_rank(current_stage) else current_stage
        if stage != current_stage and event_rank(stage) >= event_rank(current_stage):
            new_event = build_event(stage, row, source_label)
            append_event(new_event)

    pending = {
        "negotiation_stage": next_stage,
        "updated_at_kst": now.astimezone(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "monitoring_unit": "event_state_change_not_article",
    }
    write_json(PENDING_STATE_PATH, pending)
    write_json(STATUS_PATH, {
        "new_event": bool(new_event),
        "previous_stage": current_stage,
        "current_stage": next_stage,
        "candidate_count": len(candidates),
        "errors": errors,
        "monitoring_unit": "event_state_change_not_article",
    })
    print(f"clarity_negotiation_new={1 if new_event else 0} previous={current_stage or 'none'} current={next_stage or 'none'} candidates={len(candidates)}")


if __name__ == "__main__":
    main()
