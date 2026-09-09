#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import urllib.parse
from pathlib import Path

import requests

ALERT = Path("out/pjm_data_center_policy_alert.txt")
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}

# Frequently recurring PJM headlines are translated deterministically first.
# This avoids translation drift in the most important policy alerts.
KNOWN_TRANSLATIONS = {
    "FERC fails to shield PJM consumers from data center transmission costs: ratepayer advocates":
        "소비자단체 “FERC, PJM 데이터센터 송전비용으로부터 소비자 보호에 실패”",
    "PJM files backstop auction plan at FERC to meet capacity shortfall":
        "PJM, 용량 부족 해소를 위한 백스톱 경매 계획을 FERC에 제출",
    "FirstEnergy opposes key part of PJM data center backstop procurement plan":
        "FirstEnergy, PJM 데이터센터 백스톱 조달안의 핵심 조항에 반대",
    "Large loads face reliability requirements under MISO proposal":
        "MISO 제안에 따라 대형부하에 신뢰도 요건 적용",
    "PJM stakeholders advance data center backstop procurement plan":
        "PJM 이해관계자, 데이터센터 백스톱 조달안 진전",
    "PJM Plans to Release Reliability Backstop Design in April":
        "PJM, 4월 신뢰도 백스톱 설계안 공개 계획",
    "PJM Stakeholders Endorse 1 Backstop Procurement Proposal, Reject ‘Connect and Manage’":
        "PJM 이해관계자, 백스톱 조달안 1건 승인·선접속 후관리안 부결",
    "State Advocates in PJM Ask FERC to Squelch Reliability Backstop Plan":
        "PJM 지역 주정부 소비자 옹호단체, FERC에 신뢰도 백스톱 계획 중단 요청",
    "PJM Board Directs Action on Resource Adequacy, Affordability and Large Loads":
        "PJM 이사회, 자원 적정성·전력비 부담·대형부하 대응 조치 지시",
    "PJM Proposes Framework To Connect Data Centers Without Compromising Reliability, Affordability":
        "PJM, 신뢰도와 전력비 부담을 훼손하지 않는 데이터센터 접속 체계 제안",
    "PJM to Create Large Load Registry, Proposes to Hold Backstop Auction in Oct.":
        "PJM, 대형부하 등록부 구축·10월 백스톱 경매 개최 제안",
    "PJM Reliability Backstop Proposal Outlines Steps To Secure New Supply and Maintain Reliability":
        "PJM, 신규 전원 확보·신뢰도 유지를 위한 백스톱 조달 절차 제시",
}

SOURCE_SUFFIX_RE = re.compile(
    r"\s+-\s+(?:utilitydive\.com|rtoinsider\.com|reuters\.com|energy-storage\.news|publicpower\.org|PJM Inside Lines)\s*$",
    re.I,
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_source(source: str) -> str:
    low = source.lower().strip()
    if "utilitydive" in low or "utility dive" in low:
        return "Utility Dive"
    if "rtoinsider" in low or "rto insider" in low:
        return "RTO Insider"
    if "reuters" in low:
        return "Reuters"
    if "energy-storage" in low:
        return "Energy-Storage.News"
    if "publicpower" in low or "public power" in low:
        return "Public Power"
    if "pjm" in low:
        return "PJM"
    if "federal register" in low:
        return "Federal Register"
    return source


def strip_source_suffix(title: str) -> str:
    return SOURCE_SUFFIX_RE.sub("", html.unescape(normalize(title))).strip()


def has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def translate_google(text: str) -> str | None:
    try:
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "ko",
            "dt": "t",
            "q": text,
        }
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        translated = "".join(
            seg[0] for seg in (data[0] or [])
            if isinstance(seg, list) and seg and isinstance(seg[0], str)
        )
        translated = normalize(translated)
        return translated if has_korean(translated) else None
    except Exception:
        return None


def translate_mymemory(text: str) -> str | None:
    try:
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "en|ko"},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        translated = normalize((r.json().get("responseData") or {}).get("translatedText") or "")
        return translated if has_korean(translated) else None
    except Exception:
        return None


def classify(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("consumer", "ratepayer", "transmission", "affordability", "cost allocation", "costs")):
        return "비용부담·송전망"
    if any(k in low for k in ("large load", "registry", "iras", "connect and manage", "connect data center", "connect data centre")):
        return "대형부하 접속·등록"
    if any(k in low for k in ("elcc", "capacity credit", "effective load carrying")):
        return "ELCC·용량인정"
    if any(k in low for k in ("backstop", "rbp", "auction", "procurement", "reliability")):
        return "RBP 조달·FERC 심사"
    return "기타 정책 변화"


