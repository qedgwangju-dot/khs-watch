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
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

CENSUS_URL = "https://www.census.gov/construction/c30/pdf/privsa.pdf"
CENSUS_RELEASE_URL = "https://www.census.gov/construction/c30/release.html"
DODGE_INDEX_URL = "https://www.construction.com/category/total-construction-starts/"
DODGE_NEWS_URL = "https://www.construction.com/construction-news/"
DODGE_HOME_URL = "https://www.construction.com/"
YAHOO_FX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?interval=5m&range=1d"
FRED_FX_URL = "https://api.frankfurter.dev/v2/rate/USD/KRW?providers=FRED"
STATE_PATH = Path("data/us_data_center_cycle_watch_state.json")
OUT_DIR = Path("out")
ALERT_PATH = OUT_DIR / "us_data_center_cycle_alert.txt"
PENDING_PATH = OUT_DIR / "us_data_center_cycle_state_pending.json"
STATUS_PATH = OUT_DIR / "us_data_center_cycle_status.md"
ERROR_PATH = OUT_DIR / "us_data_center_cycle_errors.log"
FORMAT_VERSION = 5
KST = ZoneInfo("Asia/Seoul")

HEADERS = {
    "User-Agent": "Mozilla/5.0 KHS-US-Data-Center-Cycle-Watch/1.3",
    "Accept-Language": "en-US,en;q=0.9",
}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
FULL_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def get(url: str, timeout: int = 40) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def usd_bn_ko(value_bn: float | int | None) -> str:
    if value_bn is None:
        return "확인 불가"
    eok = float(value_bn) * 10.0
    if eok >= 10000:
        jo = int(eok // 10000)
        rem = eok - jo * 10000
        if abs(rem - round(rem)) < 0.05:
            rem_text = f"{round(rem):,.0f}"
        else:
            rem_text = f"{rem:,.1f}"
        return f"{jo:,}조{rem_text}억달러" if rem else f"{jo:,}조달러"
    if abs(eok - round(eok)) < 0.05:
        return f"{round(eok):,.0f}억달러"
    return f"{eok:,.1f}억달러"


def krw_ko_from_usd_bn(value_bn: float | int | None, usdkrw: float | None) -> str:
    if value_bn is None or usdkrw is None:
        return "원화 환산 불가"
    won = float(value_bn) * 1_000_000_000 * float(usdkrw)
    eok = int(round(won / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    return f"약 {eok:,}억원"


def money_pair(value_bn: float | int | None, fx: dict | None) -> str:
    return f"{usd_bn_ko(value_bn)} ({krw_ko_from_usd_bn(value_bn, (fx or {}).get('usdkrw'))})"


def period_ko(period_key: str | None, fallback: str | None = None) -> str:
    if period_key and re.fullmatch(r"20\d{2}-\d{2}", period_key):
        year, month = period_key.split("-")
        return f"{int(year)}년 {int(month)}월"
    if fallback:
        m = re.fullmatch(r"([A-Za-z]{3})\s+(20\d{2})", fallback.strip())
        if m and m.group(1).title() in MONTHS:
            return f"{int(m.group(2))}년 {MONTHS.index(m.group(1).title()) + 1}월"
    return "확인 불가"


def date_ko(value: str | None) -> str:
    if not value:
        return "공식 게시일 직접 추출 실패"
    value = clean(value)
    iso = re.match(r"(20\d{2})-(\d{2})-(\d{2})", value)
    if iso:
        return f"{int(iso.group(1))}년 {int(iso.group(2))}월 {int(iso.group(3))}일"
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2}),\s+(20\d{2})", value, flags=re.I,
    )
    if m:
        return f"{int(m.group(3))}년 {FULL_MONTHS[m.group(1).lower()]}월 {int(m.group(2))}일"
    return "공식 게시일 직접 추출 실패"


def pct(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text, flags=re.I)
    return float(m.group(1)) if m else None


def fetch_fx():
    from fx_api import daily_krw
    q = daily_krw()
    return {"usdkrw": q.rate, "basis_kst": q.basis, "source": q.source, "source_type": "일일 기준환율"}


