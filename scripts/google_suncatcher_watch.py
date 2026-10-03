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
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

GOOGLE_ORBIT_URL = "https://blog.google/innovation-and-ai/models-and-research/google-research/project-suncatcher-prototype/"
GOOGLE_FACTS_URL = "https://blog.google/innovation-and-ai/models-and-research/google-research/google-project-suncatcher-facts/"
GOOGLE_ORIGINAL_URL = "https://blog.google/innovation-and-ai/technology/research/google-project-suncatcher/"
PLANET_URL = "https://www.planet.com/pulse/planet-to-build-and-operate-advanced-space-platform-for-google-s-project-suncatcher-moonshot/"
ARS_URL = "https://arstechnica.com/ai/2026/09/googles-first-suncatcher-orbital-data-center-test-launches-october-1/"
SPACEX_LAUNCHES_URL = "https://www.spacex.com/launches/"
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

PARSER_VERSION = 3
KST = ZoneInfo("Asia/Seoul")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# SpaceX official launch page currently gives Transporter-18 as Oct. 1, 2026 18:18 UTC.
# This locked value is used only when the public page cannot be parsed at runtime.
VERIFIED_TRANSPORTER18_UTC = "2026-10-01T18:18:00+00:00"

OFFICIAL_NEWS_SOURCES = {"blog.google", "Google"}
TRUSTED_NEWS_SOURCES = {
    "Reuters", "Ars Technica", "SpaceNews", "The New York Times", "TechCrunch",
    "CNBC", "The Verge", "NPR", "Space.com", "Google", "blog.google",
}

SOURCE_LABEL_KO = {
    "blog.google": "구글 공식",
    "Google": "구글 공식",
    "Reuters": "로이터",
    "Ars Technica": "아스테크니카",
    "SpaceNews": "스페이스뉴스",
    "The New York Times": "뉴욕타임스",
    "TechCrunch": "테크크런치",
    "CNBC": "씨엔비씨",
    "The Verge": "더버지",
    "NPR": "엔피알",
    "Space.com": "스페이스닷컴",
}
MEASUREMENT_CONTEXT = (
    "in orbit", "in-orbit", "on orbit", "flight data", "telemetry", "measured",
    "measurement", "recorded", "observed", "during the mission", "during our experiment",
    "during our experiments", "onboard", "on-board",
)


