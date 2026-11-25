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
    "전남광주 반도체 건설인력 공공임대 모듈러 주거대책",
    "광주 반도체 도심융합특구 상무 산정지구 송정역",
    "전남광주 반도체 노바 NOVA 용역비 예산 추경",
    "호남 반도체 덕남정수장 송수관 국비 지방비 용수",
    "광주 반도체 동복댐 용수 지방재정 시의회",
    "site:assem.jeonnam-gwangju.go.kr 반도체 정주 용수 예산",
    "site:council.jeonnam-gwangju.go.kr 반도체 건설인력 주거",
    # 기반시설·생활 인프라
    '"호남권 반도체 국가산업단지" 전력 용수 변전소 송전',
    '국회입법조사처 호남 반도체 클러스터 용수 공급 타당성',
    'site:nars.go.kr 호남 반도체 클러스터 용수',
    '호남 반도체 댐 용수 하수재이용수 하천수 가뭄',
    '호남 반도체 동복댐 주암댐 장흥댐 보성강댐 나주댐',
    # Supply-mix sources are evidence only; old requests and targets must not
    # become new alerts. See honam_event_filter.py for verified milestones.
    '호남 반도체 LNG 열병합 발전사업 허가 입찰 사업자 선정 착공',
    '서남권 반도체 ESS 에너지저장장치 사업자 선정 인허가 전력',
    '호남 반도체 재생에너지 전력구매계약 PPA 체결',
    '광주 군공항 반도체 변전소 송전선 접속 전원 인가',
    'site:me.go.kr 서남권 반도체 LNG ESS 전력',
    'site:motir.go.kr 호남 반도체 전력 에너지저장장치',
    'site:news.samsung.com/kr 호남 반도체 열병합 발전',
    'site:kepco.co.kr 호남 반도체 전력망 접속 변전소',

    '"호남권 반도체 국가산업단지" 교통 도로 철도 교육 의료',
    '"호남권 반도체 국가산업단지" 기반시설 착공 준공',
    # 산단·기업투자·팹 일정
    '"호남권 반도체 국가산업단지" 삼성전자 SK하이닉스 투자 팹',
    '"호남권 반도체 국가산업단지" 착공 양산 준공 일정',
    '호남 반도체 팹 착공 2027년 7월 2028년 일정 조정 국토부',
    '호남 반도체 삼성전자 남측 SK하이닉스 북측 120만평 100만평 배치 입주협약',
    '호남 반도체 63만평 우선개발 성토재 공사 허가 시유지 야적',
    '호남 반도체 신장성 신광주 23㎞ 3.1GW 전원 인가 15만t 송수관로',
    '"호남권 반도체 국가산업단지" 확장 추가 부지 조성계획',
    '광주공항 함평 무안 반도체 클러스터 팹 배후기지',
    '함평 반도체 직접 팹 국가산단 후보지',
    '무안 반도체 소부장 물류 에너지 배후기지',
    '광주공항 반도체 팹 생산거점',
    # 경영진 실사·현장방문은 부지·투자계약의 실행단계 사건이며 특정 기사 URL을 감시하지 않는다.
    '최태원 SK하이닉스 광주 군공항 방문 팹 부지',
    '최태원 호남 반도체 광주 군공항 현장 실사 일정',
    'SK그룹 회장 광주 군공항 반도체 부지 방문 완료',
    'SK하이닉스 최고경영진 광주 반도체 부지 실사 투자협약',
    '삼성전자 이재용 광주 군공항 반도체 실사 협약',
    'site:sk.com 광주 군공항 반도체 최태원',
    'site:news.skhynix.co.kr 광주 반도체 현장 투자',
    '"호남 반도체" 함평 무안 클러스터 추가 부지',
    # 공식자료 우선
    'site:lh.or.kr "호남권 반도체 첨단 국가산업단지"',
    'site:ebid.lh.or.kr "호남권 반도체 첨단 국가산업단지"',
    'site:gwangju.go.kr "호남권 반도체"',
    'site:jeonnam.go.kr "호남권 반도체"',
    'site:molit.go.kr "호남권 반도체"',
    'site:motie.go.kr "호남권 반도체"',
    'site:president.go.kr "남부권 반도체"',
    'site:president.go.kr "호남 반도체"',
    'site:korea.kr "남부권 반도체"',
    'site:korea.kr "호남권 계통관리변전소"',
    'site:mcee.go.kr "호남권 계통관리변전소"',
    'site:mcee.go.kr "호남 반도체"',
    'site:kepco.co.kr "호남 반도체"',
    'site:me.go.kr "장록습지" 람사르',
    'site:ramsar.org Jangrok Korea wetland',
]

