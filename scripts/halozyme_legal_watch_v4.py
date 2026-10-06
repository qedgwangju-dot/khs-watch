from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import html
import json
import os
import re
import time
import urllib.parse

import halozyme_legal_watch_v3 as v3

base = v3.base
_original_get_case = base.get_case
_original_rss = base.rss

ALTEOGEN_IR_LIST_URL = "https://alteogen.com/kr/sub/ir/information.php?bid=2"
ALTEOGEN_IR_CURRENT_URL = "https://alteogen.com/kr/sub/ir/information.php?bid=2&idx=374&mode=view&page=1"
OFFICIAL_IR_HTTP_TIMEOUT = 7
OFFICIAL_IR_HTTP_ATTEMPTS = 2
OFFICIAL_IR_RETRY_BACKOFF_SECONDS = 0.5
OFFICIAL_IR_WORKERS = 4
OFFICIAL_IR_MAX_ARTICLES = 12


def _official_ir_fetch(url: str) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, OFFICIAL_IR_HTTP_ATTEMPTS + 1):
        try:
            return base.fetch(url, timeout=OFFICIAL_IR_HTTP_TIMEOUT)
        except Exception as exc:
            last_exc = exc
            if attempt < OFFICIAL_IR_HTTP_ATTEMPTS:
                time.sleep(OFFICIAL_IR_RETRY_BACKOFF_SECONDS * attempt)
    assert last_exc is not None
    raise last_exc
CURRENT_PORTFOLIO_SCORECARD = {
    "url": ALTEOGEN_IR_CURRENT_URL,
    "title": "알테오젠 파트너 MSD, 할로자임 MDASE 여섯 번째·일곱 번째 특허 무효화 판정",
    "score": {
        "total": 14,
        "won": 7,
        "pending": 7,
        "oral_date": "2026-07-23",
        "patents": ["12,049,652", "12,104,185"],
    },
}

# 동일 사건당 4개 변형 검색을 직렬 반복하던 구조를 제거한다.
# 각 알려진 PGR·IPR은 정확 사건번호 검색 1개로 전수 추적하고,
# 최종결정·국장 재검토·재심·항소·민사소송·한국어 보도는 별도 광역 검색축으로 유지한다.
base.SEARCHES = [
    '"Halozyme" "Merck" PTAB PGR',
    '"Halozyme" "Merck" "Final Written Decision"',
    '"Halozyme" "Merck" "Director Review" PTAB',
    '"Halozyme" "Merck" rehearing PTAB',
    '"Halozyme" "Merck" "Federal Circuit" patent',
    '"Halozyme" "Merck" MDASE patent',
    '"Halozyme" "Merck" modified PH20 patent',
    '"2:25-cv-03179" Halozyme Merck',
    '할로자임 MSD 특허 무효 PGR',
    '할로자임 MDASE 특허 PTAB',
    '알테오젠 할로자임 특허 분쟁 MSD',
    'Halozyme MSD 특허심판원 무효',
    '"알테오젠 파트너 MSD" 할로자임 PH20 특허 특허성 없음',
    '"할로자임 PH20" MSD 특허성 없음',
    '"Halozyme" "PH20" Merck unpatentable',
]
for case in base.KNOWN_CASES:
    base.SEARCHES.append(f'"{case}" Halozyme Merck')


_CURRENT_BATCH_SOURCE = "http://the-biz.co.kr/news/articleView.html?idxno=728392"
ALTEOGEN_IR_INDEX = "https://www.alteogen.com/kr/sub/ir/information.php?bid=2"

# 2026-10-03 사용자 제공 PTAB 결정문 첫 페이지를 기준으로 사건번호·특허번호·결정일·
# "Final Written Decision Determining All Challenged Claims Unpatentable" 문구를 직접 대조했다.
# 사건 자체는 USPTO 공개 P-TACTS 사건 페이지로 연결하고, 검색색인 지연과 무관하게
# 이번 두 최종결정은 한 번만 백필하여 즉시 알림·상태·타임라인에 반영한다.
PTACTS_CASE_URLS = {
    "PGR2025-00046": "https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557766",
    "PGR2025-00052": "https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557959",
}

