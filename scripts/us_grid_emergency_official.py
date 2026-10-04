#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
import urllib.parse
from dataclasses import dataclass
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

PJM_DASHBOARD = "https://emergencyprocedures.pjm.com/ep/pages/dashboard.jsf"
PJM_POSTING = "https://emergencyprocedures.pjm.com/ep/pages/viewposting.jsf?id={msg_id}"
DOE_202C_LIST = "https://www.energy.gov/ceser/2026-doe-202c-orders"
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
KST = ZoneInfo("Asia/Seoul")
EPT = ZoneInfo("America/New_York")

GRID_MESSAGE_TYPES = (
    "maximum generation emergency/load management alert",
    "pre-emergency load mgmt reduction action",
    "emergency load mgmt reduction action",
    "deploy all resources action",
    "voltage reduction",
    "emergency use of back-up generator",
    "manual load dump",
    "special notice",
)

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def fetch(url: str, timeout: int = 25) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_from_html(raw: str) -> str:
    return norm(BeautifulSoup(raw, "html.parser").get_text(" "))


def parse_ept(value: str) -> dt.datetime | None:
    value = norm(value)
    for fmt in ("%m.%d.%Y %H:%M", "%m/%d/%Y %H:%M"):
        try:
            naive = dt.datetime.strptime(value, fmt)
            return naive.replace(tzinfo=EPT)
        except ValueError:
            pass
    return None


def parse_english_date(value: str) -> dt.date | None:
    value = norm(value)
    m = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b",
        value,
        re.I,
    )
    if not m:
        return None
    return dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))


def ko_date(value: dt.date | dt.datetime | None) -> str:
    if value is None:
        return "확인 불가"
    return f"{value.year}년 {value.month}월 {value.day}일"


def ko_datetime(value: dt.datetime | None, tz: ZoneInfo = KST) -> str:
    if value is None:
        return "확인 불가"
    local = value.astimezone(tz)
    label = "KST" if tz == KST else "EPT"
    return f"{local.year}년 {local.month}월 {local.day}일 {local:%H:%M} {label}"


def posting_window_from_body(body: str) -> tuple[dt.datetime | None, dt.datetime | None]:
    m = re.search(
        r"(?:issued\s+)?from\s+(\d{1,2}:\d{2})\s+on\s+(\d{2}\.\d{2}\.\d{4})\s+through\s+(\d{1,2}:\d{2})\s+on\s+(\d{2}\.\d{2}\.\d{4})",
        body,
        re.I,
    )
    if not m:
        return None, None
    start = parse_ept(f"{m.group(2)} {m.group(1)}")
    end = parse_ept(f"{m.group(4)} {m.group(3)}")
    return start, end


def posting_relevant(message_type: str, body: str) -> bool:
    low_type = message_type.lower()
    low_body = body.lower()
    if "special notice" in low_type:
        return "202(c)" in low_body or "202 c" in low_body
    return any(term in low_type for term in GRID_MESSAGE_TYPES)


def parse_pjm_posting_html(raw: str, url: str) -> dict | None:
    text = text_from_html(raw)
    id_match = re.search(r"Msg ID:\s*(\d+)", text, re.I)
    type_match = re.search(r"Message Type:\s*(.*?)\s*Priority:", text, re.I)
    priority_match = re.search(r"Priority:\s*(.*?)\s*Effective Start Time:", text, re.I)
    start_match = re.search(
        r"Effective Start Time:\s*(\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2})",
        text,
        re.I,
    )
    end_match = re.search(
        r"Effective End Time:\s*(\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2})",
        text,
        re.I,
    )
    region_match = re.search(
        r"Regions\s+(.*?)\s+(?:A\s+|An\s+|The\s+|Additional Comments:)",
        text,
        re.I,
    )
    if not (id_match and type_match and start_match):
        return None
    message_type = norm(type_match.group(1))
    body_start = type_match.end()
    body = text[body_start:]
    if not posting_relevant(message_type, body):
        return None
    effective_start = parse_ept(start_match.group(1))
    effective_end = parse_ept(end_match.group(1)) if end_match else None
    op_start, op_end = posting_window_from_body(body)
    return {
        "kind": "pjm",
        "id": f"pjm:{id_match.group(1)}",
        "msg_id": id_match.group(1),
        "message_type": message_type,
        "priority": norm(priority_match.group(1)) if priority_match else "",
        "effective_start": effective_start,
        "effective_end": effective_end,
        "operational_start": op_start,
        "operational_end": op_end,
        "regions": norm(region_match.group(1)) if region_match else "",
        "body": body,
        "url": url,
    }