def parse_census() -> dict:
    r = get(CENSUS_URL)
    pdf = r.content
    reader = PdfReader(BytesIO(pdf))
    text = clean("\n".join((p.extract_text() or "") for p in reader.pages[:2]))
    pm = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(20\d{2})p\b", text, flags=re.I)
    if not pm:
        raise RuntimeError("최신 기준월을 찾지 못함")
    month = pm.group(1).title(); year = int(pm.group(2))
    rm = re.search(
        r"\bData center\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+(-?[\d.]+)\s+(-?[\d.]+)",
        text, flags=re.I,
    )
    if not rm:
        raise RuntimeError("데이터센터 행을 찾지 못함")
    vals = [int(rm.group(i).replace(",", "")) for i in range(1, 7)]
    current, previous, _p2, _p3, _p4, year_ago = vals
    mom = float(rm.group(7)); yoy = float(rm.group(8))
    release = re.search(r"Source:\s*U\.S\. Census Bureau,\s*Construction Spending,\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2})", text, flags=re.I)
    return {
        "source": "U.S. Census Bureau Construction Spending",
        "url": CENSUS_URL,
        "release_schedule_url": CENSUS_RELEASE_URL,
        "period": f"{month} {year}",
        "period_key": f"{year}-{MONTHS.index(month)+1:02d}",
        "release_date": release.group(1) if release else None,
        "data_center_saar_musd": current,
        "previous_month_saar_musd": previous,
        "year_ago_saar_musd": year_ago,
        "reported_mom_pct": mom,
        "reported_yoy_pct": yoy,
        "calculated_mom_pct": round((current / previous - 1) * 100, 3) if previous else None,
        "calculated_yoy_pct": round((current / year_ago - 1) * 100, 3) if year_ago else None,
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def latest_dodge_link_from_html(html: str, base_url: str) -> tuple[str, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        title = clean(a.get_text(" ", strip=True))
        href = urljoin(base_url, a.get("href", ""))
        low_href = href.lower()
        if href in seen:
            continue
        seen.add(href)
        if title.lower().startswith("construction starts") and "category/" not in low_href:
            return title, href
        if "construction-starts-" in low_href and "category/" not in low_href:
            slug = low_href.rstrip("/").split("/")[-1]
            fallback_title = " ".join(w.capitalize() for w in slug.replace("-", " ").split())
            return title or fallback_title, href

    raw_match = re.search(r"/(?:company-news/)?construction-starts-[a-z0-9-]+/?", html, flags=re.I)
    if raw_match:
        href = urljoin(base_url, raw_match.group(0))
        slug = href.rstrip("/").split("/")[-1]
        return " ".join(w.capitalize() for w in slug.replace("-", " ").split()), href
    return None


def discover_dodge_article() -> tuple[str, str]:
    errors: list[str] = []
    for page_url in (DODGE_INDEX_URL, DODGE_NEWS_URL, DODGE_HOME_URL):
        try:
            found = latest_dodge_link_from_html(get(page_url).text, page_url)
            if found:
                return found
        except Exception as exc:
            errors.append(f"{page_url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("최신 착공 기사를 찾지 못함" + (" | " + " | ".join(errors) if errors else ""))


def extract_published(soup: BeautifulSoup) -> str | None:
    for attrs in (
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"name": "date"},
        {"itemprop": "datePublished"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return clean(tag.get("content"))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("datePublished"):
                return clean(str(item["datePublished"]))
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                for node in item["@graph"]:
                    if isinstance(node, dict) and node.get("datePublished"):
                        return clean(str(node["datePublished"]))

    time_tag = soup.find("time")
    if time_tag:
        value = clean(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))
        if value:
            return value
    return None


def clean_project_name(description: str, kind: str) -> str:
    name = clean(description)
    name = re.sub(r"\s+in\s+[A-Z][A-Za-z .'-]+,\s*[A-Z][A-Za-z .'-]+$", "", name)
    if kind == "데이터센터":
        name = re.sub(r"^data center portion of the\s+", "", name, flags=re.I)
        return f"{name} 데이터센터 부문"
    if kind == "마이크로그리드":
        name = re.sub(r"^microgrid portion of the\s+", "", name, flags=re.I)
        return f"{name} 마이크로그리드 부문"
    return name


def extract_project_segments(sentence: str) -> list[tuple[float, str]]:
    matches = list(re.finditer(r"\$([0-9.]+)\s+billion\s+", sentence, flags=re.I))
    out: list[tuple[float, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sentence)
        desc = sentence[match.end():end]
        desc = re.sub(r",?\s*(?:and\s+)?the\s*$", "", desc, flags=re.I)
        desc = clean(desc.strip(" ,.;"))
        if desc:
            out.append((float(match.group(1)), desc))
    return out


def parse_dodge() -> dict:
    title, url = discover_dodge_article()
    article = get(url)
    soup = BeautifulSoup(article.text, "html.parser")
    text = clean(soup.get_text(" ", strip=True))
    published = extract_published(soup)

    sm = re.search(
        r"Total construction starts.{0,180}?seasonally adjusted(?: annual)? rate of\s*\$([0-9.]+)\s*(trillion|billion)",
        text, flags=re.I,
    )
    total_saar = float(sm.group(1)) * (1000.0 if sm.group(2).lower() == "trillion" else 1.0) if sm else None

    projects: list[dict] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = clean(sentence); low = s.lower()
        if "largest nonresidential building projects" in low:
            for amount, desc in extract_project_segments(s):
                if "data center" in desc.lower():
                    projects.append({"amount_usd_bn": amount, "label_ko": clean_project_name(desc, "데이터센터")})
        if "largest nonbuilding projects" in low:
            for amount, desc in extract_project_segments(s):
                if "microgrid" in desc.lower() and "data center" in desc.lower():
                    projects.append({"amount_usd_bn": amount, "label_ko": clean_project_name(desc, "마이크로그리드")})

    return {
        "source": "Dodge Construction Network Total Construction Starts",
        "index_url": DODGE_INDEX_URL,
        "title": title,
        "url": url,
        "published": published,
        "total_starts_saar_usd_bn": round(total_saar, 3) if total_saar is not None else None,
        "total_change_pct": pct(text, r"Total construction starts.{0,100}?([0-9.]+)%\s+in\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)"),
        "nonresidential_change_pct": pct(text, r"Nonresidential building starts.{0,50}?([0-9.]+)%"),
        "commercial_change_pct": pct(text, r"Commercial starts were up\s+([0-9.]+)%"),
        "office_dc_change_pct": pct(text, r"Offices and data centers.{0,80}?\(([+-]?[0-9.]+)%\s*m/m\)"),
        "utility_change_pct": pct(text, r"utilities improved\s+([0-9.]+)%\s*m/m"),
        "data_center_mention_count": text.lower().count("data center"),
        "data_center_projects": projects[:5],
        "article_sha256": hashlib.sha256(article.content).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    except Exception:
        return {}


def census_changed(old: dict | None, new: dict) -> bool:
    if not old:
        return True
    keys = ["period_key", "data_center_saar_musd", "previous_month_saar_musd", "year_ago_saar_musd", "reported_mom_pct", "reported_yoy_pct"]
    return any(old.get(k) != new.get(k) for k in keys)


def dodge_changed(old: dict | None, new: dict) -> bool:
    if not old:
        return True
    keys = ["url", "title", "published", "total_starts_saar_usd_bn", "total_change_pct", "office_dc_change_pct", "utility_change_pct", "data_center_projects"]
    return any(old.get(k) != new.get(k) for k in keys)


def signal(mom: float, yoy: float) -> str:
    if mom >= 2 and yoy > 0:
        return "지출 재가속"
    if mom > 0 and yoy > 0:
        return "지출 증가 지속"
    if mom < 0 and yoy > 0:
        return "월간 둔화·연간 증가"
    if yoy <= 0:
        return "연간 증가세 훼손"
    return "혼조"


def fx_lines(fx: dict | None) -> list[str]:
    if not fx or fx.get("usdkrw") is None:
        return ["■ 원화 환산 기준", "- USD/KRW 조회 실패로 이번 알림은 달러 원값만 표시합니다."]
    rate = float(fx["usdkrw"])
    return [
        "■ 원화 환산 기준",
        f"- 적용 환율: 1달러 = {rate:,.2f}원",
        f"- 기준시각: {fx.get('basis_kst', '확인 불가')}",
        f"- 출처: {fx.get('source', '확인 불가')} · {fx.get('source_type', '')}",
        f"- 환산식: 달러 금액 × {rate:,.2f}원/달러",
        "- 원화 금액은 알림 시점 환율을 적용한 참고 환산값입니다.",
    ]


def dodge_lines(d: dict, fx: dict | None) -> list[str]:
    lines = [
        "■ Dodge Construction Network 데이터센터 착공",
        f"- 공식 게시일: {date_ko(d.get('published'))}",
        f"- 데이터센터 관련 언급: {d.get('data_center_mention_count', 0)}회",
    ]
    if d.get("total_starts_saar_usd_bn") is not None:
        lines.append(f"- 미국 전체 건설 착공 계절조정 연율: {money_pair(d['total_starts_saar_usd_bn'], fx)}")
    if d.get("total_change_pct") is not None:
        lines.append(f"- 미국 전체 건설 착공: 전월 대비 {d['total_change_pct']:+.1f}%")
    if d.get("nonresidential_change_pct") is not None:
        lines.append(f"- 비주거용 건축 착공: 전월 대비 {d['nonresidential_change_pct']:+.1f}%")
    if d.get("commercial_change_pct") is not None:
        lines.append(f"- 상업용 건축 착공: 전월 대비 {d['commercial_change_pct']:+.1f}%")
    if d.get("office_dc_change_pct") is not None:
        suffix = " → 두 배 이상 증가" if d["office_dc_change_pct"] >= 100 else ""
        lines.append(f"- 오피스·데이터센터 착공: 전월 대비 {d['office_dc_change_pct']:+.1f}%{suffix}")
    if d.get("utility_change_pct") is not None:
        lines.append(f"- 전력·공공설비 착공: 전월 대비 {d['utility_change_pct']:+.1f}%")

    projects = d.get("data_center_projects") or []
    if projects:
        lines.append("- 데이터센터·직접 전력 프로젝트:")
        for p in projects[:4]:
            lines.append(f"  · {p['label_ko']}: {money_pair(p['amount_usd_bn'], fx)}")
    else:
        lines.append("- 데이터센터·직접 전력 프로젝트: 신규 구조화 항목 없음")

    lines += [
        "- 해석: 데이터센터 착공은 건설 지출보다 약 1년 선행하는 지표로 봅니다. 착공 급증이 유지되면 이후 건설·전력기기·냉각 지출로 이어질 가능성이 커집니다.",
        f"- 원문: {d['url']}",
    ]
    return lines


def build_alert(state: dict, changed: list[str], first: bool, format_changed: bool) -> str:
    if first:
        header = "[미국 데이터센터 건설 사이클 감시] 설정 완료"
    elif format_changed and not changed:
        header = "[미국 데이터센터 건설 사이클 감시] 원화 환산·가독성 형식 적용 완료"
    else:
        header = "[미국 데이터센터 건설 사이클 감시] 새 변화 감지"

    fx = state.get("fx")
    lines = [
        header,
        "━━━━━━━━━━━━━━━━",
        "골드만삭스 차트의 핵심 원자료인 미국 인구조사국 데이터센터 건설 지출과 Dodge Construction Network 착공 자료를 매시간 확인합니다.",
        "변화가 있을 때만 텔레그램 알림을 보내며, 모든 달러 금액에는 알림 시점 USD/KRW 환율을 적용한 원화 환산값을 함께 표시합니다.",
    ]
    c = state.get("census"); d = state.get("dodge")
    show_census = bool(c and (first or format_changed or "census" in changed))
    show_dodge = bool(d and (first or format_changed or "dodge" in changed))

    if show_census:
        current = c["data_center_saar_musd"] / 1000
        previous = c["previous_month_saar_musd"] / 1000
        year_ago = c["year_ago_saar_musd"] / 1000
        mom, yoy = c["reported_mom_pct"], c["reported_yoy_pct"]
        lines += [
            "",
            "▶ 한눈에 보기",
            f"- 데이터센터 건설 지출: {money_pair(current, fx)}",
            f"- 변화율: 전월 대비 {mom:+.1f}% · 전년 대비 {yoy:+.1f}%",
            f"- 판정: {signal(mom, yoy)}",
            "",
            "■ 미국 인구조사국 데이터센터 건설 지출",
            f"- 기준월: {period_ko(c.get('period_key'), c.get('period'))}",
            f"- 계절조정 연율: {money_pair(current, fx)}",
            f"- 직전월: {money_pair(previous, fx)}",
            f"- 전년동월: {money_pair(year_ago, fx)}",
            f"- 전월 대비: {mom:+.1f}%",
            f"- 전년 대비: {yoy:+.1f}%",
            f"- 해석: {signal(mom, yoy)}",
            f"- 원문: {c['url']}",
        ]

    if show_dodge:
        lines += ["", "━━━━━━━━━━━━━━━━"]
        lines += dodge_lines(d, fx)

    if show_census or show_dodge:
        lines += ["", "━━━━━━━━━━━━━━━━"]
        lines += fx_lines(fx)

    if not first:
        lines += [
            "",
            "━━━━━━━━━━━━━━━━",
            "■ 투자 해석",
            "- 착공이 먼저 약해지면 약 1년 뒤 건설·전력기기·냉각 지출 둔화 신호로 봅니다.",
            "- 미국 인구조사국 지출이 계속 증가하면 기존 착공 물량이 실제 공사·설비 매출로 전환되는 구간입니다.",
            "- 착공과 실제 지출이 동시에 둔화하면 데이터센터 건설 투자 사이클 정점 위험이 가장 강해졌다고 판단합니다.",
            "- 전력망 접속·변전소·송전선·냉각·전원 인가 지연은 착공이 실제 매출로 이어지는 속도를 늦출 수 있는 핵심 병목입니다.",
        ]
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)
    ERROR_PATH.unlink(missing_ok=True)
    old = load_state()
    state = {
        "watch": "US data center construction starts vs spending",
        "format_version": FORMAT_VERSION,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    errors: list[str] = []

    try:
        state["fx"] = fetch_fx()
    except Exception as exc:
        errors.append(f"USD/KRW 조회 실패: {type(exc).__name__}: {exc}")
        if old.get("fx"):
            state["fx"] = old["fx"]

    try:
        state["census"] = parse_census()
    except Exception as exc:
        errors.append(f"미국 인구조사국 조회 실패: {type(exc).__name__}: {exc}")
        if old.get("census"):
            state["census"] = old["census"]

    try:
        state["dodge"] = parse_dodge()
    except Exception as exc:
        errors.append(f"Dodge Construction Network 조회 실패: {type(exc).__name__}: {exc}")
        if old.get("dodge"):
            state["dodge"] = old["dodge"]

    if errors:
        ERROR_PATH.write_text("\n".join(errors) + "\n", encoding="utf-8")
    if "census" not in state and "dodge" not in state:
        STATUS_PATH.write_text("# 미국 데이터센터 건설 사이클 감시\n\n- 결과: 모든 원천 조회 실패\n", encoding="utf-8")
        return 2

    first = not bool(old)
    format_changed = old.get("format_version") != FORMAT_VERSION
    changed: list[str] = []
    if state.get("census") and census_changed(old.get("census"), state["census"]):
        changed.append("census")
    if state.get("dodge") and dodge_changed(old.get("dodge"), state["dodge"]):
        changed.append("dodge")

    if first or format_changed or changed:
        ALERT_PATH.write_text(build_alert(state, changed, first, format_changed), encoding="utf-8")
    PENDING_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    status = [
        "# 미국 데이터센터 건설 사이클 감시", "",
        f"- 최초 실행: {'예' if first else '아니오'}",
        f"- 원화 환산·가독성 형식 갱신: {'예' if format_changed else '아니오'}",
        f"- 변화 감지: {', '.join(changed) if changed else '없음'}",
        f"- 텔레그램 발송 파일: {'생성' if ALERT_PATH.exists() else '없음'}",
        f"- 조회 오류: {len(errors)}건",
    ]
    if state.get("fx"):
        status.append(f"- USD/KRW: {state['fx'].get('usdkrw')}원 · {state['fx'].get('basis_kst')} · {state['fx'].get('source')}")
    if state.get("census"):
        c = state["census"]
        status.append(
            f"- 미국 인구조사국: {period_ko(c.get('period_key'), c.get('period'))}, "
            f"{money_pair(c['data_center_saar_musd']/1000, state.get('fx'))}, "
            f"전월 대비 {c['reported_mom_pct']:+.1f}%, 전년 대비 {c['reported_yoy_pct']:+.1f}%"
        )
    if state.get("dodge"):
        status.append(f"- Dodge Construction Network: 공식 게시일 {date_ko(state['dodge'].get('published'))}")
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")

    print(STATUS_PATH.read_text(encoding="utf-8"))
    if errors:
        print(ERROR_PATH.read_text(encoding="utf-8"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
