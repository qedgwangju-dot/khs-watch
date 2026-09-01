import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import hormuz_maritime_watch_v4 as watcher


KNOWN_BASELINE_EVENTS = {
    "news:2026-08-30:strike:hormuz:1": {
        "baseline": True,
        "note": "Known pre-monitor single-projectile tanker incident",
    },
    "news:2026-08-31:strike:hormuz:3": {
        "baseline": True,
        "note": "Known UKMTO 124-26 three-projectile tanker incident",
    },
}

KST = ZoneInfo("Asia/Seoul")
LOCATION_KO = {
    "hormuz": "호르무즈 해협",
    "khasab": "오만 카사브 인근",
    "fujairah": "푸자이라 인근",
    "gulf-of-oman": "오만만",
    "oman": "오만 인근 해역",
    "regional": "호르무즈·인접 해역",
}
EVENT_KO = {
    "strike": "유조선·상선 피격/공격",
    "mine": "기뢰 관련 사건",
    "seizure": "나포·강제 승선",
    "explosion": "폭발·화재",
    "restriction": "강제 정지·통항 제한",
}


def calibrated_source_confidence(items):
    sources = {item.get("source") for item in items if item.get("source")}
    strong = sources & watcher.STRONG_SOURCES
    specialists = sources & watcher.SPECIALIST_SOURCES
    authority_mention = any(item.get("mentions_authority") for item in items)
    if not authority_mention:
        return False
    if len(strong) >= 2:
        return True
    if len(sources) >= 2 and strong and specialists:
        return True
    return len(sources) >= 3 and bool(strong)


_original_load_state = watcher.load_state


def calibrated_load_state():
    state, migrating = _original_load_state()
    events = state.setdefault("confirmed_events", {})
    for key, value in KNOWN_BASELINE_EVENTS.items():
        events.setdefault(key, value)
    return state, migrating


def kst_time(iso_value):
    try:
        value = str(iso_value or "").replace("Z", "+00:00")
        return dt.datetime.fromisoformat(value).astimezone(KST).strftime("%m-%d %H:%M KST")
    except Exception:
        return "시각 미확인"


def safe_link(url, label="원문"):
    clean_url = html.escape(str(url or ""), quote=True)
    return f'<a href="{clean_url}">{html.escape(label)}</a>' if clean_url else "원문 링크 미확인"


