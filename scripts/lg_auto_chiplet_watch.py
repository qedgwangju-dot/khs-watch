#!/usr/bin/env python3
"""Separate, stage-aware LG/BOS/Hana automotive chiplet Telegram watchdog."""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "lg_auto_chiplet_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
PENDING = OUT / "lg_auto_chiplet_pending_state.json"
ALERT = OUT / "lg_auto_chiplet_alert.html"
STATUS = OUT / "lg_auto_chiplet_status.md"
KST = ZoneInfo("Asia/Seoul")
USER_AGENT = "Mozilla/5.0 (compatible; KHSLGVehicleChipletWatch/1.0)"
UA = {"User-Agent": USER_AGENT, "Accept-Language": "ko,en;q=0.8"}
BASELINE = {
    "lg_bos_hana|development_mou": {
        "title": "2026-09-30 산업통상부 LG전자·보스반도체·하나마이크론 칩렛 기반 SoC 공동개발 업무협약",
        "stage": 2,
        "source_url": "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/172250/view",
        "status": "확정: 개발협력, 미확정: 보쉬 구매계약·양산·매출",
    },
    "lg_bos_hana|bosch_discussion": {
        "title": "2026-10-09 매일경제 보쉬 사용 논의 기사",
        "stage": 2,
        "source_url": "https://www.mk.co.kr/article/12172466",
        "status": "언론보도: 보쉬 적용 논의, 공급계약 아님",
    },
}
QUERIES = (
    '"LG전자" "보스반도체" "하나마이크론" 칩렛 when:60d',
    '"LG전자" "보쉬" "칩렛" when:60d',
    '"LG전자" "Bosch" "chiplet" when:60d',
    '"LG전자" "보스반도체" 차량용 반도체 when:60d',
    '"하나마이크론" "보스반도체" (칩렛 OR SoC) when:60d',
    '"LG Electronics" "BOS Semiconductors" "Hana Micron" when:90d',
    '"LG Electronics" "Bosch" "chiplet" when:90d',
    'site:motir.go.kr (LG전자 OR 보스반도체) 칩렛 when:120d',
    'site:katech.re.kr (LG전자 OR 보스반도체) 칩렛 when:120d',
    'site:bos-semi.com ("LG Electronics" OR "Hana Micron") chiplet when:120d',
    'site:imec-int.com "LG Electronics" "Bosch" chiplet when:120d',
    'site:lge.co.kr 보스반도체 칩렛 when:120d',
    'site:hana-micron.co.kr (LG전자 OR 보스반도체) 칩렛 when:120d',
)
OFFICIAL_DOMAINS = (
    "motir.go.kr", "motie.go.kr", "korea.kr", "katech.re.kr", "keit.re.kr",
    "kiat.or.kr", "lge.co.kr", "lg.co.kr", "bosch.com", "bosch-semiconductors.com",
    "imec-int.com", "bos-semi.com", "hana-micron.co.kr",
)
TRUSTED_MEDIA = (
    "매일경제", "머니투데이", "연합뉴스", "이데일리", "서울경제", "한국경제",
    "전자신문", "디일렉", "thelec", "지디넷", "zdnet", "뉴스핌",
    "파이낸셜뉴스", "디지털데일리", "조선비즈", "뉴시스", "아시아경제",
    "서울신문", "경향신문", "동아일보", "중앙일보", "아주경제",
)
NOISE_TERMS = (
    "특징주", "관련주", "테마주", "상한가", "급등주", "목표주가",
    "주가 급등", "인수설", "루머", "가능성 부각",
)
UNCERTAIN = (
    "논의", "검토", "협의", "추진", "예정", "목표", "가능성",
    "전망", "계획", "기대", "될 수", "고려", "희망",
)
BAD_OUTCOME = (
    "무산", "철회", "계약해지", "사업 중단", "개발 중단",
    "일정 연기", "인증 실패", "개발 실패", "수율 문제",
)

def now_kst():
    return dt.datetime.now(KST)

def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))).strip()

def esc(text):
    return html.escape(str(text or ""), quote=True)

def fetch(url, timeout=18):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode(res.headers.get_content_charset() or "utf-8", "replace"), res.geturl()

def pub_time(text):
    try:
        value = email.utils.parsedate_to_datetime(text)
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(KST)
    except (TypeError, ValueError, OverflowError):
        return None

def norm_title(title):
    value = clean(title).lower()
    value = re.sub(r"\s+-\s+[^-]{2,65}$", "", value)
    return re.sub(r"\s+", " ", re.sub(r"[^가-힣a-z0-9]+", " ", value)).strip()

