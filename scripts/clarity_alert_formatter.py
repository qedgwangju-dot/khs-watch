#!/usr/bin/env python3
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request

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
        "client": "gtx",
        "sl": "en",
        "tl": "ko",
        "dt": "t",
        "q": text,
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
        else:
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


def special_translation(event):
    title = clean(event.get("title", ""))
    detail = clean(event.get("detail", ""))
    signal = f"{title} {detail}".lower()
    if "sec proposes new regulation crypto assets" in signal or "regulation crypto assets" in signal:
        return (
            "SEC, 암호자산 관련 투자계약을 위한 새 규칙안 ‘Regulation Crypto Assets’ 제안",
            "미 SEC는 일부 암호자산과 관련된 투자계약에 대해 더 명확하고 해당 자산의 특성에 맞는 규제 틀을 만들기 위한 새 규칙안을 제안했습니다. 아직 최종 규칙이 아니라 제안 단계이며, CLARITY 법안이 의회에서 지연되더라도 SEC가 자기 권한 범위에서 규제 공백을 먼저 줄이려는 움직임으로 볼 수 있습니다.",
        )
    return "", ""


def fallback_korean(event):
    et = clean(event.get("event_type", ""))
    src = clean(event.get("source", ""))
    if "표결 결과" in et:
        return "의회에서 CLARITY 관련 실제 표결 결과가 새로 확인됐습니다."
    if "토론종결" in et:
        return "상원에서 CLARITY 법안의 본회의 진행 여부를 가르는 토론종결·절차 표결 변화가 확인됐습니다."
    if "본회의 일정" in et:
        return "CLARITY 법안의 상원 본회의 일정이 새로 확정되거나 변경됐습니다."
    if "수정" in et or "원문 버전" in et:
        return "CLARITY 법안 문안이 새로 올라왔거나 핵심 조항이 수정됐습니다. SEC·CFTC 권한 배분과 거래소·토큰화 증권·스테이블코인 조항을 다시 비교해야 합니다."
    if src.startswith("SEC") or "SEC" in src:
        return "SEC가 암호자산과 관련한 새로운 공식 규칙·해석·지침을 발표했습니다. CLARITY 법안 통과 여부와 별개로 SEC가 자체 규칙으로 규제 공백을 메우는 변화인지 확인해야 합니다."
    if src.startswith("CFTC") or "CFTC" in src:
        return "CFTC가 암호자산과 관련한 새로운 공식 규칙·해석·지침을 발표했습니다. CLARITY 법안 통과 여부와 별개로 CFTC가 자체 규칙으로 규제 공백을 메우는 변화인지 확인해야 합니다."
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
        return (
            "쉽게 말하면, 의회가 CLARITY 법안을 아직 끝내지 못했더라도 SEC가 먼저 ‘어떤 암호자산 관련 투자계약을 어떤 규칙으로 다룰지’를 구체화하기 시작한 것입니다. "
            "다만 ‘제안(proposal)’이므로 바로 법적 의무가 확정된 것은 아닙니다."
        )
    if "propos" in signal:
        return "새 규칙을 확정한 것이 아니라 초안을 내놓고 의견을 받는 단계입니다. 최종 규칙까지는 내용이 바뀔 수 있습니다."
    if "final rule" in signal or "adopt" in signal:
        return "규칙 초안이 아니라 최종 규칙이 확정된 변화여서 실제 사업자 의무와 비용에 바로 연결될 가능성이 더 큽니다."
    if "cloture" in signal:
        return "상원이 법안을 계속 끌지 않고 본회의 표결 단계로 넘길 수 있는지를 가르는 절차 변화입니다."
    if "passed" in signal or "passage" in signal:
        return "법안이 한 단계 실제로 통과한 것이므로 단순 일정 발표보다 입법 가능성이 크게 높아진 변화입니다."
    return body_ko


def investment_lines(event):
    signal = f"{event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if "regulation crypto assets" in signal:
        return [
            "돈 버는 능력: Coinbase에는 규칙이 명확해지면 상장·중개·기관사업의 법적 불확실성이 줄 수 있지만, 새 등록·공시 의무가 생기면 비용도 늘 수 있습니다. Circle은 이번 규칙이 스테이블코인 자체를 직접 겨냥한 내용인지 별도 확인이 필요해 직접 영향은 상대적으로 작습니다.",
            "할인율: 이번 SEC 규칙안 자체가 금리를 바꾸는 사건은 아닙니다. BTC·COIN·CRCL 주가 반응은 국채금리·달러·Nasdaq 움직임과 분리해서 봐야 합니다.",
            "수급: 규제 기준이 명확해질수록 미국 기관·거래소·개발자가 미국 내에서 사업할 유인은 커질 수 있습니다. 다만 제안 단계라 즉시 자금 유입으로 연결됐다고 보기는 이릅니다.",
            "시간표: CLARITY 법안이 늦어져도 SEC가 별도 규칙으로 일부 공백을 메우기 시작했다는 점이 실제로 바뀐 축입니다.",
        ]
    return [
        "돈 버는 능력: Coinbase·Circle 등 미국 사업자의 규제비용과 상품 확장 가능성이 실제로 바뀌는지 확인합니다.",
        "할인율: 법안보다 금리·달러·유동성이 직접 변수이므로 시장 반응의 원인을 분리합니다.",
        "수급: 규제 명확성이 미국 내 기관·개발자·자본의 잔류·유입 조건을 바꾸는지 확인합니다.",
        "시간표: 상원 최종 표결 → 필요 시 하원 재처리 → 대통령 조치까지의 일정이 얼마나 앞당겨지거나 늦어졌는지 봅니다.",
    ]


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
        lines.append(f"공식 날짜: {html.escape(clean(event.get('date','')))}")
    if body_ko:
        lines += ["", "<b>무슨 내용?</b>", html.escape(body_ko)]
    lines += ["", "<b>쉽게 말하면</b>", html.escape(meaning)]
    if url:
        lines += ["", f'<a href="{url}">원문</a>']
    return "\n".join(lines)


def build_chunks(events, limit=3900):
    header = "<b>🔔 CLARITY 법안 공식 변화</b>"
    blocks = [event_block(e, i) for i, e in enumerate(events, 1)]
    invest = ["<b>투자 4축</b>"] + [f"- {html.escape(x)}" for x in investment_lines(events[0] if events else {})]
    tail = [
        "",
        "<b>원인 분리</b>",
        "코인·주가가 움직였더라도 CLARITY/SEC 규제 변화 때문이라고 바로 단정하지 않고, 미국 국채금리·달러·Nasdaq 등 같은 시간대 변수를 함께 확인합니다.",
        "",
        "<b>핵심 한 줄 요약</b>",
        "새 공식 변화가 있을 때만 알리고, 영어 원문은 한국어로 풀어서 설명하며 링크는 ‘원문’ 글자에 연결합니다.",
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
    chunks = build_chunks(events)
    OUT_HTML.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    OUT_CHUNKS.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"clarity_korean_format_ready=true chunks={len(chunks)}")


if __name__ == "__main__":
    main()
