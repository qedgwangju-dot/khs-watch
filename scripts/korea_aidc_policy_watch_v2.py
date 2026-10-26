#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

try:
    from alert_timeline_dates import extract_original_dates, korean_date as source_korean_date, parse_timestamp, timeline_lines, verified_age_days
except ModuleNotFoundError:
    from scripts.alert_timeline_dates import extract_original_dates, korean_date as source_korean_date, parse_timestamp, timeline_lines, verified_age_days

try:
    import korea_aidc_policy_watch as base
except ModuleNotFoundError:
    from scripts import korea_aidc_policy_watch as base

try:
    from googlenewsdecoder import new_decoderv1
except Exception:  # pragma: no cover
    new_decoderv1 = None

STATE = base.STATE
OUT = base.OUT
ALERT = base.ALERT
PENDING = base.PENDING
STATUS = base.STATUS
META = OUT / "korea_aidc_policy_alert_meta.json"
KST = base.KST
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}
MAX_AGE_DAYS = base.MAX_AGE_DAYS
SGC_GUNSAN_RSS = (
    "https://news.google.com/rss/search?q="
    + quote_plus('("SGC에너지" OR "SGC AI 인프라") ("AIDC" OR "AI 데이터센터") (군산 OR "60MW" OR "300MW" OR 착공 OR 운영 OR 본계약 OR KT클라우드)')
    + "&hl=ko&gl=KR&ceid=KR:ko"
)
AIDC_ECOSYSTEM_RSS = (
    "https://news.google.com/rss/search?q="
    + quote_plus('("AIDC 생태계" OR "인공지능 데이터센터 생태계" OR "AI 데이터센터 규제") ("규제합리화" OR "인허가" OR "소부장" OR "2000억원" OR "2천억원" OR "특구")')
    + "&hl=ko&gl=KR&ceid=KR:ko"
)
AIDC_ECOSYSTEM_OFFICIAL_RSS = (
    "https://news.google.com/rss/search?q="
    + quote_plus('site:korea.kr ("AIDC" OR "인공지능 데이터센터") ("규제합리화" OR "생태계 지원" OR "2000억원")')
    + "&hl=ko&gl=KR&ceid=KR:ko"
)
EXTRA_RSS_SOURCES = (
    ("국내 AIDC 사업 실행", False, SGC_GUNSAN_RSS),
    ("AIDC 생태계 지원 언론", False, AIDC_ECOSYSTEM_RSS),
    ("AIDC 생태계 공식자료", True, AIDC_ECOSYSTEM_OFFICIAL_RSS),
)

# 검색엔진이 누락해도 원문을 직접 다시 확인한다. 이 URL은 정책 기준선일 뿐
# 검증 성공·신규 상태 상승이 없으면 알림으로 만들지 않는다.
AIDC_ECOSYSTEM_OFFICIAL_BASELINE = {
    "id": digest("2026-10-23|aidc-ecosystem-government-brief") if "digest" in globals() else "aidc-20261023-official",
    "title": "인공지능 데이터센터(AIDC) 생태계 지원 방안 발표",
    "publisher": "국무조정실",
    "source": "대한민국 정책브리핑",
    "official": True,
    "url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156786291",
    "published": "Fri, 23 Oct 2026 05:00:00 GMT",
    "category": "AIDC 생태계 지원 방안",
    "stage": 3,
}



def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def semantic_key(row: dict[str, Any]) -> str:
    """URL·언론사·기사 제목 해시가 아니라 사업·법령의 의미 있는 상태로 분류."""
    title = base.norm(str(row.get("title", ""))).lower()
    if ("sgc에너지" in title or "sgc ai 인프라" in title) and (
        "군산" in title or "300mw" in title or "60mw" in title
    ):
        if "운영" in title or "시운전" in title:
            return "aidc|sgc-gunsan|operation"
        if "착공" in title:
            return "aidc|sgc-gunsan|groundbreaking"
        if "본계약" in title or "계약 완료" in title:
            return "aidc|sgc-gunsan|contract"
        if "kt클라우드" in title or "kt cloud" in title:
            return "aidc|sgc-gunsan|operator-partner"
        return "aidc|sgc-gunsan|plan"
    if "알박기" in title and ("93%" in title or "신청 물량" in title or "신청물량" in title):
        return "aidc|anti-hoarding|queue-evidence"
    if "알박기" in title and ("법 개정" in title or "매매 제한" in title or "매각" in title):
        return "aidc|anti-hoarding|legal-limit"
    if "세액공제" in title or "자가 소비" in title or "자가소비" in title:
        return "aidc|tax-credit|eligibility"
    if "그리드코드" in title or "계통 연계 규정" in title:
        return "aidc|grid-code|requirements"
    if "입법예고" in title:
        return "aidc|decree-preannouncement"
    if any(x in title for x in ("시행령 확정", "시행령 제정", "국무회의", "시행령 공포")):
        return "aidc|decree-final"
    if any(x in title for x in ("하위법령", "공개토론회", "밑그림")):
        return "aidc|subordinate-rules-design"
    if "전력계통영향평가" in title or "전력 특례" in title:
        return "aidc|power-special"
    if "특구" in title and any(x in title for x in ("지정", "확정", "특례", "지원")):
        return "aidc|special-zone"
    if ("전원 인가" in title or "착공" in title or "발주" in title) and "aidc" in title:
        return "aidc|project-execution|unverified"

    # 알 수 없는 제목을 새 사건으로 자동 등록하지 않는다. 검증 대기만 기록.
    return "aidc|unclassified"

