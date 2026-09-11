#!/usr/bin/env python3
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import janus_watch_v2 as j2
import janus_watch_v3 as j3

# 한국의 Westinghouse 지분 인수·투자·공동사업 변화까지 기존 원전·Janus 감시에 통합한다.
# 사용자가 제공한 개별 기사는 '그 기사 자체를 계속 감시'하는 대상이 아니라,
# 감시 범위와 이슈 판정규칙을 넓히는 사례다.
# 새 기사 수가 늘었다는 이유만으로는 알리지 않고 거래단계·조건·공식입장이 바뀔 때만 알린다.
KOR_QUERY = "웨스팅하우스 지분 인수 한국전력 산업통상부 한수원 브룩필드 카메코 when:14d"
ENG_QUERY = "Westinghouse stake Korea KEPCO KHNP Brookfield Cameco when:14d"
OFFICIAL_QUERY = "웨스팅하우스 산업통상부 한국전력 공식 발표 when:30d"

for name, query in [
    ("웨스팅하우스 지분·한국 뉴스", KOR_QUERY),
    ("웨스팅하우스 지분·해외 뉴스", ENG_QUERY),
    ("웨스팅하우스 지분·공식입장 추적", OFFICIAL_QUERY),
]:
    url = (
        "https://news.google.com/rss/search?q=" + quote_plus(query)
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )
    if not any(s.get("url") == url for s in j2.base.SOURCES):
        j2.base.SOURCES.append({"name": name, "url": url, "kind": "westinghouse_rss"})

_WEC_CORE = [
    "westinghouse", "웨스팅하우스", "wec",
]
_WEC_TRANSACTION = [
    "지분", "인수", "투자", "공동 인수", "공동인수", "출자", "주주", "경영 참여",
    "stake", "equity", "acquisition", "invest", "shareholder", "buyout", "ipo", "상장", "기업공개",
    "brookfield", "브룩필드", "cameco", "카메코", "kepco", "한국전력", "한전", "khnp", "한수원",
    "산업통상부", "산업부", "미국 정부", "u.s. government", "ap1000", "지식재산", "입찰 제한",
]

# 이슈 상태가 실제로 바뀌었다고 볼 수 있는 신호.
# 단순 '검토', '가능성', '쟁점', '전망', '주가반응'은 여기에 포함하지 않는다.
_WEC_STATE_CHANGE = [
    "공식 발표", "공식 확인", "공식 부인", "사실과 다르", "부인",
    "합의", "계약", "loi", "mou", "양해각서", "실사", "due diligence",
    "협상 개시", "협상 착수", "본협상", "우선협상", "term sheet", "텀시트",
    "취득", "매각", "지분율", "인수가격", "매각가격", "출자액", "투자금",
    "경영권", "이사회", "의결권", "voting rights",
    "cfius", "nrc", "승인", "인가",
    "사업권", "설계권", "조달권", "시공권", "입찰 제한", "지식재산권",
    "상장 신청", "ipo filing", "ipo 신청",
]

_WEC_COMMENTARY = [
    "고차방정식", "열쇠", "주식인가", "사업인가", "전망", "분석", "진단", "수혜",
    "들썩", "특징주", "상승세", "주목", "기대", "논란", "평가",
]


def _clean_rss_title(title: str):
    title = j2.base.norm(title)
    # Google News 제목 뒤의 " - 매체명"은 source 태그와 중복이므로 제거한다.
    return re.sub(r"\s+-\s+[^-]{2,60}$", "", title).strip()


def _rss_relevant(title: str, outlet: str = ""):
    low = title.lower()
    outlet_low = (outlet or "").lower()
    if not (any(term in low for term in _WEC_CORE) and any(term in low for term in _WEC_TRANSACTION)):
        return False

    # 공식 당사자·정부의 직접 발표는 상태변화 후보로 통과.
    if any(x in outlet_low for x in [
        "산업통상부", "정책브리핑", "한국전력", "한수원", "kepco", "khnp",
        "westinghouse", "cameco", "brookfield",
    ]):
        return True

    # 거래단계·조건·권한·규제의 실제 변화가 제목에서 확인되는 경우만 통과.
    if any(term in low for term in _WEC_STATE_CHANGE):
        # 해설/평가 기사라면 더 강한 실행 신호가 함께 있어야 한다.
        if any(term in low for term in _WEC_COMMENTARY):
            strong = [
                "공식", "합의", "계약", "loi", "mou", "실사", "취득", "매각",
                "지분율", "인수가격", "출자액", "투자금", "cfius", "nrc", "승인",
            ]
            return any(term in low for term in strong)
        return True

    # 가격·지분율 같은 새 거래조건이 숫자로 직접 제시된 경우.
    if re.search(r"(?:\$|달러|원|억원|조원|%|퍼센트).*?\d|\d[\d,.]*\s*(?:억달러|달러|억원|조원|%)", low):
        return True

    return False