VERIFIED_CURRENT_DECISIONS = [
    {
        "engine": "USPTO/PTAB 공식 결정문",
        "title": "PGR2025-00052 Final Written Decision — all challenged claims unpatentable",
        "url": PTACTS_CASE_URLS["PGR2025-00052"],
        "description": (
            "PGR2025-00052 Patent 12,264,345 B1 Paper 89 Date October 1, 2026. "
            "JUDGMENT Final Written Decision Determining All Challenged Claims Unpatentable "
            "35 U.S.C. § 328(a). Halozyme Merck."
        ),
        "published": "Thu, 01 Oct 2026 00:00:00 GMT",
    },
    {
        "engine": "USPTO/PTAB 공식 결정문",
        "title": "PGR2025-00046 Final Written Decision — all challenged claims unpatentable",
        "url": PTACTS_CASE_URLS["PGR2025-00046"],
        "description": (
            "PGR2025-00046 Patent 12,091,692 B2 Paper 96 Date October 2, 2026. "
            "JUDGMENT Final Written Decision Determining All Challenged Claims Unpatentable "
            "35 U.S.C. § 328(a). Halozyme Merck."
        ),
        "published": "Fri, 02 Oct 2026 00:00:00 GMT",
    },
]

PTAB_VERIFIED_PORTFOLIO_SCORECARD = {
    "url": PTACTS_CASE_URLS["PGR2025-00052"],
    "source_urls": [PTACTS_CASE_URLS["PGR2025-00052"], PTACTS_CASE_URLS["PGR2025-00046"]],
    "source_kind": "ptab_verified_rollup",
    "title": "PTAB 신규 최종서면결정 2건 반영 — 누적 9/14",
    "score": {
        "total": 14,
        "won": 9,
        "pending": 5,
        "oral_date": "2026-07-23",
        "patents": ["12,264,345", "12,091,692"],
    },
}


def _strip_tags(value: str) -> str:
    import html as _html
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", _html.unescape(value)).strip()


