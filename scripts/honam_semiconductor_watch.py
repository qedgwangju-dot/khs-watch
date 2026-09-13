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

UA = "Mozilla/5.0 (compatible; khs-watch/1.3; +https://github.com/qedgwangju-dot/khs-watch)"
KST = ZoneInfo("Asia/Seoul")

# 핵심 3단계는 최우선으로 유지하고, 사용자가 요구한 국가산단 전체 진행상황도 함께 감시한다.
QUERIES = [
    # 핵심 3단계
    '"호남권 반도체 첨단 국가산업단지" 장록습지',
    '"호남권 반도체 첨단 국가산업단지" 환경영향평가',
    '"호남권 반도체 첨단 국가산업단지" 낙찰 계약 착수 현지조사',
    '"장록습지" 수량 수질 유량 수위 지하수',
    '"장록습지" 람사르 등록 심사',
    # 정주·주거·배후도시
    '"호남권 반도체 국가산업단지" 주거 정주 배후도시',
    '"호남권 반도체 첨단 국가산업단지" 주택 택지 배후도시',
    '"전남광주" 반도체 주거정책 정주 수요',
    '"호남 반도체" 산정지구 송정역 상무 주거',
    # 전력·용수·교통·생활 인프라
    '"호남권 반도체 국가산업단지" 전력 용수 변전소 송전',
    '"호남권 반도체 국가산업단지" 교통 도로 철도 교육 의료',
    '"호남권 반도체 국가산업단지" 기반시설 착공 준공',
    # 기업투자·산단 시간표
    '"호남권 반도체 국가산업단지" 삼성전자 SK하이닉스 투자 팹',
    '"호남권 반도체 국가산업단지" 착공 양산 준공 일정',
    '"호남권 반도체 국가산업단지" 확장 추가 부지 조성계획',
    # 공식자료 우선 검색
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
    "1_용역선정_현지조사": [
        "낙찰", "수행업체", "용역업체", "계약 체결", "현지조사", "현장조사",
        "환경영향평가", "기후변화영향평가", "개찰", "우선협상", "적격심사"
    ],
    "2_수량수질_조사범위": [
        "수량", "수질", "유량", "수위", "지하수", "취수", "방류", "조사범위", "조사지점", "측정지점",
        "계절조사", "갈수기", "홍수기", "완충거리", "저감대책", "생태계", "수생태"
    ],
    "3_람사르_심사결과": [
        "람사르", "ramsar", "등록", "등재", "등록습지", "심사", "보완", "승인", "지정"
    ],
    "4_정주주거_배후도시": [
        "정주", "주거", "주택", "배후도시", "배후 주거", "택지", "공공주택", "산정지구",
        "송정역", "상무 도심융합", "금호타이어", "자족형 도시", "주거종합계획", "주거정책",
        "미분양", "공실", "가구", "세대", "정주 수요"
    ],
    "5_기반시설_생활SOC": [
        "전력", "용수", "변전소", "송전", "배전", "전원 인가", "도로", "철도", "교통",
        "교육", "학교", "의료", "병원", "문화", "생활 soc", "기반시설", "산업용수", "하수"
    ],
    "6_산단투자_기업일정": [
        "삼성전자", "sk하이닉스", "팹", "fab", "투자", "착공", "준공", "양산", "생산시설",
        "후보지", "국가산단 지정", "산업단지 지정", "추가 확장", "확장", "기업 투자", "실사"
    ],
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

POSITIVE = [
    "선정", "낙찰", "계약 체결", "조사 착수", "현지조사 착수", "승인", "확정", "통과",
    "착공", "준공", "양산", "기간 단축", "앞당", "확대", "증설"
]
NEGATIVE = [
    "지연", "보완", "재검토", "반려", "중단", "연기", "갈등", "우려", "영향 불가피",
    "재입찰", "사업기간 연장", "준공 지연", "공급 부족", "병목"
]
TOPIC_TERMS = [
    "호남권 반도체", "호남 반도체", "호남권 첨단 반도체", "반도체 국가산업단지",
    "반도체 국가산단", "장록습지", "장록", "광주 군공항", "군공항 종전부지"
]

MATERIAL_TERMS = [
    "계획", "정책", "조례", "수요", "공급", "착공", "준공", "양산", "지정", "선정", "계약",
    "낙찰", "조사", "등록", "심사", "보완", "확장", "투자", "팹", "가구", "명", "억원", "조원",
    "㎞", "km", "mw", "gw", "만평", "㎡", "지구", "도시", "주택", "전력", "용수"
]

OFFICIAL_LH_DESIGN_BID = "https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidDegree=00&bidNum=2602775"


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        # LH 전자조달은 GitHub 러너에서 인증서 체인 오류가 간헐적으로 발생한다.
        # 읽기 전용 공식 LH 도메인에 한해서만 우회한다.
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
    return re.sub(r"\s+", " ", text).strip()


def parse_news_date(value: str):
    if not value:
        return None
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
    base = f"{normalized}\n{(source or '').strip().lower()}\n{day}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def resolve_google_news_url(url: str):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host != "news.google.com":
        return url, False
    try:
        from googlenewsdecoder import gnewsdecoder
    except Exception:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "googlenewsdecoder>=0.1.7"],
                check=True,
                timeout=75,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            from googlenewsdecoder import gnewsdecoder
        except Exception:
            return url, False
    try:
        result = gnewsdecoder(url, interval=0)
        decoded = ""
        if isinstance(result, dict):
            decoded = result.get("decoded_url") or result.get("url") or ""
            if not result.get("status", bool(decoded)):
                decoded = ""
        elif isinstance(result, str):
            decoded = result
        decoded = (decoded or "").strip()
        decoded_host = (urllib.parse.urlparse(decoded).hostname or "").lower()
        if decoded.startswith("http") and decoded_host and decoded_host != "news.google.com":
            return decoded, True
    except Exception:
        pass
    return url, False


