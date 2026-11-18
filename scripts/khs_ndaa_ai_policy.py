"""First-party NDAA / AI export-control events for the existing policy lane.

This module does not send messages, write seen-state, or change schedules.
GovInfo's BILLSTATUS file name contains a hyphen: BILLSTATUS-119hr2683.xml.
Date-only congressional records retain their US event date; the KST midnight
value is a sorting/freshness sentinel, not a claimed publication timestamp.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NDAA_KEY = "us_ndaa_ai_export_controls"
MAX_AGE_DAYS = 21
FETCH_TIMEOUT = 8
BASELINE_DATE = dt.date(2026, 11, 12)
BASELINE_URL = (
    "https://foreignaffairs.house.gov/news/press-releases/"
    "chairmen-mast-moolenaar-and-crawford-send-second-request-to-jensen-huang-"
    "and-nvidia-to-brief-congress-on-the-chinese-intelligence-asset"
)
TOPICS = {
    "rasa": ("RASA(원격접근보안법)", "Remote Access Security Act"),
    "match": ("MATCH Act(반도체 제조장비 통제 법안)", "MATCH Act"),
    "overwatch": ("AI OVERWATCH Act(첨단칩 수출 감독 법안)", "AI OVERWATCH Act"),
    "chip_security": ("Chip Security Act(반도체 보안 법안)", "Chip Security Act"),
    "ndaa": ("2027회계연도 국방수권법(NDAA)", "National Defense Authorization Act for Fiscal Year 2027"),
}


@dataclass(frozen=True)
class BillSpec:
    bill_type: str
    number: int
    topic: str

    @property
    def identifier(self) -> str:
        return f"{'H.R.' if self.bill_type == 'hr' else 'S.'}{self.number}"

    @property
    def url(self) -> str:
        return (f"https://www.govinfo.gov/bulkdata/BILLSTATUS/119/{self.bill_type}/"
                f"BILLSTATUS-119{self.bill_type}{self.number}.xml")


BILL_SPECS = (
    BillSpec("hr", 2683, "rasa"), BillSpec("s", 3519, "rasa"),
    BillSpec("hr", 8170, "match"), BillSpec("s", 4281, "match"),
    BillSpec("hr", 6875, "overwatch"), BillSpec("s", 4456, "overwatch"),
    BillSpec("hr", 3447, "chip_security"), BillSpec("s", 1705, "chip_security"),
    BillSpec("hr", 8800, "ndaa"), BillSpec("s", 4784, "ndaa"),
)

# Set only by the calling thread after parallel reads finish. The host can
# forward these records to its shared source-health writer sequentially.
_SOURCE_FAILURES: list[dict[str, str]] = []


def get_source_failures() -> list[dict[str, str]]:
    return [dict(row) for row in _SOURCE_FAILURES]


def _plain(value: str) -> str:
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _text(node: ET.Element, path: str) -> str:
    found = node.find(path)
    return " ".join(found.itertext()).strip() if found is not None else ""


def _day(value: str) -> dt.date:
    return dt.date.fromisoformat(value[:10])


def _recent(day: dt.date, now: dt.datetime) -> bool:
    return 0 <= (now.astimezone(KST).date() - day).days <= MAX_AGE_DAYS


STAGE_LABELS = {
    "introduced": "법안 발의", "committee-referred": "위원회 회부",
    "committee-approved": "위원회 가결·본회의 처리 전", "reported": "위원회 보고",
    "received-senate": "상원 이송", "received-house": "하원 이송",
    "amendment-submitted": "수정안 제출·채택 전", "amendment-adopted": "수정안 채택",
    "passed-house": "하원 본회의 통과", "passed-senate": "상원 본회의 통과",
    "house-agreed-senate-amendment": "하원의 상원 수정안 동의",
    "senate-agreed-house-amendment": "상원의 하원 수정안 동의",
    "conference-house": "하원 양원협의안 통과", "conference-senate": "상원 양원협의안 통과",
    "presented": "대통령 송부·서명 전", "signed": "대통령 서명",
    "enacted": "법률 제정", "vetoed": "대통령 거부권 행사",
    "cloture-failed": "토론 종결 표결 부결", "cloture-invoked": "토론 종결 가결·법안 통과 전",
    "passage-failed": "법안 통과 표결 부결",
}
_RANK = {name: i for i, name in enumerate(STAGE_LABELS)}
_RANK.update({"passed-house": 50, "passed-senate": 50, "received-senate": 51,
              "received-house": 51, "house-agreed-senate-amendment": 60,
              "senate-agreed-house-amendment": 60, "conference-house": 60,
              "conference-senate": 60, "presented": 70, "signed": 80,
              "enacted": 90, "vetoed": 80})


def classify_action(text: str, code: str = "", source: str = "") -> str | None:
    """Classify action fields only; never scan a bill's enacting-clause text."""
    low = re.sub(r"\s+", " ", text).strip().lower()
    if re.match(r"became (?:public|private) law\b", low):
        return "enacted" if re.search(r"\b119[-–]\d+\b", low) else None
    if re.match(r"signed by (?:the )?president\b", low):
        return "signed"
    if re.match(r"presented to (?:the )?president\b", low):
        return "presented"
    if re.match(r"vetoed by (?:the )?president\b", low):
        return "vetoed"
    if "cloture" in low:
        if re.search(r"\b(?:not invoked|rejected|failed)\b", low):
            return "cloture-failed"
        if re.search(r"\binvoked\b", low):
            return "cloture-invoked"
        return None
    if re.match(r"(?:on passage|on motion to suspend .*pass).*(?:failed|rejected)\b", low):
        return "passage-failed"
    for chamber in ("house", "senate"):
        other = "senate" if chamber == "house" else "house"
        if re.match(rf"{chamber} agreed to (?:the )?{other} amendment", low):
            return f"{chamber}-agreed-{other}-amendment"
        if re.match(rf"conference report agreed to in (?:the )?{chamber}\b", low):
            return f"conference-{chamber}"
        if re.match(rf"passed {chamber}\b", low):
            return f"passed-{chamber}"
    if (re.match(r"on passage passed\b", low)
            or re.match(r"on motion to suspend .*pass .*agreed to\b", low)):
        if code.startswith("H") or "house" in source.lower():
            return "passed-house"
        if code.startswith("S") or "senate" in source.lower():
            return "passed-senate"
    if re.match(r"ordered to be reported\b", low):
        return "committee-approved"
    if re.match(r"reported (?:by|to|with|without|amended)\b", low):
        return "reported"
    if re.match(r"received in (?:the )?senate\b", low):
        return "received-senate"
    if re.match(r"received in (?:the )?house\b", low):
        return "received-house"
    if re.match(r"(?:read twice and |read once and )?referred to\b", low):
        return "committee-referred"
    if re.match(r"introduced in (?:house|senate)\b", low):
        return "introduced"
    if re.match(r"(?:amendment (?:sa |s\.amdt\. ?)?\d+|s\.amdt\. ?\d+)\b", low):
        if re.search(r"\b(?:submitted|proposed|ordered to lie on the table)\b", low):
            return "amendment-submitted"
        if re.search(r"\b(?:agreed to|adopted)\b", low) and not re.search(r"\b(?:not|failed)\b", low):
            return "amendment-adopted"
    return None


