#!/usr/bin/env python3
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
ALERT_JSON = OUT_DIR / "clarity_watch_alert.json"
OUT_HTML = OUT_DIR / "clarity_watch_alert.html"
OUT_CHUNKS = OUT_DIR / "clarity_watch_telegram_chunks.json"

TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
_TRANSLATION_CACHE = {}


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def has_hangul(text):
    return bool(re.search(r"[가-힣]", text or ""))


def translate_piece(text):
    text = clean(text)
    if not text or has_hangul(text):
        return text
    if text in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[text]
    params = urllib.parse.urlencode({
        "client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": text,
    })
    req = urllib.request.Request(
        f"{TRANSLATE_URL}?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    translated = clean("".join(part[0] for part in (payload[0] or []) if part and part[0]))
    _TRANSLATION_CACHE[text] = translated or text
    return _TRANSLATION_CACHE[text]


def split_translation_text(text, limit=900):
    text = clean(text)
    if len(text) <= limit:
        return [text] if text else []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, current = [], ""
    for sentence in sentences:
        candidate = sentence if not current else current + " " + sentence
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            if cut < limit // 2:
                cut = limit
            chunks.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        current = sentence
    if current:
        chunks.append(current)
    return chunks


def translate_ko(text):
    text = clean(text)
    if not text or has_hangul(text):
        return text
    try:
        return clean(" ".join(translate_piece(chunk) for chunk in split_translation_text(text)))
    except Exception:
        return ""


def parse_event_date(value):
    value = clean(value)
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("America/New_York"))
            return parsed.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=ZoneInfo("America/New_York"))
        except ValueError:
            continue
    return None


def format_event_date_korean(value):
    """Use Korean date notation; convert timestamped official dates to Korea Standard Time."""
    raw = clean(value)
    if not raw:
        return "", False
    parsed = parse_event_date(raw)
    if parsed is None:
        return raw, False

    has_clock = bool(
        re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", raw)
        or re.search(r"\b\d{1,2}\s*(?:AM|PM)\b", raw, re.I)
    )
    if has_clock:
        kst = parsed.astimezone(ZoneInfo("Asia/Seoul"))
        return f"{kst.year}년 {kst.month}월 {kst.day}일 {kst:%H:%M} KST", True
    return f"{parsed.year}년 {parsed.month}월 {parsed.day}일", False


def is_committee_commentary(event):
    source = clean(event.get("source", ""))
    if source not in {"상원 은행위원회", "상원 농업위원회"}:
        return False
    title = clean(event.get("title", "")).lower()
    commentary_markers = (
        "opening remarks", "closing remarks", "national security advisory", "advisory:",
        "statement on", "statement regarding", "what they are saying", "icymi:",
        "highlights", "letter to", "op-ed", "remarks at",
    )
    substantive_markers = (
        "advance clarity act", "advance the clarity act", "historic markup",
        "markup of", "mark-up of", "committee vote", "bipartisan vote",
        "cloture", "scheduled consideration", "schedule", "new text", "bill text",
        "amendment adopted", "amendment rejected", "passed", "signed", "veto",
    )
    if any(marker in title for marker in substantive_markers):
        return False
    return any(marker in title for marker in commentary_markers)


def semantic_group(event):
    title = clean(event.get("title", "")).lower()
    source = clean(event.get("source", ""))
    when = parse_event_date(event.get("date", ""))
    day = when.date().isoformat() if when else clean(event.get("date", ""))
    if source == "상원 은행위원회" and (
        "markup" in title or "mark-up" in title or "advance clarity act" in title or "bipartisan vote" in title
    ):
        return ("senate_banking_committee_clarity_action", day)
    return (
        clean(event.get("event_type", "")),
        source,
        day,
        re.sub(r"[^a-z0-9가-힣]+", " ", title).strip(),
    )


def event_priority(event):
    title = clean(event.get("title", "")).lower()
    source = clean(event.get("source", ""))
    score = 0
    if "advance clarity act" in title and "vote" in title:
        score += 100
    elif "bipartisan vote" in title:
        score += 95
    elif "markup" in title or "mark-up" in title:
        score += 70
    if source == "GovInfo BILLSTATUS":
        score += 40
    elif source in {"상원 본회의", "상원 표결기록"}:
        score += 35
    elif source == "상원 은행위원회":
        score += 25
    return score


