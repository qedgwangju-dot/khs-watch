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
    params = urllib.parse.urlencode({"client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": text})
    req = urllib.request.Request(f"{TRANSLATE_URL}?{params}", headers={"User-Agent": "Mozilla/5.0"})
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


def rule_stage(event):
    event_type = clean(event.get("event_type", "")).lower()
    source = clean(event.get("source", "")).lower()
    fr_type = clean(event.get("federal_register_type", "")).lower()
    if "제안규칙" in event_type or "제안규칙" in source or "proposed rule" in fr_type or fr_type == "prorule":
        return "proposed"
    if "최종규칙" in event_type or "최종규칙" in source or fr_type == "rule" or "final rule" in fr_type:
        return "final"
    title = clean(event.get("title", "")).lower()
    if re.search(r"\bpropos(?:e|es|ed|al|ing)\b", title):
        return "proposed"
    if "final rule" in title:
        return "final"
    return ""


def is_policy_pressure(event):
    et = clean(event.get("event_type", ""))
    return "통과 촉구" in et or "정책 압력" in et


def is_political_risk(event):
    et = clean(event.get("event_type", ""))
    return "정치·윤리" in et or "이해충돌" in et


def is_industry_pressure(event):
    et = clean(event.get("event_type", ""))
    return "핵심 사업자" in et or "업계 표결 촉구" in et or bool(clean(event.get("industry_actor", "")))


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
    if is_industry_pressure(event):
        return ("industry_pressure", clean(event.get("industry_actor", "")) or title, day)
    if is_policy_pressure(event) or is_political_risk(event):
        return (clean(event.get("event_type", "")), clean(event.get("policy_actor", "")) or title, day)
    return (
        clean(event.get("event_type", "")), source, day,
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
    if is_policy_pressure(event) or is_political_risk(event):
        score += 20
    if is_industry_pressure(event):
        score += 15
    return score


def filter_alertable_events(events, now=None, freshness_days=7):
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
    if "innovation exemption" in signal and "tokenized" in signal:
        return (
            "SEC, 토큰화 미국주식 온체인 거래에 5년 한시 ‘Innovation Exemption’ 시행",
            "미 SEC는 Tokenized Securities Venue(TSV)가 일정한 토큰화 NMS 주식을 온체인에서 거래할 수 있도록 5년간 임시·조건부 면제를 부여했습니다. TSV는 거래소 정의에서, 일정 요건의 유동성 공급자는 dealer 정의에서 한시적으로 면제됩니다. 거래 대상 토큰은 기존 주식과 동일한 배당·의결권 등 권리를 제공해야 하며 합성형 토큰은 제외되고, 제3자가 토큰화한 주식은 원 발행회사가 반대하면 TSV가 거래할 수 없습니다.",
        )
    if "sec proposes new regulation crypto assets" in signal or "regulation crypto assets" in signal:
        return (
            "SEC, 암호자산 관련 투자계약을 위한 새 규칙안 ‘Regulation Crypto Assets’ 제안",
            "미 SEC는 일부 암호자산 관련 투자계약에 대해 더 명확하고 자산 특성에 맞는 규제 틀을 만들기 위한 새 규칙안을 제안했습니다. 아직 최종 규칙이 아니라 제안 단계입니다.",
        )
    if "advance clarity act" in signal and "bipartisan vote" in signal:
        return (
            "상원 은행위원회, CLARITY 법안 15대9로 가결해 본회의로 회부",
            "상원 은행위원회가 H.R. 3633 CLARITY 법안을 15대9로 가결했습니다. 위원회 심사를 통과했기 때문에 다음 핵심 단계는 상원 본회의 심사와 표결입니다.",
        )
    if "leads historic markup" in signal:
        return (
            "상원 은행위원회, CLARITY 법안 마크업 개최",
            "상원 은행위원회가 H.R. 3633 CLARITY 법안의 조문 심사와 수정안 처리를 위한 마크업을 열었습니다. 같은 날 실제 가결 결과가 확인되면 가결 결과를 우선해 하나의 사건으로 묶습니다.",
        )
    return "", ""


def fallback_korean(event):
    et = clean(event.get("event_type", ""))
    src = clean(event.get("source", ""))
    stage = rule_stage(event)
    if is_industry_pressure(event):
        return "Coinbase·BitGo 등 직접 규제 대상 사업자의 고위 임원이 CLARITY 법안 표결·통과를 공개적으로 촉구한 업계 압박 신호입니다. 정부의 공식 입법 조치와는 구분해 해석합니다."
    if is_policy_pressure(event):
        return "Trump 대통령·Bessent 재무장관·백악관·상원 지도부 등 핵심 당사자가 CLARITY 법안의 통과 또는 절차 진행을 공개적으로 압박한 새 정책 신호입니다."
    if is_political_risk(event):
        return "CLARITY 법안의 윤리·이해충돌 조항이 상원 표 확보와 협상의 핵심 변수로 다시 부각됐습니다."
    if stage == "proposed":
        return "SEC 또는 CFTC가 암호자산 관련 제안규칙을 공개했습니다. 아직 최종 확정이 아니라 의견수렴·수정 가능성이 남아 있습니다."
    if stage == "final":
        return "SEC 또는 CFTC가 암호자산 관련 최종규칙을 확정했습니다. 시행일·준수기한과 실제 사업자 의무를 확인해야 합니다."
    if "표결 결과" in et:
        return "CLARITY 관련 실제 표결 결과가 새로 확인됐습니다. 찬반 수치와 다음 절차를 기준으로 해석해야 합니다."
    if "토론종결" in et:
        return "상원에서 CLARITY 법안의 본회의 진행 여부를 가르는 토론종결·절차 표결 변화가 확인됐습니다."
    if "본회의 일정" in et:
        return "CLARITY 법안의 상원 본회의 일정이 새로 확정되거나 변경됐습니다."
    if "수정" in et or "원문 버전" in et:
        return "CLARITY 법안 문안이 새로 올라왔거나 핵심 조항이 수정됐습니다."
    if "SEC" in src or "CFTC" in src:
        return "SEC 또는 CFTC의 암호자산 관련 공식 조치가 새로 확인됐습니다."
    if "대통령" in et:
        return "백악관의 서명·거부권 등 CLARITY 법안의 최종 조치 단계에서 새 변화가 확인됐습니다."
    return "CLARITY 법안 또는 관련 규제에서 새로운 공식 변화가 확인됐습니다."


def localize_event(event):
    special_title, special_body = special_translation(event)
    if special_title:
        return special_title, special_body
    title_ko = translate_ko(event.get("title", ""))
    detail_ko = translate_ko(event.get("detail", ""))
    return title_ko or fallback_korean(event), detail_ko or fallback_korean(event)


def easy_meaning(event, body_ko):
    stage = rule_stage(event)
    signal = f"{event.get('event_type','')} {event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if "innovation exemption" in signal and "tokenized" in signal:
        return "CLARITY 법안이 상원 절차표결에서 막힌 뒤 SEC가 기존 증권법상 면제 권한을 사용해 토큰화 주식 거래의 별도 규제 통로를 즉시 열었습니다. 다만 이것은 CLARITY를 대체하는 영구 법률이 아니라 5년 한시·조건부 조치입니다. 실제 주주권이 없는 합성 토큰은 제외되고, 발행회사는 제3자 토큰화 주식의 TSV 거래에 이의를 제기할 수 있습니다."
    if is_industry_pressure(event):
        return "직접 수혜·규제 대상 기업이 의회에 표결을 압박하는 발언이라 이해관계가 있는 주장입니다. 그래서 ‘공식 절차 변화’로 보지는 않지만, 업계의 로비 강도와 미국 내 혁신·토큰화 사업이 규제 지연 때문에 해외에서 먼저 커질 위험을 보여주는 시간표·수급 보조신호로 봅니다. 실제 표 수나 법안 통과를 증명하는 신호는 아닙니다."
    if is_policy_pressure(event):
        return "실제 표결이나 법률 효력이 생긴 것은 아니지만, 대통령·재무장관·백악관 같은 최고위 당사자가 공개적으로 처리를 압박하면 상원 의원들의 협상 비용과 표결 시간표가 바뀔 수 있습니다. 따라서 ‘입법 절차 변화’와 별도로 통과 확률을 움직이는 정책 압력 신호로 봅니다."
    if is_political_risk(event):
        return "윤리·이해충돌 논란은 법안의 경제적 내용과 별개로 60표 확보와 초당적 협상을 어렵게 만들 수 있습니다. 그래서 가격보다 먼저 표결 시간표의 역풍으로 봅니다."
    if stage == "proposed":
        return "이 문서는 제안규칙입니다. 규칙 초안을 공개해 의견을 받는 단계이므로 아직 사업자에게 최종 의무가 확정된 것은 아니며, 의견수렴 뒤 내용이 바뀔 수 있습니다."
    if stage == "final":
        return "이 문서는 최종규칙입니다. 제안 단계보다 법적·사업적 영향이 직접적이므로 시행일과 준수기한을 확인해야 합니다."
    if "advance clarity act" in signal and "vote" in signal:
        return "단순 토론이나 성명이 아니라 위원회가 실제로 15대9로 법안을 통과시킨 것입니다. 이제 상원 본회의가 다음 관문입니다."
    if "cloture" in signal:
        return "상원이 법안을 계속 끌지 않고 본회의 표결 단계로 넘길 수 있는지를 가르는 절차 변화입니다."
    if "passed" in signal or "passage" in signal:
        return "법안이 실제로 한 단계 통과한 것이므로 단순 일정 발표보다 입법 가능성이 크게 높아진 변화입니다."
    return body_ko


def investment_lines(event):
    stage = rule_stage(event)
    signal = f"{event.get('event_type','')} {event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if "innovation exemption" in signal and "tokenized" in signal:
        return [
            "돈 버는 능력: Robinhood·Coinbase·Securitize처럼 토큰화 증권 거래·인프라를 준비한 사업자는 미국 내 상품 출시 경로가 바로 열려 매출 연결 가능성이 높아졌습니다. Circle은 결제·스테이블코인 인프라 측 간접 수혜로 구분합니다.",
            "할인율: CLARITY 부결로 커진 규제 공백을 SEC가 일부 메우면서 미국 토큰화 사업의 규제 불확실성 프리미엄은 낮아지는 방향입니다. 다만 행정조치라 향후 위원회 구성·소송·영구 규칙에 따라 되돌릴 위험이 법률보다 큽니다.",
            "수급: 발표 직후 HOOD·COIN·CRCL·SECZ 등 관련주에 매수 반응이 나타났으므로, BTC보다 토큰화 증권 플랫폼·인프라 종목의 직접 민감도가 더 높습니다.",
            "시간표: 면제는 즉시 효력이 생기고 5년 후 만료됩니다. 이제 핵심 일정은 TSV 실제 신청·출범, 발행사 통지·이의제기, 거래량·종목 한도, SEC의 후속 영구 rulemaking입니다.",
        ]
    if is_industry_pressure(event):
        company = clean(event.get("industry_company", "")) or "미국 암호자산 사업자"
        return [
            f"돈 버는 능력: {company} 경영진의 촉구 자체로 현재 매출·마진이 바뀐 것은 아닙니다. 다만 CLARITY 통과 시 거래·수탁·토큰화·기관사업의 법적 가시성이 높아져 상품 확장 경로에는 긍정적입니다.",
            "할인율: 업계 압박 확대는 규제 불확실성 완화 기대를 키울 수 있지만 실제 표결 전까지 위험 프리미엄 하락을 확정해서는 안 됩니다.",
            "수급: 법집행·월가·암호화폐 유권자까지 지지 연합이 넓어졌다는 주장은 입법 기대 수급에 우호적이지만, 직접 수혜자의 주장인 만큼 실제 의원 표 수와 분리합니다.",
            "시간표: 실제 일정 변경은 아니지만 ‘이제 표결할 때’라는 압박이 커졌다는 신호입니다. 다음 확인은 토론종결·motion to proceed·최종 표결 결과입니다.",
        ]
    if "regulation crypto assets" in signal:
        return [
            "돈 버는 능력: Coinbase에는 규칙 명확화가 상장·중개·기관사업 확장에 긍정적일 수 있지만 새 등록·공시 의무가 비용으로 돌아올 수 있습니다. Circle은 스테이블코인 직접 적용 여부를 별도로 봐야 합니다.",
            "할인율: 규제 불확실성 축소는 미국 암호자산 사업자의 규제 위험 프리미엄을 낮추는 방향입니다.",
            "수급: 미국 기관·사업자의 미국 내 잔류 유인은 개선될 수 있으나 제안 단계라 즉시 자금 유입으로 단정하지 않습니다.",
            "시간표: CLARITY 법안 지연과 별개로 SEC 규칙 제정 절차라는 별도 시간표가 생겼습니다.",
        ]
    if is_policy_pressure(event):
        return [
            "돈 버는 능력: 공개 촉구만으로 Coinbase·Circle의 현재 실적은 바뀌지 않습니다.",
            "할인율: 행정부의 우선순위 재확인은 규제 불확실성 완화 기대에 긍정적이지만 실제 표결 전까지 확정 효과는 아닙니다.",
            "수급: 정책 기대 수급은 COIN·CRCL에 상대적으로 더 직접적이고 BTC에는 간접적입니다.",
            "시간표: 이번 사건에서 가장 직접적으로 바뀐 축은 상원에 대한 정치적 압박입니다. 실제 일정·표결 결과를 다음으로 확인합니다.",
        ]
    if is_political_risk(event):
        return [
            "돈 버는 능력: 현재 사업 실적은 직접 바뀌지 않았습니다.",
            "할인율: 이해충돌 논란이 커지면 규제 명확화 기대보다 정치 리스크가 다시 커질 수 있습니다.",
            "수급: 단기적으로 법안 수혜 기대 수급을 약화시킬 수 있으나 실제 가격 반응은 금리·달러와 분리합니다.",
            "시간표: 윤리조항 협상이 60표 확보를 지연시키는지가 핵심 실패 경로입니다.",
        ]
    if stage == "proposed":
        return [
            "돈 버는 능력: 제안규칙만으로 Coinbase·Circle의 현재 매출·마진이 확정적으로 바뀌지는 않습니다. 최종 문안이 사업 범위와 규제비용을 어떻게 바꾸는지가 핵심입니다.",
            "할인율: 규제 방향이 구체화됐다는 점은 불확실성 완화 요인이지만 최종 확정 전이라 효과는 제한적입니다.",
            "수급: 기대 수급이 붙을 수 있으나 실제 규칙 확정·시행과 구분해야 합니다.",
            "시간표: 의견수렴 마감 → 최종규칙 채택 여부 → 시행일·준수기한을 추적합니다.",
        ]
    if stage == "final":
        return [
            "돈 버는 능력: 최종규칙이면 등록·공시·거래·상품 의무가 실제 비용과 매출 기회에 직접 연결됩니다.",
            "할인율: 규제 불확실성 축소 효과가 제안 단계보다 큽니다.",
            "수급: 법적 가시성 개선으로 미국 내 기관·사업자 자금의 잔류·유입 논리가 강화될 수 있습니다.",
            "시간표: 시행일·전환기간·준수기한이 핵심 일정입니다.",
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
    stage = rule_stage(event)
    signal = f"{event.get('event_type','')} {event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if "innovation exemption" in signal and "tokenized" in signal:
        return "SEC의 5년 한시 Innovation Exemption은 CLARITY 부결 직후 토큰화 미국주식의 온체인 거래 통로를 실제로 연 조치로, HOOD·COIN·SECZ의 상품화 시간표와 규제 할인율에는 긍정적이고 CRCL에는 간접적이며, 한시 면제·종목/거래량 제한·발행사 거부권·향후 소송 또는 정책 반전이 최대 실패 경로입니다."
    if is_industry_pressure(event):
        actor = clean(event.get("industry_actor", "")) or "핵심 사업자"
        return f"{actor}의 표결 촉구는 공식 절차 변화가 아니라 업계 압박 신호로, 현재 돈 버는 능력은 그대로지만 시간표·규제 할인율 기대에는 긍정적이며, 직접 수혜자의 주장인 만큼 실제 상원 표 수가 늘었다고 볼 수 없고 표결 지연·부결·미국 밖 선행 혁신이 최대 실패 경로입니다."
    if "regulation crypto assets" in signal:
        return "SEC의 암호자산 규칙안은 Coinbase의 규제비용·상품확장 불확실성을 낮출 가능성이 있지만 아직 제안 단계라 확정 효과가 아니며, 최종 문안 변경·소송·정책 반전이 최대 실패 경로입니다."
    if is_policy_pressure(event):
        return "행정부·핵심 당사자의 통과 촉구로 실제 바뀐 축은 시간표와 규제 할인율 기대이며 Coinbase·Circle에는 긍정적이지만 현재 실적은 그대로이고, 상원 60표 미확보·추가 수정·일정 지연이 최대 실패 경로입니다."
    if is_political_risk(event):
        return "이해충돌·윤리조항 논란은 돈 버는 능력보다 시간표와 규제 할인율에 역풍이며, 60표 확보가 늦어질수록 Coinbase·Circle의 규제 명확화 수혜 시점도 뒤로 밀리는 것이 핵심입니다."
    if stage == "proposed":
        return "이번 조치는 제안규칙이므로 현재 돈 버는 능력은 아직 확정적으로 바뀌지 않았고 규제 할인율·시간표가 일부 구체화된 단계이며, 최종 문안 변경·채택 지연·소송이 최대 실패 경로입니다."
    if stage == "final":
        return "이번 조치는 최종규칙으로 사업자의 돈 버는 능력과 규제 할인율에 직접 연결될 수 있으며, 실제 영향은 시행일·준수비용·소송 또는 시행유예 여부가 결정합니다."
    if "advance clarity act" in signal and "vote" in signal:
        return "상원 은행위원회 15대9 가결로 실제 바뀐 축은 시간표와 규제 할인율이며 Coinbase에는 긍정적, Circle은 조항별 영향 확인이 필요하고 BTC는 상대적으로 간접적이며, 상원 본회의 부결·대규모 수정이 최대 실패 경로입니다."
    if "cloture" in signal:
        return "이번 변화는 돈 버는 능력보다 시간표를 앞당기는 사건으로, 토론종결 성공 시 본회의 표결 가능성이 높아지지만 실제 통과 전까지 실적 효과는 기대 단계이고 부결·추가 수정이 최대 실패 경로입니다."
    if "schedule" in signal or "calendar" in signal or "본회의 일정" in signal:
        return "이번 변화는 실적보다 시간표만 가시화한 사건으로 실제 표결 전까지 Coinbase·Circle의 돈 버는 능력은 바뀌지 않았고, 일정 재변경·표결 연기·수정안 협상이 최대 실패 경로입니다."
    return "이번 변화가 돈 버는 능력·할인율·수급·시간표 중 어느 축을 실제로 바꿨는지와 Coinbase·Circle·BTC의 직접 영향을 구분하고, 확정 절차 전에는 기대감과 확정 효과를 섞지 않는 것이 핵심입니다."


def event_block(event, index):
    title_ko, body_ko = localize_event(event)
    meaning = easy_meaning(event, body_ko)
    url = html.escape(event.get("url", ""), quote=True)
    lines = [
        f"<b>{index}. {html.escape(title_ko)}</b>",
        f"사건 유형: {html.escape(clean(event.get('event_type','')))}",
        f"출처: {html.escape(clean(event.get('source','')))}",
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
    header = "<b>🔔 CLARITY 법안 Watch — 표결·규제·BTC/COIN/Circle 영향</b>"
    blocks = [event_block(e, i) for i, e in enumerate(events, 1)]
    first_event = events[0]
    invest = ["<b>투자 4축</b>"] + [f"- {html.escape(x)}" for x in investment_lines(first_event)]
    tail = [
        "", "<b>원인 분리</b>",
        "코인·주가가 움직였더라도 CLARITY 관련 발언·규제 변화 때문이라고 바로 단정하지 않고 미국 국채금리·달러·Nasdaq 등 같은 시간대 변수를 함께 확인합니다.",
        "", "<b>핵심 한 줄 요약</b>", html.escape(core_summary(first_event)),
    ]
    chunks, current = [], header
    for block in blocks:
        candidate = current + "\n\n" + block
        if len(candidate) > limit and current != header:
            chunks.append(current)
            current = "<b>CLARITY 법안 Watch (계속)</b>\n\n" + block
        else:
            current = candidate
    footer = "\n\n" + "\n".join(invest + tail)
    if len(current + footer) <= limit:
        current += footer
    else:
        chunks.append(current)
        current = "<b>CLARITY 법안 Watch — 투자 해석</b>\n\n" + "\n".join(invest + tail)
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