def parse_bill_status(raw: str, spec: BillSpec, now: dt.datetime) -> dict:
    """Validate identity and choose the latest meaningful recent action."""
    root = ET.fromstring(raw)
    if root.tag != "billStatus":
        raise ValueError("not a GovInfo billStatus document")
    bill = root.find("bill")
    if bill is None or (_text(bill, "congress"), _text(bill, "type").lower(), _text(bill, "number")) != ("119", spec.bill_type, str(spec.number)):
        raise ValueError("GovInfo bill identity mismatch")
    title = _text(bill, "title")
    if not title:
        raise ValueError("GovInfo title missing")
    actions = list(bill.findall("./actions/item"))
    latest = bill.find("latestAction")
    if latest is not None:
        actions.append(latest)
    if not actions:
        raise ValueError("GovInfo action records missing")
    candidates = []
    for node in actions:
        day = _day(_text(node, "actionDate"))
        if day > now.astimezone(KST).date():
            raise ValueError("future congressional action date")
        if not _recent(day, now):
            continue
        action_text, code = _text(node, "text"), _text(node, "actionCode")
        source = _text(node, "sourceSystem")
        stage = classify_action(action_text, code, source)
        if not stage:
            continue
        # The NDAA has hundreds of unrelated amendments. Only a named target
        # or a verified target amendment number may enter this policy lane.
        if stage.startswith("amendment-") and spec.topic == "ndaa":
            names = [pair[1].lower() for key, pair in TOPICS.items() if key != "ndaa"]
            if not (any(name in action_text.lower() for name in names)
                    or re.search(r"\b(?:6211|6683)\b", action_text)):
                continue
        law = re.search(r"\b119[-–]\d+\b", action_text) if stage == "enacted" else None
        amendment = re.search(r"(?:s\.amdt\.?\s*|(?:amendment\s+)?sa\s+)(\d+)", action_text, re.I)
        # Do not include updateDate or a late-uploaded text URL in an action key.
        # Those change without another vote. Legal/action identifiers remain
        # stable while the actual text version is retained separately below.
        suffix = law.group().replace("–", "-") if law else (
            f"sa{amendment.group(1)}" if amendment else "official-action")
        candidates.append({"date": day, "stage": stage, "text": action_text,
                           "code": code, "suffix": suffix})
    action = max(candidates, key=lambda row: (row["date"], _RANK[row["stage"]]), default=None)
    versions = []
    for version in bill.findall("./textVersions/item"):
        date = _text(version, "date")
        if not date:
            continue
        urls = [_text(fmt, "url") for fmt in version.findall("./formats/item")]
        versions.append({"type": _text(version, "type"), "date": date, "urls": urls})
    return {"spec": spec, "title": title, "action": action, "versions": versions}