def url_key(url):
    parsed = urllib.parse.urlsplit(clean(url))
    # The same Google News article may be republished with a different query suffix.
    query = "" if parsed.netloc.lower() == "news.google.com" else parsed.query
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), query, ""))

def article_key(item):
    raw = url_key(item["url"]) or norm_title(item["title"])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

def host_in(host, domains):
    host = host.lower().strip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in domains)

def quality(source, source_url):
    host = urllib.parse.urlsplit(source_url or "").hostname or ""
    if host_in(host, OFFICIAL_DOMAINS):
        return "당사자·기관 공식"
    if any(name.lower() in clean(source).lower() for name in TRUSTED_MEDIA):
        return "신뢰 언론 보도"
    return "기타 보도"

def relevant(title, summary=""):
    t = (clean(title) + " " + clean(summary)).lower()
    if any(x in t for x in NOISE_TERMS):
        return False
    lg = "lg전자" in t or "lg electronics" in t
    bos = "보스반도체" in t or "bos semiconductors" in t
    hana = "하나마이크론" in t or "hana micron" in t
    bosch = "보쉬" in t or bool(re.search(r"\bbosch\b", t))
    topic = any(x in t for x in ("칩렛", "chiplet", "차량용 soc", "automotive soc", "차량용 반도체", "vehicle soc", "반도체"))
    # A BOS/European OEM chiplet deal or a Bosch/imec program alone is NOT this LG project.
    return topic and (lg and (bos or hana or bosch) or bos and hana)

def event_kind(title, summary=""):
    """Assign milestone from the headline, not unverified details appearing in a related link."""
    t = clean(title).lower()
    full = (t + " " + clean(summary).lower())
    bosch = "보쉬" in full or bool(re.search(r"\bbosch\b", full))
    tentative = any(x in t for x in UNCERTAIN)
    if any(x in t for x in BAD_OUTCOME):
        return ("project_blocked", 7, "계획 철회·지연·품질 위험")
    # Contract claims must be explicit. '보쉬 사용 논의' cannot be a paid contract.
    if any(x in t for x in ("재수주", "추가 수주", "추가 발주", "후속 계약", "공급 확대")) and not tentative:
        return ("repeat_order", 6, "추가 수주·반복 공급")
    if any(x in t for x in ("공급계약 체결", "공급 계약 체결", "구매계약 체결", "공급 계약 확정", "양산 공급 계약", "대량 발주", "발주 확정", "수주 확정", "장기공급계약")) and not tentative:
        return ("purchase_contract", 6, "고객 구매·공급계약")
    if any(x in t for x in ("양산 개시", "양산 시작", "첫 양산", "양산 출하", "양산 납품")) and not tentative:
        return ("mass_production", 6, "양산·실제 출하")
    if any(x in t for x in ("품질인증 통과", "차량 인증 획득", "aec-q100 통과", "기능안전 인증", "차량용 인증")) and not tentative:
        return ("qualification", 5, "차량용 품질·안전 인증")
    if any(x in t for x in ("시제품 납품", "고객 검증", "고객 평가", "차량 탑재 실증", "보쉬 검증", "bosch validation")) and not tentative:
        return ("customer_validation", 4, "고객 기술검증·시제품 적용")
    if any(x in t for x in ("테이프아웃", "tape-out", "tapeout", "설계 완료", "시제품 개발", "시제품 제작", "칩렛 시제품")) and not tentative:
        return ("engineering_sample", 3, "설계 완료·시제품")
    if bosch and any(x in full for x in ("논의", "검토", "협의", "추진", "계획", "가능", "보쉬와 손잡", "bosch")):
        if any(x in t for x in ("공급", "양산")) and not tentative:
            # A single headline is not proof of Bosch purchase; require explicit signed-contract language.
            return ("bosch_discussion", 2, "보쉬 적용 관련 보도·구매계약 미확인")
        return ("bosch_discussion", 2, "보쉬 적용 논의·구매계약 미확인")
    if any(x in full for x in ("정부", "사업 공고", "사업공고", "국책", "과제 선정", "지원사업")) and any(x in t for x in ("예산", "공고", "선정", "협약")):
        return ("government_award", 2, "정부 과제·사업 단계")
    if any(x in t for x in ("업무협약", "mou", "공동개발", "공동 개발", "개발 협력", "협력 체결", "칩렛 개발")):
        return ("development_mou", 2, "공식 공동개발·업무협약")
    return ("research_update", 1, "개발·생태계 동향")

