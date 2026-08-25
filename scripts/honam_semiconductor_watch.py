#!/usr/bin/env python3
import datetime as dt
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
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE_PATH = DATA / "honam_semiconductor_watch_state.json"
PENDING_PATH = OUT / "honam_semiconductor_pending_state.json"
ALERT_PATH = OUT / "honam_semiconductor_alert.json"
STATUS_PATH = OUT / "honam_semiconductor_status.md"

DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

QUERIES = [
    '"호남권 반도체 첨단 국가산업단지" 장록습지',
    '"호남권 반도체 첨단 국가산업단지" 환경영향평가',
    '"장록습지" 수량 수질',
    '"장록습지" 람사르 등록 심사',
    'site:lh.or.kr "호남권 반도체 첨단 국가산업단지"',
    'site:ebid.lh.or.kr "호남권 반도체 첨단 국가산업단지"',
    'site:me.go.kr "장록습지" 람사르',
    'site:ramsar.org Jangrok Korea wetland',
]

STAGES = {
    "1_용역선정_현지조사": [
        "낙찰", "수행업체", "용역업체", "사업자 선정", "계약 체결", "계약", "착수", "현지조사", "현장조사",
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

POSITIVE = ["선정", "낙찰", "계약 체결", "착수", "조사 시작", "조사 착수", "승인", "확정", "통과"]
NEGATIVE = ["지연", "보완", "재검토", "반려", "중단", "연기", "갈등", "우려", "영향 불가피", "재입찰"]
TOPIC_TERMS = ["호남권 반도체", "호남 반도체", "장록습지", "장록", "광주 반도체", "반도체 국가산업단지"]

OFFICIAL_RAMSAR = "https://www.ramsar.org/country-profile/republic-korea"
OFFICIAL_LH_PRESS = "https://www.lh.or.kr/gallery.es?act=view&b_list=8&bid=0003&list_no=12081&mid=a10502000000&nPage=1&vlist_no_npage=1"
OFFICIAL_LH_DESIGN_BID = "https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidDegree=00&bidNum=2602775"


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


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
        return "첫 구간 시간표에 지연·보완 위험 신호"
    if any(w in text for w in POSITIVE):
        return "첫 구간 절차가 한 단계 진행된 신호"
    return "첫 구간 시간표 영향은 원문 세부조건 확인 필요"


def load_state():
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_ids": [], "ramsar_jangrok_present": False, "official_page_signatures": {}}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state.setdefault("initialized", True)
        state.setdefault("seen_ids", [])
        state.setdefault("ramsar_jangrok_present", False)
        state.setdefault("official_page_signatures", {})
        return state
    except Exception:
        return {"initialized": False, "seen_ids": [], "ramsar_jangrok_present": False, "official_page_signatures": {}}


def filtered_signature(url: str, keywords):
    raw = fetch(url)
    text = clean_text(raw.decode("utf-8", errors="ignore"))
    pieces = []
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text, flags=re.I):
            a = max(0, m.start() - 220)
            b = min(len(text), m.end() + 320)
            pieces.append(text[a:b])
    joined = " | ".join(pieces[:40])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), joined[:5000]


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

    # Direct official-page checks: Ramsar country profile and fixed LH project pages.
    official_changes = []
    page_specs = {
        "ramsar_country_profile": (OFFICIAL_RAMSAR, ["Jangrok", "Republic of Korea", "Ramsar Sites", "Wetland"]),
        "lh_project_press": (OFFICIAL_LH_PRESS, ["호남권 반도체", "국가산업단지", "사업시행자", "설계용역"]),
        "lh_design_bid": (OFFICIAL_LH_DESIGN_BID, ["호남권 반도체", "입찰", "개찰", "낙찰", "계약", "입찰진행"]),
    }
    signatures = dict(state.get("official_page_signatures", {}))
    for name, (url, kws) in page_specs.items():
        try:
            sig, snippet = filtered_signature(url, kws)
            prior = signatures.get(name)
            signatures[name] = sig
            if initialized and prior and prior != sig:
                official_changes.append({"name": name, "url": url, "snippet": snippet, "impact": "공식 페이지 변경 — 세부내용 확인 필요"})
        except Exception as exc:
            errors.append(f"공식 페이지 실패: {name}: {type(exc).__name__}: {exc}")

    ramsar_present = state.get("ramsar_jangrok_present", False)
    try:
        ramsar_text = clean_text(fetch(OFFICIAL_RAMSAR).decode("utf-8", errors="ignore"))
        now_present = bool(re.search(r"jangrok|장록", ramsar_text, flags=re.I))
        if initialized and now_present and not ramsar_present:
            official_changes.append({
                "name": "ramsar_jangrok_detected",
                "url": OFFICIAL_RAMSAR,
                "snippet": "Ramsar Republic of Korea 공식 페이지에서 Jangrok/장록 문자열이 새로 확인됨",
                "impact": "람사르 등록·등재 여부 공식 확인 필요 — 환경협의 조건 변화 가능",
            })
        ramsar_present = now_present
    except Exception as exc:
        errors.append(f"Ramsar 직접 확인 실패: {type(exc).__name__}: {exc}")

    # First run is baseline only. No Telegram spam for already-known articles.
    send_items = new_items if initialized else []
    send_official = official_changes if initialized else []

    # Keep a bounded history of relevant item IDs.
    next_seen = list(dict.fromkeys([i["id"] for i in relevant_items] + list(seen)))[:800]
    pending = {
        "initialized": True,
        "updated_at_kst": now,
        "seen_ids": next_seen,
        "ramsar_jangrok_present": ramsar_present,
        "official_page_signatures": signatures,
        "last_relevant_count": len(relevant_items),
        "errors": errors[-20:],
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    alert = None
    if send_items or send_official:
        alert = {
            "title": "호남 반도체 국가산단 · 장록습지 변화 감지",
            "checked_at_kst": now,
            "new_items": send_items[:12],
            "official_changes": send_official[:6],
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
        f"- 공식페이지 변경: {len(send_official)}건",
        f"- Ramsar 공식페이지 Jangrok/장록 감지: {'예' if ramsar_present else '아니오'}",
        f"- 초기기준선 실행: {'아니오' if initialized else '예'}",
    ]
    if errors:
        status_lines += ["", "## 일부 조회 오류"] + [f"- {e}" for e in errors[-8:]]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    print(f"relevant={len(relevant_items)} new={len(send_items)} official_changes={len(send_official)} initialized_before={initialized}")


if __name__ == "__main__":
    main()
