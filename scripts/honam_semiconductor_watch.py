#!/usr/bin/env python3
import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import ssl
import subprocess
import sys
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

UA = "Mozilla/5.0 (compatible; khs-watch/1.5; +https://github.com/qedgwangju-dot/khs-watch)"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    # 핵심 환경 3단계
    '"호남권 반도체 첨단 국가산업단지" 장록습지',
    '"호남권 반도체 첨단 국가산업단지" 환경영향평가',
    '"호남권 반도체 첨단 국가산업단지" 낙찰 계약 착수 현지조사',
    '"장록습지" 수량 수질 유량 수위 지하수',
    '"장록습지" 람사르 등록 심사',
    # 정주·주거·배후도시
    '"호남권 반도체 국가산업단지" 주거 정주 배후도시',
    '"호남권 반도체 첨단 국가산업단지" 주택 택지 배후도시',
    '"전남광주" 반도체 주거정책 정주 수요',
    '전남광주 반도체 주거정책 정주 주택',
    '광주 반도체 정주 주거 배후도시',
    '"호남 반도체" 산정지구 송정역 상무 주거',
    # 기반시설·생활 인프라
    '"호남권 반도체 국가산업단지" 전력 용수 변전소 송전',
    '국회입법조사처 호남 반도체 클러스터 용수 공급 타당성',
    'site:nars.go.kr 호남 반도체 클러스터 용수',
    '호남 반도체 댐 용수 하수재이용수 하천수 가뭄',
    '호남 반도체 동복댐 주암댐 장흥댐 보성강댐 나주댐',
    '"호남권 반도체 국가산업단지" 교통 도로 철도 교육 의료',
    '"호남권 반도체 국가산업단지" 기반시설 착공 준공',
    # 산단·기업투자·팹 일정
    '"호남권 반도체 국가산업단지" 삼성전자 SK하이닉스 투자 팹',
    '"호남권 반도체 국가산업단지" 착공 양산 준공 일정',
    '"호남권 반도체 국가산업단지" 확장 추가 부지 조성계획',
    '광주공항 함평 무안 반도체 클러스터 팹 배후기지',
    '함평 반도체 직접 팹 국가산단 후보지',
    '무안 반도체 소부장 물류 에너지 배후기지',
    '광주공항 반도체 팹 생산거점',
    '"호남 반도체" 함평 무안 클러스터 추가 부지',
    # 공식자료 우선
    'site:lh.or.kr "호남권 반도체 첨단 국가산업단지"',
    'site:ebid.lh.or.kr "호남권 반도체 첨단 국가산업단지"',
    'site:gwangju.go.kr "호남권 반도체"',
    'site:jeonnam.go.kr "호남권 반도체"',
    'site:molit.go.kr "호남권 반도체"',
    'site:motie.go.kr "호남권 반도체"',
    'site:me.go.kr "장록습지" 람사르',
    'site:ramsar.org Jangrok Korea wetland',
]

STAGES = {
    "1_용역선정_현지조사": ["낙찰", "수행업체", "용역업체", "계약 체결", "현지조사", "현장조사", "환경영향평가", "기후변화영향평가", "개찰", "우선협상", "적격심사"],
    "2_수량수질_조사범위": ["수량", "수질", "유량", "수위", "지하수", "취수", "방류", "조사범위", "조사지점", "측정지점", "계절조사", "갈수기", "홍수기", "완충거리", "저감대책", "생태계", "수생태"],
    "3_람사르_심사결과": ["람사르", "ramsar", "등록", "등재", "등록습지", "심사", "보완", "승인", "지정"],
    "4_정주주거_배후도시": ["정주", "주거", "주택", "배후도시", "배후 주거", "택지", "공공주택", "산정지구", "송정역", "상무 도심융합", "금호타이어", "자족형 도시", "주거종합계획", "주거정책", "미분양", "공실", "가구", "세대", "정주 수요"],
    "5_기반시설_생활SOC": ["전력", "용수", "변전소", "송전", "배전", "전원 인가", "도로", "철도", "교통", "교육", "학교", "의료", "병원", "문화", "생활 soc", "기반시설", "산업용수", "하수", "물류", "공항", "항공화물", "에너지", "분산에너지", "댐", "동복댐", "주암댐", "장흥댐", "보성강댐", "나주댐", "하수재이용수", "재이용수", "하천수", "이수 안전도", "유입량", "유출량", "가뭄", "물 부족", "용수 배분", "목적 외 사용", "사용료", "수자원", "용수 공급"],
    "6_산단투자_기업일정": ["삼성전자", "sk하이닉스", "팹", "fab", "직접 팹", "투자", "착공", "준공", "양산", "생산시설", "생산거점", "후보지", "국가산단 지정", "산업단지 지정", "추가 확장", "추가 부지", "확장", "기업 투자", "실사", "클러스터", "배후기지", "소부장", "공급망", "다핵"],
}