def _alteogen_official_portfolio_items() -> list[dict]:
    try:
        page = _official_ir_fetch(ALTEOGEN_IR_INDEX)
    except Exception:
        return []

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']*information\.php\?[^"\']*idx=\d+[^"\']*)["\'][^>]*>(.*?)</a>', page):
        href = match.group(1).replace("&amp;", "&")
        title = _strip_tags(match.group(2))
        url = urllib.parse.urljoin(ALTEOGEN_IR_INDEX, href)
        if url in seen:
            continue
        seen.add(url)
        low_title = title.lower()
        if not any(k in low_title for k in ("할로자임", "halozyme", "mdase", "특허")):
            continue
        candidates.append((title, url))
        if len(candidates) >= OFFICIAL_IR_MAX_ARTICLES:
            break

    if not candidates:
        return []

    def load(candidate: tuple[str, str]) -> dict | None:
        title, url = candidate
        try:
            article = _strip_tags(_official_ir_fetch(url))
        except Exception:
            article = title
        low = article.lower()
        if not ("pgr" in low and ("할로자임" in low or "halozyme" in low or "mdase" in low)):
            return None
        return {
            "engine": "알테오젠 공식 IR",
            "title": title or "알테오젠 Halozyme 특허분쟁 누적 현황",
            "url": url,
            "description": article[:12000],
            "published": "",
        }

    out: list[dict] = []
    workers = max(1, min(OFFICIAL_IR_WORKERS, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="alteogen-ir") as pool:
        futures = [pool.submit(load, candidate) for candidate in candidates]
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception:
                item = None
            if item:
                out.append(item)
    return out


_official_portfolio_cache: list[dict] | None = None


def rss(query: str, engine: str) -> list[dict]:
    out = _original_rss(query, engine)
    if engine == "Bing 웹" and query == base.SEARCHES[0]:
        out.extend([
            {
                "engine": "현재 사건 교차검증",
                "title": "PGR2025-00033 Halozyme Merck Final Written Decision all challenged claims unpatentable",
                "url": _CURRENT_BATCH_SOURCE,
                "description": "PGR2025-00033 12,049,652 PH20 특허 심판 대상 청구항 특허성 없음",
                "published": "Fri, 25 Sep 2026 12:00:00 GMT",
            },
            {
                "engine": "현재 사건 교차검증",
                "title": "PGR2025-00039 Halozyme Merck Final Written Decision all challenged claims unpatentable",
                "url": _CURRENT_BATCH_SOURCE + "#pgr2025-00039",
                "description": "PGR2025-00039 12,104,185 PH20 특허 심판 대상 청구항 특허성 없음",
                "published": "Fri, 25 Sep 2026 12:00:00 GMT",
            },
        ])
        out.extend(VERIFIED_CURRENT_DECISIONS)
    global _official_portfolio_cache
    if engine == "Bing 웹" and query == base.SEARCHES[0]:
        if _official_portfolio_cache is None:
            _official_portfolio_cache = _alteogen_official_portfolio_items()
        out.extend(_official_portfolio_cache)
    return out


base.rss = rss

FINAL_UNPATENTABLE_TERMS = (
    "all challenged claims unpatentable",
    "determining all challenged claims unpatentable",
    "held all challenged claims unpatentable",
    "found all challenged claims unpatentable",
    "all challenged claims invalid",
    "청구항 전부 무효",
    "심판 대상 청구항 전부 무효",
    "전부 무효",
    "특허성 없음",
    "특허 받을 수 없음",
)

CURRENT_CONFIRMED_UNPATENTABLE = {
    "PGR2025-00033",
    "PGR2025-00039",
    "PGR2025-00046",
    "PGR2025-00052",
}

CASE_TIMELINES = {
    "PGR2025-00033": (
        ("2025-03-07", "PGR 청구"),
        ("2025-10-01", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-09-25", "최종서면결정"),
    ),
    "PGR2025-00039": (
        ("2025-03-28", "PGR 청구"),
        ("2025-10-01", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-09-25", "최종서면결정"),
    ),
    "PGR2025-00046": (
        ("2025-04-29", "PGR 청구"),
        ("2025-10-10", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-10-02", "최종서면결정"),
    ),
    "PGR2025-00052": (
        ("2025-06-27", "PGR 청구"),
        ("2025-10-16", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-10-01", "최종서면결정"),
    ),
}


TIMELINE_EVENT_LABELS = {
    "institution": "심판 개시",
    "final_unpatentable": "최종서면결정",
    "final_decision": "최종서면결정",
    "director_review": "국장 재검토",
    "rehearing": "PTAB 재심",
    "appeal": "연방순회항소법원 항소",
    "termination": "종결·합의",
    "disclaimer": "청구항 포기",
}

_successful_timeline_events: list[dict] = []
_pending_timeline_event: dict | None = None


def _event_date(item: dict) -> str:
    published = str(item.get("published") or "").strip()
    if published:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(published).date().isoformat()
        except Exception:
            pass
    blob = " ".join(str(item.get(key) or "") for key in ("title", "description"))
    m = re.search(r"\b(20\d{2})[-./년 ](\d{1,2})[-./월 ](\d{1,2})(?:일)?\b", blob)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def _timeline_event(case: str, kind: str, item: dict) -> dict | None:
    if not case.startswith(("PGR", "IPR")):
        return None
    label = TIMELINE_EVENT_LABELS.get(kind)
    if not label:
        return None
    return {
        "case": case,
        "date": _event_date(item),
        "kind": kind,
        "label": label,
    }


def _persisted_timeline_rows(case: str) -> list[dict]:
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = (state.get("case_event_timelines") or {}).get(case) or []
    return [row for row in rows if isinstance(row, dict)]


def _merged_case_timelines(state: dict) -> dict:
    timelines = dict(state.get("case_event_timelines") or {})

    def add(case: str, date: str, label: str, kind: str = "") -> None:
        rows = [row for row in (timelines.get(case) or []) if isinstance(row, dict)]
        key = (date, label)
        if key not in {(str(row.get("date") or ""), str(row.get("label") or "")) for row in rows}:
            rows.append({"date": date, "kind": kind, "label": label})
        rows.sort(key=lambda row: (str(row.get("date") or "9999-99-99"), str(row.get("label") or "")))
        timelines[case] = rows[-30:]

    for case, rows in CASE_TIMELINES.items():
        for date, label in rows:
            add(case, date, label)

    for event in _successful_timeline_events:
        add(
            str(event.get("case") or ""),
            str(event.get("date") or ""),
            str(event.get("label") or ""),
            str(event.get("kind") or ""),
        )
    return timelines

FINAL_DECISION_TERMS = (
    "final written decision",
    "status final written decision",
    "최종서면결정",
    "최종 서면 결정",
    "최종 결정",
)


CURRENT_POST_FWD_TIMELINE_CASES = {
    "PGR2025-00033",
    "PGR2025-00039",
    "PGR2025-00046",
    "PGR2025-00052",
}


def classify(text: str, case: str) -> str:
    low = text.lower()
    if case.startswith("HALOZYME-PGR-PORTFOLIO-"):
        return "portfolio_update"
    if case == base.DISTRICT_CASE:
        return "district_order"

    # 최종서면결정 이후의 재검토·재심·항소 서류는 본문에 기존 FWD 문구를
    # 반복 인용하는 경우가 많다. 최신 판세 사건은 후속 절차를 FWD보다
    # 먼저 판정해 타임라인 변화가 기존 최종결정으로 오분류되어 누락되지 않게 한다.
    if case in CURRENT_POST_FWD_TIMELINE_CASES:
        for key, terms in (
            ("director_review", ("director review", "director-review", "국장 재검토")),
            ("rehearing", ("request for rehearing", "rehearing", "재심")),
            ("appeal", ("notice of appeal", "federal circuit", "court of appeals", "연방순회항소법원", "항소")),
        ):
            if any(term in low for term in terms):
                return key

    if any(term in low for term in FINAL_UNPATENTABLE_TERMS):
        return "final_unpatentable"

    if any(term in low for term in FINAL_DECISION_TERMS):
        if case in CURRENT_CONFIRMED_UNPATENTABLE:
            return "final_unpatentable"
        return "final_decision"

    # 최종결정 외 절차는 기존 분류 규칙을 유지한다.
    for key, terms in base.EVENTS:
        if key in ("district_order", "final_unpatentable"):
            continue
        if any(t.lower() in low for t in terms):
            return key
    return ""


def timeline_line(case: str, kind: str, item: dict) -> str:
    if case.startswith(("PGR", "IPR")):
        rows: list[tuple[str, str]] = list(CASE_TIMELINES.get(case) or ())
        for row in _persisted_timeline_rows(case):
            rows.append((str(row.get("date") or ""), str(row.get("label") or "")))
        for event in _successful_timeline_events:
            if event.get("case") == case:
                rows.append((str(event.get("date") or ""), str(event.get("label") or "")))
        current = _timeline_event(case, kind, item)
        if current:
            rows.append((str(current.get("date") or ""), str(current.get("label") or "")))

        unique: dict[tuple[str, str], tuple[str, str]] = {}
        for date, label in rows:
            if label:
                unique.setdefault((date, label), (date, label))
        ordered = sorted(unique.values(), key=lambda row: (row[0] or "9999-99-99", row[1]))
        if ordered:
            return " → ".join(
                f"{date} {label}" if date else f"날짜 확인 필요 · {label}"
                for date, label in ordered
            )

    published = str(item.get("published") or "").strip()
    event_label = {
        "district_order": "연방법원 절차 변화",
    }.get(kind, TIMELINE_EVENT_LABELS.get(kind, "새 절차 변화"))
    if published:
        try:
            from email.utils import parsedate_to_datetime
            stamp = parsedate_to_datetime(published)
            return f"{stamp.date().isoformat()} {event_label}"
        except Exception:
            pass
    return f"날짜 확인 필요 · {event_label}"


def _korean_date_label(date_text: str) -> str:
    m = re.fullmatch(r"(20\d{2})-(\d{2})-(\d{2})", date_text.strip())
    if not m:
        return html.escape(date_text)
    return f"{int(m.group(1))}년 {int(m.group(2))}월 {int(m.group(3))}일"


def timeline_html(case: str, kind: str, item: dict) -> str:
    rows: list[str] = []
    for segment in timeline_line(case, kind, item).split(" → "):
        segment = segment.strip()
        m = re.match(r"^(20\d{2}-\d{2}-\d{2})\s+(.+)$", segment)
        if m:
            rows.append(
                f"• <b>{_korean_date_label(m.group(1))}</b> {html.escape(m.group(2))}"
            )
        else:
            rows.append(f"• {html.escape(segment)}")
    return "\n".join(rows)


_original_alert = base.alert


def alert(case: str, patent: str, kind: str, item: dict) -> str:
    global _pending_timeline_event
    _pending_timeline_event = None
    if kind == "portfolio_update":
        m = re.search(r"(\d+)OF(\d+)$", case)
        decided = int(m.group(1)) if m else 0
        total = int(m.group(2)) if m else 0
        remaining = max(0, total - decided)
        url = html.escape(item["url"], quote=True)
        return (
            "<b>[바이오 감시] Halozyme 특허분쟁 누적 판세 업데이트</b>\n\n"
            f"<b>MSD PGR {total}건 중 {decided}건에서 심판 대상 청구항 특허성 부정</b>\n\n"
            "- <b>타임라인:</b>\n"
            "• <b>2026년 7월 23일</b> 잔여 사건 포함 구술심리\n"
            "• <b>2026년 9월 25일</b> PGR2025-00033·00039 최종서면결정\n"
            "• <b>2026년 9월 28일</b> 알테오젠 공식 IR 누적 판세 확인\n"
            f"- <b>현재 판세:</b> 최종결정 {decided}건 특허성 부정 · 잔여 {remaining}건 최종결정 대기\n"
            "- <b>알테오젠:</b> 단일 사건 승패가 아니라 Halozyme MDASE 특허군 전체의 방어력이 약해지는 흐름을 보여주는 후속 업데이트입니다. ALT-B4 자체 특허 유효성 판정은 아닙니다.\n"
            "- <b>다음 확인:</b> 잔여 PGR 최종서면결정 → 국장 재검토·재심 → 연방순회항소법원 항소 → 뉴저지·유럽 소송\n"
            "- <b>원문 확인:</b> 알테오젠 공식 IR 본문 직접 확인\n"
            f'- <a href="{url}">원문 뉴스보기</a>'
        )

    _pending_timeline_event = _timeline_event(case, kind, item)

    if kind != "final_decision":
        message = _original_alert(case, patent, kind, item)
        timeline = timeline_html(case, kind, item)
        lines = message.splitlines()
        for idx, line in enumerate(lines):
            if "<b>사건:</b>" in line:
                lines.insert(idx + 1, f"- <b>타임라인:</b>\n{timeline}")
                break
        if kind == "final_unpatentable":
            for idx, line in enumerate(lines):
                if "<b>다음 확인:</b>" in line:
                    lines.insert(
                        idx,
                        "- <b>절차 시계:</b> 최종서면결정 후 30일 내 USPTO 국장 재검토 또는 PTAB 재심 중 하나를 요청할 수 있습니다. 기본 항소기간은 63일이며, 적법한 재검토·재심이 있으면 항소 시계가 재설정됩니다.",
                    )
                    break
        return "\n".join(lines)

    title = f"PTAB 최종서면결정 공개 — {case}, Halozyme 특허 {patent or '관련 특허'}"
    src = "USPTO/PTAB·법원 공식자료" if base.official(item["url"]) else "2차 자료 — 공식 결정문 결과 교차확인 대상"
    url = html.escape(item["url"], quote=True)
    return (
        "<b>[바이오 감시] Halozyme 특허분쟁</b>\n\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"- <b>사건:</b> {html.escape(case)}"
        + (f" · 미국 특허 {html.escape(patent)}" if patent else "")
        + "\n"
        f"- <b>타임라인:</b>\n{timeline_html(case, kind, item)}\n"
        "- <b>결정:</b> PTAB 최종서면결정이 공개됐습니다. 청구항별 특허성 판단은 원문 결과를 추가 교차확인합니다.\n"
        "- <b>알테오젠:</b> Halozyme 변형 PH20 특허 장벽과 MSD·알테오젠의 미국 피하주사 사업 리스크에 직접 연결되는 사건입니다.\n"
        "- <b>다음 확인:</b> 청구항별 특허성 결과 → 국장 재검토·재심 → 연방순회항소법원 항소\n"
        f"- <b>원문 확인:</b> {src}\n"
        f'- <a href="{url}">원문 뉴스보기</a>'
    )


def get_case(text: str) -> tuple[str, str]:
    case, patent = _original_get_case(text)
    if case:
        return case, patent

    low = text.lower()
    # 2026-09-25에 동시에 최종서면결정이 확인된 두 사건을 다룬
    # "PH20 특허 2건" 기사 중 사건번호가 RSS 요약에서 빠진 경우의 식별 보조.
    if (
        "halozyme" in low or "할로자임" in low
    ) and (
        "ph20" in low or "mdase" in low
    ) and (
        "특허 2건" in low or "2건" in low
    ) and (
        "특허성 없음" in low or "unpatentable" in low
    ):
        return "PGR2025-00033", base.KNOWN_CASES["PGR2025-00033"]
    return "", ""


base.classify = classify
base.alert = alert
base.get_case = get_case


def _plain_text(page: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", page)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_portfolio_scorecard(text: str) -> dict | None:
    low = text.lower()
    if "halozyme" not in low and "할로자임" not in text:
        return None
    if "pgr" not in low:
        return None

    total = won = pending = None
    m = re.search(r"PGR\s*(\d+)\s*건\s*가운데\s*(\d+)\s*건", text, re.I)
    if m:
        total, won = int(m.group(1)), int(m.group(2))
    m2 = re.search(r"나머지\s*(\d+)\s*건", text)
    if m2:
        pending = int(m2.group(1))
    if total is None or won is None:
        return None
    if pending is None:
        pending = max(0, total - won)

    oral = ""
    mh = re.search(r"(?:지난\s*)?(\d{1,2})월\s*(\d{1,2})일\s*구술심리", text)
    if mh:
        oral = f"2026-{int(mh.group(1)):02d}-{int(mh.group(2)):02d}"

    patents = []
    for patent in re.findall(r"\b12[,\d]{7,}\b", text):
        cleaned = patent.replace(",", "")
        if len(cleaned) == 8:
            formatted = f"{cleaned[:2]},{cleaned[2:5]},{cleaned[5:]}"
            if formatted not in patents:
                patents.append(formatted)

    return {
        "total": total,
        "won": won,
        "pending": pending,
        "oral_date": oral,
        "patents": patents[:6],
    }


def _portfolio_ir_urls() -> list[str]:
    urls = [ALTEOGEN_IR_CURRENT_URL]
    try:
        page = base.fetch(ALTEOGEN_IR_LIST_URL, timeout=7)
        for href, label in re.findall(r'href=["\']([^"\']*information\.php\?[^"\']*idx=\d+[^"\']*)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
            title = _plain_text(label)
            if not any(k in title.lower() for k in ("halozyme", "mdase", "pgr", "ipr")) and "할로자임" not in title:
                continue
            url = urllib.parse.urljoin(ALTEOGEN_IR_LIST_URL, html.unescape(href))
            if url not in urls:
                urls.append(url)
    except Exception:
        pass
    return urls[:12]


def portfolio_scorecard_key(score: dict) -> str:
    return base.digest(
        f"portfolio|{score['total']}|{score['won']}|{score['pending']}|{score.get('oral_date') or ''}"
    )


def portfolio_updates() -> list[dict]:
    # 현재 공식 IR에서 확인된 7/14 판세는 검색색인·HTML 파싱 실패와 무관하게
    # 한 번은 반드시 이벤트로 소비하도록 검증된 기준선을 포함한다.
    updates: list[dict] = [CURRENT_PORTFOLIO_SCORECARD, PTAB_VERIFIED_PORTFOLIO_SCORECARD]
    global _official_portfolio_cache
    if _official_portfolio_cache is None:
        _official_portfolio_cache = _alteogen_official_portfolio_items()
    for official_item in _official_portfolio_cache:
        text = str(official_item.get("description") or "")
        score = parse_portfolio_scorecard(text)
        if not score:
            continue
        updates.append({
            "url": base.clean_url(str(official_item.get("url") or "")),
            "title": str(official_item.get("title") or "알테오젠 공식 IR Halozyme PGR 판세 업데이트"),
            "score": score,
        })
    unique = {}
    for item in updates:
        s = item["score"]
        key = portfolio_scorecard_key(s)
        unique.setdefault(key, item)
    return list(unique.values())


def portfolio_alert(item: dict) -> str:
    s = item["score"]
    ratio = (s["won"] / s["total"] * 100.0) if s["total"] else 0.0
    oral = f" · {s['oral_date']} 공동 구술심리" if s.get("oral_date") else ""
    patents = " · ".join(s.get("patents") or [])
    patent_line = f"\n- <b>이번 확인 특허:</b> {html.escape(patents)}" if patents else ""
    source_kind = str(item.get("source_kind") or "alteogen_ir")

    if source_kind == "ptab_verified_rollup":
        source_urls = list(item.get("source_urls") or [])
        source_links = "\n".join(
            f'- <a href="{html.escape(url, quote=True)}">USPTO/PTAB 사건 원문 {idx}</a>'
            for idx, url in enumerate(source_urls, 1)
        )
        return (
            "<b>[바이오 감시] Halozyme 특허분쟁 판세 업데이트</b>\n\n"
            f"<b>PTAB 신규 최종서면결정 2건 반영 — 누적 {s['won']}/{s['total']}건</b>\n\n"
            "- <b>타임라인:</b>\n"
            "• <b>2026년 7월 23일</b> 관련 10개 PGR 공동 구술심리\n"
            "• <b>2026년 9월 25일</b> PGR2025-00033·00039 최종서면결정\n"
            "• <b>2026년 9월 28일</b> 알테오젠 공식 IR 7/14 확인\n"
            "• <b>2026년 10월 1일</b> PGR2025-00052 최종서면결정\n"
            "• <b>2026년 10월 2일</b> PGR2025-00046 최종서면결정\n"
            f"- <b>누적 판세:</b> PTAB 확인 기준 {s['won']}/{s['total']}건 · {ratio:.0f}% · 잔여 {s['pending']}건{oral}"
            + patent_line
            + "\n- <b>결정:</b> PGR2025-00052와 PGR2025-00046 모두 PTAB가 심판 대상 청구항 전부를 특허 받을 수 없다고 최종 판단했습니다.\n"
            "- <b>정확한 성격:</b> 알테오젠이 9/14를 새 공식 IR로 발표했다는 뜻이 아니라, 9월 28일 공식 7/14 기준에 이후 PTAB 최종결정 2건을 더한 현재 확인치입니다.\n"
            "- <b>알테오젠:</b> ALT-B4 자체 특허 유효성 판정은 아니지만, Halozyme MDASE 특허 포트폴리오 방어력이 추가로 약해지는 방향입니다.\n"
            "- <b>절차 시계:</b> 각 최종서면결정 후 30일 내 USPTO 국장 재검토 또는 PTAB 재심 중 하나 → 기본 63일 내 연방순회항소법원 항소. 재검토·재심이 있으면 항소 시계는 재설정됩니다.\n"
            "- <b>다음 확인:</b> 잔여 5건 최종서면결정 → 국장 재검토·재심 → 연방순회항소법원 항소 → 뉴저지·유럽 소송\n"
            "- <b>원문 확인:</b> 사용자 제공 PTAB 결정문 첫 페이지 직접 대조 + USPTO/P-TACTS 사건 식별 교차확인\n"
            + source_links
        )

    return (
        "<b>[바이오 감시] Halozyme 특허분쟁 판세 업데이트</b>\n\n"
        f"<b>MSD, 심리 개시 PGR {s['total']}건 중 {s['won']}건에서 특허성 부정</b>\n\n"
        f"- <b>누적 판세:</b> {s['won']}/{s['total']}건 · {ratio:.0f}%\n"
        f"- <b>잔여:</b> {s['pending']}건 최종결정 대기{oral}"
        + patent_line
        + "\n- <b>의미:</b> 개별 특허 결과를 넘어 Halozyme MDASE 특허 포트폴리오 전체에서 MSD 우위가 누적되고 있다는 공식 IR 업데이트입니다.\n"
        "- <b>알테오젠:</b> ALT-B4 자체 특허 유효성 판정은 아니지만, KEYTRUDA QLEX 미국 사업에 반영되던 Halozyme 특허분쟁 불확실성을 낮추는 방향입니다.\n"
        "- <b>아직 남음:</b> 잔여 PGR 최종결정 · 국장 재검토·재심 · 연방순회항소 · 뉴저지·유럽 소송\n"
        f"- <b>다음 확인:</b> {s['won']}/{s['total']} → 다음 누적 판세 변화와 후속 절차\n"
        "- <b>원문 확인:</b> 알테오젠 공식 IR 본문 직접 열람\n"
        f'- <a href="{html.escape(item["url"], quote=True)}">원문 뉴스보기</a>'
    )


def send_portfolio_updates() -> list[int]:
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    seen = set(state.get("seen_portfolio_updates") or [])
    token = (os.getenv("BIO_TELEGRAM_BOT_TOKEN") or "").strip()
    chat = base.resolve_chat_id(token) if token else ""
    sent = []
    if not token or not chat:
        return sent

    for item in portfolio_updates():
        s = item["score"]
        key = portfolio_scorecard_key(s)
        if key in seen:
            continue
        mid = base.send(token, chat, portfolio_alert(item))
        sent.append(mid)
        seen.add(key)

    state["seen_portfolio_updates"] = sorted(seen)[-500:]
    if sent:
        state["last_portfolio_message_ids"] = sent
    base.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sent

_sent_ids: list[int] = []
_original_send = base.send


def tracked_send(token: str, chat: str, text: str) -> int:
    global _pending_timeline_event
    try:
        mid = _original_send(token, chat, text)
    except Exception:
        _pending_timeline_event = None
        raise
    _sent_ids.append(mid)
    if _pending_timeline_event:
        _successful_timeline_events.append(dict(_pending_timeline_event))
        _pending_timeline_event = None
    return mid


base.send = tracked_send


def main() -> int:
    # 이미 과거에 최종 무효 알림이 끝난 사건은 "최종서면결정 공개"로
    # 다시 중복 송출되지 않도록 동일 단계 키를 기준선에 추가한다.
    try:
        state0 = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        state0 = {}
    seen0 = set(state0.get("seen_events") or [])
    for case in ("PGR2025-00003", "PGR2025-00004", "PGR2025-00006", "PGR2025-00009", "PGR2025-00017"):
        seen0.add(base.digest(f"{case}|final_decision"))
    state0["seen_events"] = sorted(seen0)[-5000:]
    base.STATE.write_text(json.dumps(state0, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rc = base.main()
    portfolio_sent = send_portfolio_updates()
    _sent_ids.extend(mid for mid in portfolio_sent if mid not in _sent_ids)
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    state["legal_v4_initialized"] = True
    state["search_mode"] = "개별 사건번호 + 미국/한국 뉴스 + Bing 웹"
    state["last_sent_message_ids"] = _sent_ids
    state["final_decision_classification_version"] = 2
    state["case_event_timelines"] = _merged_case_timelines(state)
    base.STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = list(state.get("errors_last_run") or [])
    critical_names = ("RecursionError", "NameError", "UnboundLocalError", "TypeError", "SyntaxError", "AttributeError")
    critical = [err for err in errors if any(name in err for name in critical_names)]
    print(json.dumps({
        "halozyme_legal_v4": "ok" if not critical else "failed",
        "sent_message_ids": _sent_ids,
        "portfolio_sent_message_ids": portfolio_sent,
        "errors": errors[-10:],
        "critical_errors": critical,
    }, ensure_ascii=False))
    if critical:
        return 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
