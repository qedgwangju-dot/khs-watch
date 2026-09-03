#!/usr/bin/env python3
import argparse
import html
import importlib.util
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "war_peace_reconstruction_watch.py"

spec = importlib.util.spec_from_file_location("war_watch", TARGET)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

# 제목만으로는 놓칠 수 있는 기사 본문형 신호를 별도 검색한다.
# 예: WSJ 제목은 병력배치 기사여도 본문에는 '종전 선언 검토·중간선거 부담·경제압박 전략'이 들어갈 수 있다.
DEEP_SIGNAL_RULES = [
    {
        "query": 'site:wsj.com Iran Trump ("declare the war over" OR "end the war" OR "ending the conflict" OR "senior advisers") when:12h',
        "tags": ["종전·협상", "전략변화"],
        "signals": [
            "트럼프, 고위 보좌관들과 이란 전쟁 종료 선언 여부를 비공개 논의",
        ],
    },
    {
        "query": 'site:wsj.com Iran Trump advisers midterms escalation Republicans election when:12h',
        "tags": ["정치일정", "종전·협상"],
        "signals": [
            "보좌진, 이란전이 최근 제한 공습을 넘어 확대되면 공화당의 11월 중간선거에 악영향을 줄 수 있다고 경고",
        ],
    },
    {
        "query": 'site:wsj.com Iran Trump "economic pressure" nuclear regime collapse when:12h',
        "tags": ["전략변화", "제재·압박"],
        "signals": [
            "트럼프 행정부, 대규모 군사 확전 대신 경제 압박으로 이란의 핵 프로그램을 억제하는 전략을 병행",
        ],
    },
    {
        "query": 'site:reuters.com Iran Trump aides midterms quiet war economic pressure escalation when:12h',
        "tags": ["정치일정", "종전·협상", "제재·압박"],
        "signals": [
            "트럼프 참모진, 중간선거 전 이란전 확전을 억제하고 경제 압박을 강화하는 방안을 선호",
        ],
    },
]

# 본문형 신호 검색을 일반 속보 검색보다 먼저 실행해 동일 기사 중복 시에도 심층 신호가 보존되도록 한다.
watch.QUERIES = [r["query"] for r in DEEP_SIGNAL_RULES] + list(watch.QUERIES)
_DEEP_BY_QUERY = {r["query"]: r for r in DEEP_SIGNAL_RULES}
_signal_rows = {}


def _req_json(url, timeout=12):
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _has_korean(text):
    return bool(re.search(r"[가-힣]", text or ""))


def _clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _google_translate(text, host):
    url = (
        f"https://{host}/translate_a/single?client=gtx&sl=auto&tl=ko&dt=t&q="
        + urllib.parse.quote(text)
    )
    data = _req_json(url)
    out = _clean("".join(part[0] for part in data[0] if part and part[0]))
    return out


def _mymemory_translate(text):
    q = urllib.parse.quote(text[:450])
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en%7Cko"
    data = _req_json(url)
    out = _clean((data.get("responseData") or {}).get("translatedText") or "")
    return out


