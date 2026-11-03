#!/usr/bin/env python3
"""한국철도공사 행신역 20.1MW 태양광 컨소시엄 단계 변화 전용 감시.

기존 전기본·전력망 감시와 분리해 입찰/선정/출자/착공/운영 등 실질 변화만 보고한다.
기사 발견 시각·제목/언론사 재인용은 이벤트가 아니다.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "korail_hangsin_solar_state.json"
PENDING = ROOT / "out" / "korail_hangsin_solar_pending.json"
REPORT = ROOT / "out" / "korail_hangsin_solar_alert.html"
PROJECT = "korail_goyang_hangsin_solar_20_1mw_2026"
BASELINE = datetime(2026, 11, 3, 18, 9, tzinfo=KST)
USER_AGENT = "Mozilla/5.0 (compatible; KHS-Korail-Solar-Event-Watch/1.0)"
KORAIL_PRESS = (
    "https://info.korail.com/info/selectBbsNttView.do"
    "?bbsNo=199&key=911&nttNo=27195"
)
ARTICLE = "https://www.asiatoday.co.kr/kn/view.php?key=20261103010001199"
RSS_QUERIES = (
    '"수도권철도차량정비단" "태양광" when:30d',
    '("행신역" "태양광" "한수원" OR "그린레일에너지" OR "지투파워" "코레일") when:30d',
    'site:info.korail.com ("태양광" "행신" OR "철도차량정비단" "태양광") when:30d',
)
BING_QUERY = '수도권철도차량정비단 태양광 한수원 지투파워'
OFFICIAL_HOSTS = ("info.korail.com", "korail.com", "khnp.co.kr", "kind.krx.co.kr", "dart.fss.or.kr")
LABELS = {
    "proposal_submitted": "한수원 컨소시엄 사업제안서 실제 제출",
    "preferred_selected": "한수원 컨소시엄 우선협상대상자 선정",
    "preferred_result_published": "우선협상자 선정 결과 공고(낙찰자 식별 필요)",
    "agreement_signed": "한국철도공사 사업협약·계약 체결",
    "spc_established": "특수목적법인 실제 설립",
    "equity_approved": "참여사 출자·이사회 승인 확정",
    "permit_approved": "발전사업·계통접속·건축 인허가 승인",
    "construction_started": "행신역 태양광 실제 착공",
    "power_connected": "계통연계·전원 인가 완료",
    "operation_started": "상업운전·전력 공급 개시",
    "deadline_changed": "한국철도공사 공모 마감일 변경",
    "size_changed": "설비용량·사업범위 정정 확정",
    "other_selected": "경쟁 컨소시엄 선정·한수원 미선정",
    "withdrawn": "참여 철회·공모 취소·사업 중단",
}
BASE_SEEN = ["site_announced", "consortium_discussion", "tender_open"]
DEFERRED = (
    "예정", "계획", "추진", "검토", "협의", "방안", "가능", "가정",
    "경우", "하면", "할 경우", "한다면", "방침", "목표", "구상", "향후",
    "앞두고", "될 경우", "선정되면", "마치면", "돌입하면", "수 있다", "준비",
)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)).strip()


def is_project(text: str) -> bool:
    s = clean(text).lower().replace(" ", "")
    direct = any(k in s for k in (
        "수도권철도차량정비단", "행신역", "고양ktx차량기지", "그린레일에너지"
    ))
    if direct and any(k in s for k in ("태양광", "발전", "그린레일")):
        return True
    return "한수원" in s and "지투파워" in s and any(k in s for k in ("철도", "코레일", "태양광"))


def is_final_statement(sentence: str, positive: tuple[str, ...]) -> bool:
    """실제 완료 문장만 통과. '선정되면/제출 예정' 형태는 제외."""
    s = clean(sentence)
    if not any(x in s for x in positive):
        return False
    if any(x in s for x in DEFERRED):
        return False
    return True


def sentences(text: str) -> list[str]:
    # 제목과 뉴스 RSS 설명을 각각 짧은 문장으로 평가해 다른 문장의 '계획'과 혼동하지 않는다.
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n+", clean(text)) if s.strip()]


def detect_events(title: str, summary: str, official: bool = False) -> set[str]:
    """고유 사업의 실제 단계 전환만 감지. 공식 지위는 수집된 출처에 따라 따로 표시."""
    combined = f"{title} {summary}"
    if not is_project(combined):
        return set()
    found: set[str] = set()
    for s in [title, *sentences(summary)]:
        if not is_project(combined):
            continue
        t = clean(s).lower()
        if is_final_statement(t, ("공모 마감일 변경", "접수 마감일 변경", "접수기간 연장", "마감일 연기", "접수기한 연장", "공모 기한 연장")):
            found.add("deadline_changed")
        if is_final_statement(t, ("규모 확대 확정", "규모 축소 확정", "설비용량 변경 확정", "사업범위 변경 확정")):
            found.add("size_changed")
        if is_final_statement(t, ("한수원 컨소시엄 제안서 제출", "그린레일에너지 제안서 제출", "사업제안서를 제출했다", "사업제안서 제출 완료", "공모 신청 완료", "신청서를 제출했다")):
            found.add("proposal_submitted")
        if is_final_statement(t, ("우선협상대상자로 선정됐다", "우선협상대상자로 선정되었다", "우선협상대상자로 확정", "우선협상자에 선정", "우선협상대상자 선정 완료", "우선협상대상자 선정")):
            failed = any(x in combined for x in ("한수원 탈락", "한수원 미선정", "다른 사업자", "경쟁 컨소시엄 선정"))
            named = any(x in combined for x in ("한수원", "지투파워", "그린레일에너지", "한국수력원자력"))
            if named and not failed:
                found.add("preferred_selected")
            elif official and not failed:
                found.add("preferred_result_published")
        if is_final_statement(t, ("사업협약 체결 완료", "사업협약을 체결했다", "사업협약 체결", "부지사용계약 체결", "전력구매계약 체결")):
            found.add("agreement_signed")
        if is_final_statement(t, ("그린레일에너지 설립 완료", "그린레일에너지 설립됐다", "특수목적법인 설립 완료", "spc 설립 완료", "spc를 설립했다")):
            found.add("spc_established")
        if is_final_statement(t, ("출자 확정", "출자 의결 완료", "출자를 의결했다", "이사회 출자 승인", "이사회 의결 완료")):
            found.add("equity_approved")
        if is_final_statement(t, ("발전사업 허가 완료", "계통접속 승인", "건축허가 승인", "인허가 완료", "발전사업 허가 취득")):
            found.add("permit_approved")
        if is_final_statement(t, ("착공했다", "착공 완료", "공사에 착수했다", "착공식 개최", "본공사 착수")):
            found.add("construction_started")
        if is_final_statement(t, ("전원 인가 완료", "계통연계 완료", "계통접속 완료")):
            found.add("power_connected")
        if is_final_statement(t, ("상업운전 개시", "상업운전 시작", "상업운전 돌입", "전력공급 개시", "전력 판매 시작", "발전소 가동 개시")):
            found.add("operation_started")
        if is_final_statement(t, ("한수원 탈락 확정", "한수원 컨소시엄 탈락", "한수원 미선정 확정", "다른 사업자가 우선협상대상자로 선정")):
            found.add("other_selected")
        if is_final_statement(t, ("사업 참여 철회", "컨소시엄 참여 철회", "공모 취소 확정", "사업 중단 확정", "사업 취소 확정", "공모 유찰 확정")):
            found.add("withdrawn")
    return found


def rss_rows(xml_body: str, source: str) -> list[dict]:
    root = ET.fromstring(xml_body)
    rows = []
    for item in root.iter():
        if item.tag.split("}")[-1].lower() != "item":
            continue
        obj = {c.tag.split("}")[-1].lower(): (c.text or "") for c in item}
        title, summary = clean(obj.get("title", "")), clean(obj.get("description", ""))
        url = obj.get("link", "").strip()
        if not is_project(title + " " + summary):
            continue
        raw = obj.get("pubdate", "")
        try:
            published = parsedate_to_datetime(raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            published = None
        rows.append({"title": title, "summary": summary, "url": url, "source": source,
                     "published": published.astimezone(KST) if published else None, "official": False})
    return rows


def fetch_url(session: requests.Session, url: str, timeout: int = 15) -> requests.Response:
    last = None
    for attempt in range(2):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as ex:
            last = ex
            if attempt == 0:
                time.sleep(2)
    raise RuntimeError(str(last))


def official_rows(html_body: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html_body, "html.parser")
    items = []
    for a in soup.select("a[href]"):
        title = clean(a.get_text(" ", strip=True))
        if not any(k in title for k in ("태양광", "그린레일", "행신", "철도차량정비단")):
            continue
        href = urljoin(page_url, a.get("href", ""))
        if not href.startswith("https://info.korail.com/"):
            continue
        items.append({"title": title, "summary": "", "url": href, "source": "한국철도공사 게시판",
                      "published": None, "official": True})
    return items[:40]


def collect() -> tuple[list[dict], dict]:
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
    rows = []
    errors = []
    successes = 0
    for q in RSS_QUERIES:
        url = "https://news.google.com/rss/search?q=" + quote_plus(q) + "&hl=ko&gl=KR&ceid=KR:ko"
        try:
            rows.extend(rss_rows(fetch_url(sess, url).text, "Google 뉴스 RSS"))
            successes += 1
        except (RuntimeError, ET.ParseError) as ex:
            errors.append("Google 뉴스 수집: " + str(ex)[:130])
    try:
        url = "https://www.bing.com/news/search?q=" + quote_plus(BING_QUERY) + "&format=RSS"
        rows.extend(rss_rows(fetch_url(sess, url).text, "Bing 뉴스 RSS"))
        successes += 1
    except (RuntimeError, ET.ParseError) as ex:
        errors.append("Bing 뉴스 수집: " + str(ex)[:130])
    for page in (
        "https://info.korail.com/info/selectBbsNttList.do?bbsNo=199&key=911",
        "https://info.korail.com/info/selectBbsNttList.do?bbsNo=200&key=910",
    ):
        try:
            rows.extend(official_rows(fetch_url(sess, page).text, page))
            successes += 1
        except RuntimeError as ex:
            errors.append("철도공사 게시판: " + str(ex)[:130])
    # 고정 보도자료는 기존 8월 '사업 계획' 증거로만 확인한다. 이 문서가 성공해도
    # 현재 조달시장 감시의 성공으로 오인하지 않도록 successes에는 넣지 않는다.
    try:
        fetch_url(sess, KORAIL_PRESS)
    except RuntimeError as ex:
        errors.append("철도공사 기존 공식자료: " + str(ex)[:130])
    unique = {}
    for row in rows:
        k = hashlib.sha256((row["url"] or row["title"]).encode("utf-8")).hexdigest()
        unique[k] = row
    return list(unique.values()), {"live_sources_ok": successes, "errors": errors}


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def initial_state() -> dict:
    return {"project": PROJECT, "initialized": True, "seen_event_types": BASE_SEEN.copy(),
            "baseline_at_kst": BASELINE.isoformat(), "last_checked_at_kst": None, "last_message_ids": []}


def load_state() -> dict:
    if not STATE.exists():
        return initial_state()
    obj = json.loads(STATE.read_text(encoding="utf-8"))
    if obj.get("project") != PROJECT:
        raise RuntimeError("다른 사업 상태파일과 혼동되어 중단")
    obj.setdefault("seen_event_types", BASE_SEEN.copy())
    return obj


def select_events(rows: list[dict], state: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(KST)
    seen = set(state.get("seen_event_types", []))
    latest: dict[str, dict] = {}
    for row in rows:
        published = row.get("published")
        if published is not None:
            if published < BASELINE or published > now + timedelta(hours=6):
                continue
            if now - published > timedelta(days=45):
                continue
        for stage in detect_events(row.get("title", ""), row.get("summary", ""), bool(row.get("official"))):
            if stage in seen:
                continue
            item = dict(row)
            item["event_type"] = stage
            prev = latest.get(stage)
            if prev is None or (item["official"], published or BASELINE) > (
                prev["official"], prev.get("published") or BASELINE
            ):
                latest[stage] = item
    return [latest[k] for k in LABELS if k in latest]


def build_report(events: list[dict], health: dict) -> str:
    lines = ["<b>[철도 태양광 · 행신역 20.1MW] 단계 변화</b>",
             "<i>공모·컨소시엄 협의와 실제 계약·출자·가동은 별개</i>", ""]
    for i, row in enumerate(events, 1):
        kind = row["event_type"]
        source_level = "공식 원문" if row.get("official") else "보도 확인·공식 확정 별도 확인"
        lines.extend([
            f"<b>{i}. {html.escape(LABELS[kind])}</b>",
            f"• 현재 단계: {source_level}",
            f"• 감지 근거: {html.escape(row.get('title',''))}",
            f"• 근거 링크: {html.escape(row.get('url',''))}",
        ])
        if row.get("published"):
            lines.append("• 보도일: " + row["published"].strftime("%Y-%m-%d %H:%M KST"))
        lines.append("")
    lines.extend([
        "<b>기존 기준선(재알림 제외)</b>",
        "• 2026-11-03 기준 한수원·지투파워·신한자산운용은 참여 협의 중",
        "• 계획지분 한수원 49%·지투파워 41%·신한자산운용 10% (미확정)",
        "• 11월 24일 공모 마감 예정, 20.1MW·연 25.6GWh·사업 20년",
        "• 우선협상자 선정 후에도 한수원 내부 심의·정부 협의·이사회 의결 필요",
        "<b>다음 확인</b>",
        "• 철도공사 공모·우협결과, 참여사 공시, SPC 법인 설립, 실제 납입, 착공·전원 인가",
        "• 공고의 변경·취소는 반드시 공식자료로 재확인",
    ])
    return "\n".join(lines) + "\n"


def set_output(key: str, value: str):
    file = os.getenv("GITHUB_OUTPUT")
    if file:
        with open(file, "a", encoding="utf-8") as out:
            out.write(f"{key}={value}\n")


def main() -> int:
    state = load_state()
    rows, health = collect()
    print("rail_solar_sources_ok=", health["live_sources_ok"], "relevant_rows=", len(rows))
    if health["errors"]:
        print("rail_solar_source_errors=", " | ".join(health["errors"]))
    # 모든 동적 원천이 실패하면 '신규 변화 없음'으로 확정하지 않는다.
    if health["live_sources_ok"] < 1:
        print("rail_solar_verdict=UNKNOWN_ALL_SOURCES_FAILED")
        set_output("changed", "false")
        return 2
    events = select_events(rows, state)
    pending = dict(state)
    pending["last_checked_at_kst"] = now_iso()
    pending["source_health"] = "partial" if health["errors"] else "complete"
    pending["source_success_count"] = health["live_sources_ok"]
    pending["errors"] = health["errors"][:10]
    if events:
        pending["seen_event_types"] = list(dict.fromkeys(state["seen_event_types"] + [x["event_type"] for x in events]))
        pending["last_event_types"] = [x["event_type"] for x in events]
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(build_report(events, health), encoding="utf-8")
        print("rail_solar_changes=", [x["event_type"] for x in events])
        set_output("changed", "true")
        set_output("report_path", str(REPORT.relative_to(ROOT)))
    else:
        print("rail_solar_changes=none_based_on_available_sources")
        set_output("changed", "false")
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