def filter_alertable_events(events, now=None, freshness_days=7):
    """Suppress stale rediscoveries, commentary masquerading as events, and same-event duplicates."""
    if now is None:
        now = dt.datetime.now(ZoneInfo("America/New_York"))
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("America/New_York"))
    else:
        now = now.astimezone(ZoneInfo("America/New_York"))
    cutoff = now - dt.timedelta(days=freshness_days)

    candidates = []
    for event in events:
        when = parse_event_date(event.get("date", ""))
        if when is not None and when < cutoff:
            continue
        if is_committee_commentary(event):
            continue
        candidates.append(event)

    best_by_group = {}
    for event in candidates:
        key = semantic_group(event)
        existing = best_by_group.get(key)
        if existing is None or event_priority(event) > event_priority(existing):
            best_by_group[key] = event
    return list(best_by_group.values())


def special_translation(event):
    title = clean(event.get("title", ""))
    detail = clean(event.get("detail", ""))
    signal = f"{title} {detail}".lower()
    if "sec proposes new regulation crypto assets" in signal or "regulation crypto assets" in signal:
        return (
            "SEC, 암호자산 관련 투자계약을 위한 새 규칙안 ‘Regulation Crypto Assets’ 제안",
            "미 SEC는 일부 암호자산 관련 투자계약에 대해 더 명확하고 자산 특성에 맞는 규제 틀을 만들기 위한 새 규칙안을 제안했습니다. 아직 최종 규칙이 아니라 제안 단계이며, CLARITY 법안이 의회에서 지연되더라도 SEC가 자기 권한 범위에서 규제 공백을 먼저 줄이려는 움직임입니다.",
        )
    if "advance clarity act" in signal and "bipartisan vote" in signal:
        return (
            "상원 은행위원회, CLARITY 법안 15대9로 가결해 본회의로 회부",
            "상원 은행위원회가 H.R. 3633 CLARITY 법안을 15대9로 가결했습니다. 위원회 심사를 통과했기 때문에 다음 핵심 단계는 상원 본회의 심사와 표결입니다. 이것은 개회 연설이나 찬반 성명과 달리 실제 입법 절차가 한 단계 전진한 사건입니다.",
        )
    if "leads historic markup" in signal:
        return (
            "상원 은행위원회, CLARITY 법안 마크업 개최",
            "상원 은행위원회가 H.R. 3633 CLARITY 법안의 조문 심사와 수정안 처리를 위한 마크업을 열었습니다. 같은 날 실제 위원회 가결 결과가 확인되면 마크업 개최보다 가결 결과를 우선해 하나의 사건으로 묶어 알립니다.",
        )
    return "", ""


def fallback_korean(event):
    et = clean(event.get("event_type", ""))
    src = clean(event.get("source", ""))
    if "표결 결과" in et:
        return "CLARITY 관련 실제 표결 결과가 새로 확인됐습니다. 찬반 수치와 다음 절차를 기준으로 해석해야 합니다."
    if "토론종결" in et:
        return "상원에서 CLARITY 법안의 본회의 진행 여부를 가르는 토론종결·절차 표결 변화가 확인됐습니다."
    if "본회의 일정" in et:
        return "CLARITY 법안의 상원 본회의 일정이 새로 확정되거나 변경됐습니다."
    if "수정" in et or "원문 버전" in et:
        return "CLARITY 법안 문안이 새로 올라왔거나 핵심 조항이 수정됐습니다. SEC·CFTC 권한 배분과 거래소·토큰화 증권·스테이블코인 조항을 다시 비교해야 합니다."
    if "SEC" in src:
        return "SEC가 암호자산과 관련한 새로운 공식 규칙·해석·지침을 발표했습니다."
    if "CFTC" in src:
        return "CFTC가 암호자산과 관련한 새로운 공식 규칙·해석·지침을 발표했습니다."
    if "대통령" in et:
        return "백악관의 서명·거부권 등 CLARITY 법안의 최종 조치 단계에서 새 변화가 확인됐습니다."
    return "CLARITY 법안 또는 관련 규제에서 새로운 공식 변화가 확인됐습니다."


def localize_event(event):
    special_title, special_body = special_translation(event)
    if special_title:
        return special_title, special_body
    title_ko = translate_ko(event.get("title", ""))
    detail_ko = translate_ko(event.get("detail", ""))
    if not title_ko:
        title_ko = fallback_korean(event)
    if not detail_ko:
        detail_ko = fallback_korean(event)
    return title_ko, detail_ko