def identify_publisher(url: str, fallback_source: str):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    fallback = (fallback_source or "").strip()
    if host == "news.google.com":
        return f"Google 뉴스 경유 · {fallback}" if fallback else "Google 뉴스 경유"
    if host in {"n.news.naver.com", "news.naver.com"}:
        return f"{fallback}(네이버)" if fallback and "naver" not in fallback.lower() else "네이버뉴스"
    if host == "v.daum.net":
        return f"{fallback}(다음)" if fallback and fallback != "v.daum.net" else "다음뉴스"
    if host in {"m.news.nate.com", "news.nate.com"}:
        return f"{fallback}(네이트)" if fallback and "nate" not in fallback.lower() else "네이트뉴스"
    return fallback or host or "웹 원문"


def google_news_items(query: str):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    raw = fetch(url)
    root = ET.fromstring(raw)
    items = []
    for item in root.findall("./channel/item")[:35]:
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        pub = clean_text(item.findtext("pubDate") or "")
        source_el = item.find("source")
        source = clean_text(source_el.text if source_el is not None and source_el.text else "")
        identity = hashlib.sha256((title + "\n" + link).encode("utf-8")).hexdigest()[:24]
        items.append({
            "id": identity,
            "story_key": story_key(title, source, pub),
            "title": title,
            "link": link,
            "description": desc,
            "pubDate": pub,
            "source": source,
            "query": query,
        })
    return items


def detect_stages(text: str):
    low = text.lower()
    result = []
    for stage, words in STAGES.items():
        if any(word.lower() in low for word in words):
            result.append(stage)
    return result


def broad_material_enough(text: str, stages) -> bool:
    if not any(stage in BROAD_STAGES for stage in stages):
        return True
    low = text.lower()
    # 정주·인프라·산단 전반 뉴스는 단순 지역 홍보성 언급이 아니라 숫자·정책·일정·사업계획이 있어야 발송 후보로 본다.
    material_hits = sum(1 for term in MATERIAL_TERMS if term.lower() in low)
    has_number = bool(re.search(r"\d[\d,.]*\s*(?:명|가구|세대|년|월|일|억|조|만평|㎡|km|㎞|mw|gw|%)", low, flags=re.I))
    return material_hits >= 2 or has_number


def relevant(item):
    text = f"{item['title']} {item['description']}"
    low = text.lower()
    has_topic = any(term.lower() in low for term in TOPIC_TERMS)
    stages = detect_stages(text)
    if not has_topic or not stages:
        return False, stages
    if not broad_material_enough(text, stages):
        return False, stages
    return True, stages


def impact(text: str, stages) -> str:
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


def why_it_matters(stages) -> str:
    if "1_용역선정_현지조사" in stages:
        return "환경영향평가가 실제 조사 단계로 넘어가는지 확인하는 핵심 관문"
    if "2_수량수질_조사범위" in stages:
        return "장록습지 수량·수질 검증 범위가 산단 배치·저감대책과 승인 속도에 연결"
    if "3_람사르_심사결과" in stages:
        return "람사르 등록 결과가 환경협의 조건과 산단 첫 구간 시간표에 영향을 줄 수 있음"
    if "4_정주주거_배후도시" in stages:
        return "2030년 전후 인력 유입을 받을 주택·배후도시 공급 속도가 팹 가동의 정주 병목이 될 수 있음"
    if "5_기반시설_생활SOC" in stages:
        return "전력·용수·교통·교육·의료가 실제 착공·가동과 인력 정착을 결정하는 기반시설"
    if "6_산단투자_기업일정" in stages:
        return "앵커기업 투자·팹 착공·준공·양산 일정이 산단 전체 수요와 후속 발주를 결정"
    return "호남 반도체 국가산단의 실제 사업 진행상황과 연결"