def _rss_items(source, page_text):
    try:
        root = ET.fromstring(page_text)
    except Exception as exc:
        j2._append_error(f"Westinghouse RSS 파싱 실패 | {source['url']} | {exc}")
        return []

    rows = []
    now = datetime.now(timezone.utc)
    for item in root.findall(".//item"):
        title = _clean_rss_title(item.findtext("title") or "")
        link = j2.base.norm(item.findtext("link") or "")
        source_node = item.find("source")
        outlet = j2.base.norm(source_node.text if source_node is not None and source_node.text else "")
        pub = j2.base.norm(item.findtext("pubDate") or "")
        if not title or not link or not _rss_relevant(title, outlet):
            continue
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = (now - dt.astimezone(timezone.utc)).total_seconds() / 86400
            if age_days > 30:
                continue
        except Exception:
            pass
        rows.append({
            "source": outlet or source["name"],
            "title": title[:500],
            "url": link,
            "kind": "westinghouse_stake",
            "published": pub,
        })
        if len(rows) >= 4:
            break
    return rows


_ORIGINAL_EXTRACT = j2.base.extract_items


def _extract_with_westinghouse(source, page_text):
    if source.get("kind") == "westinghouse_rss":
        return _rss_items(source, page_text)
    return _ORIGINAL_EXTRACT(source, page_text)


j2.base.extract_items = _extract_with_westinghouse

_ORIGINAL_CATEGORY = j2._event_category
_ORIGINAL_MEANING = j2._event_meaning
_ORIGINAL_HIGHLIGHTS = j2._macro_highlights
_ORIGINAL_BOTTLENECKS = j2._bottleneck_lines
_ORIGINAL_NEXT_CHECK = j2._next_check


def _is_westinghouse_event(event):
    return event.get("kind") == "westinghouse_stake"


def _status_text(event):
    title = (event.get("title") or "").lower()
    source = (event.get("source") or "").lower()
    official_source = any(x in source for x in ["정책브리핑", "산업통상부", "한국전력", "한수원", "westinghouse", "cameco", "brookfield"])
    if any(x in title for x in ["사실과 다름", "부인", "denies", "not true"]):
        return "공식 부인·정정" if official_source else "부인 보도"
    if official_source and any(x in title for x in ["합의", "계약", "인수", "취득", "투자 확정", "agreement", "acquisition", "investment"]):
        return "공식 확인 가능성 높음 — 원문 재확인 필요"
    if any(x in title for x in ["실사", "협상 개시", "협상 착수", "loi", "mou", "합의", "계약"]):
        return "거래 단계 진전 — 공식 원문·조건 확인 필요"
    return "새 물질적 조건 확인 — 공식 확정 여부 교차검증 필요"


def _event_category_v4(event, resolved_title):
    if _is_westinghouse_event(event):
        return "지분투자·원전동맹"
    return _ORIGINAL_CATEGORY(event, resolved_title)


def _event_meaning_v4(event, category):
    if _is_westinghouse_event(event):
        return (
            "Westinghouse 지분 참여가 실제화되면 한국의 미국 AP1000 사업 참여가 단순 기자재·시공을 넘어 "
            "설계·조달·사업개발로 넓어질 여지가 있습니다. 다만 지분투자와 설계·조달권, 지식재산권·입찰제한 완화는 별도 계약 사안이므로 분리해서 확인해야 합니다."
        )
    return _ORIGINAL_MEANING(event, category)


def _macro_highlights_v4(event):
    if _is_westinghouse_event(event):
        return [
            ("현재 단계", _status_text(event)),
            ("핵심 당사자", "한국 정부·한국전력 / Westinghouse / Brookfield / Cameco"),
            ("확인할 거래조건", "지분율 · 인수가격 · 재원 · 경영참여권"),
            ("사업 연결", "AP1000 설계·조달·시공 범위 · 지식재산권 · 입찰 지역 제한"),
        ]
    return _ORIGINAL_HIGHLIGHTS(event)


def _bottleneck_lines_v4(event):
    if _is_westinghouse_event(event):
        return [
            "2026년 8월 25일 산업통상부가 '한·미 공동출자 WEC 지분 인수' 보도를 공식 부인한 전력이 있어 새 보도는 반드시 공식자료와 교차검증",
            "Brookfield·Cameco가 실제로 어느 지분을 어떤 가격에 매각할지 미확정",
            "한국의 지분 취득이 성사돼도 AP1000 설계·조달·시공 권한 확대는 별도 계약 필요",
            "미국 원전 프로젝트 참여 시 CFIUS와 NRC 외국인 소유·통제 관련 건별 심사 가능",
        ]
    return _ORIGINAL_BOTTLENECKS(event)


def _next_check_v4(event, category):
    if _is_westinghouse_event(event):
        return (
            "산업통상부·한국전력·한수원·Westinghouse·Brookfield·Cameco 공식 발표 · "
            "LOI/MOU/실사 착수 · 지분율·인수가격·재원 · CFIUS/NRC 심사 · AP1000 설계·조달·시공 권한"
        )
    return _ORIGINAL_NEXT_CHECK(event, category)


j2._event_category = _event_category_v4
j2._event_meaning = _event_meaning_v4
j2._macro_highlights = _macro_highlights_v4
j2._bottleneck_lines = _bottleneck_lines_v4
j2._next_check = _next_check_v4

if __name__ == "__main__":
    sys.exit(j2.base.main())