def translate_title_to_korean(title, fallback):
    title = re.sub(r"\s+-\s+[^-]{2,80}$", "", str(title or "")).strip()
    if not title:
        return fallback
    if len(re.findall(r"[가-힣]", title)) >= 4:
        return title
    try:
        query = urllib.parse.urlencode({
            "client": "gtx",
            "sl": "auto",
            "tl": "ko",
            "dt": "t",
            "q": title,
        })
        request = urllib.request.Request(
            "https://translate.googleapis.com/translate_a/single?" + query,
            headers={"User-Agent": "Mozilla/5.0 KHS-Hormuz-Translator/1.0"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        translated = "".join(part[0] for part in payload[0] if part and part[0]).strip()
        if translated and len(re.findall(r"[가-힣]", translated)) >= 2:
            return translated
    except Exception:
        pass
    return fallback


def official_summary(item):
    text = watcher.clean(item.get("text", ""))
    low = text.lower()
    rows = []
    location = "호르무즈·인접 해역"
    if "khasab" in low:
        location = "오만 카사브 인근"
    elif "strait of hormuz" in low or "hormuz" in low:
        location = "호르무즈 해협"
    elif "fujairah" in low:
        location = "푸자이라 인근"
    rows.append(f"<b>위치</b> · {location}")

    count_match = re.search(r"\b(\d+)\s+(?:unknown\s+|unidentified\s+)?projectiles?\b", low)
    if count_match:
        rows.append(f"<b>사건</b> · 선박이 미상 발사체 {count_match.group(1)}발에 피격")
    elif "projectile" in low or "struck" in low or "attack" in low:
        rows.append("<b>사건</b> · 선박 피격/공격 사건 확인")
    elif "mine" in low:
        rows.append("<b>사건</b> · 기뢰 관련 보안사건 확인")
    else:
        rows.append("<b>사건</b> · 선박 보안사건 확인")

    if "crew are reported safe" in low or "crew are safe" in low or "all crew are reported safe" in low:
        rows.append("<b>인명</b> · 승무원 안전 보고")
    if "no environmental impact" in low or "no reported environmental impact" in low:
        rows.append("<b>환경</b> · 보고된 해양오염 없음")
    return rows


def readable_official_alert(item, news, update):
    lines = [
        "<b>호르무즈 해상보안 공식 업데이트</b>" if update else "<b>호르무즈 해상보안 공식 신규 경보</b>",
        f"<b>UKMTO</b> · {html.escape(str(item.get('warning') or '번호 미확인'))}",
        f"<b>확인</b> · {watcher.now_kst().strftime('%Y-%m-%d %H:%M KST')}",
        "",
    ]
    lines.extend(official_summary(item))
    lines.extend([
        "<b>무기·공격주체</b> · 공식 확인 전 추정하지 않음",
        f"<b>UKMTO 원문</b> · {safe_link(item.get('url'))}",
    ])
    related = [row for row in news if row.get("warning") == item.get("warning")][:3]
    if related:
        lines.extend(["", f"<b>교차검증</b> · 독립 출처 {len(related)}곳"])
        for row in related:
            fallback = "호르무즈 해상보안 사건 관련 보도"
            ko_title = translate_title_to_korean(row.get("title"), fallback)
            lines.append(
                f"• {html.escape(str(row.get('source') or '출처 미확인'))} · "
                f"{html.escape(ko_title)} · {safe_link(row.get('url'))}"
            )
    lines.extend([
        "",
        "<b>주의</b> · 원문에서 무기 종류가 특정되지 않은 경우 <b>미상 발사체</b>로 표기하며, 미사일·포탄·드론으로 임의 단정하지 않습니다.",
    ])
    return "\n".join(lines) + "\n"


def readable_cluster_alert(cluster):
    sources = cluster.get("sources", [])
    event_name = EVENT_KO.get(cluster.get("event_kind"), "해상보안 사건")
    location = LOCATION_KO.get(cluster.get("location"), "호르무즈·인접 해역")
    lines = [
        "<b>호르무즈 해상보안 교차검증 경보</b>",
        f"<b>사건</b> · {event_name}",
        f"<b>위치</b> · {location}",
        f"<b>확인</b> · {watcher.now_kst().strftime('%Y-%m-%d %H:%M KST')}",
    ]
    if cluster.get("warning"):
        lines.append(f"<b>UKMTO 경보</b> · {html.escape(str(cluster.get('warning')))}")
    if cluster.get("projectile_count") is not None:
        lines.append(f"<b>발사체</b> · {cluster.get('projectile_count')}발")
    lines.extend([
        f"<b>검증</b> · 독립 신뢰출처 {len(sources)}곳 교차 일치",
        "",
        "<b>확인 출처</b>",
    ])
    for row in sources[:4]:
        fallback = f"{location} {event_name} 관련 보도"
        ko_title = translate_title_to_korean(row.get("title"), fallback)
        lines.append(
            f"• {html.escape(str(row.get('source') or '출처 미확인'))} · "
            f"{kst_time(row.get('published_utc'))}\n"
            f"  {html.escape(ko_title)} · {safe_link(row.get('url'))}"
        )
    lines.extend([
        "",
        "<b>판정 기준</b> · UKMTO 직접 원문을 읽지 못한 경우에만 복수 독립 출처가 같은 사건을 확인했을 때 보조 경보로 송출",
        "<b>주의</b> · 원문에서 무기 종류가 특정되지 않은 경우 <b>미상 발사체</b>로 유지하며 공격주체·미사일·포탄·드론은 공식 확인 전 단정하지 않습니다.",
    ])
    return "\n".join(lines) + "\n"


watcher.source_confidence = calibrated_source_confidence
watcher.load_state = calibrated_load_state
watcher.build_official_alert = readable_official_alert
watcher.build_cluster_alert = readable_cluster_alert


if __name__ == "__main__":
    raise SystemExit(watcher.main())