def source_status(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    official_hosts = (
        "lh.or.kr", "ebid.lh.or.kr", "gwangju.go.kr", "jeonnam.go.kr", "molit.go.kr",
        "motie.go.kr", "me.go.kr", "ramsar.org", "korea.kr"
    )
    if any(host == h or host.endswith("." + h) for h in official_hosts):
        return "공식자료"
    return "보도 단계"


def compact_news_item(item):
    stages = item.get("stages", [])
    resolved_url, resolved = resolve_google_news_url(item.get("link", ""))
    display_source = identify_publisher(resolved_url, item.get("source") or "")
    return {
        "title": item.get("title", ""),
        "source": display_source,
        "published": item.get("pubDate", ""),
        "url": resolved_url,
        "url_resolved": resolved,
        "source_status": source_status(resolved_url),
        "stages": stages,
        "stage_labels": [STAGE_LABELS.get(stage, stage) for stage in stages],
        "impact": item.get("impact", "영향 확인 필요"),
        "reason": why_it_matters(stages),
    }


def load_state():
    if not STATE_PATH.exists():
        return {
            "initialized": False,
            "seen_ids": [],
            "seen_story_keys": [],
            "official_page_signatures": {},
        }
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state.setdefault("initialized", True)
        state.setdefault("seen_ids", [])
        state.setdefault("seen_story_keys", [])
        state.setdefault("official_page_signatures", {})
        return state
    except Exception:
        return {
            "initialized": False,
            "seen_ids": [],
            "seen_story_keys": [],
            "official_page_signatures": {},
        }


def filtered_signature(url: str, keywords):
    raw = fetch(url)
    text = normalize_dynamic_noise(clean_text(raw.decode("utf-8", errors="ignore")))
    pieces = []
    for keyword in keywords:
        for match in re.finditer(re.escape(keyword), text, flags=re.I):
            start = max(0, match.start() - 180)
            end = min(len(text), match.end() + 260)
            pieces.append(text[start:end])
    joined = " | ".join(dict.fromkeys(pieces[:30]))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), joined[:2200]


def summarize_official_change(name: str, url: str, snippet: str):
    if name == "lh_design_bid":
        return {
            "stage": "1_용역선정_현지조사",
            "stage_label": STAGE_LABELS["1_용역선정_현지조사"],
            "headline": "LH 전자조달 핵심 입찰·계약 정보 변경 감지",
            "detail": "개찰·낙찰·계약·착수 상태가 실제로 바뀌었는지 확인이 필요합니다.",
            "impact": "용역업체 선정 또는 조사 착수로 확인되면 첫 구간 절차가 한 단계 진행",
            "reason": why_it_matters(["1_용역선정_현지조사"]),
            "source_status": "공식자료",
            "url": url,
        }
    return {
        "stage": "",
        "stage_label": "공식자료",
        "headline": "공식 페이지 핵심 내용 변경 감지",
        "detail": snippet[:300],
        "impact": "세부 확인 필요",
        "reason": "국가산단 공식 절차 변화 여부 확인 필요",
        "source_status": "공식자료",
        "url": url,
    }