STAGE_LABELS = {
    "1_용역선정_현지조사": "① 용역업체 선정·현지조사",
    "2_수량수질_조사범위": "② 장록습지 수량·수질",
    "3_람사르_심사결과": "③ 람사르 등록 심사",
    "4_정주주거_배후도시": "④ 정주·주거·배후도시",
    "5_기반시설_생활SOC": "⑤ 전력·용수·교통·생활 인프라",
    "6_산단투자_기업일정": "⑥ 산단·기업투자·팹 일정",
}
CORE_STAGES = {"1_용역선정_현지조사", "2_수량수질_조사범위", "3_람사르_심사결과"}
BROAD_STAGES = {"4_정주주거_배후도시", "5_기반시설_생활SOC", "6_산단투자_기업일정"}
TOPIC_TERMS = ["호남권 반도체", "호남 반도체", "호남권 첨단 반도체", "호남 반도체 클러스터", "반도체 국가산업단지", "반도체 국가산단", "장록습지", "장록", "광주 군공항", "광주공항", "군공항 종전부지"]
LOCAL_TERMS = ["전남광주", "전남광주시", "광주", "광산구", "산정지구", "송정역", "상무", "군공항", "광주공항", "함평", "함평군", "빛그린산단", "무안", "무안군", "무안공항", "현경면"]
MATERIAL_TERMS = ["계획", "정책", "조례", "수요", "공급", "검토", "착공", "준공", "양산", "지정", "선정", "계약", "낙찰", "조사", "등록", "심사", "보완", "확장", "투자", "팹", "직접 팹", "생산거점", "후보지", "클러스터", "배후기지", "소부장", "공급망", "물류", "실사", "가구", "명", "억원", "조원", "㎞", "km", "mw", "gw", "만평", "㎡", "지구", "도시", "주택", "전력", "용수", "댐", "하수재이용수", "하천수", "가뭄", "물 부족", "유입량", "유출량", "이수 안전도", "수자원"]
POSITIVE = ["선정", "낙찰", "계약 체결", "조사 착수", "현지조사 착수", "승인", "확정", "통과", "착공", "준공", "양산", "기간 단축", "앞당", "확대", "증설"]
NEGATIVE = ["지연", "보완", "재검토", "반려", "중단", "연기", "갈등", "우려", "영향 불가피", "재입찰", "사업기간 연장", "준공 지연", "공급 부족", "병목"]
OFFICIAL_LH_DESIGN_BID = "https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidDegree=00&bidNum=2602775"\nOFFICIAL_LH_ENV_BID = "https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidDegree=00&bidNum=2603004"


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        if urllib.parse.urlparse(url).hostname == "ebid.lh.or.kr" and "CERTIFICATE_VERIFY_FAILED" in str(exc):
            with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
                return resp.read()
        raise


def clean_text(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_news_date(value: str):
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None


def parse_iso_kst(value: str):
    try:
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)
    except Exception:
        return None


