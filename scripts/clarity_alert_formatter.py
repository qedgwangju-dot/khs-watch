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


def koreanize_regulatory_terms(text):
    text = clean(text)
    if not text:
        return text
    replacements = [
        (r"\bPending Review\b", "Pending Review(검토 중)"),
        (r"\bConcluded\b", "Concluded(검토 완료)"),
        (r"\bPrerule Stage\b", "Prerule Stage(사전규칙 단계)"),
        (r"\bPrerule\b", "Prerule(사전규칙 단계)"),
        (r"\bProposed Rule Stage\b", "Proposed Rule Stage(제안규칙 단계)"),
        (r"\bProposed Rule\b", "Proposed Rule(제안규칙)"),
        (r"\bFinal Rule Stage\b", "Final Rule Stage(최종규칙 단계)"),
        (r"\bInterim Final Rule\b", "Interim Final Rule(잠정 최종규칙)"),
        (r"\bFinal Rule\b", "Final Rule(최종규칙)"),
        (r"\bEconomically Significant\b", "Economically Significant(경제적으로 중대한 규제 여부)"),
        (r"\bLegal Deadline\b", "Legal Deadline(법정 처리기한)"),
        (r"\bReceived Date\b", "Received Date(접수일)"),
        (r"\bStatus\b", "Status(상태)"),
        (r"\bStage\b", "Stage(단계)"),
        (r"\bcrypto exchanges?\b", "crypto exchange(암호자산 거래소)"),
        (r"\bcrypto asset markets?\b", "crypto asset market(암호자산 시장)"),
        (r"\bonchain finance protocols?\b", "onchain finance protocol(온체인 금융 프로토콜)"),
        (r"\bderivatives\b", "derivatives(파생상품)"),
        (r"\bperpetuals?\b", "perpetual(무기한 선물)"),
        (r"\brulemaking\b", "rulemaking(규칙제정)"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return clean(text)


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


def is_oira_prerule(event):
    signal = f"{event.get('event_type','')} {event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if is_sec_crypto_custody_2026(event):
        return (
            "쉽게 말하면, SEC가 기관의 암호자산 보관 규칙을 현실에 맞게 넓히려는 제안입니다. "
            "특정 조건에서는 외부 수탁기관 없이 자체 수탁도 허용하고 주 신탁회사도 수탁 경로로 인정하려는 방향이지만, "
            "모든 코인에 자동 적용되는 규칙은 아니고 아직 Proposed Rule(제안규칙)이라 즉시 효력도 없습니다."
        )
    return ("oira" in signal or "reginfo" in signal) and ("prerule" in signal or "pre-rule" in signal)


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
    if is_oira_prerule(event):
        return "prerule"
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


def is_volatility_3x_crypto_launch(event):
    signal = clean(
        f"{event.get('event_type','')} {event.get('title','')} {event.get('detail','')} {event.get('source','')}"
    ).lower()
    return (
        "volatility shares" in signal
        and ("bith" in signal or "ethk" in signal)
        and ("상품목록" in signal or "product page listed" in signal or "거래개시" in signal)
    )


def is_sec_3x_crypto_etp_approval(event):
    signal = clean(
        f"{event.get('title','')} {event.get('detail','')} {event.get('source','')}"
    ).lower()
    return (
        "3x bitcoin etf" in signal
        and ("3x ether etf" in signal or "3x ethereum etf" in signal)
        and ("order granting approval" in signal or "approval" in signal or "approved" in signal)
    )


def is_sec_crypto_custody_2026(event):
    signal = clean(
        f"{event.get('title','')} {event.get('detail','')} {event.get('source','')}"
    ).lower()
    if "sec" not in signal and "securities and exchange commission" not in signal:
        return False
    custody = "custody" in signal or "custodian" in signal
    crypto = "crypto" in signal
    adviser_fund = any(x in signal for x in [
        "investment adviser", "investment advisers", "regulated fund", "regulated funds",
        "investment company act", "advisers act",
    ])
    return custody and crypto and adviser_fund


def is_sec_statement(event):
    return clean(event.get("source", "")) == "SEC 발언·성명"


def semantic_group(event):
    title = clean(event.get("title", "")).lower()
    source = clean(event.get("source", ""))
    when = parse_event_date(event.get("date", ""))
    day = when.date().isoformat() if when else clean(event.get("date", ""))
    if is_sec_3x_crypto_etp_approval(event):
        return ("sec_3x_btc_eth_etp_sr_cboebzx_2026_065", day)
    if is_volatility_3x_crypto_launch(event):
        return ("volatility_3x_crypto_launch", day)
    if is_sec_crypto_custody_2026(event):
        return ("sec_crypto_custody_s7_2026_35", day)
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
    if is_volatility_3x_crypto_launch(event):
        score += 260
    if is_sec_3x_crypto_etp_approval(event):
        score += 320
    if is_sec_crypto_custody_2026(event):
        if source == "SEC 보도자료":
            score += 250
        elif source == "SEC Federal Register 제안규칙":
            score += 300
        elif source == "SEC 발언·성명":
            score += 50
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
    grouped_sources = {}
    for event in candidates:
        key = semantic_group(event)
        grouped_sources.setdefault(key, [])
        src = clean(event.get("source", ""))
        if src and src not in grouped_sources[key]:
            grouped_sources[key].append(src)
        existing = best_by_group.get(key)
        if existing is None or event_priority(event) > event_priority(existing):
            best_by_group[key] = event
    output = []
    for key, event in best_by_group.items():
        event = dict(event)
        if key and key[0] == "sec_3x_btc_eth_etp_sr_cboebzx_2026_065":
            event["evidence_sources"] = [
                "SEC Release 34-106577 / SR-CboeBZX-2026-065",
                "Cboe BZX 공식 규칙변경",
                "Volatility Shares 등록서류",
            ]
            event["semantic_event"] = "sec_3x_btc_eth_etp_sr_cboebzx_2026_065"
        if key and key[0] == "sec_crypto_custody_s7_2026_35":
            event["evidence_sources"] = [
                "SEC 보도자료 2026-100",
                "SEC Fact Sheet — IA-7023 / IC-36353",
                "NYDFS 가상자산 규제기관 목록(Coinbase Custody·Circle New York Trust)",
            ]
            event["semantic_event"] = "sec_crypto_custody_s7_2026_35"
        output.append(event)
    return output


def federal_register_comments_close(event):
    detail = clean(event.get("detail", ""))
    m = re.search(r"Comments Close:\s*(\d{4}-\d{2}-\d{2})", detail, re.I)
    return m.group(1) if m else ""


def federal_register_document_number(event):
    detail = clean(event.get("detail", ""))
    m = re.search(r"Document Number:\s*([^|]+)", detail, re.I)
    return clean(m.group(1)) if m else ""

def federal_register_effective_date(event):
    detail = clean(event.get("detail", ""))
    m = re.search(r"Effective Date:\s*(\d{4}-\d{2}-\d{2})", detail, re.I)
    return m.group(1) if m else ""


def special_translation(event):
    title = clean(event.get("title", ""))
    detail = clean(event.get("detail", ""))
    signal = f"{title} {detail}".lower()
    if is_volatility_3x_crypto_launch(event):
        tickers = []
        if "bith" in signal:
            tickers.append("BITH(3x Bitcoin ETF)")
        if "ethk" in signal:
            tickers.append("ETHK(3x Ether ETF)")
        ticker_text = " · ".join(tickers) if tickers else "BITH·ETHK"
        return (
            "Volatility Shares, 3배 BTC·ETH ETP 실제 상품목록 등재",
            f"Volatility Shares 공식 상품목록에 {ticker_text}가 실제로 올라온 상태 변화입니다. "
            "SEC의 상장규칙 승인에서 발행사 상품 출시 단계로 한 칸 진전한 것이며, "
            "공식 inception date(설정일)·첫 거래일·AUM·거래대금을 확인해 실제 시장 수요로 넘어갔는지 판단해야 합니다.",
        )
    if is_sec_3x_crypto_etp_approval(event):
        return (
            "SEC, BITH·ETHK 3배 BTC·ETH ETP 상장규칙 승인",
            "SEC가 Cboe BZX의 SR-CboeBZX-2026-065를 승인해 VS Trust의 BITH(3x Bitcoin ETF)와 ETHK(3x Ether ETF)를 포함한 6개 3배 상품의 상장·거래 규칙을 승인했습니다. "
            "정확히는 현물 BTC·ETH를 3배 보유하는 상품이 아니라, CME 비트코인·이더 선물의 최근월·차근월 벤치마크 하루 수익률을 3배 추종하는 일일 재설정형 상품입니다. "
            "이번 SEC 조치는 거래소 상장규칙 승인이고, 실제 거래개시는 VS Trust 등록서류 효력·발행사 출시 절차를 별도로 확인해야 합니다.",
        )
    if is_sec_crypto_custody_2026(event):
        stage = rule_stage(event)
        due = federal_register_comments_close(event)
        effective = federal_register_effective_date(event)
        doc = federal_register_document_number(event)
        doc_text = f" Federal Register 문서번호는 {doc}입니다." if doc else ""
        if stage == "final":
            effective_text = f" 시행일은 {effective}입니다." if effective else " 시행일·준수기한은 Federal Register 원문에서 확인해야 합니다."
            return (
                "SEC, 투자자문사·펀드의 암호자산 수탁 최종규칙 확정",
                "SEC가 등록 투자자문사와 규제 펀드의 암호자산 수탁 규칙을 최종 확정했습니다. "
                "핵심 적용범위와 self-custody(자체 수탁), state trust company(주 신탁회사) 수탁 조건은 최종 문안 기준으로 판단해야 합니다. "
                "File No. S7-2026-35 계열 규칙입니다." + doc_text + effective_text,
            )
        due_text = f" 의견수렴 마감일은 {due}입니다." if due else " 의견 제출기한은 Federal Register(연방관보) 게재 후 60일입니다."
        return (
            "SEC, 투자자문사·펀드의 암호자산 수탁 규칙 개정안 제안",
            "SEC는 등록 투자자문사와 규제 펀드의 암호자산 수탁 규칙을 새로 제안했습니다. "
            "핵심은 제한적 self-custody(자체 수탁), 조건부 state trust company(주 신탁회사) 수탁 허용, "
            "기록보관·공시 규칙 현대화입니다. 다만 모든 암호자산에 자동 적용되는 것은 아니며, "
            "투자자문사 규칙은 해당 암호자산이 funds or securities(자금 또는 증권)에 해당하는 범위, "
            "규제 펀드는 securities or similar investments(증권 또는 유사 투자자산)에 해당하는 범위가 핵심입니다. "
            "File No. S7-2026-35, Release No. IA-7023 / IC-36353입니다." + doc_text + due_text,
        )
    if "3038-af80" in signal or "regulation crypto asset transactions and regulation crypto asset markets" in signal:
        return (
            "CFTC, 암호자산 거래·시장 규제안 RIN 3038-AF80을 백악관 규제검토에 제출",
            "미 백악관 규제정보·심사국(OIRA)의 RegInfo에는 CFTC RIN 3038-AF80 ‘Regulation Crypto Asset Transactions and Regulation Crypto Asset Markets(암호자산 거래 및 암호자산 시장 규제)’가 2026년 9월 17일 접수돼 Pending Review(검토 중)로 표시돼 있습니다. 규칙제정 단계는 Prerule(사전규칙 단계)이고, Economically Significant(경제적으로 중대한 규제 여부)는 No(아니오), Legal Deadline(법정 처리기한)은 None(없음)으로 표시됩니다. 공개된 규칙 본문·적용 자산·거래소 의무는 아직 없어 Proposed Rule(제안규칙)이나 Final Rule(최종규칙)로 보면 안 됩니다.",
        )
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
    if stage == "prerule":
        return "SEC 또는 CFTC의 암호자산 관련 규칙 작업이 OIRA 사전검토 단계에 들어갔습니다. 아직 제안규칙·최종규칙·시행 규정은 아닙니다."
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
    title_ko = koreanize_regulatory_terms(translate_ko(event.get("title", "")))
    detail_ko = koreanize_regulatory_terms(translate_ko(event.get("detail", "")))
    return title_ko or fallback_korean(event), detail_ko or fallback_korean(event)


def easy_meaning(event, body_ko):
    stage = rule_stage(event)
    signal = f"{event.get('event_type','')} {event.get('source','')} {event.get('title','')} {event.get('detail','')}".lower()
    if is_volatility_3x_crypto_launch(event):
        return (
            "쉽게 말하면, ‘SEC가 상장할 수 있게 허용했다’는 단계에서 한 걸음 더 나아가 발행사 공식 상품목록에 BITH·ETHK가 실제로 등장한 것입니다. "
            "이제부터 핵심은 첫 거래일과 AUM·거래대금이 얼마나 붙는지입니다."
        )
    if is_sec_3x_crypto_etp_approval(event):
        return (
            "쉽게 말하면, 미국 증시에서 BTC·ETH 방향에 하루 3배로 베팅하는 규제 상품을 상장할 수 있게 된 것입니다. "
            "다만 현물 코인을 3배 보유하는 상품이 아니라 선물 기반·일일 재설정 구조라 장기 수익률이 BTC·ETH 누적수익률의 정확히 3배가 되지는 않습니다."
        )
    if "3038-af80" in signal or "regulation crypto asset transactions and regulation crypto asset markets" in signal:
        return (
            "한마디로, CLARITY가 의회에서 막혀도 CFTC가 기다리지 않고 현재 가진 권한으로 미국 암호자산 시장 규칙을 먼저 만들기 시작했다는 뜻입니다. "
            "CFTC가 공식적으로 밝힌 방향은 기존 등록사와 일부 비등록 암호자산 거래소를 CFTC 감독의 ‘암호자산 시장’형 지정계약시장(DCM)으로 편입해 "
            "암호자산의 레버리지·마진 거래를 미국 규제권 안에서 허용하고, 온체인 금융 프로토콜 개발자에게도 합법적 운영 경로를 만드는 것입니다. "
            "다만 RIN 3038-AF80 자체는 아직 Prerule(사전규칙 단계)이고 규칙 본문이 공개되지 않았으며, 이것만으로 CFTC가 미국 현물 암호자산 시장 전체의 포괄적 감독권을 새로 얻었다고 볼 수는 없습니다."
        )
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
    if is_volatility_3x_crypto_launch(event):
        return [
            "BTC·ETH: 실제 거래가 시작되면 현물 직접매수보다 CME 선물·연계 ETP 수요와 일일 리밸런싱 수급이 더 직접적으로 늘어납니다.",
            "COIN: Volatility Shares·Cboe·CME 중심 구조라 직접 매출 연결은 약합니다. 미국 내 암호자산 투자상품군 확대라는 간접 생태계 효과로 구분합니다.",
            "수급: 첫 5거래일 AUM·거래대금·프리미엄/디스카운트와 CME 선물 미결제약정이 실제 시장 영향의 핵심 숫자입니다.",
            "실패 경로: 상품목록 등재 뒤에도 AUM·거래량이 작거나 선물 롤비용·변동성 끌림이 크면 장기 투자수요로 이어지지 않을 수 있습니다.",
        ]
    if is_sec_3x_crypto_etp_approval(event):
        return [
            "BTC·ETH: 직접 현물 매수 수요라기보다 CME 선물·연계 ETP 거래 수요를 키우는 경로입니다. 단기 거래량·변동성 확대 가능성이 더 직접적입니다.",
            "COIN: 이번 상품은 Volatility Shares·Cboe·CME 선물시장 구조라 Coinbase의 직접 상품매출 연결은 약합니다. 미국 암호자산 투자상품군 확대라는 간접 효과로 구분합니다.",
            "수급: 레버리지 상품의 일일 리밸런싱 때문에 급등·급락 구간에서 선물 수급이 증폭될 수 있습니다. 실제 영향은 출시 후 AUM·거래대금·CME 미결제약정으로 확인해야 합니다.",
            "시간표: SEC 상장규칙 승인은 완료됐지만 실제 거래개시는 별도입니다. BITH·ETHK 티커는 VS Trust S-1에서 이미 확인되며, 다음 관문은 해당 VS Trust 등록서류의 효력과 발행사 공식 출시·첫 거래입니다.",
        ]
    if is_sec_crypto_custody_2026(event):
        if stage == "final":
            return [
                "COIN: 최종규칙이 state trust company(주 신탁회사)를 허용하면 Coinbase Custody Trust Company의 규제 적합성이 더 명확해질 수 있습니다. 실제 수탁자산·기관고객 증가가 매출 확인 지표입니다.",
                "CRCL: Circle Internet Trust Company LLC도 NYDFS limited purpose trust company(제한목적 신탁회사) 인가를 보유합니다. 실제 제3자 기관 수탁 서비스 제공·매출 발생 여부는 별도 확인해야 합니다.",
                "BTC·ETH: 최종규칙의 적용 자산 범위에 따라 기관의 직접 보유·수탁 경로가 달라집니다. 자금 유입은 실제 펀드 보유량으로 확인해야 합니다.",
                "시간표: 시행일·전환기간·준수기한과 기관별 실제 수탁 개시를 추적합니다.",
            ]
        return [
            "COIN: Coinbase Custody Trust Company는 뉴욕주 limited purpose trust company(제한목적 신탁회사)라 최종 규칙의 state trust company 수탁 경로와 연결될 가능성이 있습니다. 다만 self-custody(자체 수탁) 허용은 외부 수탁 수요를 일부 상쇄할 수 있습니다.",
            "CRCL: Circle Internet Trust Company LLC도 NYDFS limited purpose trust company(제한목적 신탁회사) 인가를 보유해 제도상 연결 가능성이 있습니다. 다만 제3자 기관자산 수탁 서비스의 실제 제공·매출 연결은 아직 공식 확인이 필요합니다.",
            "BTC·ETH: 이번 규칙이 모든 암호자산에 자동 적용되는 것은 아니므로 ‘BTC·ETH 기관자금 유입 확정’으로 해석하면 안 됩니다. 실제 적용 범위와 최종 문구를 확인해야 합니다.",
            "시간표: Federal Register 게재 → 60일 의견수렴 → 수정·Final Rule(최종규칙) 채택 여부를 확인합니다.",
        ]
    if "3038-af80" in signal or "regulation crypto asset transactions and regulation crypto asset markets" in signal:
        return [
            "돈 버는 능력: 지금 당장 매출이 바뀌는 단계는 아닙니다. 실제 수혜 여부는 향후 문안이 Coinbase 같은 미국 거래소의 파생상품·무기한 선물(perpetual)·레버리지·마진 거래와 등록 경로를 얼마나 넓히는지에 달려 있습니다. Circle은 USDC가 담보·결제 자산으로 명시될 때 직접 연결됩니다.",
            "할인율: CLARITY 부결에도 CFTC가 별도 행정 규칙 경로를 가동했다는 점은 ‘아무 규칙도 없는 공백’ 위험을 낮추지만, 세부 문안이 아직 없어 규제가 완화될지 새 준수비용이 생길지는 미확정입니다.",
            "수급: COIN·BTC·ETH·UNI 등이 반응할 수 있어도 OIRA 접수 하나만으로 가격 원인을 단정하지 않습니다. 실제 규칙 적용 범위와 같은 시간대 금리·달러·Nasdaq을 같이 봅니다.",
            "시간표: OIRA Pending Review(검토 중) → 검토 종료 → CFTC 공개 문안 → Proposed Rule(제안규칙) 여부 순으로 확인합니다. 현재는 Prerule(사전규칙 단계)이고 Legal Deadline(법정 처리기한)도 없어 시행 시점은 아직 없습니다.",
        ]
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
    if is_volatility_3x_crypto_launch(event):
        return (
            "BITH·ETHK가 발행사 공식 상품목록에 실제 등재되면 SEC 상장규칙 승인에서 상품 출시 단계로 진전한 것으로, "
            "BTC·ETH 현물수요보다 CME 선물·일일 리밸런싱 수급 영향이 직접적이며 첫 5거래일 AUM·거래대금이 재평가 기준입니다."
        )
    if is_sec_3x_crypto_etp_approval(event):
        return (
            "SEC 34-106577은 VS Trust의 BITH·ETHK가 CME 선물의 하루 수익률을 3배 추종하도록 Cboe BZX에 상장될 수 있게 한 규칙 승인입니다. "
            "현물 BTC·ETH 3배 보유 승인이 아니며, 티커는 이미 확인됐고 실제 거래개시는 VS Trust 등록서류 효력과 발행사 출시 확인이 다음 관문입니다."
        )
    if is_sec_crypto_custody_2026(event):
        if stage == "final":
            return (
                "SEC 암호자산 수탁 규칙이 최종 확정되면 COIN·CRCL의 신탁회사 수탁 경로와 기관의 직접 수탁 선택지가 실제 제도권 규칙으로 바뀐 것이므로, "
                "이후 핵심은 시행일·적용 자산·기관 수탁자산 증가와 실제 수탁 매출입니다."
            )
        return (
            "SEC의 S7-2026-35는 CLARITY 법안 자체 변경이 아니라 별도 행정규칙 경로에서 기관의 암호자산 수탁 규칙을 넓히려는 제안입니다. "
            "COIN에는 state trust company 수탁 경로가 기회가 될 수 있지만 self-custody(자체 수탁)가 외부 수탁 수요를 일부 상쇄할 수 있고, "
            "CRCL도 Circle New York Trust를 통해 제도상 연결 가능성이 있으나 실제 제3자 수탁 매출은 미확정이며, BTC·ETH는 적용 범위가 자산의 법적 성격에 따라 달라집니다."
        )
    if "3038-af80" in signal or "regulation crypto asset transactions and regulation crypto asset markets" in signal:
        return "CFTC RIN 3038-AF80은 CLARITY 부결 뒤 의회 입법과 별개인 행정 규칙 경로가 실제 백악관 OIRA 검토에 들어갔다는 시간표 변화지만, 현재는 Pending Review(검토 중)·Prerule(사전규칙 단계)이고 규칙 본문도 비공개라 COIN·CRCL의 돈 버는 능력이 즉시 바뀐 단계는 아니며, 다음 핵심은 OIRA 검토 종료와 CFTC의 공개 문안입니다."
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
        f"사건 유형: {html.escape(koreanize_regulatory_terms(clean(event.get('event_type',''))))}",
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