def _base_profile() -> dict:
    return {
        "timeline": "입법 촉구 → 수정안 제출·채택 → 양원 최종 문안 → 대통령 서명 → 후속 규칙·실제 적용",
        "next": "법안번호·수정안 문안·양원 표결·서명·시행일·허가 예외가 실제 바뀌었는지 확인합니다.",
        "investment": "첨단 반도체·제조장비·클라우드의 허가 비용과 고객 주문·납기 변화를 확인합니다.",
        "korea": "삼성전자·SK하이닉스의 중국 공장·고대역폭 메모리 수요, 국내 장비사의 고객별 허가 영향은 별도 확인합니다.",
        "priced_in": "법안 처리 기대와 실제 수출 제한·기업 수주 변화를 구분합니다.",
        "failure": "문안 삭제·완화, 처리 지연, 예외 변경과 고객 투자 지연 가능성을 함께 추적합니다.",
        "counter": "국방수권법의 높은 통과 관행이 개별 조항의 채택·즉시 시행을 보장하지 않습니다.",
        "impacts": ("매출·현금흐름", "수급", "시간표"),
        "paths": ("허가·예외 변경 → 고객 주문·납기 → 반도체·장비·클라우드 실적",),
        "sectors": ("반도체", "반도체 제조장비", "클라우드", "데이터센터"),
    }


def _item(profile: dict, day: dt.date, url: str, event_key: str, source: str) -> dict:
    return {"title": profile["title"], "description": " ".join(profile["actual_bullets"]),
            "link": url, "source": source,
            "published_kst": dt.datetime.combine(day, dt.time(), KST).isoformat(timespec="seconds"),
            "priority": 0, "official_direct_verified": True, "date_precision": "day",
            "ndaa_event_key": event_key, "ndaa_profile": profile}


def baseline_item(raw: str, now: dt.datetime) -> dict | None:
    if not _recent(BASELINE_DATE, now):
        return None
    low = _plain(raw).lower()
    markers = ("chairmen mast, moolenaar, and crawford", "send second request",
               "november 12, 2026", "ai overwatch act", "chip security act",
               "match act", "remote access security act")
    if not all(marker in low for marker in markers) or not re.search(r"must immediately pass.{0,300}\bin the ndaa\b", low):
        raise ValueError("committee statement date, identity, four bills or urging stage not verified")
    profile = {**_base_profile(),
        "title": "미 하원 위원장 3명, 인공지능 수출통제 4법안의 국방수권법 반영 촉구",
        "core": "2026년 11월 12일 하원 외교위·정보위·중국특위 위원장이 네 법안의 국방수권법 내 통과를 공동 촉구했습니다.",
        "stage": "공식 공동 촉구·패키지 최종 채택이나 법 제정 확인 아님",
        "event_date": BASELINE_DATE.isoformat(), "event_date_label": "미국 공식 발표일·시각 미공개",
        "actual_bullets": [
            "11월 12일 Brian Mast·Rick Crawford·John Moolenaar 위원장이 네 법안을 국방수권법에 담아 통과시킬 것을 공동 촉구했습니다.",
            "RASA는 원격접근, MATCH는 반도체 제조장비·유지보수, AI OVERWATCH는 첨단칩 수출허가 감독, Chip Security는 우회유출 방지·보안수단을 다룹니다.",
            "이 공동성명은 네 법안의 일괄 채택·제정 증거가 아니며, 기존에 제출된 법안·수정안과 이후 공식 표결을 구분합니다.",
            "Chip Security의 구체적인 보안수단과 시행기한은 수정 문안을 확인하며, 특정 위치추적 하드웨어의 일률적 의무화로 단정하지 않습니다.",
        ],
        "scope_note": "발언·입법 절차·행정규칙은 별개이며, 원격접근에 관한 BIS 규칙의 공개나 발효가 RASA 제정을 뜻하지 않습니다.",
    }
    return _item(profile, BASELINE_DATE, BASELINE_URL, "package-urged-2026-11-12", "미 하원 외교위원회 공동성명")