def project_kind(title, summary):
    t = (clean(title) + " " + clean(summary)).lower()
    if ("아이멕" in t or "imec" in t) and not ("보스반도체" in t or "하나마이크론" in t or "bos semiconductors" in t):
        return "imec_alliance"
    return "lg_bos_hana"

def candidate_event(item):
    kind, stage, description = event_kind(item["title"], item.get("summary", ""))
    project = project_kind(item["title"], item.get("summary", ""))
    return f"{project}|{kind}", stage, description

def parse_feed(xml_text, lane):
    root = ET.fromstring(xml_text)
    out = []
    for node in root.findall("./channel/item"):
        title = clean(node.findtext("title"))
        summary = clean(node.findtext("description"))
        if not relevant(title, summary):
            continue
        src = node.find("source")
        source = clean(src.text) if src is not None else "구글뉴스"
        source_url = src.get("url", "") if src is not None else ""
        q = quality(source, source_url)
        if q == "기타 보도":
            continue
        url = clean(node.findtext("link"))
        if not url:
            continue
        date = pub_time(node.findtext("pubDate"))
        item = {
            "title": title, "summary": summary, "source": source, "source_url": source_url,
            "url": url, "quality": q, "lane": lane,
            "published_kst": date.isoformat(timespec="minutes") if date else None,
        }
        item["event_id"], item["stage"], item["stage_desc"] = candidate_event(item)
        out.append(item)
    return out

def collect():
    records, failed, success = [], [], 0
    for query in QUERIES:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
        try:
            xml_text, _ = fetch(url)
            records.extend(parse_feed(xml_text, query))
            success += 1
        except (OSError, ValueError, ET.ParseError) as exc:
            failed.append(f"{query}: {type(exc).__name__}")
    if success < 4:
        raise RuntimeError(f"차량용 칩렛 원천 조회 부족: {success}/{len(QUERIES)}; 중단해 무변화 오판 방지")
    return records, success, failed

def resolve_publisher(url):
    if "news.google.com/" not in url:
        return url, "원문"
    try:
        from googlenewsdecoder import gnewsdecoder
        result = gnewsdecoder(url, interval=0)
        decoded = result.get("decoded_url") if isinstance(result, dict) and result.get("status") else None
        if decoded and decoded.startswith(("https://", "http://")) and "news.google.com/" not in decoded:
            return decoded, "원문"
    except Exception:
        pass
    try:
        _, final = fetch(url, timeout=10)
        if final and "news.google.com/" not in final:
            return final, "원문"
    except Exception:
        pass
    return url, "기사 보기(구글뉴스 경유)"

def read_state():
    if not STATE.exists():
        return {"initialized": False, "seen": {}, "events": {}}
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        state.setdefault("seen", {})
        state.setdefault("events", {})
        return state
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"상태파일 손상: {exc}") from exc

def meta(item, now, **extra):
    return {
        "title": item["title"], "url": item["url"], "source": item["source"],
        "event_id": item["event_id"], "stage": item["stage"],
        "published_kst": item.get("published_kst"),
        "first_seen_kst": now.isoformat(timespec="seconds"), **extra,
    }