def easy_meaning(event, body_ko):
    signal = f"{event.get('event_type','')} {event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if "regulation crypto assets" in signal:
        return "의회 입법이 끝나기 전에도 SEC가 자체 규칙으로 일부 규제 공백을 메우려는 것입니다. 다만 아직 제안 단계여서 최종 내용은 바뀔 수 있습니다."
    if "advance clarity act" in signal and "vote" in signal:
        return "단순 토론이나 성명이 아니라 위원회가 실제로 15대9로 법안을 통과시킨 것입니다. 이제 상원 본회의가 다음 관문입니다."
    if "cloture" in signal:
        return "상원이 법안을 계속 끌지 않고 본회의 표결 단계로 넘길 수 있는지를 가르는 절차 변화입니다."
    if "final rule" in signal or "adopt" in signal:
        return "규칙 초안이 아니라 최종 규칙이 확정된 변화여서 실제 사업자 의무와 비용에 직접 연결될 가능성이 큽니다."
    if "propos" in signal:
        return "새 규칙을 확정한 것이 아니라 초안을 내놓고 의견을 받는 단계입니다."
    if "passed" in signal or "passage" in signal:
        return "법안이 실제로 한 단계 통과한 것이므로 단순 일정 발표보다 입법 가능성이 크게 높아진 변화입니다."
    return body_ko


def investment_lines(event):
    signal = f"{event.get('event_type','')} {event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if "regulation crypto assets" in signal:
        return [
            "돈 버는 능력: Coinbase에는 규칙 명확화가 상장·중개·기관사업 확장에 긍정적일 수 있지만 새 등록·공시 의무가 비용으로 돌아올 수 있습니다. Circle은 스테이블코인 직접 적용 여부를 별도로 봐야 합니다.",
            "할인율: 규제 불확실성 축소는 미국 암호자산 사업자의 규제 위험 프리미엄을 낮추는 방향입니다.",
            "수급: 미국 기관·사업자의 미국 내 잔류 유인은 개선될 수 있으나 제안 단계라 즉시 자금 유입으로 단정하지 않습니다.",
            "시간표: CLARITY 법안 지연과 별개로 SEC 규칙 제정 절차라는 별도 시간표가 생겼습니다.",
        ]
    if "advance clarity act" in signal and "vote" in signal:
        return [
            "돈 버는 능력: 위원회 통과만으로 Coinbase·Circle의 현재 매출·마진이 바로 바뀌지는 않습니다.",
            "할인율: 법안 통과 확률이 높아져 미국 사업자의 규제 불확실성은 낮아지는 방향입니다.",
            "수급: COIN·CRCL에는 입법 기대 수급이 붙을 수 있지만 BTC 자체 영향은 상대적으로 간접적입니다.",
            "시간표: 실제로 바뀐 핵심 축입니다. 위원회 15대9 통과 뒤 상원 본회의가 다음 관문입니다.",
        ]
    if "cloture" in signal:
        return [
            "돈 버는 능력: 아직 사업자 매출·마진이 직접 바뀐 단계는 아닙니다.",
            "할인율: 입법 불확실성 축소 가능성이 커지지만 실제 표결 결과 전까지 확정 효과는 아닙니다.",
            "수급: COIN·CRCL 기대 수급이 붙을 수 있으나 실제 표결과 분리합니다.",
            "시간표: 가장 직접적으로 바뀐 축이며 토론종결 성공 여부가 본회의 최종 표결의 관문입니다.",
        ]
    if "schedule" in signal or "calendar" in signal or "본회의 일정" in signal:
        return [
            "돈 버는 능력: 아직 직접 변화는 없습니다.",
            "할인율: 일정 가시성 개선 효과는 있으나 결과 전까지 제한적입니다.",
            "수급: 이벤트 기대 수급은 생길 수 있으나 실제 표결 결과와 분리합니다.",
            "시간표: 이번 사건에서 실제로 바뀐 핵심 축입니다.",
        ]
    return [
        "돈 버는 능력: Coinbase·Circle 등 미국 사업자의 규제비용과 상품 확장 가능성이 실제로 바뀌는지 확인합니다.",
        "할인율: 규제 불확실성과 금리·달러·유동성을 분리해 봅니다.",
        "수급: 미국 내 기관·개발자·자본의 잔류·유입 조건이 바뀌는지 확인합니다.",
        "시간표: 상원 표결 → 필요 시 하원 재처리 → 대통령 조치까지의 일정 변화를 봅니다.",
    ]


