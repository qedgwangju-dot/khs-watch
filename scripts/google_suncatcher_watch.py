#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

GOOGLE_FACTS_URL = "https://blog.google/innovation-and-ai/models-and-research/google-research/google-project-suncatcher-facts/"
GOOGLE_ORIGINAL_URL = "https://blog.google/innovation-and-ai/technology/research/google-project-suncatcher/"
PLANET_URL = "https://www.planet.com/pulse/planet-to-build-and-operate-advanced-space-platform-for-google-s-project-suncatcher-moonshot/"
ARS_URL = "https://arstechnica.com/google/2026/09/googles-first-suncatcher-orbital-data-center-test-launches-october-1/"
NEXTSPACEFLIGHT_URL = "https://www.nextspaceflight.com/launches/details/7611/"
NEWS_RSS = (
    "https://news.google.com/rss/search?q="
    + quote_plus('"Project Suncatcher" OR "Suncatcher" Google TPU space')
    + "&hl=en-US&gl=US&ceid=US:en"
)

STATE = Path("data/google_suncatcher_watch_state.json")
OUT = Path("out")
ALERT = OUT / "google_suncatcher_alert.txt"
PENDING = OUT / "google_suncatcher_pending_state.json"
STATUS = OUT / "google_suncatcher_status.md"
ERRORS = OUT / "google_suncatcher_errors.log"

HEADERS = {
    "User-Agent": "Mozilla/5.0 KHS-Google-Suncatcher-Watch/1.0",
    "Accept-Language": "en-US,en;q=0.9",
}

TRIGGER_TERMS = (
    "launch", "launched", "liftoff", "lifted off", "orbit", "orbital", "deployed",
    "deployment", "success", "successful", "failed", "failure", "scrub", "delay",
    "temperature", "thermal", "cooling", "radiator", "runtime", "run time",
    "minutes", "continuous", "error", "error rate", "bit flip", "radiation",
    "single event", "upset", "gemini", "tpu", "tensor processing unit",
    "power", "watt", "kilowatt",
)
METRIC_TERMS = (
    "temperature", "thermal", "cooling", "radiator", "runtime", "run time",
    "minutes", "continuous", "error", "error rate", "bit flip", "radiation",
    "single event", "upset", "gemini", "tpu", "tensor processing unit",
    "power", "watt", "kilowatt",
)
LAUNCH_TERMS = (
    "launch", "launched", "liftoff", "lifted off", "orbit", "deployed", "deployment",
    "success", "successful", "failed", "failure", "scrub", "delay",
)
RELIABLE_NEWS_SOURCES = {
    "Ars Technica", "Reuters", "The Verge", "TechCrunch", "SpaceNews",
    "Google", "blog.google", "SpaceX", "Planet", "Planet Labs", "CNBC",
    "The New York Times", "Engadget",
}


def fetch(url: str, timeout: int = 30) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def page_text(url: str) -> str:
    html = fetch(url).text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return clean(soup.get_text(" ", strip=True))


def relevant_sentences(text: str, limit: int = 80) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", clean(text))
    out = []
    for sentence in sentences:
        low = sentence.lower()
        if "suncatcher" in low or any(term in low for term in TRIGGER_TERMS):
            if len(sentence) >= 20:
                out.append(sentence[:1000])
        if len(out) >= limit:
            break
    return out


def relevant_hash(sentences: list[str]) -> str:
    normalized = "\n".join(sentences)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_numeric_metrics(sentences: list[str]) -> dict:
    text = " ".join(sentences)
    metrics: dict[str, list[str]] = {}

    patterns = {
        "온도": r"(?i)(?:temperature|thermal)[^.;]{0,90}?(-?\d+(?:\.\d+)?)\s*°?\s*(?:C|Celsius|F|Fahrenheit)",
        "연속가동": r"(?i)(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|hours?|hrs?)\b[^.;]{0,80}?(?:run|runtime|continuous|operate|operation)",
        "오류율": r"(?i)(?:error rate|errors?|bit flips?|upsets?)[^.;]{0,90}?(\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?(?:e[-+]?\d+)?)",
        "방사선": r"(?i)(\d+(?:\.\d+)?)\s*(?:rad|krad|Gy|gray)\b",
        "전력": r"(?i)(\d+(?:\.\d+)?)\s*(?:kW|W|watts?|kilowatts?)\b",
        "처리량": r"(?i)(\d+(?:\.\d+)?)\s*(?:Gbps|Tbps|tokens?/?s|tokens? per second)\b",
    }
    for label, pattern in patterns.items():
        found = []
        for m in re.finditer(pattern, text):
            snippet = clean(text[max(0, m.start()-80): min(len(text), m.end()+120)])
            if snippet not in found:
                found.append(snippet)
            if len(found) >= 6:
                break
        if found:
            metrics[label] = found
    return metrics