def fallback_korean(theme: str) -> str:
    return {
        "비용부담·송전망": "데이터센터 비용부담·송전망 관련 신규 자료",
        "대형부하 접속·등록": "대형부하 접속·등록 관련 신규 자료",
        "ELCC·용량인정": "ELCC·용량인정 관련 신규 자료",
        "RBP 조달·FERC 심사": "RBP 조달·FERC 심사 관련 신규 자료",
    }.get(theme, "PJM 데이터센터 전력정책 관련 신규 자료")


def translate_title(title: str, theme: str) -> str:
    clean = strip_source_suffix(title)
    if has_korean(clean):
        return clean

    for en, ko in KNOWN_TRANSLATIONS.items():
        if clean.casefold() == en.casefold():
            return ko

    translated = translate_google(clean) or translate_mymemory(clean)
    if translated:
        # Normalize recurring technical descriptions while preserving identifiers.
        replacements = {
            "데이터 센터": "데이터센터",
            "백 스톱": "백스톱",
            "송전 비용": "송전비용",
            "대규모 부하": "대형부하",
        }
        for old, new in replacements.items():
            translated = translated.replace(old, new)
        return translated

    # English headlines are never emitted untranslated. If both translation
    # services fail, emit a Korean topic label while preserving the clickable URL.
    return fallback_korean(theme)


def main() -> None:
    if not ALERT.exists():
        return
    text = ALERT.read_text(encoding="utf-8").strip()
    if not text:
        return

    lines = text.splitlines()
    try:
        start = lines.index("<b>🆕 신규 확인</b>")
    except ValueError:
        return

    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i] == "<b>📊 투자 해석</b>"),
        len(lines),
    )
    section = lines[start + 1:end]

    summary = next((ln for ln in section if ln.startswith("• 새 자료 ")), None)
    source_rows = [ln for ln in section if "<a href=" in ln and ("[공식]" in ln or "[보도]" in ln)]
    if not source_rows:
        return

    row_re = re.compile(
        r'^• <b>\[(?P<badge>공식|보도)\] (?P<source>.*?)</b> · (?P<title>.*?)\s+<a href="(?P<url>[^"]+)">원문</a>$'
    )

    parsed: list[dict[str, str]] = []
    for row in source_rows:
        m = row_re.match(row)
        if not m:
            continue
        original_title = html.unescape(m.group("title").strip())
        parsed.append({
            "badge": m.group("badge"),
            "source": clean_source(html.unescape(m.group("source"))),
            "title": original_title,
            "url": html.unescape(m.group("url")),
            "theme": classify(original_title),
        })

    if not parsed:
        return

    chosen: list[dict[str, str]] = []
    used_themes: set[str] = set()
    for item in parsed:
        theme = item["theme"]
        if theme in used_themes:
            continue
        used_themes.add(theme)
        chosen.append(item)
        if len(chosen) >= 4:
            break

    rebuilt = ["<b>🆕 핵심 신규 변화</b>"]
    if summary:
        rebuilt.append(summary)

    for item in chosen:
        theme = item["theme"]
        badge = item["badge"]
        source = item["source"]
        title_ko = translate_title(item["title"], theme)
        url = html.escape(item["url"], quote=True)
        rebuilt.append(f"• <b>{html.escape(theme)}</b> · [{badge}] {html.escape(source)}")
        rebuilt.append(f"  ↳ 🔗 <a href=\"{url}\">{html.escape(title_ko)}</a>")

    total_match = re.search(r"새 자료 <b>(\d+)건</b>", summary or "")
    total = int(total_match.group(1)) if total_match else len(source_rows)
    hidden = max(0, total - len(chosen))
    if hidden:
        rebuilt.append(f"• <i>나머지 {hidden}건은 중복·추적 상태에 저장해 다음 변화 판정에 반영합니다.</i>")

    # Keep a blank line before the next major section.
    new_lines = lines[:start] + rebuilt + [""] + lines[end:]
    output = "\n".join(new_lines).strip() + "\n"
    output = output.replace("FERC Decisions", "FERC 결정·공고")
    ALERT.write_text(output, encoding="utf-8")
    print(f"pjm_alert_grouped themes={len(chosen)} hidden={hidden} korean_links={len(chosen)}")


if __name__ == "__main__":
    main()