def main():
    for path in (PENDING, ALERT, STATUS):
        path.unlink(missing_ok=True)
    now = now_kst()
    state = read_state()
    seen = dict(state.get("seen") or {})
    events = dict(state.get("events") or {})
    candidates, healthy, failures = collect()
    print(f"chiplet_feeds_ok={healthy}/{len(QUERIES)} matched={len(candidates)}")
    if failures:
        print(f"chiplet_source_errors={'; '.join(failures[:3])}")
    deduped = {}
    for item in candidates:
        k = article_key(item)
        old = deduped.get(k)
        if old is None or item["quality"] == "당사자·기관 공식":
            deduped[k] = item
    ordered = sorted(deduped.values(), key=lambda x: (x.get("published_kst") or "", x["stage"]))

    if not state.get("initialized"):
        for event_id, seed in BASELINE.items():
            events.setdefault(event_id, {**seed, "registered_kst": now.isoformat(timespec="seconds"), "baseline": True})
        for item in ordered:
            seen[article_key(item)] = meta(item, now, baseline=True)
            events.setdefault(item["event_id"], {
                "title": item["title"], "stage": item["stage"], "source_url": item["url"],
                "registered_kst": now.isoformat(timespec="seconds"), "baseline": True,
            })
        next_state = {
            "initialized": True, "bootstrap_kst": now.isoformat(timespec="seconds"),
            "last_checked_kst": now.isoformat(timespec="seconds"), "seen": seen, "events": events,
        }
        PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text(
            f"# LG전자·보스반도체·하나마이크론 차량용 칩렛\n\n"
            f"- 상태: 최초 기준선 생성\n- 기존 기사: {len(ordered)}건\n"
            f"- 기준선 사건: {len(events)}건\n- 새 알림: 0건\n"
            f"- 원천 성공: {healthy}/{len(QUERIES)}\n- 조회: {now:%Y-%m-%d %H:%M} KST\n",
            encoding="utf-8",
        )
        return

    try:
        last = dt.datetime.fromisoformat(str(state["last_checked_kst"]))
    except (KeyError, ValueError) as exc:
        raise RuntimeError(f"마지막 성공 실행시각 확인 실패: {exc}") from exc
    if last.tzinfo is None:
        last = last.replace(tzinfo=KST)
    new_items, suppressed, stale = [], 0, 0

    # The old confirmed consortium and today's possible Bosch application are baseline facts.
    for event_id, seed in BASELINE.items():
        events.setdefault(event_id, {**seed, "registered_kst": now.isoformat(timespec="seconds"), "baseline": True})

    for item in ordered:
        key = article_key(item)
        if key in seen:
            continue
        published = dt.datetime.fromisoformat(item["published_kst"]) if item.get("published_kst") else None
        if published and published < last - dt.timedelta(hours=36):
            seen[key] = meta(item, now, suppressed_stale=True)
            stale += 1
            continue
        if item["event_id"] in events:
            seen[key] = meta(item, now, suppressed_duplicate="same_event")
            suppressed += 1
            continue
        # Send at most five events per run; leave other events unregistered for later runs.
        if len(new_items) >= 5:
            continue
        # Previously unseen event. Register immediately, so another outlet in the same run is suppressed.
        seen[key] = meta(item, now, pending_alert=True)
        events[item["event_id"]] = {
            "title": item["title"], "stage": item["stage"], "source_url": item["url"],
            "registered_kst": now.isoformat(timespec="seconds"), "quality": item["quality"],
        }
        new_items.append(item)

    if new_items:
        lines = [
            "<b>차량용 칩렛 개발·보쉬 고객검증 알림</b>",
            "",
            f"조회시각: {now:%Y-%m-%d %H:%M} KST",
            f"실제 신규 단계: {len(new_items)}건",
            "",
        ]
        for i, item in enumerate(new_items[:5], 1):
            url, label = resolve_publisher(item["url"])
            level = "공식 확인" if item["quality"] == "당사자·기관 공식" else "언론 보도·공식 재확인 필요"
            lines.append(f"<b>{i}. [{esc(item['stage_desc'])}] {esc(item['title'])}</b>")
            lines.append(f"• 확인 수준: {level}")
            lines.append(f"• 현재 단계: {item['stage']}/7")
            if item["event_id"].endswith("bosch_discussion"):
                lines.append("• 보쉬 채택·양산·공급계약: 미확정")
            if item["event_id"].endswith("development_mou"):
                lines.append("• LG전자 베이스 칩 · 보스반도체 AI 칩 · 하나마이크론 검증·패키징")
            lines.append(f"• 출처: {esc(item['source'])} · 공개: {esc(item['published_kst'] or '확인 필요')}")
            if item.get("published_kst"):
                lag = max(0, int((now - dt.datetime.fromisoformat(item["published_kst"])).total_seconds() // 60))
                if lag > 90:
                    lines.append(f"• 공개 후 감지 시차: 약 {lag // 60}시간 {lag % 60}분")
            lines.append(f'• <a href="{esc(url)}">{label}</a>')
            lines.append("")
            seen[article_key(item)] = meta(item, now, alerted=True)
            events[item["event_id"]]["alerted"] = True
        ALERT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    if len(seen) > 2500:
        seen = dict(list(seen.items())[-2500:])
    next_state = {
        **{k: v for k, v in state.items() if k not in ("seen", "events")},
        "initialized": True, "last_checked_kst": now.isoformat(timespec="seconds"),
        "seen": seen, "events": events,
    }
    PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        f"# LG전자·보스반도체·하나마이크론 차량용 칩렛\n\n"
        f"- 상태: 정상 조회\n- 후보: {len(ordered)}건\n"
        f"- 신규 알림: {len(new_items)}건\n- 사건 중복 억제: {suppressed}건\n"
        f"- 과거 재노출 억제: {stale}건\n- 원천 성공: {healthy}/{len(QUERIES)}\n"
        f"- 감시 사건: {len(events)}개\n- 조회: {now:%Y-%m-%d %H:%M} KST\n",
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