def story_key(title: str, source: str, pub: str) -> str:
    normalized = re.sub(r"\s+", " ", (title or "").strip().lower())
    published = parse_news_date(pub)
    day = published.strftime("%Y-%m-%d") if published else "unknown"
    raw = f"{normalized}\n{(source or '').strip().lower()}\n{day}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def resolve_google_news_url(url: str):
    if (urllib.parse.urlparse(url).hostname or "").lower() != "news.google.com":
        return url, False
    try:
        from googlenewsdecoder import gnewsdecoder
    except Exception:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "googlenewsdecoder>=0.1.7"], check=True, timeout=75, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            from googlenewsdecoder import gnewsdecoder
        except Exception:
            return url, False
    try:
        result = gnewsdecoder(url, interval=0)
        decoded = result.get("decoded_url") or result.get("url") or "" if isinstance(result, dict) else (result if isinstance(result, str) else "")
        decoded = (decoded or "").strip()
        host = (urllib.parse.urlparse(decoded).hostname or "").lower()
        if decoded.startswith("http") and host and host != "news.google.com":
            return decoded, True
    except Exception:
        pass
    return url, False


def identify_publisher(url: str, fallback: str):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    fallback = (fallback or "").strip()
    if host == "news.google.com":
        return f"Google 뉴스 경유 · {fallback}" if fallback else "Google 뉴스 경유"
    if host in {"n.news.naver.com", "news.naver.com"}:
        return f"{fallback}(네이버)" if fallback else "네이버뉴스"
    if host == "v.daum.net":
        return f"{fallback}(다음)" if fallback else "다음뉴스"
    return fallback or host or "웹 원문"


def google_news_items(query: str):
    rss = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    root = ET.fromstring(fetch(rss))
    items = []
    for node in root.findall("./channel/item")[:40]:
        title = clean_text(node.findtext("title") or "")
        link = clean_text(node.findtext("link") or "")
        desc = clean_text(node.findtext("description") or "")
        pub = clean_text(node.findtext("pubDate") or "")
        source_el = node.find("source")
        source = clean_text(source_el.text if source_el is not None and source_el.text else "")
        items.append({"id": hashlib.sha256((title + "\n" + link).encode()).hexdigest()[:24], "story_key": story_key(title, source, pub), "title": title, "link": link, "description": desc, "pubDate": pub, "source": source})
    return items


def detect_stages(text: str):
    low = text.lower()
    return [stage for stage, words in STAGES.items() if any(word.lower() in low for word in words)]


def relevant(item):
    text = f"{item['title']} {item['description']}"
    low = text.lower()
    explicit_topic = any(term.lower() in low for term in TOPIC_TERMS)
    local_semiconductor = "반도체" in low and any(term in low for term in LOCAL_TERMS)
    stages = detect_stages(text)
    if not (explicit_topic or local_semiconductor) or not stages:
        return False, stages
    if any(stage in BROAD_STAGES for stage in stages):
        hits = sum(1 for term in MATERIAL_TERMS if term.lower() in low)
        has_number = bool(re.search(r"\d[\d,.]*\s*(?:명|가구|세대|년|월|일|억|조|만평|㎡|km|㎞|mw|gw|%)", low, flags=re.I))
        if hits < 2 and not has_number:
            return False, stages
    return True, stages


def impact(text: str, stages):
    if any(word in text for word in NEGATIVE):
        return "지연·병목 위험"
    if "4_정주주거_배후도시" in stages:
        return "정주·인력유입 준비도 변화"
    if "5_기반시설_생활SOC" in stages:
        return "기반시설·전원 인가 시간표 영향"
    if "6_산단투자_기업일정" in stages:
        return "산단·팹 투자 시간표 변화"
    if any(word in text for word in POSITIVE):
        return "절차 한 단계 진행"
    return "영향 확인 필요"


def why_it_matters(stages):
    if "1_용역선정_현지조사" in stages:
        return "환경영향평가가 실제 조사 단계로 넘어가는 핵심 관문"
    if "2_수량수질_조사범위" in stages:
        return "장록습지 수량·수질 검증 범위가 산단 배치·저감대책과 승인 속도에 연결"
    if "3_람사르_심사결과" in stages:
        return "람사르 등록 결과가 환경협의 조건과 첫 구간 시간표에 영향을 줄 수 있음"
    if "4_정주주거_배후도시" in stages:
        return "2030년 전후 인력 유입을 받을 주택·배후도시 공급 속도가 팹 가동의 정주 병목이 될 수 있음"
    if "5_기반시설_생활SOC" in stages:
        return "전력·용수·교통·교육·의료가 실제 착공·가동과 인력 정착을 결정"
    if "6_산단투자_기업일정" in stages:
        return "앵커기업 투자·팹 착공·준공·양산 일정이 후속 발주와 산단 수요를 결정"
    return "호남 반도체 국가산단 진행상황과 직접 연결"