BING_QUERIES = [
    "전남광주 반도체 건설인력 공공임대 모듈러 주거대책",
    "광주 반도체 도심융합특구 상무 산정지구 송정역",
    "전남광주 반도체 노바 NOVA 용역비 예산 추경",
    "호남 반도체 덕남정수장 송수관 국비 지방비 용수",
    "광주 반도체 동복댐 용수 지방재정 시의회"
]

STAGES = {
    "1_용역선정_현지조사": ["낙찰", "수행업체", "용역업체", "계약 체결", "현지조사", "현장조사", "환경영향평가", "기후변화영향평가", "개찰", "우선협상", "적격심사"],
    "2_수량수질_조사범위": ["수량", "수질", "유량", "수위", "지하수", "취수", "방류", "조사범위", "조사지점", "측정지점", "계절조사", "갈수기", "홍수기", "완충거리", "저감대책", "생태계", "수생태"],
    "3_람사르_심사결과": ["람사르", "ramsar", "등록", "등재", "등록습지", "심사", "보완", "승인", "지정"],
    "4_정주주거_배후도시": ["정주", "주거", "주택", "배후도시", "배후 주거", "택지", "공공주택", "산정지구", "송정역", "상무 도심융합", "금호타이어", "자족형 도시", "주거종합계획", "주거정책", "미분양", "공실", "가구", "세대", "정주 수요"],
    "5_기반시설_생활SOC": ["전력", "용수", "변전소", "송전", "배전", "전원 인가", "도로", "철도", "교통", "교육", "학교", "의료", "병원", "문화", "생활 soc", "기반시설", "산업용수", "하수", "물류", "공항", "항공화물", "에너지", "분산에너지", "댐", "동복댐", "주암댐", "장흥댐", "보성강댐", "나주댐", "하수재이용수", "재이용수", "하천수", "이수 안전도", "유입량", "유출량", "가뭄", "물 부족", "용수 배분", "목적 외 사용", "사용료", "수자원", "용수 공급", "LNG", "액화천연가스", "열병합", "ESS", "에너지저장장치", "재생에너지", "전력구매계약", "PPA", "발전사업", "발전소", "상업운전", "계통 접속"],
    "6_산단투자_기업일정": ["삼성전자", "sk하이닉스", "팹", "fab", "직접 팹", "투자", "착공", "준공", "양산", "생산시설", "생산거점", "후보지", "국가산단 지정", "산업단지 지정", "추가 확장", "추가 부지", "확장", "기업 투자", "실사", "현장 방문", "현장 실사", "부지 점검", "최고경영진", "최태원", "이재용", "회장", "클러스터", "배후기지", "소부장", "공급망", "다핵"],
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
MATERIAL_TERMS = ["계획", "정책", "조례", "수요", "공급", "검토", "착공", "준공", "양산", "지정", "선정", "계약", "낙찰", "조사", "등록", "심사", "보완", "확장", "투자", "팹", "현장 방문", "실사", "경영진", "회장", "부지 점검", "직접 팹", "생산거점", "후보지", "클러스터", "배후기지", "소부장", "공급망", "물류", "실사", "가구", "명", "억원", "조원", "㎞", "km", "mw", "gw", "만평", "㎡", "지구", "도시", "주택", "전력", "용수", "댐", "하수재이용수", "하천수", "가뭄", "물 부족", "유입량", "유출량", "이수 안전도", "수자원", "ESS", "LNG", "열병합", "에너지저장장치", "전력구매계약", "PPA", "발전사업", "재생에너지"]
POSITIVE = ["선정", "낙찰", "계약 체결", "조사 착수", "현지조사 착수", "승인", "확정", "통과", "착공", "준공", "양산", "기간 단축", "앞당", "확대", "증설"]
NEGATIVE = ["지연", "보완", "재검토", "반려", "중단", "연기", "갈등", "우려", "영향 불가피", "재입찰", "사업기간 연장", "준공 지연", "공급 부족", "병목"]
OFFICIAL_LH_DESIGN_BID = "https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidDegree=00&bidNum=2602775"
OFFICIAL_LH_ENV_BID = "https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidDegree=00&bidNum=2603004"
# 검증된 사건을 한 번만 초기 등록하는 입력. 뉴스 URL 자체를 정기 감시하지 않는다.
VERIFIED_INTAKE_PATH = DATA / "honam_verified_event_intake.json"


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



def canonical_headline_key(title: str, pub: str) -> str:
    # Google News RSS 제목은 보통 마지막 " - 매체명"을 붙인다.
    # 매체명이 뉴스1 / news1.kr처럼 바뀌어도 같은 기사로 보도록 제거한다.
    normalized = re.sub(r"\s+", " ", (title or "").strip().lower())
    if " - " in normalized:
        normalized = normalized.rsplit(" - ", 1)[0].strip()
    published = parse_news_date(pub)
    day = published.strftime("%Y-%m-%d") if published else "unknown"
    return hashlib.sha256(f"{normalized}\n{day}".encode("utf-8")).hexdigest()[:24]


def canonical_url_key(url: str) -> str:
    parsed = urllib.parse.urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    path = re.sub(r"/+$", "", parsed.path or "/")
    if host == "news.google.com":
        # oc, hl 등 추적 쿼리가 달라도 같은 Google News 기사 ID면 동일 근거다.
        basis = f"{host}{path}"
    else:
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        kept = []
        for key, value in pairs:
            low = key.lower()
            if low.startswith("utm_") or low in {"oc", "gclid", "fbclid", "ref", "from"}:
                continue
            kept.append((key, value))
        query = urllib.parse.urlencode(sorted(kept))
        basis = f"{host}{path}" + (f"?{query}" if query else "")
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def resolve_google_news_url(url: str):
    if (urllib.parse.urlparse(url).hostname or "").lower() != "news.google.com":
        return url, False
    try:
        from googlenewsdecoder import new_decoderv1, gnewsdecoder
        decoders = (new_decoderv1, gnewsdecoder)
    except ImportError:
        try:
            from googlenewsdecoder import new_decoderv1
            decoders = (new_decoderv1,)
        except ImportError:
            decoders = ()

    for decoder in decoders:
        try:
            result = decoder(url, interval=0)
            if isinstance(result, dict):
                decoded = str(result.get("decoded_url") or result.get("url") or "").strip()
            elif isinstance(result, str):
                decoded = result.strip()
            else:
                decoded = ""
            host = (urllib.parse.urlparse(decoded).hostname or "").lower()
            if decoded.startswith("https://") and host and host != "news.google.com":
                return decoded, True
        except Exception:
            continue

    # 페이지 리디렉션도 실제 기사 도메인으로 확인될 때만 원문으로 표시한다.
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as response:
            resolved = response.geturl()
        host = (urllib.parse.urlparse(resolved).hostname or "").lower()
        if resolved.startswith("https://") and host and not host.endswith("google.com"):
            return resolved, True
    except Exception:
        pass
    return url, False


def normalize_publisher_name(value: str) -> str:
    raw = (value or "").strip()
    low = raw.lower()
    aliases = {
        "news1.kr": "뉴스1",
        "news1": "뉴스1",
        "뉴스1": "뉴스1",
    }
    return aliases.get(low, raw)


def identify_publisher(url: str, fallback: str):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    fallback = normalize_publisher_name(fallback)
    if host == "news.google.com":
        return f"Google 뉴스 경유 · {fallback}" if fallback else "Google 뉴스 경유"
    if host in {"n.news.naver.com", "news.naver.com"}:
        return f"{fallback}(네이버)" if fallback else "네이버뉴스"
    if host == "v.daum.net":
        return f"{fallback}(다음)" if fallback else "다음뉴스"
    return fallback or host or "웹 원문"


def source_collection_health(success_count: int, failure_count: int, total_count: int) -> str:
    """Data availability is not the same as no newly published event."""
    if total_count < 1 or success_count < 0 or failure_count < 0 or success_count + failure_count != total_count:
        raise ValueError("Invalid RSS source collection counters")
    if success_count == 0:
        return "전체 조회 실패(신규 변화 없음으로 판정 금지)"
    if failure_count:
        return f"부분 조회 실패({failure_count}/{total_count}개 검색어, 해당 원천 확인 전)"
    return "조회 성공(신규 발표 여부는 사건 판정 결과 참조)"


def _direct_news_url(link):
    link = html.unescape(str(link or "").strip())
    parsed = urllib.parse.urlparse(link)
    host = (parsed.hostname or "").lower()
    if host == "bing.com" or host.endswith(".bing.com"):
        target = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
        if target.startswith("https://"):
            link = target
            parsed = urllib.parse.urlparse(link)
            host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host or host in ("localhost", "127.0.0.1") or re.fullmatch(r"\d+(?:\.\d+){3}", host):
        return ""
    return link


def _rss_items(root):
    items = []
    for node in root.findall("./channel/item"):
        title = clean_text(node.findtext("title") or "")
        link = _direct_news_url(node.findtext("link") or "")
        if not title or not link:
            continue
        desc = clean_text(node.findtext("description") or "")
        pub = clean_text(node.findtext("pubDate") or "")
        source = ""
        for el in node:
            if el.tag.split("}")[-1].lower() == "source":
                source = clean_text(el.text or "")
                break
        if not source:
            host = (urllib.parse.urlparse(link).hostname or "").removeprefix("www.")
            source = host if host not in ("news.google.com", "bing.com") else ""
        items.append({
            "id": hashlib.sha256((title + "\n" + link).encode()).hexdigest()[:24],
            "story_key": story_key(title, source, pub),
            "headline_key": canonical_headline_key(title, pub),
            "url_key": canonical_url_key(link),
            "title": title, "link": link, "description": desc,
            "pubDate": pub, "source": source,
        })
    return items


def google_news_items(query: str):
    rss = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    return _rss_items(ET.fromstring(fetch(rss)))


def bing_news_items(query: str):
    rss = f"https://www.bing.com/news/search?q={urllib.parse.quote(query)}&format=rss&setlang=ko-kr"
    return _rss_items(ET.fromstring(fetch(rss, timeout=10)))

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


def headline_identity(title):
    return re.sub(r"[^0-9a-z가-힣]", "", str(title or "").rsplit(" - ", 1)[0].casefold())


def article_body(raw, expected_title):
    """Require a matching publisher headline and an article body, not menu text."""
    expected = headline_identity(expected_title)
    heads = re.findall(r"<(?:title|h1)\b[^>]*>(.*?)</(?:title|h1)>", raw, re.I | re.S)
    if len(expected) < 10 or not any(expected in headline_identity(clean_text(h)) for h in heads):
        return ""
    def locate(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("articleBody"), str) and len(obj["articleBody"]) >= 60:
                return obj["articleBody"]
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    found = locate(value)
                    if found:
                        return found
        if isinstance(obj, list):
            for value in obj:
                found = locate(value)
                if found:
                    return found
        return ""
    for script in re.findall(r'<script\b[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>', raw, re.I | re.S):
        try:
            found = locate(json.loads(script))
            if found:
                return "\n".join(clean_text(p) for p in found.splitlines() if clean_text(p))
        except (ValueError, TypeError):
            continue
    areas = re.findall(r"<article\b[^>]*>(.*?)</article>", raw, re.I | re.S)
    for area in areas:
        parts = [clean_text(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", area, re.I | re.S)]
        parts = [p for p in parts if len(p) >= 25 and len(re.findall(r"[가-힣]", p)) >= 15 and not any(x in p for x in ("무단 전재", "재판매 및 DB 금지", "저작권자", "제보는 카카오톡"))]
        if parts:
            return "\n".join(dict.fromkeys(parts))
    return ""


def fetch_article_excerpt(url: str, limit: int = 12000, expected_title: str = "") -> str:
    if not url or (urllib.parse.urlparse(url).hostname or "").lower() in {"news.google.com", "bing.com", "www.bing.com"}:
        return ""
    try:
        return article_body(fetch(url, timeout=14).decode("utf-8", errors="ignore"), expected_title)[:limit]
    except Exception:
        return ""


def restore_publisher_url(item):
    """A bounded exact-title alternative search; never fabricate article URLs."""
    domains = {"연합뉴스":"yna.co.kr", "뉴시스":"newsis.com", "뉴스1":"news1.kr",
               "남도일보":"namdonews.com", "무등일보":"mdilbo.com", "전남일보":"jnilbo.com",
               "KBC광주방송":"ikbc.co.kr", "녹색경제신문":"greened.kr"}
    source = normalize_publisher_name(item.get("source", ""))
    domain = domains.get(source)
    expected = headline_identity(item.get("title"))
    if not domain or len(expected) < 10:
        return ""
    try:
        for candidate in bing_news_items('"' + item["title"].rsplit(" - ", 1)[0] + '" ' + source):
            url = candidate.get("link", "")
            host = (urllib.parse.urlparse(url).hostname or "").lower()
            if headline_identity(candidate.get("title")) == expected and (host == domain or host.endswith("." + domain)):
                return url
    except Exception:
        pass
    return ""


def article_fact_lines(body):
    terms = ("건설인력", "공공임대", "모듈러", "주거", "정주", "도심융합특구", "산정지구", "송정역", "노바", "예산", "국비", "지방비", "사업비", "설계", "협의체", "용수", "정수장", "송수관", "동복댐", "전력", "착공", "준공", "양산", "계약", "낙찰", "지정", "공급", "인허가", "환경영향평가", "람사르", "현지조사", "수량", "수질")
    result = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", body or ""):
        text = re.sub(r"\s+", " ", part).strip()
        if 0 < len(text) <= 450 and any(term in text for term in terms) and (re.search(r"\d[\d,.]*\s*(?:조|억|만|천|명|호|가구|년|월|일|평|㎡|km|㎞|GW|MW|톤|t|%)", text, re.I) or any(s in text for s in ("검토", "미반영", "미편성", "협의", "확보", "착수", "승인", "지시", "요구", "추진", "반려", "지연"))):
            if text not in result:
                result.append(text)
    return result

def compact_news_item(item):
    resolved_url, resolved = resolve_google_news_url(item.get("link", ""))
    if (urllib.parse.urlparse(resolved_url).hostname or "").lower() in ("news.google.com", "bing.com", "www.bing.com"):
        alternate = restore_publisher_url(item)
        if alternate:
            resolved_url, resolved = alternate, True
    else:
        resolved = bool(_direct_news_url(resolved_url))
    stages = item.get("stages", [])
    host = (urllib.parse.urlparse(resolved_url).hostname or "").lower()
    official_hosts = [
        "lh.or.kr", "gwangju.go.kr", "jeonnam.go.kr", "molit.go.kr", "motie.go.kr",
        "me.go.kr", "mcee.go.kr", "president.go.kr", "ramsar.org", "korea.kr",
        "nars.go.kr", "kepco.co.kr", "kwater.or.kr",
        "motir.go.kr", "kpx.or.kr", "energy.or.kr", "news.samsung.com",
    ]
    official = any(host == h or host.endswith("." + h) for h in official_hosts)
    excerpt = fetch_article_excerpt(resolved_url, expected_title=item.get("title", "")) if resolved else ""
    body_status = "발행사 본문 확인" if excerpt else "본문 미확보(제목·검색 요약만 확인)"
    return {
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "body_excerpt": excerpt,
        "body_status": body_status,
        "fact_lines": article_fact_lines(excerpt),
        "source": identify_publisher(resolved_url, item.get("source", "")),
        "published": item.get("pubDate", ""),
        "url": resolved_url,
        "url_resolved": resolved,
        "source_status": "공식자료" if official and excerpt else ("공식 링크·본문 미확보" if official else "보도 단계"),
        "stages": stages,
        "stage_labels": [STAGE_LABELS.get(s, s) for s in stages],
        "impact": item.get("impact", "영향 확인 필요"),
        "reason": why_it_matters(stages),
    }


def load_state():
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_ids": [], "seen_story_keys": [], "seen_headline_keys": [], "seen_url_keys": [], "official_page_signatures": {}}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state.setdefault("seen_ids", [])
        state.setdefault("seen_story_keys", [])
        state.setdefault("seen_headline_keys", [])
        state.setdefault("seen_url_keys", [])
        state.setdefault("official_page_signatures", {})
        return state
    except Exception as exc:
        raise RuntimeError("호남 상태 파일 읽기 실패: 기존 상태 초기화 금지") from exc


def official_signature(url: str):
    text = clean_text(fetch(url).decode("utf-8", errors="ignore"))
    text = re.sub(r"다운로드\s*:?\s*\d+|조회수\s*:?\s*\d+", " ", text)
    parts = []
    for kw in ["호남권 반도체", "입찰", "개찰", "낙찰", "계약", "착수", "입찰진행"]:
        for m in re.finditer(re.escape(kw), text, flags=re.I):
            parts.append(text[max(0, m.start()-160):m.end()+240])
    joined = " | ".join(dict.fromkeys(parts[:30]))
    return hashlib.sha256(joined.encode()).hexdigest()


def registered_covered_headlines():
    if not VERIFIED_INTAKE_PATH.exists():
        return set()
    data = json.loads(VERIFIED_INTAKE_PATH.read_text(encoding="utf-8"))
    return {str(key) for event in data.get("events", []) for key in event.get("covered_headline_keys", [])
            if re.fullmatch(r"[0-9a-f]{24}", str(key))}


def verified_intake_events(state: dict) -> list[dict]:
    """Register independently checked event evidence once, by event family.

    This is an incident intake, not a URL subscription. The permanent topic
    queries continue to discover independent follow-up changes.
    """
    if not VERIFIED_INTAKE_PATH.exists():
        return []
    payload = json.loads(VERIFIED_INTAKE_PATH.read_text(encoding="utf-8"))
    seen = set(state.get("seen_event_keys") or [])
    out = []
    for event in payload.get("events", []):
        family = str(event.get("event_family") or "").strip()
        if not family or not family.startswith("honam_"):
            continue
        event_key = hashlib.sha256(("family|" + family).encode("utf-8")).hexdigest()[:28]
        if event_key in seen:
            continue
        for src in event.get("evidence", []):
            url = str(src.get("url") or "").strip()
            if not url.startswith("https://"):
                continue
            out.append({
                "title": str(event.get("title") or ""),
                "description": str(event.get("description") or ""),
                "source": str(src.get("source") or "보도"),
                "published": str(src.get("published_rfc2822") or ""),
                "url": url,
                "url_resolved": True,
                "source_status": "보도 단계",
                "event_family": family,
                "intake_verified": True,
                "alert_type": str(event.get("alert_type") or ""),
                "recovery": bool(event.get("recovery")),
                "body_status": "등록된 출처별 검증 메모",
                "verification_note": str(event.get("verification_note") or ""),
                "summary_lines": list(event.get("summary_lines") or []),
                "detail_lines": list(event.get("detail_lines") or []),
                "event_phase": str(event.get("event_phase") or "scheduled"),
                "stages": list(event.get("stages") or ["6_산단투자_기업일정"]),
                "stage_labels": [STAGE_LABELS.get(s, s) for s in (event.get("stages") or ["6_산단투자_기업일정"])],
                "impact": str(event.get("impact") or "경영진 현장점검 예정·실제 투자 확정 아님"),
                "reason": str(event.get("reason") or "기존 사장단 부지검토에서 회장 현장방문 예정으로 진전, 향후 투자계약·전력·용수 및 인허가 협의 추적"),
            })
    return out


def main():
    now_dt = dt.datetime.now(KST)
    now = now_dt.isoformat(timespec="seconds")
    state = load_state()
    initialized = bool(state.get("initialized", True))
    monitor_started = parse_iso_kst(state.get("monitor_started_at_kst", "")) or parse_iso_kst(state.get("updated_at_kst", "")) or now_dt
    seen_ids = set(state.get("seen_ids", []))
    seen_keys = set(state.get("seen_story_keys", []))
    seen_headlines = set(state.get("seen_headline_keys", []))
    seen_urls = set(state.get("seen_url_keys", []))
    errors, all_items = [], []
    rss_success_count = 0
    rss_failure_count = 0

    for query in QUERIES:
        try:
            all_items.extend(google_news_items(query))
            rss_success_count += 1
        except Exception as exc:
            rss_failure_count += 1
            errors.append(f"RSS 실패: {query}: {type(exc).__name__}: {exc}")

    priority = [query for query in QUERIES if query in BING_QUERIES]
    bing_ok, bing_failed = 0, 0
    for query in priority:
        try:
            all_items.extend(bing_news_items(query))
            bing_ok += 1
        except Exception as exc:
            bing_failed += 1
            errors.append(f"Bing RSS 실패: {query}: {type(exc).__name__}: {exc}")
    rss_success_count += bing_ok
    rss_failure_count += bing_failed
    rss_health = source_collection_health(rss_success_count, rss_failure_count, len(QUERIES) + len(priority))
    if rss_success_count == 0:
        # An outright source outage must not advance dedupe cursors or turn
        # the absence of data into "no news". The next scheduled scan retries.
        raise RuntimeError("호남 반도체 전체 RSS 수집 실패: 신규 변화 없음으로 판정·상태 갱신 금지")

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
    covered_headlines = registered_covered_headlines()
    broad_cutoff = max(monitor_started, now_dt - dt.timedelta(days=7))
    for item in relevant_items:
        if (
            item["id"] in seen_ids
            or item["story_key"] in seen_keys
            or item.get("headline_key") in seen_headlines
            or item.get("headline_key") in covered_headlines
            or item.get("url_key") in seen_urls
        ):
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

    # 검증된 신규 사건을 먼저 처리해 RSS 색인 지연으로 누락되는 것을 방지한다.
    # 최초 발송 뒤에는 기존 seen_event_keys로 중복 차단한다.
    intake_items = verified_intake_events(state) if initialized else []
    send_items = intake_items + ([compact_news_item(i) for i in new_items] if initialized else [])
    send_official = official_changes if initialized else []

    pending = {
        "initialized": True,
        "scope_version": "v5_core3_plus_multinode_cluster",
        "monitor_started_at_kst": state.get("monitor_started_at_kst") or monitor_started.isoformat(timespec="seconds"),
        "updated_at_kst": now,
        "seen_ids": list(dict.fromkeys([i["id"] for i in relevant_items] + list(seen_ids)))[:2000],
        "seen_story_keys": list(dict.fromkeys([i["story_key"] for i in relevant_items] + list(seen_keys)))[:3000],
        "seen_headline_keys": list(dict.fromkeys([i.get("headline_key") for i in relevant_items if i.get("headline_key")] + list(seen_headlines)))[:3000],
        "seen_url_keys": list(dict.fromkeys([i.get("url_key") for i in relevant_items if i.get("url_key")] + list(seen_urls)))[:3000],
        "official_page_signatures": signatures,
        "last_relevant_count": len(relevant_items),
        "last_stale_suppressed_count": len(stale),
        "errors": errors[-20:],
        "rss_collection_health": rss_health,
        "rss_failed_queries": rss_failure_count,
        "rss_successful_queries": rss_success_count,
        "bing_successful_queries": bing_ok,
        "bing_failed_queries": bing_failed,
        "official_source_health": "일부 원천 조회 실패(상태 변화 없음으로 단정 금지)" if any(e.startswith("LH ") for e in errors) else "LH 핵심 페이지 조회 성공",
        "alert_basis": "topic_event_official_state_change",
        "article_role": "evidence_and_crosscheck_only",
        "baseline_guard": "suppress_20260922_roadmap_rehash_unless_execution_or_status_changes",
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if send_items or send_official:
        ALERT_PATH.write_text(json.dumps({"title": "호남 반도체 국가산단", "checked_at_kst": now, "new_count": len(send_items) + len(send_official), "new_items": send_items, "official_changes": send_official, "rss_failed_queries": rss_failure_count, "official_source_partial_failure": any(e.startswith("LH ") for e in errors)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif ALERT_PATH.exists():
        ALERT_PATH.unlink()

    STATUS_PATH.write_text("\n".join([
        "# 호남 반도체 국가산단 웹감시 상태",
        f"- 확인시각(KST): {now}",
        f"- 관련 검색결과: {len(relevant_items)}건",
        f"- 새 관련정보: {len(send_items)}건",
        f"- 과거·중복 차단: {len(stale)}건",
        f"- 공식 핵심페이지 변경: {len(send_official)}건",
        f"- RSS 원천 조회: {rss_health}",
        f"- LH 공식 원천: {'일부 조회 실패(신규 변화 없음으로 단정 금지)' if any(e.startswith('LH ') for e in errors) else '조회 성공'}",
        f"- 전체 수집 실패 건수: {len(errors)}건(실패 원천만 해당, 나머지 정상 수집과 구별)",
        "- 감시 범위: 환경 3단계 + 정주·주거 + 전력·용수·교통·생활 인프라(ESS·LNG 열병합·재생에너지·전력구매계약·인허가·전원 인가) + 산단·기업투자·팹 일정 + 광주·함평·무안 다핵 클러스터",
    ]) + "\n", encoding="utf-8")
    print(f"relevant={len(relevant_items)} new={len(send_items)} stale_suppressed={len(stale)} official_changes={len(send_official)} initialized_before={initialized} rss_ok={rss_success_count} rss_failed={rss_failure_count} official_source_partial_failure={any(e.startswith('LH ') for e in errors)}")


if __name__ == "__main__":
    main()
