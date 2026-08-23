#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

CENSUS_URL = "https://www.census.gov/construction/c30/pdf/privsa.pdf"
CENSUS_RELEASE_URL = "https://www.census.gov/construction/c30/release.html"
DODGE_STARTS_INDEX_URL = "https://www.construction.com/category/total-construction-starts/"
STATE_PATH = Path("data/us_data_center_cycle_watch_state.json")
OUT_DIR = Path("out")
ALERT_PATH = OUT_DIR / "us_data_center_cycle_alert.txt"
PENDING_STATE_PATH = OUT_DIR / "us_data_center_cycle_state_pending.json"
STATUS_PATH = OUT_DIR / "us_data_center_cycle_status.md"
ERROR_PATH = OUT_DIR / "us_data_center_cycle_errors.log"
FORMAT_VERSION = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36 "
        "KHS-US-Data-Center-Cycle-Watch/1.0"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
FULL_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def get(url: str, *, timeout: int = 40) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


def korean_period(period_key: str | None, fallback: str | None = None) -> str:
    if period_key and re.fullmatch(r"20\d{2}-\d{2}", period_key):
        year, month = period_key.split("-")
        return f"{int(year)}년 {int(month)}월"
    if fallback:
        m = re.fullmatch(r"([A-Za-z]{3})\s+(20\d{2})", fallback.strip())
        if m and m.group(1).title() in MONTHS:
            return f"{int(m.group(2))}년 {MONTHS.index(m.group(1).title()) + 1}월"
    return fallback or "확인 불가"


def korean_date(value: str | None) -> str:
    if not value:
        return "날짜 직접 추출 실패"
    value = clean(value)
    iso = re.match(r"(20\d{2})-(\d{2})-(\d{2})", value)
    if iso:
        return f"{int(iso.group(1))}년 {int(iso.group(2))}월 {int(iso.group(3))}일"
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2}),\s+(20\d{2})",
        value,
        flags=re.I,
    )
    if m:
        return f"{int(m.group(3))}년 {FULL_MONTHS[m.group(1).lower()]}월 {int(m.group(2))}일"
    return value


