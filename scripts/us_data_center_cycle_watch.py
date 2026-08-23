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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36 "
        "KHS-US-Data-Center-Cycle-Watch/1.0"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def get(url: str, *, timeout: int = 40) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


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

    return {
        "source": "Dodge Construction Network Total Construction Starts",
        "index_url": DODGE_STARTS_INDEX_URL,
        "title": title,
        "url": article_url,
        "published": published,
        "total_starts_saar_usd_bn": total_saar_usd_bn,
        "data_center_mention_count": article_text.lower().count("data center"),
        "data_center_sentences": data_center_sentences,
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


def build_alert(old_state: dict, new_state: dict, changed_sources: list[str], first_run: bool) -> str:
    lines: list[str] = []
    if first_run:
        lines.append("[미국 데이터센터 건설 사이클 감시] 설정 완료")
        lines.append("")
        lines.append("Goldman Sachs 차트의 핵심 원자료인 Census 데이터센터 건설 지출과 Dodge 착공 자료를 매시간 확인합니다.")
        lines.append("변화가 있을 때만 Telegram 알림을 보냅니다.")
    else:
        lines.append("[미국 데이터센터 건설 사이클 감시] 새 변화 감지")

    census = new_state.get("census")
    if census and (first_run or "census" in changed_sources):
        current_bn = census["data_center_saar_musd"] / 1000.0
        previous_bn = census["previous_month_saar_musd"] / 1000.0
        year_ago_bn = census["year_ago_saar_musd"] / 1000.0
        mom = census["reported_mom_pct"]
        yoy = census["reported_yoy_pct"]
        lines.extend(
            [
                "",
                "■ Census 데이터센터 건설 지출",
                f"- 기준월: {census['period']}",
                f"- 계절조정 연율: ${current_bn:,.1f}B",
                f"- 직전월: ${previous_bn:,.1f}B / 전년동월: ${year_ago_bn:,.1f}B",
                f"- 변화: 전월 대비 {mom:+.1f}% / 전년 대비 {yoy:+.1f}%",
                f"- 해석: {signal_label(mom, yoy)}",
                f"- 원문: {census['url']}",
            ]
        )

    dodge = new_state.get("dodge")
    if dodge and (first_run or "dodge" in changed_sources):
        lines.extend(
            [
                "",
                "■ Dodge Construction Starts",
                f"- 최신: {dodge['title']}",
                f"- 발표: {dodge.get('published') or '페이지에서 날짜 직접 추출 실패'}",
                f"- 데이터센터 언급: {dodge.get('data_center_mention_count', 0)}회",
            ]
        )
        if dodge.get("total_starts_saar_usd_bn") is not None:
            lines.append(f"- 전체 착공 계절조정 연율: ${dodge['total_starts_saar_usd_bn']:,.1f}B")
        snippets = dodge.get("data_center_sentences") or []
        for snippet in snippets[:3]:
            lines.append(f"- 데이터센터 핵심: {snippet}")
        if not snippets:
            lines.append("- 데이터센터 핵심: 최신 착공 보도에서 데이터센터 직접 언급이 확인되지 않음 → 선행 파이프라인 둔화 여부 점검 필요")
        lines.append(f"- 원문: {dodge['url']}")

    if not first_run:
        lines.extend(
            [
                "",
                "■ 투자 해석",
                "- 착공이 먼저 약해지면 약 1년 뒤 건설·전력기기·냉각 지출 둔화 신호로 봅니다.",
                "- Census 지출이 계속 증가하면 기존 착공 물량이 실제 매출로 전환되는 구간입니다.",
                "- 두 지표가 동시에 둔화할 때 데이터센터 건설 투자 사이클 피크 위험을 가장 강하게 봅니다.",
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
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    errors: list[str] = []

    try:
        new_state["census"] = parse_census()
    except Exception as exc:
        errors.append(f"Census: {type(exc).__name__}: {exc}")
        if old_state.get("census"):
            new_state["census"] = old_state["census"]

    try:
        new_state["dodge"] = parse_dodge()
    except Exception as exc:
        errors.append(f"Dodge: {type(exc).__name__}: {exc}")
        if old_state.get("dodge"):
            new_state["dodge"] = old_state["dodge"]

    if errors:
        ERROR_PATH.write_text("\n".join(errors) + "\n", encoding="utf-8")

    if "census" not in new_state and "dodge" not in new_state:
        STATUS_PATH.write_text("# 미국 데이터센터 건설 사이클 감시\n\n- 결과: 모든 원천 조회 실패\n", encoding="utf-8")
        return 2

    first_run = not bool(old_state)
    changed_sources: list[str] = []
    if "census" in new_state and census_changed(old_state.get("census"), new_state["census"]):
        changed_sources.append("census")
    if "dodge" in new_state and dodge_changed(old_state.get("dodge"), new_state["dodge"]):
        changed_sources.append("dodge")

    if first_run or changed_sources:
        ALERT_PATH.write_text(
            build_alert(old_state, new_state, changed_sources, first_run),
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
        f"- 변화 감지: {', '.join(changed_sources) if changed_sources else '없음'}",
        f"- Telegram 발송 파일: {'생성' if ALERT_PATH.exists() else '없음'}",
        f"- 조회 오류: {len(errors)}건",
    ]
    if new_state.get("census"):
        c = new_state["census"]
        status_lines.append(
            f"- Census: {c['period']} ${c['data_center_saar_musd']/1000:.1f}B, MoM {c['reported_mom_pct']:+.1f}%, YoY {c['reported_yoy_pct']:+.1f}%"
        )
    if new_state.get("dodge"):
        d = new_state["dodge"]
        status_lines.append(f"- Dodge: {d['title']}")
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    print(STATUS_PATH.read_text(encoding="utf-8"))
    if errors:
        print(ERROR_PATH.read_text(encoding="utf-8"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