def _inclusion(raw: str, expected_spec: BillSpec | None = None) -> list[str]:
    """Require an operative short-title clause, not a table of contents/name hit."""
    root = ET.fromstring(raw)
    if root.tag.rsplit("}", 1)[-1] != "bill":
        raise ValueError("not an official bill-text XML document")
    if expected_spec is not None:
        number = re.sub(r"[^a-z0-9]", "", _text(root, "./form/legis-num").lower())
        if (number != f"{expected_spec.bill_type}{expected_spec.number}"
                or not re.match(r"119\b|119th\b", _text(root, "./form/congress"))):
            raise ValueError("NDAA text bill identity mismatch")
    clauses = []
    for section in root.iter():
        if section.tag.rsplit("}", 1)[-1] not in {"section", "subsection"}:
            continue
        direct = " ".join(" ".join(child.itertext()) for child in section
                          if child.tag.rsplit("}", 1)[-1] in {"text", "paragraph", "short-title"})
        clauses.extend(match.group(1).lower() for match in re.finditer(
            r"this\s+(?:act|subtitle|title|section|division)\s+may\s+be\s+cited\s+as\s+(.{1,350})", direct, re.I))
    return [key for key, pair in TOPICS.items() if key != "ndaa"
            and any(pair[1].lower() in clause for clause in clauses)]


def _body_check(doc: dict, fetch: Callable) -> tuple[str, list[str], dict | None]:
    spec, action = doc["spec"], doc["action"]
    versions = [v for v in doc["versions"] if _day(v["date"]) <= action["date"]]
    if not versions:
        return "본문 문안 미확인·네 법안 편입 확정 아님", [], None
    version = max(versions, key=lambda v: v["date"])
    pattern = rf"/content/pkg/BILLS-119{spec.bill_type}{spec.number}[a-z]+/xml/BILLS-119{spec.bill_type}{spec.number}[a-z]+\.xml"
    urls = [u for u in version["urls"] if urlparse(u).scheme == "https"
            and urlparse(u).hostname == "www.govinfo.gov" and re.fullmatch(pattern, urlparse(u).path)]
    if not urls:
        return "공식 본문 주소 미확인·네 법안 편입 확정 아님", [], None
    url = urls[0]
    try:
        included = _inclusion(fetch(url, timeout=FETCH_TIMEOUT), spec)
    except Exception as exc:
        return "공식 본문 조회 실패·네 법안 편입 미확인", [], {
            "source": f"NDAA 본문 {spec.identifier}", "url": url,
            "error": f"{type(exc).__name__}: {exc}"[:500]}
    suffix = "본문의 단축명 조항 확인: " + "·".join(TOPICS[key][0] for key in included) if included else "네 법안의 명시적 단축명 조항 미검출·동등 조항 존재 여부는 미확인"
    version_label = {
        "Introduced in House": "하원 발의본", "Introduced in Senate": "상원 발의본",
        "Reported in House": "하원 위원회 보고본", "Reported to Senate": "상원 위원회 보고본",
        "Reported in Senate": "상원 위원회 보고본", "Engrossed in House": "하원 통과본",
        "Engrossed in Senate": "상원 통과본", "Referred in Senate": "상원 회부본",
        "Engrossed Amendment House": "하원 수정안 통과본", "Engrossed Amendment Senate": "상원 수정안 통과본",
        "Enrolled Bill": "양원 최종 의결본", "Public Law": "제정 법률",
    }.get(version["type"], "공식 문안·버전 종류 별도 확인")
    return f"참조 문안 {version['date'][:10]}({version_label}): {suffix}; 현재 처리단계와 같은 최종 문안인지 별도 확인", included, None