def usd_bn_ko(value_bn: float | int | None) -> str:
    if value_bn is None:
        return "확인 불가"
    hundred_million_usd = float(value_bn) * 10.0
    if hundred_million_usd >= 10000:
        trillion = int(hundred_million_usd // 10000)
        remainder = round(hundred_million_usd - trillion * 10000)
        return f"{trillion}조{remainder:,.0f}억달러" if remainder else f"{trillion}조달러"
    return f"{hundred_million_usd:,.0f}억달러"


def extract_pct(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text, flags=re.I)
    return float(m.group(1)) if m else None


def parse_census() -> dict:
    response = get(CENSUS_URL)
    pdf_bytes = response.content
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:2])
    normalized = clean(text)

    period_match = re.search(
        r"\b(" + "|".join(MONTHS) + r")\s+(20\d{2})p\b",
        normalized,
        flags=re.I,
    )
    if not period_match:
        raise RuntimeError("Census latest reporting period not found in privsa.pdf")
    month = period_match.group(1).title()
    year = int(period_match.group(2))

    row_match = re.search(
        r"\bData center\s+"
        r"([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+"
        r"(-?[\d.]+)\s+(-?[\d.]+)",
        normalized,
        flags=re.I,
    )
    if not row_match:
        raise RuntimeError("Census Data center row not found in privsa.pdf")

    values = [int(row_match.group(i).replace(",", "")) for i in range(1, 7)]
    current_musd, previous_musd, prior2_musd, prior3_musd, prior4_musd, year_ago_musd = values
    reported_mom = float(row_match.group(7))
    reported_yoy = float(row_match.group(8))
    calc_mom = (current_musd / previous_musd - 1.0) * 100 if previous_musd else None
    calc_yoy = (current_musd / year_ago_musd - 1.0) * 100 if year_ago_musd else None

    release_match = re.search(
        r"Source:\s*U\.S\. Census Bureau,\s*Construction Spending,\s*"
        r"([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
        normalized,
        flags=re.I,
    )

    return {
        "source": "U.S. Census Bureau Construction Spending",
        "url": CENSUS_URL,
        "release_schedule_url": CENSUS_RELEASE_URL,
        "period": f"{month} {year}",
        "period_key": f"{year}-{MONTHS.index(month) + 1:02d}",
        "release_date": release_match.group(1) if release_match else None,
        "data_center_saar_musd": current_musd,
        "previous_month_saar_musd": previous_musd,
        "year_ago_saar_musd": year_ago_musd,
        "reported_mom_pct": reported_mom,
        "reported_yoy_pct": reported_yoy,
        "calculated_mom_pct": round(calc_mom, 3) if calc_mom is not None else None,
        "calculated_yoy_pct": round(calc_yoy, 3) if calc_yoy is not None else None,
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def latest_dodge_starts_link(index_html: str) -> tuple[str, str]:
    soup = BeautifulSoup(index_html, "html.parser")
    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        title = clean(anchor.get_text(" ", strip=True))
        href = urljoin(DODGE_STARTS_INDEX_URL, anchor.get("href", ""))
        if not title.lower().startswith("construction starts"):
            continue
        if href in seen:
            continue
        seen.add(href)
        candidates.append((title, href))
    if not candidates:
        raise RuntimeError("No Dodge Construction Starts article link found")
    return candidates[0]


def parse_dodge() -> dict:
    index_response = get(DODGE_STARTS_INDEX_URL)
    title, article_url = latest_dodge_starts_link(index_response.text)
    article_response = get(article_url)
    soup = BeautifulSoup(article_response.text, "html.parser")
    article_text = clean(soup.get_text(" ", strip=True))

    published = None
    time_tag = soup.find("time")
    if time_tag:
        published = clean(time_tag.get("datetime") or time_tag.get_text(" ", strip=True)) or None
    if not published:
        date_match = re.search(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"\d{1,2},\s+20\d{2}\b",
            article_text,
        )
        if date_match:
            published = date_match.group(0)

    saar_match = re.search(
        r"Total construction starts.{0,180}?seasonally adjusted(?: annual)? rate of\s*\$([0-9.]+)\s*(trillion|billion)",
        article_text,
        flags=re.I,
    )
    total_saar_usd_bn = None
    if saar_match:
        amount = float(saar_match.group(1))
        unit = saar_match.group(2).lower()
        total_saar_usd_bn = round(amount * (1000.0 if unit == "trillion" else 1.0), 3)

    total_change_pct = extract_pct(article_text, r"Total construction starts.{0,100}?([0-9.]+)%\s+in\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)")
    nonresidential_change_pct = extract_pct(article_text, r"Nonresidential building starts.{0,50}?([0-9.]+)%")
    commercial_change_pct = extract_pct(article_text, r"Commercial starts were up\s+([0-9.]+)%")
    office_dc_change_pct = extract_pct(article_text, r"Offices and data centers.{0,80}?\(([+-]?[0-9.]+)%\s*m/m\)")
    utility_change_pct = extract_pct(article_text, r"utilities improved\s+([0-9.]+)%\s*m/m")

    sentence_candidates = re.split(r"(?<=[.!?])\s+", article_text)
    data_center_sentences: list[str] = []
    for sentence in sentence_candidates:
        sentence_clean = clean(sentence)
        if "data center" not in sentence_clean.lower():
            continue
        if len(sentence_clean) < 25:
            continue
        if sentence_clean not in data_center_sentences:
            data_center_sentences.append(sentence_clean[:650])
        if len(data_center_sentences) >= 6:
            break

    project_matches = re.findall(
        r"\$([0-9.]+)\s+billion\s+(.{5,180}?(?:Data Center|data center).{0,100}?)(?=,\s+the\s+\$|\.\s|$)",
        article_text,
        flags=re.I,
    )
    data_center_projects = []
    for amount, description in project_matches[:5]:
        description = clean(description)
        description = re.sub(r"\s+in\s+[A-Z][A-Za-z .'-]+,\s*[A-Z][A-Za-z .'-]+$", "", description)
        data_center_projects.append({"amount_usd_bn": float(amount), "name": description})

    return {
        "source": "Dodge Construction Network Total Construction Starts",
        "index_url": DODGE_STARTS_INDEX_URL,
        "title": title,
        "url": article_url,
        "published": published,
        "total_starts_saar_usd_bn": total_saar_usd_bn,
        "total_change_pct": total_change_pct,
        "nonresidential_change_pct": nonresidential_change_pct,
        "commercial_change_pct": commercial_change_pct,
        "office_dc_change_pct": office_dc_change_pct,
        "utility_change_pct": utility_change_pct,
        "data_center_mention_count": article_text.lower().count("data center"),
        "data_center_sentences": data_center_sentences,
        "data_center_projects": data_center_projects,
        "article_sha256": hashlib.sha256(article_response.content).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def census_changed(old: dict | None, new: dict) -> bool:
    if not old:
        return True
    keys = [
        "period_key",
        "data_center_saar_musd",
        "previous_month_saar_musd",
        "year_ago_saar_musd",
        "reported_mom_pct",
        "reported_yoy_pct",
    ]
    return any(old.get(key) != new.get(key) for key in keys)


def dodge_changed(old: dict | None, new: dict) -> bool:
    if not old:
        return True
    return old.get("url") != new.get("url") or old.get("title") != new.get("title")


def signal_label(mom: float, yoy: float) -> str:
    if mom >= 2 and yoy > 0:
        return "지출 재가속"
    if mom > 0 and yoy > 0:
        return "지출 증가 지속"
    if mom < 0 and yoy > 0:
        return "월간 둔화·연간 증가"
    if yoy <= 0:
        return "연간 증가세 훼손"
    return "혼조"


def dodge_korean_lines(dodge: dict) -> list[str]:
    lines = [
        "■ Dodge Construction Network 데이터센터 착공",
        f"- 발표일: {korean_date(dodge.get('published'))}",
        f"- 데이터센터 언급: {dodge.get('data_center_mention_count', 0)}회",
    ]
    if dodge.get("total_starts_saar_usd_bn") is not None:
        lines.append(f"- 미국 전체 건설 착공 계절조정 연율: {usd_bn_ko(dodge['total_starts_saar_usd_bn'])}")
    if dodge.get("total_change_pct") is not None:
        lines.append(f"- 미국 전체 건설 착공: 전월 대비 {dodge['total_change_pct']:+.1f}%")
    if dodge.get("nonresidential_change_pct") is not None:
        lines.append(f"- 비주거용 건축 착공: 전월 대비 {dodge['nonresidential_change_pct']:+.1f}%")
    if dodge.get("commercial_change_pct") is not None:
        lines.append(f"- 상업용 건축 착공: 전월 대비 {dodge['commercial_change_pct']:+.1f}%")
    if dodge.get("office_dc_change_pct") is not None:
        lines.append(f"- 오피스·데이터센터 착공: 전월 대비 {dodge['office_dc_change_pct']:+.1f}% → 두 배 이상 증가")
    if dodge.get("utility_change_pct") is not None:
        lines.append(f"- 전력·공공설비 착공: 전월 대비 {dodge['utility_change_pct']:+.1f}%")

    projects = dodge.get("data_center_projects") or []
    if projects:
        lines.append("- 주요 데이터센터 착공 프로젝트:")
        for project in projects[:3]:
            name = project.get("name") or "프로젝트명 확인 불가"
            amount = usd_bn_ko(project.get("amount_usd_bn"))
            lines.append(f"  · {name}: {amount}")
    else:
        lines.append("- 주요 데이터센터 착공 프로젝트: 자동 구조화된 신규 프로젝트가 없거나 추출되지 않음")

    lines.append("- 해석: 데이터센터 착공이 급증하면 약 1년 뒤 건설·전력기기·냉각 지출로 이어질 가능성이 커집니다.")
    lines.append(f"- 원문: {dodge['url']}")
    return lines


def build_alert(old_state: dict, new_state: dict, changed_sources: list[str], first_run: bool, format_changed: bool) -> str:
    lines: list[str] = []
    if first_run:
        lines.append("[미국 데이터센터 건설 사이클 감시] 설정 완료")
    elif format_changed and not changed_sources:
        lines.append("[미국 데이터센터 건설 사이클 감시] 한국어 알림 형식 적용 완료")
    else:
        lines.append("[미국 데이터센터 건설 사이클 감시] 새 변화 감지")

    lines.extend(
        [
            "",
            "골드만삭스 차트의 핵심 원자료인 미국 인구조사국 데이터센터 건설 지출과 Dodge Construction Network 착공 자료를 매시간 확인합니다.",
            "변화가 있을 때만 텔레그램 알림을 보냅니다.",
            "영문 원문은 내부에서 숫자와 사실관계 확인에만 사용하고, 알림 본문은 한국어로 전달합니다.",
        ]
    )

    census = new_state.get("census")
    if census and (first_run or format_changed or "census" in changed_sources):
        current_bn = census["data_center_saar_musd"] / 1000.0
        previous_bn = census["previous_month_saar_musd"] / 1000.0
        year_ago_bn = census["year_ago_saar_musd"] / 1000.0
        mom = census["reported_mom_pct"]
        yoy = census["reported_yoy_pct"]
        lines.extend(
            [
                "",
                "■ 미국 인구조사국 데이터센터 건설 지출",
                f"- 기준월: {korean_period(census.get('period_key'), census.get('period'))}",
                f"- 계절조정 연율: {usd_bn_ko(current_bn)}",
                f"- 직전월: {usd_bn_ko(previous_bn)} / 전년동월: {usd_bn_ko(year_ago_bn)}",
                f"- 변화: 전월 대비 {mom:+.1f}% / 전년 대비 {yoy:+.1f}%",
                f"- 해석: {signal_label(mom, yoy)}",
                f"- 원문: {census['url']}",
            ]
        )

    dodge = new_state.get("dodge")
    if dodge and (first_run or format_changed or "dodge" in changed_sources):
        lines.append("")
        lines.extend(dodge_korean_lines(dodge))

    if not first_run:
        lines.extend(
            [
                "",
                "■ 투자 해석",
                "- 착공이 먼저 약해지면 약 1년 뒤 건설·전력기기·냉각 지출 둔화 신호로 봅니다.",
                "- 미국 인구조사국 지출이 계속 증가하면 기존 착공 물량이 실제 공사·설비 매출로 전환되는 구간입니다.",
                "- 두 지표가 동시에 둔화할 때 데이터센터 건설 투자 사이클 정점 위험을 가장 강하게 봅니다.",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)
    ERROR_PATH.unlink(missing_ok=True)

    old_state = load_state()
    new_state = {
        "watch": "US data center construction starts vs spending",
        "format_version": FORMAT_VERSION,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    errors: list[str] = []

    try:
        new_state["census"] = parse_census()
    except Exception as exc:
        errors.append(f"미국 인구조사국: {type(exc).__name__}: {exc}")
        if old_state.get("census"):
            new_state["census"] = old_state["census"]

    try:
        new_state["dodge"] = parse_dodge()
    except Exception as exc:
        errors.append(f"Dodge Construction Network: {type(exc).__name__}: {exc}")
        if old_state.get("dodge"):
            new_state["dodge"] = old_state["dodge"]

    if errors:
        ERROR_PATH.write_text("\n".join(errors) + "\n", encoding="utf-8")

    if "census" not in new_state and "dodge" not in new_state:
        STATUS_PATH.write_text("# 미국 데이터센터 건설 사이클 감시\n\n- 결과: 모든 원천 조회 실패\n", encoding="utf-8")
        return 2

    first_run = not bool(old_state)
    format_changed = old_state.get("format_version") != FORMAT_VERSION
    changed_sources: list[str] = []
    if "census" in new_state and census_changed(old_state.get("census"), new_state["census"]):
        changed_sources.append("미국 인구조사국")
    if "dodge" in new_state and dodge_changed(old_state.get("dodge"), new_state["dodge"]):
        changed_sources.append("Dodge Construction Network")

    source_keys = []
    if "미국 인구조사국" in changed_sources:
        source_keys.append("census")
    if "Dodge Construction Network" in changed_sources:
        source_keys.append("dodge")

    if first_run or format_changed or source_keys:
        ALERT_PATH.write_text(
            build_alert(old_state, new_state, source_keys, first_run, format_changed),
            encoding="utf-8",
        )

    PENDING_STATE_PATH.write_text(
        json.dumps(new_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    status_lines = [
        "# 미국 데이터센터 건설 사이클 감시",
        "",
        f"- 최초 실행: {'예' if first_run else '아니오'}",
        f"- 한국어 알림 형식 갱신: {'예' if format_changed else '아니오'}",
        f"- 변화 감지: {', '.join(changed_sources) if changed_sources else '없음'}",
        f"- 텔레그램 발송 파일: {'생성' if ALERT_PATH.exists() else '없음'}",
        f"- 조회 오류: {len(errors)}건",
    ]
    if new_state.get("census"):
        c = new_state["census"]
        status_lines.append(
            f"- 미국 인구조사국: {korean_period(c.get('period_key'), c.get('period'))}, {usd_bn_ko(c['data_center_saar_musd']/1000)}, 전월 대비 {c['reported_mom_pct']:+.1f}%, 전년 대비 {c['reported_yoy_pct']:+.1f}%"
        )
    if new_state.get("dodge"):
        d = new_state["dodge"]
        status_lines.append(f"- Dodge Construction Network: 발표일 {korean_date(d.get('published'))}")
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    print(STATUS_PATH.read_text(encoding="utf-8"))
    if errors:
        print(ERROR_PATH.read_text(encoding="utf-8"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