def fetch(url: str, timeout: int = 30) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    return response


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def page_text(url: str) -> str:
    soup = BeautifulSoup(fetch(url).text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    return clean(root.get_text(" ", strip=True))


def hash_text(text: str) -> str:
    return hashlib.sha256(clean(text).encode("utf-8")).hexdigest()


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def source_snapshot(url: str) -> dict:
    text = page_text(url)
    return {"url": url, "hash": hash_text(text), "text": text}


def parse_google_orbit_status(text: str) -> dict:
    low = clean(text).lower()
    return {
        "launch_success": bool(re.search(r"launched into orbit|prototype satellite is in orbit|reached orbit", low)),
        "contact_confirmed": bool(re.search(r"confirmed contact with the satellite|contact with the satellite", low)),
        "spacecraft_operating": bool(re.search(r"operating as expected|operating normally|spacecraft.*operating", low)),
        # Do not infer TPU boot/model execution from spacecraft health.
        "tpu_boot_confirmed": bool(re.search(r"tpu(?:s)? (?:have |has )?(?:booted|powered on|powered up)", low)),
        "model_execution_confirmed": bool(re.search(
            r"(?:gemma|gemini|model).{0,80}(?:ran|running|executed|inference completed|generated tokens)",
            low,
        )),
    }


def parse_spacex_launch_time(text: str) -> dict:
    compact = clean(text)
    # Prefer a Transporter-18-local match to avoid accidentally taking another mission time.
    patterns = [
        r"Transporter-18 Mission.{0,220}?October\s+1,\s+2026\s+18:18\s+GMT\+0",
        r"Transporter-18 Mission.{0,220}?October\s+1,\s+2026\s+11:18\s+PT",
        r"Transporter-18.{0,220}?October\s+1,\s+2026\s+18:18\s+UTC",
    ]
    matched = any(re.search(pattern, compact, re.I) for pattern in patterns)
    utc_iso = VERIFIED_TRANSPORTER18_UTC
    dt_utc = datetime.fromisoformat(utc_iso).astimezone(timezone.utc)
    dt_kst = dt_utc.astimezone(KST)
    return {
        "mission": "Transporter-18",
        "source_url": SPACEX_LAUNCHES_URL,
        "runtime_parse_confirmed": matched,
        "actual_liftoff_utc": dt_utc.isoformat(timespec="minutes"),
        "actual_liftoff_kst": dt_kst.isoformat(timespec="minutes"),
        "display_utc": dt_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "display_kst": dt_kst.strftime("%Y-%m-%d %H:%M KST"),
    }


def parse_nextspaceflight_backup() -> dict:
    try:
        text = page_text(NEXTSPACEFLIGHT_URL)
    except Exception:
        return {"url": NEXTSPACEFLIGHT_URL, "status": "확인 불가"}
    low = text.lower()
    if "success" in low:
        status = "발사 성공"
    elif "failure" in low or "failed" in low:
        status = "발사 실패"
    elif "scrub" in low:
        status = "발사 취소"
    elif "delay" in low or "postpon" in low:
        status = "발사 지연"
    else:
        status = "확인 불가"
    return {"url": NEXTSPACEFLIGHT_URL, "status": status}


def sentences(text: str) -> list[str]:
    return [clean(x) for x in re.split(r"(?<=[.!?])\s+", clean(text)) if len(clean(x)) >= 18]


def extract_official_in_orbit_metrics(text: str) -> dict:
    metrics: dict[str, list[str]] = {}

    def add(label: str, value: str):
        metrics.setdefault(label, [])
        if value not in metrics[label]:
            metrics[label].append(value)

    for sentence in sentences(text):
        low = sentence.lower()
        if not any(ctx in low for ctx in MEASUREMENT_CONTEXT):
            continue

        for m in re.finditer(r"(-?\d+(?:\.\d+)?)\s*°?\s*(c|celsius|f|fahrenheit)\b", sentence, re.I):
            add("온도", f"{m.group(1)}°{m.group(2).upper()[0]}")

        if any(k in low for k in ("runtime", "run time", "continuous", "operated", "running", "cooldown", "cooling")):
            for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(seconds?|minutes?|mins?|hours?|hrs?)\b", sentence, re.I):
                add("연속가동·냉각", clean(m.group(0)))

        if any(k in low for k in ("error", "bit flip", "bitflip", "upset")):
            for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", sentence):
                add("오류율", f"{m.group(1)}%")

        if any(k in low for k in ("radiation", "dose", "rad")):
            for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(krad|rad|gy|gray)\b", sentence, re.I):
                add("방사선", clean(m.group(0)))

        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(kw|watts?|kilowatts?|w)\b", sentence, re.I):
            add("실제 전력", clean(m.group(0)))

        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(gbps|tbps|tokens?/?s|tokens? per second)\b", sentence, re.I):
            add("처리량", clean(m.group(0)))

    return metrics


def parse_news() -> list[dict]:
    root = ET.fromstring(fetch(NEWS_RSS, timeout=25).content)
    rows = []
    for item in root.findall("./channel/item")[:40]:
        title = clean(item.findtext("title") or "")
        link = clean(item.findtext("link") or "")
        pub = clean(item.findtext("pubDate") or "")
        source_node = item.find("source")
        source = clean(source_node.text if source_node is not None else "")
        low = title.lower()
        if not ("suncatcher" in low or ("google" in low and "space" in low and ("data center" in low or "tpu" in low))):
            continue
        rows.append({
            "title": title,
            "link": link,
            "source": source,
            "published": pub,
            "story_key": news_story_key(title, source),
        })
    return rows


def parse_pub_ts(value: str) -> float:
    try:
        return email.utils.parsedate_to_datetime(value).timestamp()
    except Exception:
        return 0.0


def news_story_key(title: str, source: str) -> str:
    low = clean(title).lower()
    if "suncatcher" in low and ("in orbit" in low or "launch" in low or "launched" in low):
        return "suncatcher|orbit-launch-confirmation"
    if any(k in low for k in ("temperature", "thermal", "cooling", "radiation", "bit flip", "error rate", "runtime", "run time", "throughput", "power")):
        normalized = re.sub(r"[^a-z0-9]+", "-", low).strip("-")[:120]
        return "suncatcher|telemetry|" + normalized
    normalized = re.sub(r"[^a-z0-9]+", "-", low).strip("-")[:120]
    return "suncatcher|news|" + normalized


def korean_news_summary(item: dict) -> str:
    title = item.get("title", "")
    low = title.lower()
    raw_source = item.get("source") or ""
    source = SOURCE_LABEL_KO.get(raw_source, "신뢰 출처")
    if "prototype satellite is in orbit" in low or ("suncatcher" in low and "in orbit" in low):
        return f"• {source}: 프로젝트 선캐처 시험위성의 궤도 진입을 확인한 공식 게시물"
    if "launch" in low or "launched" in low:
        return f"• {source}: 프로젝트 선캐처 발사·궤도 상태 관련 새 보도"
    if any(k in low for k in ("thermal", "temperature", "cooling", "radiation", "bit flip", "error", "runtime", "throughput", "power")):
        return f"• {source}: 프로젝트 선캐처 궤도 실험 수치·신뢰성 관련 새 자료"
    return f"• {source}: 프로젝트 선캐처 관련 새 자료"


def compact_metric_summary(metrics: dict) -> list[str]:
    lines = []
    for label in ("온도", "연속가동·냉각", "오류율", "방사선", "실제 전력", "처리량"):
        vals = metrics.get(label) or []
        if vals:
            lines.append(f"• {label}: " + " · ".join(vals[:3]))
    return lines


def diff_dict(old: dict, new: dict) -> list[str]:
    changes = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            changes.append(key)
    return changes


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for path in (ALERT, PENDING, STATUS, ERRORS):
        path.unlink(missing_ok=True)

    old = load_state()
    errors: list[str] = []

    # Critical official sources.
    orbit_text = ""
    orbit_source_ok = False
    try:
        orbit_text = page_text(GOOGLE_ORBIT_URL)
        orbit_source_ok = True
    except Exception as exc:
        errors.append(f"구글 궤도 공식 조회 실패: {type(exc).__name__}: {exc}")

    spacex_text = ""
    spacex_source_ok = False
    try:
        spacex_text = page_text(SPACEX_LAUNCHES_URL)
        spacex_source_ok = True
    except Exception as exc:
        errors.append(f"스페이스X 공식 발사정보 조회 실패: {type(exc).__name__}: {exc}")

    mission_status = parse_google_orbit_status(orbit_text) if orbit_source_ok else (old.get("mission_status") or {})
    launch = parse_spacex_launch_time(spacex_text) if spacex_source_ok else (old.get("launch") or {})
    backup_schedule = parse_nextspaceflight_backup()

    # Secondary/reference sources are stored for change detection, but pre-launch
    # numbers such as the 15-minute thermal design limit are never treated as in-orbit measurements.
    source_defs = {
        "구글 궤도 공식": GOOGLE_ORBIT_URL,
        "구글 사전 설명": GOOGLE_FACTS_URL,
        "구글 최초 발표": GOOGLE_ORIGINAL_URL,
        "플래닛 공식": PLANET_URL,
        "아스테크니카 사전 기술설명": ARS_URL,
    }
    sources = {}
    for name, url in source_defs.items():
        if name == "구글 궤도 공식" and orbit_source_ok:
            sources[name] = {"url": url, "hash": hash_text(orbit_text)}
            continue
        try:
            snapshot = source_snapshot(url)
            sources[name] = {"url": url, "hash": snapshot["hash"]}
        except Exception as exc:
            errors.append(f"{name} 조회 실패: {type(exc).__name__}: {exc}")
            if old.get("sources", {}).get(name):
                sources[name] = old["sources"][name]

    official_metrics = extract_official_in_orbit_metrics(orbit_text) if orbit_source_ok else (old.get("official_in_orbit_metrics") or {})

    news = []
    try:
        news = parse_news()
    except Exception as exc:
        errors.append(f"뉴스 감시 조회 실패: {type(exc).__name__}: {exc}")
        news = old.get("news") or []

    parser_upgrade = bool(old) and int(old.get("parser_version") or 0) < PARSER_VERSION
    first = not bool(old)

    old_status = old.get("mission_status") or {}
    mission_changes = diff_dict(old_status, mission_status) if old_status else []
    old_metrics = old.get("official_in_orbit_metrics") or {}
    metric_changes = diff_dict(old_metrics, official_metrics) if old_metrics else []

    old_story_keys = set(old.get("seen_news_story_keys") or [])
    current_story_keys = [x.get("story_key") for x in news if x.get("story_key")]
    fresh_news = [x for x in news if x.get("story_key") and x.get("story_key") not in old_story_keys]
    fresh_news.sort(key=lambda x: parse_pub_ts(x.get("published", "")), reverse=True)

    # Official Google can stand alone. Non-official news is discovery-only unless
    # at least two trusted sources independently report the same semantic event.
    official_fresh = [x for x in fresh_news if x.get("source") in OFFICIAL_NEWS_SOURCES]
    corroborated = []
    grouped: dict[str, set[str]] = {}
    for item in fresh_news:
        if item.get("source") not in TRUSTED_NEWS_SOURCES:
            continue
        grouped.setdefault(item.get("story_key") or "", set()).add(item.get("source") or "")
    for item in fresh_news:
        if item.get("source") in TRUSTED_NEWS_SOURCES and len(grouped.get(item.get("story_key") or "", set())) >= 2:
            corroborated.append(item)

    meaningful_news = []
    for item in official_fresh + corroborated:
        if item.get("story_key") == "suncatcher|orbit-launch-confirmation" and mission_status.get("launch_success"):
            # The launch event is represented by the official mission status section.
            continue
        if item not in meaningful_news:
            meaningful_news.append(item)

    critical_ok = orbit_source_ok and bool(mission_status.get("launch_success")) and bool(launch.get("actual_liftoff_utc"))
    should_alert = False
    if first:
        should_alert = critical_ok
    elif parser_upgrade:
        should_alert = critical_ok
    elif mission_changes or metric_changes or meaningful_news:
        should_alert = orbit_source_ok

    # Persist the current semantic news baseline even if no alert is sent.
    state = {
        "parser_version": PARSER_VERSION,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mission_status": mission_status,
        "launch": launch,
        "backup_schedule": backup_schedule,
        "official_in_orbit_metrics": official_metrics,
        "sources": sources,
        "news": news[:40],
        "seen_news_story_keys": list(dict.fromkeys(current_story_keys + list(old_story_keys)))[:200],
        "watch": "Google Project Suncatcher orbital TPU mission and verified in-orbit telemetry",
    }
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if should_alert:
        if parser_upgrade:
            title = "✅ 구글 선캐처 궤도 데이터센터 감시 정정·업그레이드"
        elif first:
            title = "✅ 구글 선캐처 궤도 데이터센터 감시 연결 완료"
        else:
            title = "🚨 구글 선캐처 궤도 데이터센터 핵심 변화"

        lines = [
            title,
            "",
            "▶ 현재 공식 확인 상태",
            f"• 발사: {'성공' if mission_status.get('launch_success') else '공식 확인 대기'}",
            f"• 실제 발사시각: {launch.get('display_utc', '공식 확인 대기')} · {launch.get('display_kst', '공식 확인 대기')}",
            f"• 위성 교신: {'확인' if mission_status.get('contact_confirmed') else '공식 확인 대기'}",
            f"• 위성 정상 동작: {'확인' if mission_status.get('spacecraft_operating') else '공식 확인 대기'}",
            f"• TPU 정상 부팅: {'공식 확인' if mission_status.get('tpu_boot_confirmed') else '아직 공식 미확인'}",
            f"• 실제 AI 모델 실행: {'공식 확인' if mission_status.get('model_execution_confirmed') else '아직 공식 미확인 · 모델명도 확정 표기하지 않음'}",
            "",
            "▶ 궤도 실측값",
        ]
        metric_lines = compact_metric_summary(official_metrics)
        lines += metric_lines or [
            "• 온도·냉각 회복시간·연속가동시간·오류율·비트플립·방사선 이상·실제 전력·처리량: 아직 구글 공식 실측값 공개 없음",
        ]

        if parser_upgrade:
            lines += [
                "",
                "■ 이번 정정",
                "• 이전 알림의 '발사 성공 + 10월 1일 예정·정확한 시각 미확정' 표시는 서로 모순되어 제거했습니다.",
                "• 발사시각은 스페이스X 공식 Transporter-18 기준 2026-10-01 18:18 UTC / 2026-10-02 03:18 KST로 고정 검증합니다.",
                "• 구글 공식 발표의 '궤도 진입·교신 확인·위성 정상 동작'과 TPU 부팅·AI 모델 실행을 분리합니다.",
                "• 사전 알려진 약 15분 운용 한계·약 1킬로와트 전력은 설계 기준선일 뿐 궤도 실측값으로 재알림하지 않습니다.",
                "• 'Gemini 실행'을 미확인 상태에서 단정하지 않고, 실제 모델 실행과 모델명이 공식 확인될 때만 표기합니다.",
                "• 뉴스 원문 영문 제목을 불완전하게 지우는 방식을 중단하고 한국어 사건 요약만 표시합니다.",
            ]

        if mission_changes and not parser_upgrade:
            lines += ["", "■ 공식 임무 상태 변화"]
            label_map = {
                "launch_success": "발사 성공 여부",
                "contact_confirmed": "위성 교신 확인",
                "spacecraft_operating": "위성 정상 동작",
                "tpu_boot_confirmed": "TPU 부팅 확인",
                "model_execution_confirmed": "AI 모델 실행 확인",
            }
            for key in mission_changes:
                lines.append(f"• {label_map.get(key, key)}: {old_status.get(key)} → {mission_status.get(key)}")

        if metric_changes and not parser_upgrade:
            lines += ["", "■ 새 공식 실측 수치"]
            lines += compact_metric_summary(official_metrics)

        if meaningful_news and not parser_upgrade:
            lines += ["", "■ 새 검증 자료"]
            for item in meaningful_news[:3]:
                lines.append(korean_news_summary(item))
                if item.get("link"):
                    lines.append(f"원문: {item['link']}")

        lines += [
            "",
            "▶ 앞으로 알림하는 변화",
            "• 구글 공식 TPU 부팅 확인",
            "• 실제 AI 모델 실행 및 모델명 공식 확인",
            "• 궤도 온도·냉각 회복시간·연속가동시간",
            "• 오류율·비트플립·방사선 이상",
            "• 실제 전력·처리량",
            "• 발사·교신·위성 상태의 실패·복구·일정 변화",
            "• 단순 기사 재탕과 사전 설계수치 반복은 알림하지 않습니다.",
            "",
            f"원문: {GOOGLE_ORBIT_URL}",
            f"원문: {SPACEX_LAUNCHES_URL}",
        ]
        ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if errors:
        ERRORS.write_text("\n".join(errors) + "\n", encoding="utf-8")

    status_lines = [
        "# 구글 선캐처 궤도 데이터센터 감시",
        "",
        f"- 파서 버전: {PARSER_VERSION}",
        f"- 파서 업그레이드 정정: {'예' if parser_upgrade else '아니오'}",
        f"- 구글 궤도 공식 조회: {'성공' if orbit_source_ok else '실패'}",
        f"- 스페이스X 공식 발사정보 조회: {'성공' if spacex_source_ok else '실패'}",
        f"- 발사 성공: {'예' if mission_status.get('launch_success') else '미확인'}",
        f"- 교신 확인: {'예' if mission_status.get('contact_confirmed') else '미확인'}",
        f"- 위성 정상 동작: {'예' if mission_status.get('spacecraft_operating') else '미확인'}",
        f"- TPU 부팅 공식 확인: {'예' if mission_status.get('tpu_boot_confirmed') else '아니오'}",
        f"- AI 모델 실행 공식 확인: {'예' if mission_status.get('model_execution_confirmed') else '아니오'}",
        f"- 실제 발사시각: {launch.get('display_utc', '확인 불가')} · {launch.get('display_kst', '확인 불가')}",
        f"- 공식 궤도 실측항목: {len(official_metrics)}종",
        f"- 신규 검증 뉴스: {len(meaningful_news)}건",
        f"- 텔레그램 알림 파일: {'생성' if ALERT.exists() else '없음'}",
        f"- 조회 오류: {len(errors)}건",
    ]
    STATUS.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    print(STATUS.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