def _action_item(doc: dict, fetch: Callable) -> tuple[dict, dict | None]:
    spec, action = doc["spec"], doc["action"]
    stage, day = action["stage"], action["date"]
    label = TOPICS[spec.topic][0]
    profile = {**_base_profile(), "title": f"{label} {spec.identifier} · {STAGE_LABELS[stage]}",
        "core": f"{spec.identifier}의 {day.isoformat()} 미국 의회 공식 행동에서 {STAGE_LABELS[stage]}이 확인됐습니다.",
        "stage": STAGE_LABELS[stage], "event_date": day.isoformat(),
        "event_date_label": "미국 의회 기록상 사건일·시각 미공개",
        "actual_bullets": [f"119대 의회 {spec.identifier}: {day.isoformat()} {STAGE_LABELS[stage]}.",
                           "법안 처리 단계와 기업별 허가·예외·실제 적용일을 구분해 확인합니다."],
        "scope_note": "공식 행동 기록을 확인했으며, 후속 규칙과 기업별 실적 영향은 별도 검증 대상입니다.",
    }
    if stage == "enacted":
        profile["actual_bullets"].insert(1, f"확인된 법률번호는 {action['suffix']}이며, 법률 성립과 조항별 시행·유예기한은 구분합니다.")
    votes = re.search(r"(?:Yeas and Nays|Yea-Nay Vote).*?:?\s(\d+)\s*-\s*(\d+)\b", action["text"], re.I)
    if votes:
        profile["actual_bullets"].insert(1, f"공식 행동 기록의 표결은 찬성 {votes.group(1)}표·반대 {votes.group(2)}표입니다.")
    failure = None
    included = []
    if spec.topic == "ndaa":
        scope, included, failure = _body_check(doc, fetch)
        profile["scope_note"] = scope
        profile["actual_bullets"].append("국방수권법 전체의 처리 결과만으로 네 수출통제 법안이 모두 포함됐다고 판단하지 않습니다.")
    key = f"119-{spec.bill_type}{spec.number}-{stage}-{day.isoformat()}-{action['suffix']}"
    item = _item(profile, day, spec.url, key, "미 정부출판국(GovInfo) 의회 공식 행동 기록")
    item.update({"ndaa_bill_id": f"119-{spec.bill_type}{spec.number}", "ndaa_stage": stage,
                 "ndaa_action_code": action["code"], "ndaa_action_text": action["text"],
                 "ndaa_text_versions": doc["versions"], "ndaa_included_topics": included})
    return item, failure


def collect_ndaa_items(now: dt.datetime, fetch_text_callable: Callable) -> list[dict]:
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    _SOURCE_FAILURES.clear()
    items: list[dict] = []

    def read(spec: BillSpec) -> tuple[dict | None, dict | None]:
        try:
            raw = fetch_text_callable(spec.url, timeout=FETCH_TIMEOUT)
            return parse_bill_status(raw, spec, now), None
        except Exception as exc:
            return None, {"source": f"NDAA GovInfo {spec.identifier}", "url": spec.url,
                          "error": f"{type(exc).__name__}: {exc}"[:500]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read, BILL_SPECS))
    for doc, failure in results:
        if failure:
            _SOURCE_FAILURES.append(failure)
        elif doc is not None and doc["action"] is not None:
            item, body_failure = _action_item(doc, fetch_text_callable)
            items.append(item)
            if body_failure:
                _SOURCE_FAILURES.append(body_failure)
    if _recent(BASELINE_DATE, now):
        try:
            item = baseline_item(fetch_text_callable(BASELINE_URL, timeout=FETCH_TIMEOUT), now)
            if item:
                items.append(item)
        except Exception as exc:
            _SOURCE_FAILURES.append({"source": "NDAA 하원 위원장 공동성명", "url": BASELINE_URL,
                                     "error": f"{type(exc).__name__}: {exc}"[:500]})
    for failure in _SOURCE_FAILURES:
        print(f"ndaa_policy=source_failure source={failure['source']!r} url={failure['url']} error={failure['error']!r}")
    print(f"ndaa_policy=collection_complete bill_sources={len(BILL_SPECS)} "
          f"bill_sources_ok={sum(doc is not None for doc, _ in results)} "
          f"source_failures={len(_SOURCE_FAILURES)} events={len(items)}")
    return sorted(items, key=lambda row: (row["published_kst"], row["ndaa_event_key"]), reverse=True)