def collect_pjm(now: dt.datetime) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    out: list[dict] = []
    try:
        dashboard = fetch(PJM_DASHBOARD).text
        dash_text = text_from_html(dashboard)
        ids = list(dict.fromkeys(re.findall(r"Msg ID:\s*(\d+)", dash_text, re.I)))[:40]
        # Some JSF renders retain direct posting links even when text extraction changes.
        ids += [
            m.group(1)
            for m in re.finditer(r"viewposting\.jsf\?id=(\d+)", dashboard, re.I)
            if m.group(1) not in ids
        ]
        for msg_id in ids[:40]:
            url = PJM_POSTING.format(msg_id=msg_id)
            try:
                event = parse_pjm_posting_html(fetch(url, 20).text, url)
                if event:
                    out.append(event)
            except Exception as exc:
                errors.append(f"PJM {msg_id}: {type(exc).__name__}")
    except Exception as exc:
        errors.append(f"PJM dashboard: {type(exc).__name__}")
    return out, errors


def extract_doe_detail_links(raw: str) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(DOE_202C_LIST, a.get("href") or "")
        low = href.lower()
        if "energy.gov/ceser/federal-power-act-section-202c-" not in low:
            continue
        if href not in links:
            links.append(href)
    return links[:40]


def doe_party(text: str) -> str:
    low = text.lower()
    if "pjm interconnection" in low:
        return "PJM"
    if "northern indiana public service company" in low and "midcontinent independent system operator" in low:
        return "NIPSCO·MISO"
    if "midcontinent independent system operator" in low:
        return "MISO"
    if "transalta centralia generation" in low:
        return "TransAlta"
    return "대상 기관 확인 필요"


def parse_doe_detail_html(raw: str, url: str) -> dict | None:
    text = text_from_html(raw)
    order_match = re.search(r"Order No\.?\s*(202-\d{2}-\d{1,2}[A-Z]?)", text, re.I)
    if not order_match:
        return None
    order_no = order_match.group(1).upper()
    issue_match = re.search(
        r"On\s+((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})",
        text,
        re.I,
    )
    issue_date = parse_english_date(issue_match.group(1)) if issue_match else None

    start_date = end_date = None
    m = re.search(
        r"(?:in effect|effective).*?beginning\s+(?:on\s+)?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}).*?(?:through|until|expire(?:s|d)?(?:\s+at.*?)?\s+on?)\s+((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})",
        text,
        re.I,
    )
    if m:
        start_date = parse_english_date(m.group(1))
        end_date = parse_english_date(m.group(2))
    else:
        # PJM orders can say "effective ... September 17 through September 18, 2026".
        m = re.search(
            r"effective.*?(September|October|November|December|January|February|March|April|May|June|July|August)\s+(\d{1,2})\s+through\s+(September|October|November|December|January|February|March|April|May|June|July|August)\s+(\d{1,2}),\s+(\d{4})",
            text,
            re.I,
        )
        if m:
            start_date = dt.date(int(m.group(5)), MONTHS[m.group(1).lower()], int(m.group(2)))
            end_date = dt.date(int(m.group(5)), MONTHS[m.group(3).lower()], int(m.group(4)))

    return {
        "kind": "doe",
        "id": f"doe:{order_no}",
        "order_no": order_no,
        "party": doe_party(text),
        "issue_date": issue_date,
        "effective_start_date": start_date,
        "effective_end_date": end_date,
        "body": text,
        "url": url,
    }


def collect_doe(now: dt.datetime) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    out: list[dict] = []
    try:
        raw = fetch(DOE_202C_LIST).text
        for url in extract_doe_detail_links(raw):
            try:
                event = parse_doe_detail_html(fetch(url, 20).text, url)
                if event:
                    out.append(event)
            except Exception as exc:
                errors.append(f"DOE detail: {type(exc).__name__}")
    except Exception as exc:
        errors.append(f"DOE list: {type(exc).__name__}")
    # newest first, missing dates last
    out.sort(key=lambda x: x.get("issue_date") or dt.date.min, reverse=True)
    return out[:30], errors