def event_level(row: dict[str, Any]) -> int:
    key = semantic_key(row)
    if key.startswith("aidc|sgc-gunsan|"):
        stage = key.rsplit("|", 1)[-1]
        return {"plan": 31, "operator-partner": 41, "contract": 51,
                "groundbreaking": 61, "operation": 71}.get(stage, 31)
    if key in ("aidc|unclassified", "aidc|project-execution|unverified"):
        return 0
    if key in ("aidc|tax-credit|eligibility", "aidc|grid-code|requirements"):
        # 언론 발언(20)·정부 확정 규칙(65)은 서로 다른 정책 단계.
        return 65 if row.get("official") and str(row.get("category")) == "시행령 확정" else (
            45 if row.get("official") else 20
        )
    return base.event_level(row)

def collapse(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(semantic_key(row), []).append(row)
    result: list[dict[str, Any]] = []
    for key, members in grouped.items():
        best = max(
            members,
            key=lambda r: (
                event_level(r),
                base.source_score(r),
                len(re.findall(r"\d+(?:\.\d+)?(?:gw|mw|%|년|일)?", str(r.get("title", "")).lower())),
                str(r.get("published", "")),
            ),
        ).copy()
        best["event_key"] = key
        best["members"] = members
        result.append(best)
    result.sort(
        key=lambda r: (
            event_level(r),
            base.parse_date(str(r.get("published", ""))) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return result


def resolve_url(url: str) -> str:
    url = str(url or "").strip()
    if not url or "news.google.com" not in url:
        return url
    if new_decoderv1 is not None:
        try:
            decoded = new_decoderv1(url, interval=0.15)
            if isinstance(decoded, dict) and decoded.get("status") and decoded.get("decoded_url"):
                return str(decoded["decoded_url"]).strip()
        except Exception as exc:  # noqa: BLE001
            print(f"aidc_google_news_decode_failed={type(exc).__name__}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        response.raise_for_status()
        if response.url and "news.google.com" not in response.url:
            return response.url
    except Exception as exc:  # noqa: BLE001
        print(f"aidc_google_news_redirect_failed={type(exc).__name__}")
    return url


def clean_paragraph(text: str) -> str:
    value = " ".join(str(text or "").split())
    noise = ("재판매 및 db 금지", "무단전재", "copyright", "기사제보", "많이 본", "관련기사")
    if any(x in value.lower() for x in noise):
        return ""
    return value


def enrich(row: dict[str, Any], session: requests.Session) -> dict[str, Any]:
    result = row.copy()
    resolved = resolve_url(str(row.get("url", "")))
    if resolved:
        result["url"] = resolved
    if not resolved or "news.google.com" in resolved:
        result["article_body"] = ""
        result["enrich_error"] = "Google News 원문 링크 복원 실패"
        return result
    try:
        response = session.get(resolved, headers=HEADERS, timeout=20, allow_redirects=True)
        response.raise_for_status()
        if response.url:
            result["url"] = response.url
        soup = BeautifulSoup(response.text, "html.parser")
        # 원문 게시일·수정일·법령 시행일과 Google News RSS 노출일은 분리한다.
        evidence = extract_original_dates(response.text)
        result["timeline_evidence"] = evidence
        result["rss_published"] = str(result.get("published", ""))
        if evidence.get("published"):
            from email.utils import format_datetime
            parsed = parse_timestamp(evidence["published"])
            if parsed is not None:
                result["published"] = format_datetime(parsed)
                result["date_verified_from_publisher"] = True
        else:
            result["date_verified_from_publisher"] = False
        for node in soup.select("script, style, noscript, nav, footer, header, aside"):
            node.decompose()
        selectors = (
            "article p", "#articleBody p", "#article_body p", "#textBody p",
            ".articleBody p", ".article-body p", ".article_view p", ".article-view p",
            ".view_text p", ".viewer p", ".news_body p", ".news-body p", "main p",
        )
        best: list[str] = []
        for selector in selectors:
            paragraphs = [clean_paragraph(n.get_text(" ", strip=True)) for n in soup.select(selector)]
            paragraphs = [x for x in paragraphs if len(x) >= 35]
            if sum(map(len, paragraphs)) > sum(map(len, best)):
                best = paragraphs
        if sum(map(len, best)) < 400:
            fallback = [clean_paragraph(n.get_text(" ", strip=True)) for n in soup.find_all("p")]
            fallback = [x for x in fallback if len(x) >= 45]
            if sum(map(len, fallback)) > sum(map(len, best)):
                best = fallback
        # 언론사 중에는 기사 본문을 p 태그가 아니라 div 섹션으로 제공하는 곳도 있다.
        # 페이지 전체가 아니라 기사 컨테이너만 대상으로 2차 복원한다.
        if sum(map(len, best)) < 350:
            for selector in (
                "[itemprop='articleBody']", "#articleBody", "#articleView",
                ".article-body", ".article_body", ".article_view", ".articleView",
                ".article-content", ".article_content", ".view-content",
                ".view_body", ".news_body", "article",
            ):
                candidates = []
                for node in soup.select(selector):
                    chunks = [
                        clean_paragraph(x) for x in node.get_text("\n", strip=True).splitlines()
                    ]
                    chunks = [x for x in chunks if len(x) >= 35]
                    candidate = "\n".join(chunks)
                    if 350 <= len(candidate) <= 25000 and (
                        "AIDC" in candidate or "인공지능 데이터센터" in candidate
                        or "AI 데이터센터" in candidate
                    ):
                        candidates.append(chunks)
                if candidates:
                    best = max(candidates, key=lambda x: sum(map(len, x)))
                    break
        unique: list[str] = []
        seen: set[str] = set()
        for paragraph in best:
            if paragraph and paragraph not in seen:
                unique.append(paragraph)
                seen.add(paragraph)
        result["article_body"] = "\n".join(unique)
        if len(result["article_body"]) < 300:
            result["enrich_error"] = f"본문 추출량 부족({len(result['article_body'])}자)"
    except Exception as exc:  # noqa: BLE001
        result["article_body"] = ""
        result["enrich_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return result


OFFICIAL_HOSTS = ("msit.go.kr", "korea.kr", "law.go.kr", "mcee.go.kr")


def verified_official_url(row: dict[str, Any]) -> bool:
    from urllib.parse import urlparse
    host = (urlparse(str(row.get("url", ""))).hostname or "").lower()
    return bool(row.get("official")) and any(
        host == root or host.endswith("." + root) for root in OFFICIAL_HOSTS
    )


def material_signature(row: dict[str, Any]) -> str:
    """입법예고·세제·전력 용량의 실제 상태값만 별도로 지문에 반영한다."""
    key = str(row.get("event_key") or semantic_key(row))
    body = str(row.get("article_body") or "").lower()
    if key == "aidc|tax-credit|eligibility":
        rate = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%\s*세액공제", body)
        return "rate=" + (rate.group(1) if rate else "unspecified") + (
            "|rental" if ("코로케이션" in body or "임대" in body) else ""
        )
    if key in ("aidc|power-special", "aidc|grid-code|requirements"):
        mw = sorted(set(re.findall(r"\d+(?:\.\d+)?\s*(?:mw|gw)", body)))
        return "|".join(mw[:8]) or "requirements"
    if key.startswith("aidc|sgc-gunsan|"):
        mw = sorted(set(re.findall(r"\d+(?:\.\d+)?\s*mw", body)))
        return "|".join(mw[:8]) or "project-stage"
    if key in ("aidc|decree-preannouncement", "aidc|decree-final"):
        return "official-document-" + key.rsplit("|", 1)[-1]
    return ""


def verify_change(row: dict[str, Any]) -> tuple[bool, str]:
    """검증 실패 또는 제목만으로 만든 상태 변화를 알림에서 거부."""
    key = str(row.get("event_key") or semantic_key(row))
    body = " ".join(str(row.get("article_body") or "").lower().split())
    title = str(row.get("title") or "").lower()
    official = verified_official_url(row)

    if key in ("aidc|unclassified", "aidc|project-execution|unverified"):
        return False, "제목 외 구체적인 사업·정책 상태 변화 검증 불가"

    if len(body) < 300:
        return False, "기사·공식자료 본문 직접 검증 실패"

    if not ("aidc" in body or "인공지능 데이터센터" in body or "ai 데이터센터" in body):
        return False, "본문의 AIDC 관련성을 검증하지 못함"

    if key == "aidc|tax-credit|eligibility":
        if not any(x in body for x in ("세액공제", "세액 공제")):
            return False, "세액공제 조건을 본문에서 확인하지 못함"
        if not any(x in body for x in ("자가 소비", "자가소비", "임대", "코로케이션", "15%")):
            return False, "적용 대상·세액공제 수치 확인 실패"
        if official and not any(
            x in body for x in ("법률 개정", "시행령 개정", "개정안 공포", "규정 확정", "세제개편안 발표")
        ):
            return False, "공식 자료여도 세제 적용조건을 바꾼 문서인지 확인할 수 없음"
        return True, "산업계 세제 개선 요구" if not official else "공식 세제 변경"

    if key == "aidc|anti-hoarding|queue-evidence":
        if not all(x in body for x in ("67.4", "62.8", "93")):
            return False, "전력 선점 물량 세 수치 교차 확인 실패"
        return True, "정량 근거 확인"
    if key == "aidc|anti-hoarding|legal-limit":
        if not ("법 개정" in body or "법률상 근거" in body or "매매 제한" in body):
            return False, "사업권 제한 법률 근거를 본문에서 확인하지 못함"
        return True, "법적 제약 제시"

    if key.startswith("aidc|sgc-gunsan|"):
        if not ("sgc" in body and "군산" in body):
            return False, "사업자·현장 교차 확인 실패"
        stage = key.rsplit("|", 1)[-1]
        markers = {
            "plan": ("계획", "추진", "투자"),
            "operator-partner": ("kt클라우드", "kt cloud"),
            "contract": ("본계약", "계약 체결", "계약 완료"),
            "groundbreaking": ("착공", "기공식"),
            "operation": ("상업운전", "운영 개시", "가동 개시", "시운전"),
        }
        if not any(x in body for x in markers[stage]):
            return False, f"프로젝트 {stage} 단계 본문 증거 없음"
        return True, "실제 프로젝트 단계 근거 확인"

    if key in ("aidc|decree-preannouncement", "aidc|decree-final"):
        if not official:
            return False, "입법예고·확정은 1차 공식 법령으로 재검증 필요"
        if key.endswith("preannouncement") and not any(x in body for x in ("입법예고", "시행령안")):
            return False, "공식 입법예고 본문 증거 없음"
        if key.endswith("final") and not any(x in body for x in ("공포", "국무회의", "시행령 확정", "제정")):
            return False, "공식 확정 본문 증거 없음"
        return True, "공식 법령 단계 확인"

    if key == "aidc|subordinate-rules-design":
        if not any(x in body for x in ("하위법령", "공개토론회", "연구반", "시행령")):
            return False, "하위법령 설계 공식·보도 근거 부족"
        return True, "하위법령 설계 관련 사실 확인"

    if key in ("aidc|power-special", "aidc|grid-code|requirements", "aidc|special-zone"):
        if not official:
            return False, "의견·보도는 확정 전력 특례/특구/계통 규칙 변경이 아님"
        if not any(x in body for x in ("확정", "고시", "의결", "공포", "입법예고", "지정", "시행")):
            return False, "공식 내용의 실질적 변화 근거 부족"
        return True, "공식 적용 규정 확인"

    return False, "정의되지 않은 신규 사건으로 송출 금지"


def has(body: str, *terms: str) -> bool:
    lower = body.lower()
    return any(term.lower() in lower for term in terms)


def fact_lines(row: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    key = str(row.get("event_key", ""))
    body = str(row.get("article_body", ""))
    lower = body.lower()

    if key == "aidc|anti-hoarding|queue-evidence":
        new = [
            "• 이번 변화의 핵심은 하위법령 논의 자체가 아니라 <b>전력 선점 문제가 실제 물량으로 확인됐다는 점</b>",
        ]
        if "67.4gw" in lower and "62.8gw" in lower and "93%" in lower:
            new.append("• 전력계통영향평가 신청 <b>67.4GW</b> 가운데 데이터센터가 <b>62.8GW·93%</b>를 차지")
        if "39.9gw" in lower and "7gw" in lower:
            new.append("• 1차 심사 공급가능 물량은 <b>39.9GW</b>지만 본심사 완료는 <b>7GW</b>에 그쳐, 약 <b>33GW</b>가 중간 단계에 머물러 있음")
        if has(body, "기한 근거", "추진해야 하는지"):
            new.append("• 시행령 구성 초안에는 AIDC 인정 뒤 <b>언제까지 실제 사업을 추진해야 하는지에 대한 기한 근거가 없는 것</b>으로 보도됨")
        changed = [
            "• 9월 9일의 ‘하위법령을 만든다’에서 한 단계 나아가, <b>특례가 계통 선점·허수 수요를 키울 수 있다는 정량 근거</b>가 추가됨",
            "• 따라서 전력 특례의 크기뿐 아니라 <b>미추진 사업 회수·유효기간·실수요 검증 장치</b>가 중요해짐",
        ]
        invest = [
            "• 실제 착공 프로젝트에는 계통 확보 경쟁이 더 중요해지고, <b>변압기·개폐기·케이블·UPS·BESS 발주는 ‘신청 GW’보다 본심사·전원 인가 GW</b>를 봐야 함",
            "• 허수 물량 정리가 강화되면 실수요 프로젝트의 접속 여력이 개선될 수 있지만, 규제가 약하면 계통 병목이 장기화될 수 있음",
        ]
        return new, changed, invest

    if key == "aidc|anti-hoarding|legal-limit":
        new = [
            "• 전력계통영향평가 면제를 받아도 <b>전력 공급이 자동 보장되는 것은 아니라는 점</b>이 확인됨",
            "• 연구반은 설계전력·AI 장비 전력·한전 계약전력의 <b>정합성을 신고 단계에서 확인</b>해 허수 사업자를 걸러내는 방향을 검토",
        ]
        if has(body, "매각 금지", "매매 제한", "법률상 근거"):
            new.append("• 사업권 매각·매매 자체를 막으려면 재산권 제한 문제가 있어 <b>시행령만으로는 어렵고 법률 개정 근거가 필요</b>하다는 연구반 설명")
        if "300" in lower and "확정" in lower:
            new.append("• 일각의 <b>300kW 기준은 확정된 수치가 아니며</b>, AIDC 인정 기준과 AI 장비 전력 비율도 계속 논의 중")
        changed = [
            "• 9월 9일 공개토론회의 큰 틀에서 새로 나온 것은 <b>‘알박기’를 시행령만으로 완전히 막기 어렵다는 법적 한계</b>",
            "• 즉 특례 확대와 함께 진성 사업자 검증·법 개정 여부가 별도 정책 변수로 생김",
        ]
        invest = [
            "• 전력 특례 수혜 여부보다 <b>한전 계약전력·실제 공급 가능 용량·착공 의지</b>가 프로젝트 가치 판단에서 더 중요해짐",
            "• 사업권 거래 제한이 법 개정으로 강화되면 단순 부지·계통 선점 가치보다 실제 개발 능력을 가진 사업자의 상대가치가 커질 수 있음",
        ]
        return new, changed, invest

    if key == "aidc|subordinate-rules-design":
        new = [
            "• 2027년 3월 10일 특별법 시행 전 <b>AIDC 인정 범위·신고·인허가 일괄처리·전력 특례·비수도권 특구</b>의 세부 기준을 만드는 단계",
            "• 이 단계에서는 구체 시행령 조문이 확정된 것이 아니라 연구반 구성안과 이해관계자 의견을 모으는 중",
        ]
        changed = [
            "• 특별법이 이미 공포된 상태에서 <b>누가 실제 특례 대상이 되고 어떤 절차를 줄일지</b>를 정하는 실행 규칙 단계로 이동",
        ]
        invest = [
            "• 실제 돈은 시행령·전력 기준 확정 → 전원 인가 → 착공 이후 <b>변압기·개폐기·케이블·UPS·BESS·냉각·건설</b> 발주로 연결",
            "• 가장 중요한 미확정은 AIDC 인정 기준과 전력계통영향평가 특례·면제의 구체 범위",
        ]
        return new, changed, invest

    if key == "aidc|tax-credit|eligibility":
        rate_match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%\s*세액공제", lower)
        rate_label = f"{rate_match.group(1)}%" if rate_match else "공제율 재검증 필요"
        date_label = base.kdate(str(row.get("published", "")))
        is_official = verified_official_url(row)
        status = "정부 공식 세제 적용조건" if is_official else "산업계의 제도 개선 요구"
        new = [
            f"• <b>{date_label} {status}</b>: 자가소비 전용과 임대·외부 제공형 AIDC의 세액공제 적용 범위가 핵심 쟁점",
            f"• 기사에 등장하는 세액공제율은 <b>{rate_label}</b>. 정부의 공식 적용대상 변경인지, 업계 요구인지 반드시 구분",
        ]
        if has(body, "100㎿", "100mw"):
            new.append(
                "• 100MW급 AIDC의 생산유발효과 등은 포럼 발표자가 제시한 추산이며, <b>국가 예산·실제 수주·매출 확정액이 아님</b>"
            )
        if has(body, "150일", "90일", "40일"):
            new.append(
                "• 법정 처리 기한은 150일·90일·40일(사유에 따른 1회 최대 30일 연장)이며, <b>기한 내 거부통지가 없을 때 처리 완료로 보는 규정</b>과 실제 전력 공급 보장은 구분"
            )
        changed = [
            "• 기존 하위법령 설계 논의에서 세액공제의 실질적 수혜대상·사업자 유형이 구체적인 논쟁으로 부상",
            f"• 확인 상태는 <b>{status}</b>이고, 최종 세법 개정·시행령 확정 여부는 별도 추적",
        ]
        invest = [
            "• 임대형·외부 서비스형 데이터센터 포함 여부는 운영사의 세후 투자수익률에 영향을 줄 수 있음",
            "• 세액공제 법령·적용조건·전력계통 접속·착공·금융조달 확인 전에는 확정 지원금·매출로 계산하지 않음",
        ]
        return new, changed, invest

    if key == "aidc|grid-code|requirements":
        return (
            ["• AIDC 전력계통 연계 기술기준·그리드코드의 공식 적용조건이 새로 확인된 단계"],
            ["• 산업계 규제완화 건의와 기후에너지환경부의 확정 기술요건은 별개"],
            ["• 계통 연계·인버터·전력변환장치·안전인증 사양 확정 후 실제 발주에 연결"],
        )

    if key == "aidc|decree-preannouncement":
        return (
            ["• 정부 시행령 초안이 공개돼 <b>AIDC 인정·전력·인허가 특례 문구를 실제 조문으로 검증할 수 있는 단계</b>"],
            ["• 토론회·연구반 의견 수준에서 <b>공식 입법예고안</b>으로 단계가 올라감"],
            ["• 숫자·면제 범위가 구체화되면 실제 프로젝트별 전원 인가·착공 가능성을 다시 평가해야 함"],
        )

    if key == "aidc|decree-final":
        return (
            ["• 시행령·하위규칙이 확정돼 <b>실제 적용 기준이 법적 효력을 갖는 단계</b>로 이동"],
            ["• 입법예고안과 최종 조문 사이에서 바뀐 숫자·대상·경과조치를 확인해야 함"],
            ["• 이제 정책 기대보다 실제 전원 인가·특구 지정·착공·발주가 실적 연결의 핵심"],
        )

    if key.startswith("aidc|sgc-gunsan|"):
        step = key.rsplit("|", 1)[-1]
        stage_text = {"plan": "계획", "operator-partner": "운영사 참여", "contract": "본계약", "groundbreaking": "착공", "operation": "운영"}.get(step, "사업 진행")
        new = [f"• SGC에너지 군산 AIDC: <b>{stage_text}</b> 단계. 1단계 <b>60MW</b>, 수요에 따른 최대 <b>300MW</b> 단계적 확장 가능성을 분리해 확인"]
        if has(body, "2028년 1분기", "2028년 1q"):
            new.append("• 1단계 운영 목표는 <b>2028년 1분기</b>로 확인")
        if has(body, "kt클라우드", "kt cloud"):
            new.append("• KT클라우드는 설계·구축·운영(DBO) 파트너로 참여하며, 단순 테마가 아니라 실제 구축·운영 역할이 확인됨")
        if has(body, "현대엔지니어링"):
            new.append("• 현대엔지니어링은 공동 시공사로 건축·토목·설비·통신 및 일부 전력·냉각 설비를 담당")
        changed = [
            "• 국내 AIDC 기대를 신청용량이 아니라 <b>본계약 → 착공 → 전원 인가 → 시운전 → 운영</b> 단계로 분리해 추적",
            "• 300MW는 확정 동시 가동용량이 아니라 <b>수요에 따른 단계적 확장 상단</b>으로 분리",
        ]
        invest = [
            "• 직접 매출 연결은 60MW 1단계의 EPC·전력·냉각·모듈형 설비 발주와 운영 개시가 먼저이며, 300MW 전량을 선반영하지 않음",
            "• SGC에너지의 에너지 공급·개발 참여와 KT클라우드 DBO, 시공사 역할을 구분해 실제 수익 귀속을 추적",
        ]
        return new, changed, invest

    # 여기로 온 사건은 알림 게이트에서 차단된다. 제목 재서술을 '새 사실'로 만들지 않는다.
    return (
        ["• 직접 검증된 새로운 정책·사업 상태가 없음"],
        ["• 기사 발행과 정책 변경을 구분"],
        ["• 실제 공식 조건·전원 인가·착공·발주 확인 후 재평가"],
    )


def source_link(row: dict[str, Any]) -> str:
    label = html.escape(str(row.get("publisher") or row.get("source") or "원문"))
    url = html.escape(str(row.get("url") or ""), quote=True)
    return f'<a href="{url}"><b>{label}</b></a>' if url else label


def render(row: dict[str, Any]) -> str:
    title = html.escape(base.norm(str(row.get("title", ""))))
    category = html.escape(str(row.get("category", "AIDC 특별법")))
    if str(row.get("event_key")) == "aidc|tax-credit|eligibility":
        category = "공식 세제 변경" if verified_official_url(row) else "산업계 세제 개선 요구"
    new, changed, invest = fact_lines(row)
    project_event = str(row.get("event_key", "")).startswith("aidc|sgc-gunsan|")
    header = "<b>한국 AIDC 사업 실행 새 변화</b>" if project_event else "<b>한국 AIDC 정책·전력 특례 새 변화</b>"
    evidence = dict(row.get("timeline_evidence") or {})
    rss_date = str(row.get("rss_published") or row.get("published") or "")
    chronology = timeline_lines(evidence, rss_published=rss_date)
    if evidence.get("published") and evidence.get("published") != rss_date:
        # 날짜값 자체가 다를 때만 검색 노출일을 별도 참고값으로 쓴다.
        if source_korean_date(evidence.get("published")) != source_korean_date(rss_date):
            chronology.append(f"검색 노출일(게시일과 다름)  {source_korean_date(rss_date)}")
    chronology_html = [f"<b>{html.escape(text.split('  ', 1)[0])}</b>  {html.escape(text.split('  ', 1)[-1])}"
                       for text in chronology]
    return "\n".join([
        header,
        "",
        "<b>한눈에 보기</b>",
        f"• <b>현재 단계</b>  {category}",
        f"• <b>이번 핵심</b>  {re.sub('<[^>]+>', '', new[0]).removeprefix('• ').strip()}",
        "• <b>알림 기준</b>  같은 기사 재노출이 아니라 새 숫자·법적 제약·공식화·사업단계 변화가 생길 때만 전송",
        "",
        f"<b>{title}</b>",
        *chronology_html,
        f"<b>출처</b>  {source_link(row)}",
        "",
        "<b>이번에 새로 추가된 사실</b>",
        *new,
        "",
        "<b>기존 알림과 달라진 점</b>",
        *changed,
        "",
        "<b>투자 연결</b>",
        *invest,
        "",
        "<b>다음 확인</b>",
        "• 입법예고·시행령 확정 여부와 최종 조문",
        "• 전력계통영향평가 특례·면제의 실제 MW·적용 조건",
        "• 계통 신청 → 본심사 → 전원 인가 → 착공으로 실제 전환되는 GW",
        "• 미추진 사업 회수·유효기간·사업권 거래 제한에 대한 추가 법 개정 여부",
    ]).rstrip() + "\n"


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for path in (ALERT, PENDING, STATUS, META):
        if path.exists():
            path.unlink()

    state = base.load_state()
    last_state_time = parse_iso(str(state.get("updated_at", "")))
    now = datetime.now(timezone.utc)
    migration = int(state.get("dedupe_version") or 0) < 4
    session = requests.Session()
    session.headers.update(HEADERS)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for source, official, url in base.RSS_SOURCES + EXTRA_RSS_SOURCES:
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            rows.extend(base.parse_rss(response.text, source, official))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {type(exc).__name__}")

    recent: list[dict[str, Any]] = []
    for row in rows:
        dt = base.parse_date(str(row.get("published", "")))
        if dt and now - dt.astimezone(timezone.utc) > timedelta(days=MAX_AGE_DAYS):
            continue
        recent.append(row)

    events = collapse(recent)
    seen = {str(k): int(v) for k, v in dict(state.get("seen_events", {})).items()}
    known_signatures = {str(k): str(v) for k, v in dict(state.get("material_signatures", {})).items()}
    held: list[str] = []
    selected: dict[str, Any] | None = None
    backlog_count = 0
    ignored_legacy = 0

    for event in events:
        key = str(event["event_key"])
        if key == "aidc|unclassified" or key == "aidc|project-execution|unverified":
            held.append("미분류: 구체적인 사업·정책 상태 추출 필요")
            continue

        current = event_level(event)
        previous = int(seen.get(key, 0))
        if current < previous:
            continue

        if previous == current and current > 0:
            # 동일 정책 상태·출처 등급의 후속 기사: 새로운 사실이 아닐 수 있음.
            # 동일 공식 문서의 수치 변경 감시 대상만 아래에서 추가 검증한다.
            if key not in (
                "aidc|tax-credit|eligibility", "aidc|power-special",
                "aidc|grid-code|requirements", "aidc|decree-final",
                "aidc|decree-preannouncement",
            ):
                continue

        members = list(event.get("members") or [event])
        candidates = sorted(
            members, key=lambda r: (event_level(r), base.source_score(r)), reverse=True
        )
        verified = None
        reject_reasons: list[str] = []
        for candidate in candidates[:3]:
            enriched = enrich(candidate, session)
            enriched["event_key"] = key
            ok, reason = verify_change(enriched)
            if ok:
                verified = enriched
                verified["verification"] = reason
                break
            reason = str(enriched.get("enrich_error") or reason)
            reject_reasons.append(reason)

        if verified is None:
            held.append(f"{key}: {'; '.join(reject_reasons[:2]) or '본문 직접 검증 실패'}")
            continue

        evidence = dict(verified.get("timeline_evidence") or {})
        original_age = verified_age_days(evidence, now)
        revised = parse_timestamp(evidence.get("modified", ""))
        revised_age = ((now - revised).total_seconds() / 86400) if revised else None
        if original_age is not None and original_age > MAX_AGE_DAYS and (
            revised_age is None or revised_age > MAX_AGE_DAYS
        ):
            # 검색엔진이 새로 색인한 과거 문서: 신규 공식 변경으로 보고하지 않는다.
            held.append(f"{key}: 과거 원문 재색인 차단 / {source_korean_date(evidence['published'])}")
            seen[key] = max(previous, current)
            continue

        fact_sig = material_signature(verified)
        sig_changed = bool(
            fact_sig and known_signatures.get(key) is not None
            and known_signatures[key] != fact_sig
        )
        should_notify = current > previous or sig_changed

        pub = base.parse_date(str(verified.get("published", "")))
        pub_utc = pub.astimezone(timezone.utc) if pub else None

        # v4 최초 도입 당시 이전에 전송되었던 지난 기사 재해석으로 인한 일괄 재발송 금지.
        if migration and (not bool(state.get("initialized")) or (last_state_time and pub_utc and pub_utc <= last_state_time)):
            should_notify = False
            ignored_legacy += 1

        if not should_notify:
            seen[key] = max(previous, current)
            if fact_sig:
                known_signatures.setdefault(key, fact_sig)
            continue

        if selected is None:
            selected = verified
            selected["event_key"] = key
            selected["event_level"] = current
            selected["material_signature"] = fact_sig
        else:
            # 이번 실행에서 전송할 첫 사건만 소비하고 나머지는 다음 실행에 남긴다.
            backlog_count += 1

    if selected is not None:
        key = str(selected["event_key"])
        seen[key] = max(int(seen.get(key, 0)), int(selected["event_level"]))
        if selected["material_signature"]:
            known_signatures[key] = str(selected["material_signature"])

    pending = {
        "initialized": True,
        "seen_events": seen,
        "material_signatures": known_signatures,
        "updated_at": now.isoformat(),
        "source_errors": errors,
        "dedupe_version": 4,
        "held_for_verification_count": len(held),
        "held_examples": held[:5],
        "eligible_backlog_count": backlog_count,
        "legacy_suppressed_count": ignored_legacy,
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if selected is not None:
        ALERT.write_text(render(selected), encoding="utf-8")
        meta = {
            "event_key": str(selected["event_key"]),
            "event_level": int(selected["event_level"]),
            "material_signature": str(selected["material_signature"]),
            "title": str(selected.get("title", "")),
            "verification": str(selected.get("verification", "")),
            "fingerprint": digest(
                str(selected["event_key"]) + "|" + str(selected["event_level"])
                + "|" + str(selected["material_signature"])
            ),
        }
        META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    STATUS.write_text(
        "# 한국 AIDC 정책·전력 특례 감시 v4\n\n"
        f"- 정책 후보: **{len(events)}건**\n"
        f"- 검증 후 알림: **{'예' if selected else '아니오'}**\n"
        f"- 공식·본문 확인 실패 또는 미분류: **{len(held)}건**\n"
        f"- 다음 실행 보류 사건: **{backlog_count}건**\n"
        f"- 이전 기사 재전송 차단: **{ignored_legacy}건**\n"
        f"- 원천 오류: **{len(errors)}곳**\n"
        "- 트리거: **검증한 사건·공식 상태 변화만, 제목 자체는 제외**\n",
        encoding="utf-8",
    )
    print(
        f"aidc_v4_events={len(events)} notify={bool(selected)} "
        f"held={len(held)} backlog={backlog_count} migration={migration} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
