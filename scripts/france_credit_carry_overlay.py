#!/usr/bin/env python3
"""France sovereign-rating milestone overlay for the existing European yield watcher.

Runs AFTER europe_sovereign_yield_watch.py and BEFORE the same Telegram delivery.
AFT official rating table is mandatory; press speculation cannot become a rating event.
The shared Europe pending state is finalized only on safe no-alert or Telegram ACK.
No separate bot, schedule, or state writer is created.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from scripts import europe_sovereign_yield_watch as base
from scripts.khs_source_fetch import fetch_text
from scripts.france_ministry_moodys_fallback import discover_ministry_notice

KST = ZoneInfo("Asia/Seoul")
PARIS = ZoneInfo("Europe/Paris")
AFT_EN = "https://www.aft.gouv.fr/en/frances-credit-ratings"
AFT_FR = "https://www.aft.gouv.fr/fr/calendrier-notations-france"
AFT_TEXT_RECOVERY = "https://r.jina.ai/https://www.aft.gouv.fr/en/frances-credit-ratings"
ORIGINAL_STORY = "https://www.briefs.co/news/hedge-funds-scramble-as-french-bond-rout-blows-out-spreads/"
REVIEW_DATE = dt.date(2026, 10, 23)
SP_REVIEW_DATE = dt.date(2026, 11, 27)
# AFT official-site indexed table was cross-checked with Reuters on 2026-10-14.
# This is NOT an AFT live-page fetch. Historical baseline is ONLY for reminders; do
# not treat it as a live agency rating or a rating decision.
VERIFIED_AFT_SNAPSHOT = {
    "agency": "Moody's", "rating": "Aa3", "outlook": "Negative",
    "decision_date": "2026-04-10", "next_review": "2026-10-23",
    "url": AFT_EN, "source_kind": "historical_official_snapshot",
    "verified_on": "2026-10-14",
}
MILESTONES = {7: "일주일 전", 3: "3일 전", 1: "하루 전", 0: "당일"}
# Historical AFT index snapshot, independently verified 2026-10-22.
# Reminder only: must not be mistaken for a live S&P rating action.
VERIFIED_SP_SNAPSHOT = {
    "agency": "S&P Global Ratings", "rating": "A+", "outlook": "Stable",
    "decision_date": "2026-05-29", "next_review": "2026-11-27",
    "url": AFT_EN, "source_kind": "historical_official_snapshot",
    "verified_on": "2026-10-22",
}
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS = ROOT / "out" / "france_credit_overlay_status.md"


class RatingTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag.lower() in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join(" ".join(self._cell).split()))
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12, "janvier": 1, "fevrier": 2,
    "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}


def parse_date(cell: str) -> str | None:
    txt = " ".join(cell.strip().split()).lower()
    m = re.search(r"(\d{1,2})\s+([a-zàâéêîôûù]+)\s+(20\d{2})", txt, re.I)
    if m:
        month = _MONTHS.get(m.group(2).lower())
        if month:
            try:
                return dt.date(int(m.group(3)), month, int(m.group(1))).isoformat()
            except ValueError:
                pass
    m = re.search(r"([a-zàâéêîôûù]+)\s+(\d{1,2}),?\s+(20\d{2})", txt, re.I)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        if month:
            try:
                return dt.date(int(m.group(3)), month, int(m.group(2))).isoformat()
            except ValueError:
                pass
    return None


def parse_moodys(html_text: str) -> dict:
    table = RatingTable()
    table.feed(html_text)
    rows = [cells for cells in table.rows if cells and "moody" in cells[0].casefold()]
    if len(rows) != 1:
        raise ValueError("Official AFT Moody's rating row missing or ambiguous")
    cells = rows[0]
    if len(cells) < 5:
        raise ValueError("Official rating row missing columns")
    # Agency | rating | outlook | last action | next review
    agency, grade, outlook = cells[:3]
    grade = grade.strip().replace(" ", "")
    if not re.fullmatch(r"(?:Aaa|Aa[1-3]|A[1-3]|Baa[1-3]|Ba[1-3]|B[1-3]|Caa[1-3]|Ca|C)", grade, re.I):
        raise ValueError("Unrecognized Moody's rating; refusing to generate alert")
    if len(outlook) > 60 or not outlook:
        raise ValueError("Unrecognized Moody's outlook")
    last = parse_date(cells[3])
    next_date = parse_date(cells[4])
    if last is None:
        raise ValueError("AFT latest Moody's decision date missing")
    return {"agency": "Moody's", "rating": grade, "outlook": outlook,
            "decision_date": last, "next_review": next_date}


def parse_aft_text_recovery(text: str) -> dict:
    """Read a text-only rendition of AFT, never a generic third-party headline.

    The text must explicitly attribute the URL Source to the exact AFT page.
    This recovery route is used only for scheduled reminders, NOT new rating
    changes unless the official live table has been directly verified.
    """
    if not re.search(r"URL Source:\s*https://www\.aft\.gouv\.fr/en/frances-credit-ratings",
                     text, re.I):
        raise ValueError("AFT text recovery does not identify the original government URL")
    line = next((line for line in text.splitlines()
                 if re.search(r"^\s*\|?\s*Moody'?s\b", line, re.I)), None)
    if line is None:
        raise ValueError("AFT Moody's row absent from recovered text")
    if "|" in line:
        cells = [x.strip() for x in line.split("|") if x.strip()]
    else:
        cells = [x.strip() for x in re.split(r"\s{2,}", line.strip()) if x.strip()]
    if len(cells) < 5 or not re.fullmatch(r"Aa[1-3]|A[1-3]|Baa[1-3]|Aaa", cells[1]):
        raise ValueError("Text recovery rating row does not match expected structure")
    last, upcoming = parse_date(cells[3]), parse_date(cells[4])
    if last is None:
        raise ValueError("Text recovery last-rating date missing")
    return {
        "agency": "Moody's",
        "rating": cells[1],
        "outlook": cells[2],
        "decision_date": last,
        "next_review": upcoming,
        "source_kind": "secondary_text_recovery",
    }


def fetch_rating(*, fetch=None) -> tuple[dict | None, list[str]]:
    if fetch is None:
        def fetch(url: str) -> str:
            body, error = fetch_text(
                url,
                "Mozilla/5.0 (khs-france-credit-monitor/1.0)",
                timeout=13,
                attempts=1,
                accept="text/html",
            )
            if error is not None or not body:
                raise RuntimeError(error or "official rating page was empty")
            return body
    errors = []
    for url in (AFT_EN, AFT_FR):
        try:
            rating = parse_moodys(fetch(url))
            rating["url"] = url
            rating["source_kind"] = "official_document"
            return rating, errors
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__} {str(exc)[:180]}")
    # Some GitHub runner IP ranges are rejected by AFT (HTTP 403). A text
    # recovery gateway can still preserve the AFT source attribution. It is
    # NOT sufficient on its own to assert a newly changed sovereign rating.
    recovery_text = ""
    try:
        recovery_text = fetch(AFT_TEXT_RECOVERY)
        rating = parse_aft_text_recovery(recovery_text)
        rating["url"] = AFT_EN
        return rating, errors
    except Exception as exc:
        errors.append(f"Government text recovery: {type(exc).__name__} {str(exc)[:180]}")
        if recovery_text:
            # Public webpage debugging only: no credentials or user data.
            base.OUT.mkdir(parents=True, exist_ok=True)
            (base.OUT / "france_credit_recovery_debug.txt").write_text(
                recovery_text[:15000], encoding="utf-8")
    return None, errors


def credit_events(now: dt.date, old: dict, rating: dict) -> list[dict]:
    """A verified future event, or a changed official rating/decision, only once."""
    delivered = set(old.get("sent_keys") or [])
    events = []
    prev = old.get("last_official") or {}
    last_old = prev.get("decision_date")
    last_new = rating.get("decision_date")
    changed_rating = bool(prev and (prev.get("rating") != rating["rating"]
                    or prev.get("outlook") != rating["outlook"]))
    new_official_review = bool(prev and last_old and last_new and last_new > last_old)
    if (changed_rating or new_official_review) and rating.get("source_kind") == "official_document":
        key = f"decision:{last_new}:{rating['rating']}:{rating['outlook']}"
        if key not in delivered:
            events.append({"kind": "decision", "key": key})
    # Pre-review milestones are derived from VERIFIED official next-review date.
    review = rating.get("next_review")
    if review == REVIEW_DATE.isoformat() and now <= REVIEW_DATE:
        remaining = (REVIEW_DATE - now).days
        if remaining in MILESTONES:
            key = f"milestone:{review}:D-{remaining}"
            if key not in delivered:
                events.append({"kind": "milestone", "key": key,
                               "days": remaining})
    return events


def sp_review_events(local_day: dt.date, sent_keys: set[str]) -> list[dict]:
    """Remind on published S&P rating-review dates, not presumed downgrades."""
    if local_day > SP_REVIEW_DATE:
        overdue = f"sp_review_unverified_after_due:{SP_REVIEW_DATE.isoformat()}"
        return [] if overdue in sent_keys else [{"kind": "sp_review_overdue", "key": overdue}]
    remaining = (SP_REVIEW_DATE - local_day).days
    if remaining not in MILESTONES:
        return []
    key = f"sp_milestone:{SP_REVIEW_DATE.isoformat()}:D-{remaining}"
    return [] if key in sent_keys else [
        {"kind": "sp_milestone", "key": key, "days": remaining}
    ]


def money_spread(pending: dict) -> tuple[str, str]:
    data = pending.get("last_values") or {}
    dates = pending.get("last_source_dates") or {}
    stale = pending.get("stale") or []
    if dates.get("fr_mkt") and dates.get("fr_mkt") == dates.get("de_mkt") and not (
        "fr_mkt" in stale or "de_mkt" in stale
    ):
        try:
            gap = (float(data["fr_mkt"]) - float(data["de_mkt"])) * 100
            return f"{gap:.1f}bp", dates["fr_mkt"]
        except (KeyError, ValueError, TypeError):
            pass
    return "확인 불가(동일 기준일 자료 부족)", "확인 불가"


def format_event(rating: dict, events: list[dict], pending: dict,
                 now_kst: dt.datetime) -> tuple[str, str]:
    spread, date = money_spread(pending)
    changed = any(event["kind"] == "decision" for event in events)
    if changed:
        name = "프랑스 Moody’s 공식 신용등급 검토 결과"
        status = (f"공식자료 기준 Moody’s {rating['rating']} / 전망 {rating['outlook']} / "
                  f"최근 결정일 {rating['decision_date']}.")
        caveat = "등급 변동·전망 변경 여부는 이전 공식 기록과 비교해 판단합니다."
    elif any(x["kind"] == "government_rating_notice" for x in events):
        notice = next(x for x in events if x["kind"] == "government_rating_notice")
        name = "프랑스 재무부의 Moody’s 신용등급 관련 공식 입장"
        status = (f"{notice['date']} 프랑스 재무부의 Moody’s 관련 공식 보도자료가 공개됐습니다. "
                  "신용등급과 전망의 최종 확정값은 Moody’s 직접 발표 또는 AFT 최신 자료 "
                  "검증 전까지 표시하지 않습니다.")
        caveat = "정부의 대응 발표 확인과 Moody’s 신용등급 결정문 직접 확인은 서로 다른 단계입니다."
    elif any(x["kind"] == "milestone" for x in events):
        days = min(x["days"] for x in events if x["kind"] == "milestone")
        name = f"프랑스 Moody’s 신용등급 검토 D-{days}"
        if rating.get("source_kind") in ("historical_official_snapshot", "secondary_text_recovery"):
            status = (f"2026-10-14 확인한 AFT 공식 페이지 검색 색인의 일정: 2026-10-23(프랑스 현지 날짜). "
                      f"당일 공식 페이지 재조회는 제한되어 최신 일정 변경 여부는 확인 불가. "
                      f"마지막 확인 등급 {rating['rating']}·전망 {rating['outlook']}.")
        else:
            status = (f"공식 최신 확인 일정: 2026-10-23(프랑스 현지 날짜), "
                      f"등급 {rating['rating']}·전망 {rating['outlook']}.")
        caveat = "등급 강등 확정이 아닌 예정된 심사입니다. 포지션 청산 마감일도 아닙니다."
    elif any(x["kind"] == "sp_milestone" for x in events):
        days = min(x["days"] for x in events if x["kind"] == "sp_milestone")
        name = f"프랑스 S&P 신용등급 검토 D-{days}"
        status = ("2026-10-22 확인한 프랑스 국채관리청(AFT) 공식 일정: "
                  "S&P 2026-11-27(현지 날짜). "
                  "당시 등급 A+·전망 Stable. 날짜 변경 여부와 새 결정은 직접 원문 재검증 필요.")
        caveat = "심사 예정일은 하향조정 확정이나 캐리 포지션 청산 마감일이 아닙니다."
    elif any(x["kind"] == "sp_review_overdue" for x in events):
        name = "프랑스 S&P 신용등급 평가 결과 확인 필요"
        status = ("2026-11-27 예정된 S&P 평가일 경과. "
                  "이번 알림에서는 신용등급 결과를 직접 검증하지 못했으므로 "
                  "하향·유지·전망 변경을 확정하지 않습니다.")
        caveat = "프랑스 국채관리청·S&P 공식 자료 확인 전까지 미확인 상태입니다."
    elif any(x["kind"] == "review_overdue" for x in events):
        name = "프랑스 신용등급 결과 재검증 필요"
        status = "10월 23일 예정일이 지났지만 신용등급 결과는 공식 원문 접근 제한으로 확인되지 않았습니다."
        caveat = "심사 결과 발표 여부나 등급 유지는 확인되지 않았으므로 추정하지 않습니다."
    else:
        name = "프랑스 신용등급 공식자료 조회 장애"
        status = ("프랑스 국채관리청의 Moody’s 등급표가 반복적으로 접근 제한 상태입니다. "
                  "AFT 공식 페이지 검색 색인 확인일은 2026-10-14이며 직접 원문 조회는 제한됐습니다.")
        caveat = "등급 변경이나 시장의 강등 가능성을 확정할 수 없습니다. 공식 결과 조회가 지연될 수 있습니다."

    sp_only = any(x["kind"] in ("sp_milestone", "sp_review_overdue") for x in events)
    primary_link = ("• AFT France S&P rating calendar: " + AFT_EN if sp_only else
                    "• AFT France Moody's rating calendar: " + rating["url"])
    next_boundary = base.next_spread_marker(
        float(spread.replace("bp", "")) if re.fullmatch(r"\d+(?:\.\d+)?bp", spread) else None
    )
    msg = "\n".join([
        f"🔔 [프랑스 국채·신용등급] {name}",
        "",
        f"■ 확인 시각: {now_kst.strftime('%Y-%m-%d %H:%M')} 한국시간",
        f"• {status}",
        f"• 같은 제공사 기준 프랑스-독일 10년 금리차: {spread} (기준일 {date}).",
        f"• 주의: {caveat}",
        "",
        "■ 캐리거래와 글로벌 시장 연결",
        "• 보도된 구조: 프랑스 국채와 금리스와프 사이 가격 차이에 레버리지 투자 → "
        "국채가격 급락 → 담보가치 감소·증거금 요구 증가 → 차입 축소·포지션 정리.",
        "• 메모리주 영향은 조건부: 프랑스 국채 금리차 재확대 + 금융시장 변동성 상승"
        " + 기술주 동반 매도가 겹칠 때 광범위한 레버리지 축소 가능성을 점검합니다.",
        "• 반대 경로: 스프레드 축소와 국채 입찰 수요 회복이 확인되면"
        " 재정위기·캐리 청산 전염 가설은 약해집니다.",
        "",
        "■ 먼저 확인할 지표",
        f"• 프랑스-독일 동일 기준일 국채금리차 다음 경계 {next_boundary} 및 일간 변화",
        "• 유럽 국채 유동성·매수/매도 호가차·환매조건부채권 거래조건",
        "• 프랑스 10월 23일 공식 신용등급 결과와 2027년 예산 논의",
        "",
        primary_link,
        f"• Briefs France carry story: {ORIGINAL_STORY}",
        *([f"• France government Moody press: {next(x for x in events if x['kind'] == 'government_rating_notice')['url']}"]
          if any(x["kind"] == "government_rating_notice" for x in events) else []),
    ])
    return name, msg


def add_market_carry_context(existing: str, pending: dict, local_day: dt.date) -> str:
    """Add context to a genuine bond-spread alert; never emit a separate alert."""
    gap_text, asof = money_spread(pending)
    if "확인 불가" in gap_text or not gap_text.endswith("bp"):
        return existing
    try:
        gap = float(gap_text[:-2])
    except ValueError:
        return existing
    if gap < 125.0 or "■ 캐리·레버리지 전염 확인" in existing:
        return existing
    review = (
        "• Moody’s 프랑스 등급 검토는 10월 23일 예정(10월 14일 공식 확인 기준)."
        " 강등이나 포지션 청산 마감일은 확정되지 않았습니다."
        if local_day <= REVIEW_DATE else
        "• 10월 23일 예정됐던 Moody’s 등급 검토 결과는 새 공식 발표로 확인해야 합니다."
    )
    section = "\n".join([
        "■ 캐리·레버리지 전염 확인",
        f"• 동일 기준일 프랑스-독일 시장금리차: {gap:.1f}bp ({asof}). 다음 감시 {base.next_spread_marker(gap)}.",
        "• 10월 2일 보도: 프랑스 국채·금리스와프 가격차에 투자한 레버리지 포지션 축소가 관측됐습니다.",
        "• 메모리주에 직접 영향을 줬는지는 미확인입니다."
        " 국채 유동성 악화·달러 및 엔화 변화·기술주 동반 매도가 확인돼야 전염 가설을 강화할 수 있습니다.",
        review,
    ])
    marker = "■ 시장 영향"
    return existing.replace(marker, section + "\n\n" + marker, 1) if marker in existing else existing + "\n\n" + section


def main() -> int:
    base.OUT.mkdir(parents=True, exist_ok=True)
    pending = base.load_json(base.PENDING, {})
    if not pending:
        STATUS.write_text("공식 국채 감시 대기: 공유 상태 파일 없음\n", encoding="utf-8")
        return 0
    state = base.load_json(base.STATE, {})
    existing_credit = state.get("france_credit") or {}
    now = dt.datetime.now(KST)
    official, errors = fetch_rating()
    # A recovery gateway is not equivalent to direct official-source access.
    source_ok = official is not None
    direct_official = bool(official and official.get("source_kind") == "official_document")
    fail_streak = (0 if direct_official else
                   int(existing_credit.get("source_fail_streak") or 0) + 1)
    # Do not fabricate a live rating when the issuer website and proxy reject
    # automation. Carry forward the date-stamped official snapshot only.
    rating = official if source_ok else {
        **(existing_credit.get("last_official") or VERIFIED_AFT_SNAPSHOT),
        "source_kind": "historical_official_snapshot",
        "verified_on": (existing_credit.get("last_official") or VERIFIED_AFT_SNAPSHOT).get("verified_on", "2026-10-14"),
    }
    local_day = now.astimezone(PARIS).date()
    events = credit_events(local_day, existing_credit, rating)
    delivered = set(existing_credit.get("sent_keys") or [])
    events.extend(sp_review_events(local_day, delivered))

    # First-party French Finance Ministry is a backup for the AFT's HTTP 403
    # problem. A ministry response can confirm publication of an official
    # government statement, but it must NOT be interpreted as a Moody's
    # rating or outlook action without Moody's issuer decision.
    government_notice = None
    government_errors = []
    if local_day >= REVIEW_DATE:
        def government_fetch(url):
            data, err = fetch_text(
                url, "Mozilla/5.0 (khs-france-rating-press/1.0)",
                timeout=13, attempts=1, accept="text/html",
            )
            if err is not None or not data:
                raise RuntimeError(err or "empty ministry notice")
            return data
        government_notice, government_errors = discover_ministry_notice(government_fetch, now)
        if government_notice:
            digest = hashlib.sha256(government_notice["url"].encode("utf-8")).hexdigest()[:16]
            key = f"government_notice:{government_notice['date']}:{digest}"
            if key not in delivered:
                events.append({"kind": "government_rating_notice",
                               "key": key, "date": government_notice["date"],
                               "url": government_notice["url"],
                               "title": government_notice.get("title", "")})
    if not direct_official and fail_streak >= 4:
        key = "official_rating_source_unavailable:2026-10"
        if key not in delivered:
            events.append({"kind": "source_outage", "key": key})
    if not source_ok and now.astimezone(PARIS).date() >= dt.date(2026, 10, 24):
        key = "review_unverified_after_due:2026-10-23"
        if key not in delivered:
            events.append({"kind": "review_overdue", "key": key})

    next_credit = {
        "last_official": rating if source_ok else (existing_credit.get("last_official") or VERIFIED_AFT_SNAPSHOT),
        "sent_keys": list(existing_credit.get("sent_keys") or [])[-30:],
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "source_fail_streak": fail_streak,
        "source_access": ("official_document" if direct_official
                          else "secondary_text_recovery" if source_ok
                          else "access_restricted"),
    }
    if events:
        next_credit["sent_keys"] = (next_credit["sent_keys"] + [e["key"] for e in events])[-30:]
    pending["france_credit"] = next_credit
    base.PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if base.ALERT.exists() and not events:
        # Same alert ID and delivery lane: no independent memory alert.
        original = base.ALERT.read_text(encoding="utf-8").strip()
        enriched = add_market_carry_context(original, pending, now.astimezone(PARIS).date())
        if enriched != original:
            base.ALERT.write_text(enriched + "\n", encoding="utf-8")

    if events:
        title, body = format_event(rating, events, pending, now)
        if base.ALERT.exists():
            # Preserve the existing sovereign-yield event and append new factual context.
            original = base.ALERT.read_text(encoding="utf-8").strip()
            base.ALERT.write_text(original + "\n\n" + body + "\n", encoding="utf-8")
        else:
            base.ALERT.write_text(body + "\n", encoding="utf-8")
            base.TITLE.write_text(title + "\n", encoding="utf-8")
        detail = base.load_json(base.DETAIL, {})
        detail.setdefault("related_events", []).extend(events)
        detail["moody_source"] = rating
        base.DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    STATUS.write_text(
        "\n".join([
            "# 프랑스 신용등급·국채 캐리 감시",
            f"- 조회: {now.isoformat(timespec='seconds')}",
            f"- 출처 상태: {'공식 페이지 직접 확인' if direct_official else '공식 페이지 직접 검증 미완료·보조 복원' if source_ok else '접근 제한·2026-10-14 AFT 검색 색인 참고'}",
            f"- 최근 공식확인: Moody's {rating['rating']}, {rating['outlook']}, {rating['decision_date']}",
            f"- 다음 심사: {rating['next_review'] or '미게시'}",
            f"- 연속 원문 오류: {fail_streak}",
            f"- 프랑스 재무부 공식 입장: {government_notice['url'] if government_notice else '신규 확인 없음'}",
            f"- 이번 새 이벤트: {len(events)}",
            f"- 중복키: {', '.join(x['key'] for x in events) if events else '없음'}",
            f"- 공식 페이지: {rating['url']}",
            *([f"- {x}" for x in errors[:3]] if errors else []),
            *([f"- 재무부 보조원천: {x}" for x in government_errors[:2]] if government_errors else []),
        ]) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