def core_summary(event):
    signal = f"{event.get('event_type','')} {event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if "regulation crypto assets" in signal:
        return "SEC의 별도 규칙안은 Coinbase의 돈 버는 능력·규제 할인율을 개선할 가능성이 있지만 아직 제안 단계라 확정 효과가 아니며, 최종 규칙 수정·소송·정책 반전이 최대 실패 경로입니다."
    if "advance clarity act" in signal and "vote" in signal:
        return "상원 은행위원회 15대9 가결로 실제 바뀐 축은 시간표와 규제 할인율이며 Coinbase에는 긍정적, Circle은 조항별 영향 확인이 필요하고 BTC는 상대적으로 간접적이며, 상원 본회의 부결·대규모 수정이 최대 실패 경로입니다."
    if "cloture" in signal:
        return "이번 변화는 돈 버는 능력보다 시간표를 앞당기는 사건으로, 토론종결 성공 시 본회의 표결 가능성이 높아지지만 실제 통과 전까지 실적 효과는 기대 단계이고 부결·추가 수정이 최대 실패 경로입니다."
    if "schedule" in signal or "calendar" in signal or "본회의 일정" in signal:
        return "이번 변화는 실적보다 시간표만 가시화한 사건으로 실제 표결 전까지 Coinbase·Circle의 돈 버는 능력은 바뀌지 않았고, 일정 재변경·표결 연기·수정안 협상이 최대 실패 경로입니다."
    return "이번 공식 변화가 돈 버는 능력·할인율·수급·시간표 중 어느 축을 실제로 바꿨는지와 Coinbase·Circle·BTC의 직접 영향을 구분하고, 확정 절차 전에는 기대감과 확정 효과를 섞지 않는 것이 핵심입니다."


def event_block(event, index):
    title_ko, body_ko = localize_event(event)
    meaning = easy_meaning(event, body_ko)
    url = html.escape(event.get("url", ""), quote=True)
    lines = [
        f"<b>{index}. {html.escape(title_ko)}</b>",
        f"사건 유형: {html.escape(clean(event.get('event_type','')))}",
        f"공식 출처: {html.escape(clean(event.get('source','')))}",
    ]
    if event.get("date"):
        formatted_date, converted_to_kst = format_event_date_korean(event.get("date", ""))
        label = "공식 날짜(한국시간)" if converted_to_kst else "공식 날짜"
        lines.append(f"{label}: {html.escape(formatted_date)}")
    if body_ko:
        lines += ["", "<b>무슨 내용?</b>", html.escape(body_ko)]
    lines += ["", "<b>쉽게 말하면</b>", html.escape(meaning)]
    if url:
        lines += ["", f'<a href="{url}">원문</a>']
    return "\n".join(lines)


def build_chunks(events, limit=3900):
    if not events:
        return []
    header = "<b>🔔 CLARITY 법안 공식 변화</b>"
    blocks = [event_block(e, i) for i, e in enumerate(events, 1)]
    first_event = events[0]
    invest = ["<b>투자 4축</b>"] + [f"- {html.escape(x)}" for x in investment_lines(first_event)]
    tail = [
        "", "<b>원인 분리</b>",
        "코인·주가가 움직였더라도 CLARITY/SEC 규제 변화 때문이라고 바로 단정하지 않고 미국 국채금리·달러·Nasdaq 등 같은 시간대 변수를 함께 확인합니다.",
        "", "<b>핵심 한 줄 요약</b>", html.escape(core_summary(first_event)),
    ]
    chunks, current = [], header
    for block in blocks:
        candidate = current + "\n\n" + block
        if len(candidate) > limit and current != header:
            chunks.append(current)
            current = "<b>CLARITY 법안 공식 변화 (계속)</b>\n\n" + block
        else:
            current = candidate
    footer = "\n\n" + "\n".join(invest + tail)
    if len(current + footer) <= limit:
        current += footer
    else:
        chunks.append(current)
        current = "<b>CLARITY 법안 공식 변화 — 투자 해석</b>\n\n" + "\n".join(invest + tail)
    chunks.append(current)
    return chunks


def main():
    events = json.loads(ALERT_JSON.read_text(encoding="utf-8"))
    events = filter_alertable_events(events)

    for path in (OUT_HTML, OUT_CHUNKS):
        if path.exists():
            path.unlink()

    if not events:
        print("clarity_korean_format_ready=false reason=no_fresh_substantive_event")
        return

    chunks = build_chunks(events)
    OUT_HTML.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    OUT_CHUNKS.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"clarity_korean_format_ready=true chunks={len(chunks)} filtered_events={len(events)}")


if __name__ == "__main__":
    main()