def event_is_alertable(event: dict, now: dt.datetime) -> bool:
    now_kst = now.astimezone(KST)
    if event["kind"] == "pjm":
        end = event.get("operational_end") or event.get("effective_end")
        start = event.get("effective_start")
        if end is not None and now.astimezone(EPT) > end + dt.timedelta(minutes=30):
            return False
        if start is not None and now.astimezone(EPT) - start > dt.timedelta(hours=36):
            return False
        return True
    issue = event.get("issue_date")
    if issue is None:
        return False
    return (now_kst.date() - issue).days <= 2


def pjm_title(event: dict) -> str:
    t = event.get("message_type", "")
    low = t.lower()
    if "eea 1" in low or "eea1" in low:
        return "PJM, EEA1·최대발전 비상경보 발령"
    if "emergency use of back-up generator action" in low:
        return "PJM, 대형부하 비상 백업발전 실제 동원 단계 발령"
    if "emergency use of back-up generator warning" in low:
        return "PJM, 대형부하 비상 백업발전 동원 경고 발령"
    if "manual load dump" in low:
        return "PJM, EEA3·수동 부하차단 단계 진입"
    if "special notice" in low and "202(c)" in event.get("body", ""):
        body_low = event.get("body", "").lower()
        if "request for 202(c)" in body_low or "requested a 202(c) order" in body_low:
            return "PJM, DOE 202(c) 긴급명령 요청·사전 준비 공지"
        if "has received doe 202(c)" in body_low or "applicability" in body_low:
            return "PJM, DOE 202(c) 명령의 운영 적용 공지"
        return "PJM, DOE 202(c) 관련 특별공지"
    return f"PJM, {t}"


def pjm_stage_explanation(event: dict) -> str:
    low = event.get("message_type", "").lower()
    if "eea 1" in low or "eea1" in low:
        return "EEA1은 공급여력이 빡빡해 비상자원을 준비하는 경보 단계이며, 순환정전 지시나 백업발전 실제 동원을 뜻하지 않습니다."
    if "emergency use of back-up generator action" in low:
        return "대형부하가 백업발전을 실제 가동하도록 지시하는 단계입니다."
    if "emergency use of back-up generator warning" in low:
        return "대형부하 백업발전 가동 가능성을 사전 경고하는 단계이며, 실제 동원 지시는 아닙니다."
    if "manual load dump" in low:
        return "EEA3에서 추가 비상자원으로도 부족해 강제 부하차단이 필요한 단계입니다."
    if "special notice" in low:
        body_low = event.get("body", "").lower()
        if "request for 202(c)" in body_low or "requested a 202(c) order" in body_low:
            return (
                "PJM이 DOE에 202(c) 긴급명령을 요청하거나 대형부하·발전자원에 사전 준비를 요구한 단계입니다. "
                "DOE 명령 발령이나 백업발전 실제 동원을 뜻하지 않습니다."
            )
        if "has not identified a reliability need to utilize" in body_low:
            return (
                "DOE 202(c) 명령은 존재하지만 PJM이 해당 운영일에 지정자원을 사용할 신뢰도 필요를 확인하지 않았다는 공지입니다. "
                "상시 최대출력 운전이나 백업발전 실제 동원을 뜻하지 않습니다."
            )
        if "has identified a reliability need to utilize" in body_low:
            return (
                "PJM이 해당 운영일에 DOE 202(c) 지정자원을 사용할 신뢰도 필요를 확인한 공지입니다. "
                "다만 대형부하 백업발전 실제 가동은 별도의 Back-Up Generator Action을 확인해야 합니다."
            )
        return "202(c) 관련 특별공지의 적용범위와 실제 필요 판정을 확인해야 하며, 명령 존재 자체가 최대출력 상시운전을 뜻하지 않습니다."
    return "PJM 공식 비상운영 단계의 실제 의미는 메시지 정의와 운영지시를 함께 확인해야 합니다."