def compact_news_item(item):
    resolved_url, resolved = resolve_google_news_url(item.get("link", ""))
    stages = item.get("stages", [])
    host = (urllib.parse.urlparse(resolved_url).hostname or "").lower()
    official = any(host == h or host.endswith("." + h) for h in ["lh.or.kr", "gwangju.go.kr", "jeonnam.go.kr", "molit.go.kr", "motie.go.kr", "me.go.kr", "ramsar.org", "korea.kr"])
    return {"title": item.get("title", ""), "description": item.get("description", ""), "source": identify_publisher(resolved_url, item.get("source", "")), "published": item.get("pubDate", ""), "url": resolved_url, "url_resolved": resolved, "source_status": "공식자료" if official else "보도 단계", "stages": stages, "stage_labels": [STAGE_LABELS.get(s, s) for s in stages], "impact": item.get("impact", "영향 확인 필요"), "reason": why_it_matters(stages)}


def load_state():
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_ids": [], "seen_story_keys": [], "official_page_signatures": {}}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state.setdefault("seen_ids", [])
        state.setdefault("seen_story_keys", [])
        state.setdefault("official_page_signatures", {})
        return state
    except Exception:
        return {"initialized": False, "seen_ids": [], "seen_story_keys": [], "official_page_signatures": {}}


def official_signature(url: str):
    text = clean_text(fetch(url).decode("utf-8", errors="ignore"))
    text = re.sub(r"다운로드\s*:?\s*\d+|조회수\s*:?\s*\d+", " ", text)
    parts = []
    for kw in ["호남권 반도체", "입찰", "개찰", "낙찰", "계약", "착수", "입찰진행"]:
        for m in re.finditer(re.escape(kw), text, flags=re.I):
            parts.append(text[max(0, m.start()-160):m.end()+240])
    joined = " | ".join(dict.fromkeys(parts[:30]))
    return hashlib.sha256(joined.encode()).hexdigest()


