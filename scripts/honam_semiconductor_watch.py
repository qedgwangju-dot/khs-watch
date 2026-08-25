#!/usr/bin/env python3
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE_PATH = DATA / "honam_semiconductor_watch_state.json"
PENDING_PATH = OUT / "honam_semiconductor_pending_state.json"
ALERT_PATH = OUT / "honam_semiconductor_alert.json"
STATUS_PATH = OUT / "honam_semiconductor_status.md"

DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (compatible; khs-watch/1.1; +https://github.com/qedgwangju-dot/khs-watch)"

QUERIES = [
    '"호남권 반도체 첨단 국가산업단지" 장록습지',
    '"호남권 반도체 첨단 국가산업단지" 환경영향평가',
    '"호남권 반도체 첨단 국가산업단지" 낙찰 계약 착수',
    '"장록습지" 수량 수질 유량 수위 지하수',
    '"장록습지" 람사르 등록 심사',
    'site:lh.or.kr "호남권 반도체 첨단 국가산업단지"',
    'site:ebid.lh.or.kr "호남권 반도체 첨단 국가산업단지"',
    'site:me.go.kr "장록습지" 람사르',
    'site:ramsar.org Jangrok Korea wetland',
]

STAGES = {
    "1_용역선정_현지조사": [
        "낙찰", "수행업체", "용역업체", "사업자 선정", "계약 체결", "착수", "현지조사", "현장조사",
        "환경영향평가", "기후변화영향평가", "개찰", "우선협상", "적격심사"
    ],
    "2_수량수질_조사범위": [
        "수량", "수질", "유량", "수위", "지하수", "취수", "방류", "조사범위", "조사지점", "측정지점",
        "계절조사", "갈수기", "홍수기", "완충거리", "저감대책", "생태계", "수생태"
    ],
    "3_람사르_심사결과": [
        "람사르", "ramsar", "등록", "등재", "등록습지", "심사", "보완", "승인", "지정"
    ],
}

STAGE_LABELS = {
    "1_용역선정_현지조사": "① 용역업체 선정·현지조사",
    "2_수량수질_조사범위": "② 장록습지 수량·수질",
    "3_람사르_심사결과": "③ 람사르 등록 심사",
}

POSITIVE = ["선정", "낙찰", "계약 체결", "착수", "조사 시작", "조사 착수", "승인", "확정", "통과"]
NEGATIVE = ["지연", "보완", "재검토", "반려", "중단", "연기", "갈등", "우려", "영향 불가피", "재입찰"]
TOPIC_TERMS = ["호남권 반도체", "호남 반도체", "장록습지", "장록", "광주 반도체", "반도체 국가산업단지"]

OFFICIAL_LH_DESIGN_BID = "https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidDegree=00&bidNum=2602775"


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        # LH e-bid occasionally presents a certificate-chain issue on GitHub hosted runners.
        # This fallback is read-only and restricted to the official LH e-bid hostname.
        if urllib.parse.urlparse(url).hostname == "ebid.lh.or.kr" and "CERTIFICATE_VERIFY_FAILED" in str(exc):
            with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
                return resp.read()
        raise


def clean_text(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_dynamic_noise(text: str) -> str:
    text = re.sub(r"다운로드\s*:?\s*\d+", "다운로드", text, flags=re.I)
    text = re.sub(r"조회수\s*:?\s*\d+", "조회수", text, flags=re.I)
    text = re.sub(r"\b(?:session|jsessionid|token|timestamp)\s*[:=]\s*[A-Za-z0-9._-]+", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def google_news_items(query: str):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    raw = fetch(url)
    root = ET.fromstring(raw)
    items = []
    for item in root.findall("./channel/item")[:30]:
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        pub = clean_text(item.findtext("pubDate") or "")
        source_el = item.find("source")
        source = clean_text(source_el.text if source_el is not None and source_el.text else "")
        identity = hashlib.sha256((title + "\n" + link).encode("utf-8")).hexdigest()[:24]
        items.append({"id": identity, "title": title, "link": link, "description": desc, "pubDate": pub, "source": source, "query": query})
    return items


def detect_stages(text: str):
    low = text.lower()
    result = []
    for stage, words in STAGES.items():
        if any(w.lower() in low for w in words):
            result.append(stage)
    return result


def relevant(item):
    text = f"{item['title']} {item['description']}"
    low = text.lower()
    has_topic = any(term.lower() in low for term in TOPIC_TERMS) or "jangrok" in low
    stages = detect_stages(text)
    return has_topic and bool(stages), stages


def impact(text: str):
    if any(w in text for w in NEGATIVE):
        return "지연·보완 위험"
    if any(w in text for w in POSITIVE):
        return "절차 한 단계 진행"
    return "영향 확인 필요"


def compact_news_item(item):
    stages = item.get("stages", [])
    return {
        "title": item.get("title", ""),
        "source": item.get("source") or "웹 검색",
        "published": item.get("pubDate", ""),
        "url": item.get("link", ""),
        "stages": stages,
        "stage_labels": [STAGE_LABELS.get(s, s) for s in stages],
        "impact": item.get("impact", "영향 확인 필요"),
    }


def load_state():
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_ids": [], "official_page_signatures": {}}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state.setdefault("initialized", True)
        state.setdefault("seen_ids", [])
        state.setdefault("official_page_signatures", {})
        return state
    except Exception:
        return {"initialized": False, "seen_ids": [], "official_page_signatures": {}}


def filtered_signature(url: str, keywords):
    raw = fetch(url)
    text = normalize_dynamic_noise(clean_text(raw.decode("utf-8", errors="ignore")))
    pieces = []
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text, flags=re.I):
            a = max(0, m.start() - 180)
            b = min(len(text), m.end() + 260)
            pieces.append(text[a:b])
    joined = " | ".join(dict.fromkeys(pieces[:30]))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), joined[:2200]


def summarize_official_change(name: str, url: str, snippet: str):
    if name == "lh_design_bid":
        return {
            "stage": "1_용역선정_현지조사",
            "stage_label": STAGE_LABELS["1_용역선정_현지조사"],
            "headline": "LH 전자조달 페이지의 핵심 입찰·계약 정보 변경 감지",
            "detail": "개찰·낙찰·계약·착수 관련 상태가 바뀌었을 가능성이 있어 원문 확인이 필요합니다.",
            "impact": "용역업체 선정 또는 착수로 확인되면 첫 구간 시간표가 한 단계 진행",
            "url": url,
        }
    return {
        "stage": "",
        "stage_label": "공식자료",
        "headline": "공식 페이지 핵심 내용 변경 감지",
        "detail": snippet[:300],
        "impact": "세부 확인 필요",
        "url": url,
    }


def main():
    now = dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    state = load_state()
    initialized = bool(state.get("initialized"))
    seen = set(state.get("seen_ids", []))
    all_items = []
    errors = []

    for query in QUERIES:
        try:
            all_items.extend(google_news_items(query))
        except Exception as exc:
            errors.append(f"RSS 실패: {query}: {type(exc).__name__}: {exc}")

    dedup = {}
    for item in all_items:
        dedup[item["id"]] = item

    relevant_items = []
    for item in dedup.values():
        ok, stages = relevant(item)
        if not ok:
            continue
        item["stages"] = stages
        item["impact"] = impact(f"{item['title']} {item['description']}")
        relevant_items.append(item)

    relevant_items.sort(key=lambda x: x.get("pubDate", ""), reverse=True)
    new_items = [i for i in relevant_items if i["id"] not in seen]

    # Fixed 2026-07-30 LH press-release pages are intentionally NOT hashed.
    # Their download counters change continuously and previously caused false alerts.
    official_changes = []
    page_specs = {
        "lh_design_bid": (OFFICIAL_LH_DESIGN_BID, ["호남권 반도체", "입찰", "개찰", "낙찰", "계약", "착수", "입찰진행"]),
    }
    signatures = dict(state.get("official_page_signatures", {}))
    for name, (url, kws) in page_specs.items():
        try:
            sig, snippet = filtered_signature(url, kws)
            prior = signatures.get(name)
            signatures[name] = sig
            if initialized and prior and prior != sig:
                official_changes.append(summarize_official_change(name, url, snippet))
        except Exception as exc:
            errors.append(f"공식 페이지 실패: {name}: {type(exc).__name__}: {exc}")

    send_items = [compact_news_item(i) for i in new_items] if initialized else []
    send_official = official_changes if initialized else []

    next_seen = list(dict.fromkeys([i["id"] for i in relevant_items] + list(seen)))[:800]
    pending = {
        "initialized": True,
        "updated_at_kst": now,
        "seen_ids": next_seen,
        "official_page_signatures": signatures,
        "last_relevant_count": len(relevant_items),
        "errors": errors[-20:],
        "noise_filters": ["LH 보도자료 다운로드 수", "조회수", "스크립트·메뉴 문구"],
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if send_items or send_official:
        alert = {
            "title": "호남 반도체 국가산단 · 장록습지",
            "checked_at_kst": now,
            "new_count": len(send_items) + len(send_official),
            "new_items": send_items[:10],
            "official_changes": send_official[:5],
        }
        ALERT_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif ALERT_PATH.exists():
        ALERT_PATH.unlink()

    status_lines = [
        "# 호남 반도체·장록습지 웹감시 상태",
        "",
        f"- 확인시각(KST): {now}",
        f"- 관련 검색결과: {len(relevant_items)}건",
        f"- 새 관련정보: {len(send_items)}건",
        f"- 공식 핵심페이지 변경: {len(send_official)}건",
        f"- 초기기준선 실행: {'아니오' if initialized else '예'}",
        "- 동적 잡음 제외: LH 다운로드 수·조회수·메뉴/스크립트 문구",
    ]
    if errors:
        status_lines += ["", "## 일부 조회 오류"] + [f"- {e}" for e in errors[-8:]]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    print(f"relevant={len(relevant_items)} new={len(send_items)} official_changes={len(send_official)} initialized_before={initialized}")


if __name__ == "__main__":
    main()