def doe_content(event: dict) -> tuple[str, str]:
    body = event.get("body", "")
    low = body.lower()
    party = event.get("party", "")
    if party == "PJM":
        content = "PJM이 지정 발전자원을 필요 시 급전하고, EEA3 직전 또는 EEA3에서 최후수단으로 대형부하 백업발전을 지시할 수 있도록 한 명령입니다."
        distinction = "필요 시 동원 권한이며 모든 지정자원의 상시 최대출력 운전이나 일반 고객 순환정전을 뜻하지 않습니다."
        return content, distinction
    if party == "NIPSCO·MISO":
        content = "NIPSCO·MISO가 R.M. Schahfer 발전소 17·18호기를 운전 가능한 상태로 유지하고 비용 최소화를 위해 경제급전을 적용하도록 한 명령입니다."
        distinction = "PJM의 대형부하 백업발전 명령이 아니며, 폐지·정지 예정 발전자원의 공급능력을 계속 보존하는 조치입니다."
        return content, distinction
    if "backup generation" in low or "backup generators" in low:
        return (
            "공식 원문에 명시된 지정자원·백업발전 운용 권한을 부여한 202(c) 명령입니다.",
            "실제 가동 여부와 적용 조건은 계통운영자의 후속 필요 판정으로 확인해야 합니다.",
        )
    return (
        "DOE가 연방전력법 202(c)에 따라 전력계통 신뢰도 유지를 위한 긴급 운용을 지시한 명령입니다.",
        "세부 대상 자원과 운전조건은 해당 명령 원문을 기준으로 확인해야 합니다.",
    )


def render_event(event: dict, now: dt.datetime) -> str:
    if event["kind"] == "pjm":
        op_start = event.get("operational_start")
        op_end = event.get("operational_end")
        eff_start = event.get("effective_start")
        eff_end = event.get("effective_end")
        timeline = []
        if eff_start:
            timeline.append(
                f"• 게시·발효: {ko_datetime(eff_start, KST)} ({ko_date(eff_start.astimezone(EPT))} {eff_start.astimezone(EPT):%H:%M} EPT)"
            )
        if op_start and op_end:
            timeline.append(
                f"• 실제 적용: {ko_datetime(op_start, KST)} ~ {ko_datetime(op_end, KST)}"
            )
        elif eff_end:
            timeline.append(
                f"• 공식 효력: {ko_datetime(eff_start, KST)} ~ {ko_datetime(eff_end, KST)}"
            )
        return "\n".join(
            [
                "🚨 미국 전력망 비상운영·PJM 중요 변화",
                "",
                pjm_title(event),
                "",
                *timeline,
                f"• 단계: {event.get('message_type', '확인 필요')}",
                f"• 적용 지역: {event.get('regions') or 'PJM-RTO'}",
                f"• 실제 내용: {pjm_stage_explanation(event)}",
                "• 다음 확인: EEA 단계 상·하향, 수요반응·백업발전 실제 동원 MW·MWh, 지정자원 운전지시, 비상조치 해제시각",
                "",
                f'<a href="{event["url"]}">원문</a>',
            ]
        )

    party = event.get("party", "대상 기관 확인 필요")
    content, distinction = doe_content(event)
    heading = f"🚨 미국 전력망 비상운영·{party} 중요 변화"
    return "\n".join(
        [
            heading,
            "",
            f"DOE, {party}에 202(c) 긴급명령 {event.get('order_no')} 발령",
            "",
            f"• DOE 발령일: {ko_date(event.get('issue_date'))}",
            f"• 효력 시작일: {ko_date(event.get('effective_start_date'))}",
            f"• 종료 예정일: {ko_date(event.get('effective_end_date'))}",
            "• 단계: 연방전력법 202(c) 긴급명령",
            f"• 실제 내용: {content}",
            f"• 구분: {distinction}",
            "• 다음 확인: 실제 발전자원 동원 MW·MWh, 계통 비상단계, 명령의 연장·종료, 후속 자원목록·운전지시",
            "",
            f'<a href="{event["url"]}">원문</a>',
        ]
    )


def collect_all(now: dt.datetime) -> tuple[list[dict], list[str]]:
    pjm, pjm_errors = collect_pjm(now)
    doe, doe_errors = collect_doe(now)
    events = pjm + doe
    # Stable identity, newest first.
    def sort_key(item: dict):
        if item["kind"] == "pjm":
            when = item.get("effective_start")
            return when.timestamp() if when else 0
        date = item.get("issue_date")
        return dt.datetime.combine(date, dt.time.max, tzinfo=KST).timestamp() if date else 0
    events.sort(key=sort_key, reverse=True)
    return events, pjm_errors + doe_errors


