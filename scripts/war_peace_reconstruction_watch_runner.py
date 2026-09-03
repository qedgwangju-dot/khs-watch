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
    # 공개 번역 메모리 API를 2차 백업으로 사용한다. 영문 속보 제목 길이만 전달한다.
    q = urllib.parse.quote(text[:450])
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en%7Cko"
    data = _req_json(url)
    out = _clean((data.get("responseData") or {}).get("translatedText") or "")
    return out


def _emergency_translate(text):
    # 외부 번역 서비스가 동시에 실패할 때도 핵심 전쟁·협상 속보가 영문으로 노출되지 않도록 하는 최후 백업.
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
    # 남은 일반 영문 토큰은 사용자에게 노출하지 않는다. 숫자·기호와 번역된 핵심어는 유지한다.
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