def launch_signal(sentences: list[str]) -> list[str]:
    out = []
    for sentence in sentences:
        low = sentence.lower()
        if any(term in low for term in LAUNCH_TERMS) and (
            "suncatcher" in low or "satellite" in low or "transporter-18" in low or "transporter 18" in low
        ):
            out.append(sentence)
    return out[:12]


def parse_nextspaceflight() -> dict:
    text = page_text(NEXTSPACEFLIGHT_URL)
    time_match = re.search(
        r"Liftoff Time \(GMT\)\s*(\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)\s*"
        r"([A-Za-z]+day\s+[A-Za-z]+\s+\d{1,2},\s+20\d{2})",
        text,
        flags=re.I,
    )
    if not time_match:
        time_match = re.search(
            r"(\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)\s*"
            r"([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
            text,
            flags=re.I,
        )
    status = None
    for key in ("Launch Status", "Planned Liftoff", "To Be Confirmed", "Success", "Failure", "Scrubbed", "Delayed"):
        if key.lower() in text.lower():
            status = key
            break
    return {
        "url": NEXTSPACEFLIGHT_URL,
        "status": status or "확인 불가",
        "liftoff_gmt": f"{time_match.group(2)} {time_match.group(1)} GMT" if time_match else None,
    }


def parse_news() -> list[dict]:
    xml = fetch(NEWS_RSS, timeout=25).content
    root = ET.fromstring(xml)
    rows = []
    for item in root.findall("./channel/item")[:30]:
        title = clean(item.findtext("title") or "")
        link = clean(item.findtext("link") or "")
        guid = clean(item.findtext("guid") or link or title)
        pub = clean(item.findtext("pubDate") or "")
        source_node = item.find("source")
        source = clean(source_node.text if source_node is not None else "")
        low = title.lower()
        if not ("suncatcher" in low or ("google" in low and ("orbital" in low or "space" in low) and "data center" in low)):
            continue
        rows.append({
            "id": guid,
            "title": title,
            "link": link,
            "source": source,
            "published": pub,
        })
    return rows


def parse_pub_ts(value: str) -> float:
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return dt.timestamp()
    except Exception:
        return 0.0


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def korean_status(value: str | None) -> str:
    if not value:
        return "확인 불가"
    low = value.lower()
    if "success" in low:
        return "발사 성공"
    if "failure" in low or "failed" in low:
        return "발사 실패"
    if "scrub" in low:
        return "발사 취소·재시도 대기"
    if "delay" in low:
        return "발사 지연"
    if "planned" in low:
        return "발사 예정"
    if "confirm" in low:
        return "시간 미확정"
    return value


def koreanize_title(title: str) -> str:
    repl = [
        ("Google", "구글"),
        ("Project Suncatcher", "프로젝트 선캐처"),
        ("Suncatcher", "선캐처"),
        ("orbital data center", "궤도 데이터센터"),
        ("orbital data centers", "궤도 데이터센터"),
        ("data center", "데이터센터"),
        ("data centers", "데이터센터"),
        ("TPUs", "TPU"),
        ("Transporter-18", "트랜스포터-18"),
    ]
    out = title
    for src, dst in repl:
        out = out.replace(src, dst)
    return out