def self_test() -> None:
    pjm_html = """
    <html><body>
    Msg ID: 105520
    Message Type: Maximum Generation Emergency/Load Management Alert-Capacity Emergency-NERC EEA 1
    Priority: Alert
    Effective Start Time: 09.16.2026 13:05
    Regions PJM-RTO
    A Maximum Generation Emergency/Load Management Alert-Capacity Emergency-NERC EEA 1
    has been issued from 00:01 on 09.17.2026 through 23:59 on 09.17.2026 .
    Maximum Generation Emergency has been called into the operating capacity.
    </body></html>
    """
    p = parse_pjm_posting_html(pjm_html, PJM_POSTING.format(msg_id="105520"))
    assert p and p["msg_id"] == "105520"
    assert p["operational_end"] and p["operational_end"].date() == dt.date(2026, 9, 17)
    stale_now = dt.datetime(2026, 9, 19, 15, 27, tzinfo=KST)
    assert not event_is_alertable(p, stale_now), "expired 105520 must not re-alert on Sep 19"

    pre_order_notice_html = """
    <html><body>
    Msg ID: 105521
    Message Type: Special Notice
    Priority: Informational
    Effective Start Time: 09.16.2026 13:11
    Regions PJM-RTO
    A Special Notice : Request for 202(c) Emergency Use of Back-up Generators and Running Emissions Limited Generation
    Additional Comments: PJM has requested a 202(c) order to permit use of emissions-limited generation and
    emergency back-up generation and is coordinating with large loads in advance.
    </body></html>
    """
    pre = parse_pjm_posting_html(
        pre_order_notice_html, PJM_POSTING.format(msg_id="105521")
    )
    assert pre and pre["msg_id"] == "105521"
    assert "요청·사전 준비" in pjm_title(pre)
    assert "DOE 명령 발령" in pjm_stage_explanation(pre)
    assert "실제 동원" in pjm_stage_explanation(pre)
    assert "운영 적용" not in pjm_title(pre)

    doe45 = """
    On September 17, 2026, the Department of Energy (DOE) issued emergency DOE Order No. 202-26-45,
    pursuant to section 202(c) of the Federal Power Act, to PJM Interconnection, L.L.C. (PJM).
    The order directs PJM to dispatch specified units and to order their operation as needed to maintain reliability.
    The order also authorizes PJM to direct backup generation resources to operate as a last resort before declaring
    an Energy Emergency Alert (EEA) 3 or during an EEA 3. The order is effective September 17 through September 18, 2026.
    """
    d45 = parse_doe_detail_html(doe45, "https://www.energy.gov/ceser/example-202-26-45")
    assert d45 and d45["party"] == "PJM" and d45["order_no"] == "202-26-45"
    c45, _ = doe_content(d45)
    assert "백업발전" in c45 and "EEA3" in c45

    doe46 = """
    On September 18, 2026, the U.S. Department of Energy (DOE) issued emergency DOE Order No. 202-26-46,
    pursuant to section 202(c) of the Federal Power Act, to Northern Indiana Public Service Company (NIPSCO)
    and the Midcontinent Independent System Operator, Inc. (MISO). The order directs NIPSCO and MISO to take
    all measures necessary to ensure that Units 17 and 18 at the R.M. Schahfer Generating Station in Wheatfield,
    Indiana are available to operate and to employ economic dispatch to minimize costs for the American people.
    The order is in effect beginning on September 20, 2026, through December 18, 2026.
    """
    d46 = parse_doe_detail_html(doe46, "https://www.energy.gov/ceser/example-202-26-46")
    assert d46 and d46["party"] == "NIPSCO·MISO" and d46["order_no"] == "202-26-46"
    c46, distinction46 = doe_content(d46)
    assert "Schahfer" in c46 and "경제급전" in c46
    assert "PJM" in distinction46 and "아니며" in distinction46
    rendered46 = render_event(d46, dt.datetime(2026, 9, 19, 20, 16, tzinfo=KST))
    assert "PJM에 202(c) 긴급명령 202-26-46" not in rendered46
    assert "NIPSCO·MISO에 202(c) 긴급명령 202-26-46" in rendered46
    assert "September" not in rendered46
    assert "2026년 9월 18일" in rendered46
    print("us_grid_emergency_official_self_test=passed")


if __name__ == "__main__":
    self_test()