def _emergency_translate(text):
    t = f" {text.strip()} "
    phrases = [
        (r"\bDonald Trump\b", "도널드 트럼프"),
        (r"\bTrump\b", "트럼프"),
        (r"\bVladimir Putin\b", "블라디미르 푸틴"),
        (r"\bPutin\b", "푸틴"),
        (r"\bVolodymyr Zelenskyy?\b", "볼로디미르 젤렌스키"),
        (r"\bZelenskyy?\b", "젤렌스키"),
        (r"\bIran\b", "이란"),
        (r"\bUkraine\b", "우크라이나"),
        (r"\bRussia\b", "러시아"),
        (r"\bIsrael\b", "이스라엘"),
        (r"\bLebanon\b", "레바논"),
        (r"\bStrait of Hormuz\b", "호르무즈 해협"),
        (r"\bHormuz\b", "호르무즈"),
        (r"\bUnited States\b|\bU\.S\.\b|\bUS\b", "미국"),
        (r"\bWhite House\b", "백악관"),
        (r"\bPentagon\b", "미 국방부"),
        (r"\bceasefire\b", "휴전"),
        (r"\bpeace talks?\b", "평화협상"),
        (r"\bpeace deal\b|\bpeace agreement\b", "평화합의"),
        (r"\bnegotiations?\b", "협상"),
        (r"\btalks\b", "회담"),
        (r"\bsummit\b", "정상회담"),
        (r"\btrilateral\b", "3자"),
        (r"\bend(?:ing)? the war\b|\bend war\b", "전쟁 종료"),
        (r"\bwar\b", "전쟁"),
        (r"\bstrike(?:s)?\b|\bairstrike(?:s)?\b", "공습"),
        (r"\battack(?:s)?\b", "공격"),
        (r"\bmissile(?:s)?\b", "미사일"),
        (r"\bdrone(?:s)?\b", "드론"),
        (r"\bblockade\b", "봉쇄"),
        (r"\bwithdrawal\b|\bwithdraw\b", "철수"),
        (r"\bsanctions?\b", "제재"),
        (r"\breconstruction\b|\brebuilding\b", "재건"),
        (r"\breconstruction fund\b", "재건기금"),
        (r"\binfrastructure\b", "인프라"),
        (r"\bsenior advisers?\b", "고위 보좌관들"),
        (r"\bmidterms?\b", "중간선거"),
        (r"\beconomic pressure\b", "경제 압박"),
        (r"\bnuclear program\b", "핵 프로그램"),
        (r"\bregime collapse\b", "정권 붕괴"),
        (r"\bdiscuss(?:es|ed|ing)?\b", "논의"),
        (r"\bwith\b", "와"),
        (r"\bnew\b", "새로운"),
        (r"\bpossible\b|\bpossibility\b", "가능성"),
        (r"\bready\b", "준비"),
        (r"\bcontinue(?:s|d)?\b", "지속"),
        (r"\bagree(?:s|d)?\b|\bagreement\b", "합의"),
        (r"\bmeeting\b", "회담"),
        (r"\bofficials?\b", "당국자"),
        (r"\bgovernment\b", "정부"),
        (r"\bmilitary\b", "군"),
    ]
    for pat, rep in phrases:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)
    t = re.sub(r"\b[A-Za-z][A-Za-z'’-]*\b", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—:;,.")
    if _has_korean(t) and len(t) >= 8:
        return t
    return "해외 속보 번역 지연 — 원문 링크 우선 확인"


def translate_ko_robust(text):
    text = _clean(text)
    if not text or _has_korean(text):
        return text
    errors = []
    for host in ("translate.googleapis.com", "translate.google.com"):
        for attempt in range(2):
            try:
                out = _google_translate(text, host)
                if _has_korean(out):
                    return out
            except Exception as e:
                errors.append(f"{host}:{type(e).__name__}")
                time.sleep(0.4 * (attempt + 1))
    try:
        out = _mymemory_translate(text)
        if _has_korean(out):
            return out
    except Exception as e:
        errors.append(f"mymemory:{type(e).__name__}")
    out = _emergency_translate(text)
    print("translation_fallback=true backends=" + ",".join(errors))
    return out


watch.translate_ko = translate_ko_robust

# 일반 제목 검색 결과에 '어떤 본문형 검색에서 잡혔는지'를 붙인다.
_original_google_news = watch.google_news


def google_news_with_deep_signals(query):
    rows, err = _original_google_news(query)
    rule = _DEEP_BY_QUERY.get(query)
    for row in rows:
        iid = watch.item_id(row)
        bucket = _signal_rows.setdefault(iid, [])
        bucket.append(row)
        if rule:
            merged_signals = []
            merged_tags = []
            for existing in bucket:
                merged_signals.extend(existing.get("signals_ko", []))
                merged_tags.extend(existing.get("forced_tags", []))
            merged_signals.extend(rule["signals"])
            merged_tags.extend(rule["tags"])
            merged_signals = list(dict.fromkeys(merged_signals))
            merged_tags = list(dict.fromkeys(merged_tags))
            for existing in bucket:
                existing["signals_ko"] = merged_signals
                existing["forced_tags"] = merged_tags
                existing["deep_signal"] = True
    return rows, err


watch.google_news = google_news_with_deep_signals

_original_score_item = watch.score_item


def score_item_with_deep_signals(x, now):
    score, tags = _original_score_item(x, now)
    if x.get("deep_signal"):
        score += 12
        tags = sorted(set(tags + list(x.get("forced_tags", []))))
    return score, tags


watch.score_item = score_item_with_deep_signals


def build_alert_with_deep_signals(items, markets, now):
    peace = any("종전·협상" in x["tags"] for x in items)
    escalation = any("확전" in x["tags"] for x in items)
    rebuild = any("재건" in x["tags"] for x in items)

    lines = [
        "🚨 <b>전쟁·종전·재건 웹감시</b>",
        f"🕒 조회 {now:%Y-%m-%d %H:%M} KST",
        "",
        "⚡ <b>핵심 변화</b>",
    ]

    for idx, x in enumerate(items[:8], 1):
        tags = " · ".join(x["tags"]) or "전쟁"
        level, fresh = watch.freshness_label(x, now)
        signals = list(x.get("signals_ko", []))
        headline = signals[0] if signals else x["title_ko"]
        lines.append(f"{level} <b>{idx}. [{watch.h(watch.topic_label(x))}]</b> {watch.h(headline)}")
        if signals:
            for extra in signals[1:4]:
                lines.append(f"   • {watch.h(extra)}")
            lines.append(f"   └ {watch.h(fresh)} · 본문형 신호 · {watch.h(tags)} · {watch.h(x['source'] or '출처미상')}")
        else:
            lines.append(f"   └ {watch.h(fresh)} · {watch.h(tags)} · {watch.h(x['source'] or '출처미상')}")

    if markets:
        lines += ["", "📊 <b>시장 반응</b>"]
        for m in markets:
            lines.append(f"• {watch.h(m['name'])} <b>{m['price']:,.2f}</b> {m['arrow']} {m['pct']:+.2f}%")

    lines += ["", "🎯 <b>투자 판정</b>"]
    if peace:
        lines.append("• <b>할인율:</b> 종전·휴전 진전이면 유가·전쟁 위험프리미엄 완화 가능")
        lines.append("• <b>수급:</b> 달러·금리 안정 동반 시 나스닥·신흥국 위험선호에 우호적")
        lines.append("• <b>시간표:</b> 종전 선언·공식 휴전문·정상회담·제재 변화·병력 철수 확인")
    if any("정치일정" in x["tags"] for x in items):
        lines.append("• <b>정치일정:</b> 11월 중간선거 부담이 확전 억제 또는 종전 선언을 앞당기는지 확인")
    if any("제재·압박" in x["tags"] for x in items):
        lines.append("• <b>전략변화:</b> 군사 확전보다 제재·경제 압박으로 무게가 이동하는지 확인")
    if rebuild:
        lines.append("• <b>돈 버는 능력:</b> 재건기금 → 입찰 → 본계약 → 수주 → 매출 인식 순서 확인")
        lines.append("• <b>한국 기업:</b> 실명·계약금액·발주처 공식 확인 전에는 후보 단계")
    if escalation:
        lines += ["", "⚠️ <b>반대 신호</b>", "• 공습·미사일·봉쇄·병력 증강이 함께 감지됨 — 종전 기대와 확전 위험이 동시에 존재"]

    lines += ["", "🔎 <b>다음 확인</b>"]
    checkpoints = []
    if peace:
        checkpoints.extend(["트럼프의 종전 선언 여부", "공식 합의문·공동성명", "실제 교전 중단", "후속 정상·실무회담 일정"])
    if any("정치일정" in x["tags"] for x in items):
        checkpoints.extend(["공화당 중간선거 여론·전쟁 지지율", "추가 대규모 공습 승인 여부"])
    if rebuild:
        checkpoints.extend(["재건기금 운용주체", "한국 기업 실명", "입찰·MOU·본계약 구분"])
    if escalation:
        checkpoints.extend(["추가 공습 여부", "호르무즈 통항량·보험료"])
    for cp in list(dict.fromkeys(checkpoints))[:7]:
        lines.append(f"• {watch.h(cp)}")

    lines += ["", "🔗 <b>원문</b>"]
    for idx, x in enumerate(items[:8], 1):
        src = watch.h(x["source"] or "출처미상")
        url = watch.h(x["link"])
        lines.append(f"{idx}. {src} · <a href=\"{url}\">기사 열기</a>")

    return "\n".join(lines)[:4000] + "\n"


watch.build_alert = build_alert_with_deep_signals


def verify_alert(test_mode=False):
    if not watch.ALERT.exists():
        return
    text = watch.ALERT.read_text(encoding="utf-8")
    forbidden = [
        "영문 속보 번역이 일시적으로 지연됨",
        "Trump discusses ending the Iran war with senior advisers",
    ]
    if any(x in text for x in forbidden):
        raise RuntimeError("한국어 번역 검증 실패: 영문 또는 기존 오류 문구가 알림에 남아 있음")
    if test_mode and "트럼프" not in text:
        raise RuntimeError("한국어 번역 검증 실패: 테스트 제목에 '트럼프'가 없음")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    watch.run(test=args.telegram_test)
    verify_alert(test_mode=args.telegram_test)


if __name__ == "__main__":
    main()