def main():
    now_dt = dt.datetime.now(KST)
    now = now_dt.isoformat(timespec="seconds")
    state = load_state()
    initialized = bool(state.get("initialized", True))
    monitor_started = parse_iso_kst(state.get("monitor_started_at_kst", "")) or parse_iso_kst(state.get("updated_at_kst", "")) or now_dt
    seen_ids = set(state.get("seen_ids", []))
    seen_keys = set(state.get("seen_story_keys", []))
    errors, all_items = [], []

    for query in QUERIES:
        try:
            all_items.extend(google_news_items(query))
        except Exception as exc:
            errors.append(f"RSS 실패: {query}: {type(exc).__name__}: {exc}")

    dedup = {item["story_key"]: item for item in all_items}
    relevant_items = []
    for item in dedup.values():
        ok, stages = relevant(item)
        if not ok:
            continue
        item["stages"] = stages
        item["impact"] = impact(f"{item['title']} {item['description']}", stages)
        relevant_items.append(item)
    relevant_items.sort(key=lambda x: parse_news_date(x.get("pubDate", "")) or dt.datetime.min.replace(tzinfo=KST), reverse=True)

    new_items, stale = [], []
    broad_cutoff = max(monitor_started, now_dt - dt.timedelta(days=7))
    for item in relevant_items:
        if item["id"] in seen_ids or item["story_key"] in seen_keys:
            continue
        published = parse_news_date(item.get("pubDate", ""))
        cutoff = broad_cutoff if set(item.get("stages", [])) & BROAD_STAGES else monitor_started
        if initialized and published and published < cutoff:
            stale.append(item)
            continue
        if published and published > now_dt + dt.timedelta(hours=6):
            stale.append(item)
            continue
        new_items.append(item)

    official_changes = []
    signatures = dict(state.get("official_page_signatures", {}))

    # 조사설계용역(2602775)은 환경영향평가 수행업체 선정과 다른 절차다.
    # 핵심 ①에 섞지 않고 산단 사업 추진 일정으로 분리한다.
    try:
        sig = official_signature(OFFICIAL_LH_DESIGN_BID)
        prior = signatures.get("lh_design_bid")
        signatures["lh_design_bid"] = sig
        if initialized and prior and prior != sig:
            official_changes.append({
                "stage": "6_산단투자_기업일정",
                "stage_label": STAGE_LABELS["6_산단투자_기업일정"],
                "headline": "LH 조사설계용역 입찰·개찰 상태 변경",
                "detail": "조사설계용역 공고 2602775의 개찰·낙찰·계약 단계 변화. 환경영향평가 용역과는 별도 절차",
                "impact": "산단 사업 추진 일정 변화",
                "reason": "기본·실시설계와 조사설계 진행은 산단 조성 시간표에 직접 연결",
                "source_status": "공식자료",
                "url": OFFICIAL_LH_DESIGN_BID,
            })
    except Exception as exc:
        errors.append(f"LH 조사설계용역 확인 실패: {type(exc).__name__}: {exc}")

    # 핵심 ①은 환경영향평가·기후변화영향평가 용역(2603004)만 직접 감시한다.
    try:
        sig = official_signature(OFFICIAL_LH_ENV_BID)
        prior = signatures.get("lh_env_bid")
        signatures["lh_env_bid"] = sig
        if initialized and prior and prior != sig:
            official_changes.append({
                "stage": "1_용역선정_현지조사",
                "stage_label": STAGE_LABELS["1_용역선정_현지조사"],
                "headline": "환경영향평가·기후변화영향평가 용역 상태 변경",
                "detail": "공고 2603004의 개찰·낙찰·계약·착수 단계가 변경됨. 수행업체 선정과 실제 현지조사 착수 여부를 이어서 확인",
                "impact": "환경평가 절차 한 단계 진행 가능",
                "reason": why_it_matters(["1_용역선정_현지조사"]),
                "source_status": "공식자료",
                "url": OFFICIAL_LH_ENV_BID,
            })
    except Exception as exc:
        errors.append(f"LH 환경영향평가용역 확인 실패: {type(exc).__name__}: {exc}")

    send_items = [compact_news_item(i) for i in new_items] if initialized else []
    send_official = official_changes if initialized else []

    pending = {
        "initialized": True,
        "scope_version": "v5_core3_plus_multinode_cluster",
        "monitor_started_at_kst": state.get("monitor_started_at_kst") or monitor_started.isoformat(timespec="seconds"),
        "updated_at_kst": now,
        "seen_ids": list(dict.fromkeys([i["id"] for i in relevant_items] + list(seen_ids)))[:2000],
        "seen_story_keys": list(dict.fromkeys([i["story_key"] for i in relevant_items] + list(seen_keys)))[:2000],
        "official_page_signatures": signatures,
        "last_relevant_count": len(relevant_items),
        "last_stale_suppressed_count": len(stale),
        "errors": errors[-20:],
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if send_items or send_official:
        ALERT_PATH.write_text(json.dumps({"title": "호남 반도체 국가산단", "checked_at_kst": now, "new_count": len(send_items) + len(send_official), "new_items": send_items[:12], "official_changes": send_official[:5]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif ALERT_PATH.exists():
        ALERT_PATH.unlink()

    STATUS_PATH.write_text("\n".join([
        "# 호남 반도체 국가산단 웹감시 상태",
        f"- 확인시각(KST): {now}",
        f"- 관련 검색결과: {len(relevant_items)}건",
        f"- 새 관련정보: {len(send_items)}건",
        f"- 과거·중복 차단: {len(stale)}건",
        f"- 공식 핵심페이지 변경: {len(send_official)}건",
        "- 감시 범위: 환경 3단계 + 정주·주거 + 전력·용수·교통·생활 인프라 + 산단·기업투자·팹 일정 + 광주·함평·무안 다핵 클러스터",
    ]) + "\n", encoding="utf-8")
    print(f"relevant={len(relevant_items)} new={len(send_items)} stale_suppressed={len(stale)} official_changes={len(send_official)} initialized_before={initialized}")


if __name__ == "__main__":
    main()