def compact_metric_summary(metrics: dict) -> list[str]:
    lines = []
    for label in ("온도", "연속가동", "오류율", "방사선", "전력", "처리량"):
        vals = metrics.get(label) or []
        if vals:
            # 원문 문장을 그대로 길게 복사하지 않고 숫자가 담긴 짧은 문맥만 한국어 라벨로 표시한다.
            numeric = []
            for value in vals[:2]:
                numbers = re.findall(r"-?\d+(?:\.\d+)?\s*(?:%|°?\s*[CF]|rad|krad|Gy|kW|W|Gbps|Tbps|minutes?|mins?|hours?|hrs?)?", value, flags=re.I)
                picked = [clean(n) for n in numbers if clean(n)]
                if picked:
                    numeric.extend(picked[:2])
            if numeric:
                lines.append(f"• {label}: " + " · ".join(dict.fromkeys(numeric)))
    return lines


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (ALERT, PENDING, STATUS, ERRORS):
        p.unlink(missing_ok=True)

    old = load_state()
    errors: list[str] = []
    sources = {}
    source_defs = {
        "구글 공식": GOOGLE_FACTS_URL,
        "구글 최초 발표": GOOGLE_ORIGINAL_URL,
        "플래닛 공식": PLANET_URL,
        "아스테크니카": ARS_URL,
    }

    for name, url in source_defs.items():
        try:
            text = page_text(url)
            sentences = relevant_sentences(text)
            sources[name] = {
                "url": url,
                "hash": relevant_hash(sentences),
                "sentences": sentences,
                "metrics": extract_numeric_metrics(sentences),
                "launch_signal": launch_signal(sentences),
            }
        except Exception as exc:
            errors.append(f"{name} 조회 실패: {type(exc).__name__}: {exc}")
            if old.get("sources", {}).get(name):
                sources[name] = old["sources"][name]

    schedule = None
    try:
        schedule = parse_nextspaceflight()
    except Exception as exc:
        errors.append(f"발사 일정 조회 실패: {type(exc).__name__}: {exc}")
        schedule = old.get("schedule")

    news = []
    try:
        news = parse_news()
    except Exception as exc:
        errors.append(f"뉴스 감시 조회 실패: {type(exc).__name__}: {exc}")
        news = old.get("news", [])

    first = not bool(old)
    old_sources = old.get("sources", {})
    changed_sources = []
    metric_changes = []
    launch_changes = []

    for name, current in sources.items():
        previous = old_sources.get(name) or {}
        if previous and previous.get("hash") != current.get("hash"):
            changed_sources.append(name)
            if previous.get("metrics") != current.get("metrics"):
                metric_changes.append(name)
            if previous.get("launch_signal") != current.get("launch_signal"):
                launch_changes.append(name)

    schedule_changed = False
    if old.get("schedule") and schedule:
        schedule_changed = (
            old["schedule"].get("status") != schedule.get("status")
            or old["schedule"].get("liftoff_gmt") != schedule.get("liftoff_gmt")
        )

    old_seen = set(old.get("seen_news_ids", []))
    fresh_news = [item for item in news if item.get("id") not in old_seen]
    fresh_news.sort(key=lambda x: parse_pub_ts(x.get("published", "")), reverse=True)

    meaningful_news = []
    for item in fresh_news:
        source = item.get("source", "")
        title_low = item.get("title", "").lower()
        if source and source not in RELIABLE_NEWS_SOURCES:
            # 신뢰 출처가 아닌 신규 기사만으로는 알림을 만들지 않는다.
            continue
        if any(term in title_low for term in LAUNCH_TERMS + METRIC_TERMS):
            meaningful_news.append(item)

    should_alert = first or bool(metric_changes or launch_changes or schedule_changed or meaningful_news)

    state = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "schedule": schedule,
        "news": news[:30],
        "seen_news_ids": list(dict.fromkeys([item.get("id") for item in news if item.get("id")]))[:80],
        "watch": "Google Project Suncatcher orbital TPU launch and in-orbit metrics",
    }
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if should_alert:
        title = "✅ 구글 선캐처 궤도 데이터센터 감시 연결 완료" if first else "🚨 구글 선캐처 궤도 데이터센터 핵심 변화"
        lines = [
            title,
            "",
            "▶ 감시 기준",
            "• 발사 성공·실패·지연·일정 변경",
            "• TPU 정상 부팅 및 Gemini 실제 실행 여부",
            "• TPU 온도·방열·냉각 회복시간",
            "• 연속가동시간",
            "• 오류율·비트플립·방사선 이상",
            "• 실제 전력·처리량이 공개될 때만 의미 있는 변화로 알림",
        ]

        if schedule:
            lines += [
                "",
                "■ 발사 상태",
                f"• 현재 판정: {korean_status(schedule.get('status'))}",
                f"• 현재 예정시각: {schedule.get('liftoff_gmt') or '정확한 시각 미확정'}",
                "• 발사 일정은 기상·기술·발사장 상황에 따라 바뀔 수 있어 공식 발표를 우선합니다.",
                f"원문: {schedule['url']}",
            ]

        if first:
            lines += [
                "",
                "■ 현재 기준선",
                "• 시험위성: 냉장고 크기급 MVP",
                "• 연산장치: 구글 TPU 4개",
                "• 태양광 전력: 약 1킬로와트",
                "• 현재 알려진 연속가동 한계: 약 15분 후 냉각 필요",
                "• 목적: 상용화가 아니라 발사충격·방사선·열관리 실전 검증",
                "• 2027년 후속 단계: 플래닛과 2위성 고대역폭 광링크 시험",
            ]

        if metric_changes:
            lines += ["", "■ 새 실측 수치 공개"]
            merged = {}
            for name in metric_changes:
                for label, vals in (sources[name].get("metrics") or {}).items():
                    merged.setdefault(label, []).extend(vals)
            metric_lines = compact_metric_summary(merged)
            lines += metric_lines or ["• 수치가 포함된 공식 문맥 변화 감지 — 원문 재확인 필요"]

        if launch_changes:
            lines += ["", "■ 발사·궤도 상태 변화"]
            for name in launch_changes:
                lines.append(f"• {name}: 발사 또는 궤도 상태 관련 문구가 변경됐습니다.")

        if meaningful_news:
            lines += ["", "■ 새 확인 기사"]
            for item in meaningful_news[:4]:
                source = item.get("source") or "출처 확인 필요"
                lines.append(f"• {koreanize_title(item.get('title',''))}")
                lines.append(f"  출처: {source}")
                if item.get("link"):
                    lines.append(f"원문: {item['link']}")

        lines += [
            "",
            "■ 판정 규칙",
            "• 발사만 성공하고 TPU 실측값이 없으면 '발사 검증 통과' 단계로만 봅니다.",
            "• 15분보다 연속가동시간이 늘고 온도·냉각·오류율이 안정적이면 기술 재평가 신호입니다.",
            "• 과열·잦은 재부팅·비트플립·방사선 오류가 확인되면 실패 경로를 우선 경고합니다.",
            "• 단순 기사 재탕이나 기존 수치 반복은 알림하지 않습니다.",
            "",
            f"원문: {GOOGLE_FACTS_URL}",
        ]

        ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if errors:
        ERRORS.write_text("\n".join(errors) + "\n", encoding="utf-8")

    status = [
        "# 구글 선캐처 궤도 데이터센터 감시",
        "",
        f"- 최초 실행: {'예' if first else '아니오'}",
        f"- 발사·궤도 문구 변화: {', '.join(launch_changes) if launch_changes else '없음'}",
        f"- 실측 수치 변화: {', '.join(metric_changes) if metric_changes else '없음'}",
        f"- 발사 일정 변화: {'예' if schedule_changed else '아니오'}",
        f"- 신규 신뢰 기사: {len(meaningful_news)}건",
        f"- 텔레그램 알림 파일: {'생성' if ALERT.exists() else '없음'}",
        f"- 조회 오류: {len(errors)}건",
    ]
    if schedule:
        status.append(f"- 현재 발사 상태: {korean_status(schedule.get('status'))} · {schedule.get('liftoff_gmt') or '시각 미확정'}")
    STATUS.write_text("\n".join(status) + "\n", encoding="utf-8")

    print(STATUS.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