def main():
    now_dt = dt.datetime.now(KST)
    now = now_dt.isoformat(timespec="seconds")
    state = load_state()
    initialized = bool(state.get("initialized"))
    seen = set(state.get("seen_ids", []))
    seen_story_keys = set(state.get("seen_story_keys", []))
    all_items = []
    errors = []

    monitor_started = parse_iso_kst(state.get("monitor_started_at_kst") or "")
    if monitor_started is None:
        monitor_started = parse_iso_kst(state.get("updated_at_kst") or "") or now_dt

    for query in QUERIES:
        try:
            all_items.extend(google_news_items(query))
        except Exception as exc:
            errors.append(f"RSS 실패: {query}: {type(exc).__name__}: {exc}")

    # 제목·매체·발행일 기준으로 중복 제거한다. Google News 중계 URL이 바뀌어도 같은 기사로 취급한다.
    dedup = {}
    for item in all_items:
        dedup[item["story_key"]] = item

    relevant_items = []
    for item in dedup.values():
        ok, stages = relevant(item)
        if not ok:
            continue
        item["stages"] = stages
        item["impact"] = impact(f"{item['title']} {item['description']}", stages)
        relevant_items.append(item)

    relevant_items.sort(
        key=lambda item: parse_news_date(item.get("pubDate", "")) or dt.datetime.min.replace(tzinfo=KST),
        reverse=True,
    )

    new_items = []
    stale_suppressed = []
    broad_cutoff = max(monitor_started, now_dt - dt.timedelta(days=7))
    for item in relevant_items:
        if item["id"] in seen or item["story_key"] in seen_story_keys:
            continue
        published = parse_news_date(item.get("pubDate", ""))
        stages = set(item.get("stages", []))
        # 핵심 3단계는 감시 시작 이후 변화만, 새로 확장한 정주·인프라·투자 축은 최근 7일만 소급한다.
        cutoff = broad_cutoff if stages & BROAD_STAGES else monitor_started
        if initialized and published and published < cutoff:
            stale_suppressed.append(item)
            continue
        if published and published > now_dt + dt.timedelta(hours=6):
            stale_suppressed.append(item)
            continue
        new_items.append(item)

    official_changes = []
    page_specs = {
        "lh_design_bid": (
            OFFICIAL_LH_DESIGN_BID,
            ["호남권 반도체", "입찰", "개찰", "낙찰", "계약", "착수", "입찰진행"],
        ),
    }
    signatures = dict(state.get("official_page_signatures", {}))
    for name, (url, keywords) in page_specs.items():
        try:
            signature, snippet = filtered_signature(url, keywords)
            prior = signatures.get(name)
            signatures[name] = signature
            if initialized and prior and prior != signature:
                official_changes.append(summarize_official_change(name, url, snippet))
        except Exception as exc:
            errors.append(f"공식 페이지 실패: {name}: {type(exc).__name__}: {exc}")

    send_items = [compact_news_item(item) for item in new_items] if initialized else []
    send_official = official_changes if initialized else []

    next_seen = list(dict.fromkeys([item["id"] for item in relevant_items] + list(seen)))[:1800]
    next_story_keys = list(dict.fromkeys([item["story_key"] for item in relevant_items] + list(seen_story_keys)))[:1800]
    pending = {
        "initialized": True,
        "scope_version": "v3_core3_plus_project",
        "monitor_started_at_kst": state.get("monitor_started_at_kst") or monitor_started.isoformat(timespec="seconds"),
        "updated_at_kst": now,
        "seen_ids": next_seen,
        "seen_story_keys": next_story_keys,
        "official_page_signatures": signatures,
        "last_relevant_count": len(relevant_items),
        "last_stale_suppressed_count": len(stale_suppressed),
        "errors": errors[-20:],
        "noise_filters": [
            "LH 보도자료 다운로드 수·조회수",
            "스크립트·메뉴 문구",
            "감시 기준보다 오래된 기사 재노출",
            "동일 제목·출처·발행일 중복",
            "숫자·정책·일정 없는 단순 지역 홍보성 언급",
        ],
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if send_items or send_official:
        alert = {
            "title": "호남 반도체 국가산단",
            "checked_at_kst": now,
            "new_count": len(send_items) + len(send_official),
            "new_items": send_items[:12],
            "official_changes": send_official[:5],
        }
        ALERT_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif ALERT_PATH.exists():
        ALERT_PATH.unlink()

    status_lines = [
        "# 호남 반도체 국가산단 웹감시 상태",
        "",
        f"- 확인시각(KST): {now}",
        f"- 핵심 기준선(KST): {monitor_started.isoformat(timespec='seconds')}",
        f"- 전체 관련 검색결과: {len(relevant_items)}건",
        f"- 새 관련정보: {len(send_items)}건",
        f"- 과거·중복 기사 차단: {len(stale_suppressed)}건",
        f"- 공식 핵심페이지 변경: {len(send_official)}건",
        "- 감시 범위: 환경 3단계 + 정주·주거 + 전력·용수·교통·생활 인프라 + 산단·기업투자·팹 일정",
        "- 원문 링크: Google News 중계 URL은 가능한 경우 실제 기사 URL로 변환",
        "- 출처 표기: 실제 기사 페이지 또는 중계 여부를 구분",
    ]
    if errors:
        status_lines += ["", "## 일부 조회 오류"] + [f"- {error}" for error in errors[-8:]]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    print(
        f"relevant={len(relevant_items)} new={len(send_items)} stale_suppressed={len(stale_suppressed)} "
        f"official_changes={len(send_official)} initialized_before={initialized}"
    )


if __name__ == "__main__":
    main()
