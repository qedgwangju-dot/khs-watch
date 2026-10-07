#!/usr/bin/env python3
"""Robust ECB monetary-policy / press-conference watcher.

Design goals:
- Official ECB sources only for policy facts.
- RSS is convenient but never a single point of failure.
- Fall back to the ECB press-conference index and yearly press-release index.
- Fail closed on uncertain parsing: do not send an alert and do not consume the event.
- A source outage is recorded as degraded status instead of making every scheduled run fail.
- State is finalized only after confirmed Telegram delivery when an alert exists.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html as htmllib
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
STATE = DATA / "ecb_policy_watch_state.json"
PENDING = OUT / "ecb_policy_watch_pending_state.json"
ALERT = OUT / "ecb_policy_watch_alert.md"
TITLE = OUT / "ecb_policy_watch_alert_title.txt"
DETAIL = OUT / "ecb_policy_watch_alert.json"
STATUS = OUT / "ecb_policy_watch_status.md"
CONFIRMED = OUT / "ecb_policy_watch_telegram_confirmed.json"

RSS = "https://www.ecb.europa.eu/rss/press.html"
PRESS_CONFERENCE_INDEX = "https://www.ecb.europa.eu/press/press_conference/html/index.en.html"
PRESS_RELEASE_INDEX = "https://www.ecb.europa.eu/press/pr/date/{year}/html/index.en.html"
MEETINGS = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
UA = "khs-watch-ecb-policy/2.0"


def fetch(url: str, *, tries: int = 3, timeout: int = 30) -> str:
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml,*/*",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                charset = r.headers.get_content_charset() or "utf-8"
                return data.decode(charset, errors="replace")
        except Exception as exc:
            last = exc
            if attempt + 1 < tries:
                time.sleep(1.0 + attempt)
    raise last or RuntimeError("fetch failed")


def strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", htmllib.unescape(value)).strip()


def load_json(path: pathlib.Path, default: dict) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else dict(default)
    except Exception:
        return dict(default)


def rss_items(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        description = strip_html(item.findtext("description") or "")
        try:
            published = parsedate_to_datetime(pub)
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except Exception:
            published = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        items.append({
            "title": title,
            "link": link,
            "pubDate": pub,
            "description": description,
            "published": published,
            "date": published.date().isoformat() if published.year > 1900 else "",
            "source": "rss",
        })
    return items


def doc_date_from_url(url: str) -> str:
    m = re.search(r"ecb\.(?:mp|is)(\d{2})(\d{2})(\d{2})", url, re.I)
    if not m:
        return ""
    yy, mm, dd = map(int, m.groups())
    return f"20{yy:02d}-{mm:02d}-{dd:02d}"


def extract_official_links(html_text: str, base_url: str) -> list[dict]:
    out = []
    for href, label in re.findall(
        r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        html_text,
        flags=re.I | re.S,
    ):
        url = urllib.parse.urljoin(base_url, htmllib.unescape(href))
        text = strip_html(label)
        low = url.lower()
        kind = None
        if "ecb.mp" in low and "/press/pr/date/" in low:
            kind = "decision"
        elif "ecb.is" in low and "monetary-policy-statement" in low:
            kind = "statement"
        if kind:
            out.append({
                "kind": kind,
                "title": text,
                "link": url,
                "date": doc_date_from_url(url),
                "source": "html-index",
            })
    return out


def collect_latest_documents(now: dt.datetime) -> tuple[dict | None, dict | None, list[str], list[str]]:
    candidates: list[dict] = []
    errors: list[str] = []
    sources_ok: list[str] = []

    try:
        text = fetch(RSS)
        for item in rss_items(text):
            title = item.get("title", "")
            if re.search(r"monetary policy decision", title, re.I):
                item["kind"] = "decision"
                candidates.append(item)
            elif re.search(r"monetary policy statement", title, re.I):
                item["kind"] = "statement"
                candidates.append(item)
        sources_ok.append("ECB RSS")
    except Exception as exc:
        errors.append(f"ECB RSS: {type(exc).__name__}: {exc}")

    try:
        text = fetch(PRESS_CONFERENCE_INDEX)
        candidates.extend(extract_official_links(text, PRESS_CONFERENCE_INDEX))
        sources_ok.append("ECB 기자회견 인덱스")
    except Exception as exc:
        errors.append(f"ECB 기자회견 인덱스: {type(exc).__name__}: {exc}")

    for year in sorted({now.year, now.year - 1}, reverse=True):
        url = PRESS_RELEASE_INDEX.format(year=year)
        try:
            text = fetch(url)
            candidates.extend(extract_official_links(text, url))
            sources_ok.append(f"ECB 보도자료 {year}")
        except Exception as exc:
            errors.append(f"ECB 보도자료 {year}: {type(exc).__name__}: {exc}")

    dedup: dict[tuple[str, str], dict] = {}
    for c in candidates:
        if not c.get("link") or not c.get("kind"):
            continue
        if not c.get("date"):
            c["date"] = doc_date_from_url(c["link"])
        dedup[(c["kind"], c["link"])] = c

    def latest(kind: str) -> dict | None:
        rows = [x for x in dedup.values() if x.get("kind") == kind and x.get("date")]
        rows.sort(key=lambda x: (x["date"], x["link"]), reverse=True)
        return rows[0] if rows else None

    decision = latest("decision")
    statement = latest("statement")
    if decision and statement and statement.get("date") != decision.get("date"):
        # Keep the statement only as a separate latest document. The caller will
        # attach it to a decision only when the dates match.
        pass
    return decision, statement, errors, sources_ok


def number_after(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I | re.S)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None


def parse_decision(text: str) -> dict:
    plain = strip_html(text)
    lower = plain.lower()
    action = "변경"
    bp = number_after(r"(?:raise|increase|lower|reduce|cut)[^\.]{0,120}?by\s+([0-9]+(?:\.[0-9]+)?)\s+basis points", plain)
    if "decided to raise" in lower or "decided to increase" in lower:
        action = "인상"
    elif "decided to lower" in lower or "decided to reduce" in lower or "decided to cut" in lower:
        action = "인하"
    elif "keep the three key ecb interest rates unchanged" in lower or "remain unchanged" in lower:
        action = "동결"
        bp = 0.0

    rate_match = re.search(
        r"deposit facility,\s*the main refinancing operations and the marginal lending facility[^\.]{0,320}?"
        r"(?:increased|decreased|set|remain)[^\.]{0,160}?to\s*([0-9]+(?:\.[0-9]+)?)%\s*,?\s*"
        r"([0-9]+(?:\.[0-9]+)?)%\s*(?:and|,)?\s*([0-9]+(?:\.[0-9]+)?)%",
        plain,
        re.I,
    )
    deposit = main_refi = marginal = None
    if rate_match:
        deposit, main_refi, marginal = map(float, rate_match.groups())
    else:
        deposit = number_after(r"deposit facility[^\.]{0,160}?(?:to|at)\s*([0-9]+(?:\.[0-9]+)?)%", plain)
        main_refi = number_after(r"main refinancing operations[^\.]{0,160}?(?:to|at)\s*([0-9]+(?:\.[0-9]+)?)%", plain)
        marginal = number_after(r"marginal lending facility[^\.]{0,160}?(?:to|at)\s*([0-9]+(?:\.[0-9]+)?)%", plain)

    if deposit is not None and bp is not None:
        step = bp / 100.0
        previous_deposit = deposit - step if action == "인상" else deposit + step if action == "인하" else deposit
    else:
        previous_deposit = None

    headline = []
    core = []
    mh = re.search(r"headline inflation averaging\s+([0-9.]+)\s*(?:per cent|%)\s+in\s+(20\d{2}),\s*([0-9.]+)\s*(?:per cent|%)\s+in\s+(20\d{2})\s+and\s+([0-9.]+)\s*(?:per cent|%)\s+in\s+(20\d{2})", plain, re.I)
    if mh:
        headline = [(mh.group(2), float(mh.group(1))), (mh.group(4), float(mh.group(3))), (mh.group(6), float(mh.group(5)))]
    mc = re.search(r"inflation excluding energy and food[^\.]{0,180}?(?:foresees|average(?: of)?)\s+([0-9.]+)\s*(?:per cent|%)?\s+in\s+(20\d{2}),\s*([0-9.]+)\s*(?:per cent|%)?\s+in\s+(20\d{2})\s+and\s+([0-9.]+)\s*(?:per cent|%)?\s+in\s+(20\d{2})", plain, re.I)
    if mc:
        core = [(mc.group(2), float(mc.group(1))), (mc.group(4), float(mc.group(3))), (mc.group(6), float(mc.group(5)))]

    valid = action in {"인상", "인하", "동결"}
    if action in {"인상", "인하"}:
        valid = valid and bp is not None and deposit is not None
    if action == "동결":
        valid = valid and deposit is not None

    return {
        "valid": bool(valid),
        "action": action,
        "bp": bp,
        "deposit": deposit,
        "previous_deposit": previous_deposit,
        "main_refi": main_refi,
        "marginal": marginal,
        "headline_projection": headline,
        "core_projection": core,
        "mentions_middle_east": "middle east" in lower,
        "mentions_energy": "energy" in lower,
        "mentions_above_target": "above target" in lower or "well above target" in lower,
        "plain": plain,
    }


def parse_statement(text: str) -> dict:
    plain = strip_html(text)
    lower = plain.lower()
    indirect_contained = bool(
        re.search(r"indirect effects[^\.]{0,120}(?:contained|limited|not really seeing much)", lower)
        or re.search(r"(?:not really seeing much|contained)[^\.]{0,120}indirect effects", lower)
    )
    second_round_not_seen = bool(
        re.search(r"second[- ]round effects[^\.]{0,120}(?:not seeing|not yet|not observed)", lower)
        or re.search(r"(?:not seeing|not yet observed)[^\.]{0,120}second[- ]round effects", lower)
    )
    food_future = bool(
        "higher food prices in the future" in lower
        or re.search(r"(?:would|could) impact food prices", lower)
        or re.search(r"food prices[^\.]{0,120}(?:future|higher|increase)", lower)
    )
    longer_energy = bool(
        "longer-than-anticipated energy shock" in lower
        or re.search(r"longer[^\.]{0,80}energy shock", lower)
        or re.search(r"energy prices stay high", lower)
    )
    return {
        "plain": plain,
        "energy": "energy" in lower,
        "food": "food" in lower,
        "indirect": "indirect" in lower,
        "second_round": "second-round" in lower or "second round" in lower,
        "wages": "wage" in lower,
        "expectations": "inflation expectations" in lower,
        "duration": any(k in lower for k in ("duration", "persistent", "persist", "longer")),
        "gas": "gas" in lower,
        "fertil": "fertili" in lower,
        "transport": "transport" in lower,
        "indirect_contained": indirect_contained,
        "second_round_not_seen": second_round_not_seen,
        "food_future": food_future,
        "longer_energy": longer_energy,
    }


def fmt_rate(v: float | None) -> str:
    return "확인 불가" if v is None else f"{v:.2f}%"


def projection_line(values: list[tuple[str, float]], label: str) -> str | None:
    if not values:
        return None
    return f"• {label}: " + " → ".join(f"{y}년 {v:.1f}%" for y, v in values)


def signature(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def build_main_alert(item: dict, decision: dict, statement_item: dict | None, statement: dict | None) -> tuple[str, str, dict]:
    action = decision["action"]
    bp = decision.get("bp")
    dep = decision.get("deposit")
    prev_dep = decision.get("previous_deposit")
    rate_summary = f"예금금리 {fmt_rate(prev_dep)} → {fmt_rate(dep)}"
    if bp not in (None, 0):
        rate_summary += f" ({'+' if action == '인상' else '-'}{bp/100:.2f}%p)"

    lines = [
        f"🔔 [유럽 통화정책] ECB {action} — {rate_summary}",
        "",
        "🇪🇺 ECB는?",
        "유럽중앙은행(European Central Bank). 유로화를 사용하는 21개국의 단일 통화정책을 결정하며, 미국의 Fed에 해당합니다.",
        "",
        "■ 이번 결정",
        f"• 예금금리: {fmt_rate(prev_dep)} → {fmt_rate(dep)}" + (f" ({'+' if action == '인상' else '-'}{bp/100:.2f}%p)" if bp not in (None, 0) else ""),
    ]
    if decision.get("main_refi") is not None and decision.get("marginal") is not None:
        lines.append(f"• 주요 재융자금리 {fmt_rate(decision['main_refi'])} / 한계대출금리 {fmt_rate(decision['marginal'])}")
    ph = projection_line(decision.get("headline_projection") or [], "ECB 종합 물가 전망")
    pc = projection_line(decision.get("core_projection") or [], "에너지·식료품 제외 물가 전망")
    if ph:
        lines.append(ph)
    if pc:
        lines.append(pc)

    lines += ["", "■ 왜 움직였나"]
    if decision.get("mentions_energy") and decision.get("mentions_middle_east"):
        lines.append("• 중동발 에너지 충격이 물가를 다시 밀어 올리고, 높은 물가가 예상보다 오래 지속될 위험을 반영했습니다.")
    elif decision.get("mentions_energy"):
        lines.append("• 에너지 가격과 물가 경로가 핵심 정책 변수입니다.")
    else:
        lines.append("• ECB는 물가 전망·근원물가·통화정책 전달 강도를 기준으로 회의별 판단을 이어가고 있습니다.")

    if statement:
        lines += ["", "■ 라가르드 총재·ECB가 보는 전이 경로"]
        if statement.get("indirect_contained"):
            lines.append("• 현재: 에너지 충격의 간접 파급은 아직 제한적이라고 설명했습니다.")
        if statement.get("second_round_not_seen"):
            lines.append("• 현재: 임금·기대·가격설정으로 번지는 2차 파급은 아직 관측되지 않았다고 설명했습니다.")
        if statement.get("longer_energy") or (statement.get("duration") and statement.get("energy")):
            lines.append("• 위험: 에너지 충격이 예상보다 오래가면 비에너지 물가로 파급될 가능성이 커집니다.")
        if statement.get("food_future") or statement.get("food"):
            lines.append("• 식료품: 에너지 → 비료·운송·생산비 → 식료품 가격으로 이어지는 간접 파급을 주의합니다.")
        if statement.get("gas"):
            lines.append("• 가스 가격·재고도 별도 위험요인입니다. 유가만 보면 에너지 충격을 과소평가할 수 있습니다.")
        lines.append("• 구분: 식료품 가격 상승 자체는 간접 파급이고, 기대인플레이션·임금·기업 가격설정까지 번질 때 2차 파급입니다.")
    else:
        lines += ["", "■ 총재 발언", "• 같은 날 기자회견 공식 원문이 아직 확인되지 않았습니다. 공개되면 별도 업데이트합니다."]

    lines += [
        "",
        "■ 시장에서 볼 것",
        "🔴 에너지·식료품 상승 + 임금·기대인플레이션 재가속 → 추가 긴축 위험↑ → 장기금리·할인율 부담↑",
        "🟢 에너지 안정 + 근원물가·임금 둔화 → 2차 파급 제한 → 추가 긴축 필요성↓",
        "",
        "■ 자산 영향",
        "• 성장주·리츠·고부채 기업: 장기금리가 함께 오르면 할인율 부담이 커집니다.",
        "• 은행: 금리 상승에 따른 이자마진 개선과 경기둔화·신용비용 상승을 함께 봐야 합니다.",
        "",
        "■ 다음 확인",
        "• 에너지·가스 → 식료품·상품·서비스 → 기대인플레이션·임금 순으로 실제 전이가 확인되는지 점검합니다.",
        "• ECB는 특정 금리 경로를 미리 확정하지 않고 데이터와 회의별 판단을 강조합니다.",
        "",
        f"원문(ECB 결정): {item['link']}",
    ]
    if statement_item and statement_item.get("link"):
        lines.append(f"원문(ECB 기자회견): {statement_item['link']}")
    lines.append(f"ECB 회의 일정: {MEETINGS}")

    detail = {
        "kind": "decision",
        "date": item.get("date"),
        "decision_url": item.get("link"),
        "statement_url": (statement_item or {}).get("link"),
        "decision": {k: v for k, v in decision.items() if k != "plain"},
        "statement_signals": {k: v for k, v in (statement or {}).items() if k != "plain"},
    }
    detail["signature"] = signature(detail)
    return f"ECB {action} {fmt_rate(dep)}", "\n".join(lines), detail


def build_statement_update(item: dict, statement: dict) -> tuple[str, str, dict]:
    lines = [
        "🔔 [ECB 총재 발언 업데이트] 라가르드 — 에너지 충격의 장기화·파급 경로",
        "",
        "🇪🇺 ECB는?",
        "유럽중앙은행(European Central Bank). 유로화를 사용하는 21개국의 단일 통화정책을 결정하며 미국의 Fed에 해당합니다.",
        "",
        "■ 지금 확인된 상태",
    ]
    if statement.get("indirect_contained"):
        lines.append("• 간접 파급: 아직 제한적.")
    if statement.get("second_round_not_seen"):
        lines.append("• 2차 파급: 아직 관측되지 않음.")
    if not statement.get("indirect_contained") and not statement.get("second_round_not_seen"):
        lines.append("• ECB는 에너지 충격의 간접·2차 파급을 계속 점검하고 있습니다.")

    lines += ["", "■ 앞으로의 위험"]
    if statement.get("longer_energy") or (statement.get("duration") and statement.get("energy")):
        lines.append("• 에너지 충격이 예상보다 오래가면 더 넓은 물가 항목으로 번질 가능성이 커집니다.")
    if statement.get("food_future") or statement.get("food"):
        lines.append("• 식료품: 비료·운송·생산비를 통해 비용 상승이 뒤늦게 전달될 수 있습니다.")
    if statement.get("gas"):
        lines.append("• 가스 가격·재고도 핵심 위험요인입니다.")

    lines += [
        "",
        "■ 정확한 구분",
        "에너지 → 비료·운송·생산비 → 식료품·상품·서비스 가격은 ‘간접 파급’입니다.",
        "그 뒤 기대인플레이션 → 임금 요구 → 기업 가격 인상으로 이어지면 ‘2차 파급’ 위험이 커집니다.",
        "",
        "■ 시장에서 볼 것",
        "🔴 식료품·서비스 물가와 임금이 함께 재가속하면 ECB 추가 긴축 가능성이 커집니다.",
        "🟢 에너지 가격이 안정되고 임금 둔화가 지속되면 충격이 일회성에 가까워집니다.",
        "",
        f"원문(ECB 기자회견): {item['link']}",
    ]
    detail = {
        "kind": "statement",
        "date": item.get("date"),
        "statement_url": item.get("link"),
        "statement_signals": {k: v for k, v in statement.items() if k != "plain"},
    }
    detail["signature"] = signature(detail)
    return "ECB 라가르드 발언 업데이트", "\n".join(lines), detail


def finalize() -> int:
    if not PENDING.exists():
        return 0
    alert_exists = ALERT.exists()
    confirmed = CONFIRMED.exists()
    if alert_exists and not confirmed:
        raise RuntimeError("ECB 알림이 생성됐지만 텔레그램 전송 확인이 없어 상태를 확정하지 않습니다.")
    DATA.mkdir(parents=True, exist_ok=True)
    STATE.write_text(PENDING.read_text(encoding="utf-8"), encoding="utf-8")
    return 0


def write_status(now: dt.datetime, next_state: dict, decision_item: dict | None, statement_item: dict | None, alert: bool, errors: list[str], sources_ok: list[str], note: str = "") -> None:
    lines = [
        "# ECB 정책 감시",
        "",
        f"- 조회: {now.isoformat(timespec='seconds')}",
        f"- 최신 통화정책 결정일: {(decision_item or {}).get('date') or '확인 불가'}",
        f"- 최신 기자회견일: {(statement_item or {}).get('date') or '확인 불가'}",
        f"- 신규 알림: {'예' if alert else '아니오'}",
        f"- 공식 소스 정상: {', '.join(sources_ok) if sources_ok else '없음'}",
        f"- 연속 소스 장애: {next_state.get('source_fail_streak', 0)}회",
    ]
    if note:
        lines.append(f"- 상태: {note}")
    if errors:
        lines += ["", "## 소스 오류(대체경로 포함)"] + [f"- {x}" for x in errors[:6]]
    STATUS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize()

    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, TITLE, DETAIL, CONFIRMED, PENDING):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    now = dt.datetime.now(KST)
    state = load_json(STATE, {})
    decision_item, statement_item, source_errors, sources_ok = collect_latest_documents(now)

    next_state = dict(state)
    next_state["last_checked_kst"] = now.isoformat(timespec="seconds")

    if not decision_item:
        next_state["source_fail_streak"] = int(state.get("source_fail_streak") or 0) + 1
        PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_status(now, next_state, None, statement_item, False, source_errors, sources_ok, "공식 인덱스에서 최신 통화정책 결정을 식별하지 못해 상태를 소비하지 않음")
        # Do not turn a transient source/layout issue into a permanently red scheduled job.
        return 0

    next_state["source_fail_streak"] = 0
    current_decision_date = decision_item.get("date") or ""
    current_statement_date = (statement_item or {}).get("date") or ""

    decision_text = None
    try:
        decision_text = fetch(decision_item["link"])
    except Exception as exc:
        source_errors.append(f"ECB 결정 원문: {type(exc).__name__}: {exc}")

    if not decision_text:
        PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_status(now, next_state, decision_item, statement_item, False, source_errors, sources_ok, "결정 원문 직접 열람 실패 — 알림/상태 소비 안 함")
        return 0

    decision = parse_decision(decision_text)
    if not decision.get("valid"):
        next_state["parse_fail_streak"] = int(state.get("parse_fail_streak") or 0) + 1
        PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_status(now, next_state, decision_item, statement_item, False, source_errors, sources_ok, "결정문 핵심 금리 파싱 불완전 — 오발송 방지를 위해 보류")
        return 0

    next_state["parse_fail_streak"] = 0

    statement = None
    if statement_item and current_statement_date == current_decision_date:
        try:
            statement = parse_statement(fetch(statement_item["link"]))
        except Exception as exc:
            source_errors.append(f"ECB 기자회견 원문: {type(exc).__name__}: {exc}")

    main_tuple = build_main_alert(
        decision_item,
        decision,
        statement_item if current_statement_date == current_decision_date else None,
        statement,
    )
    main_sig = main_tuple[2]["signature"]
    new_decision = bool(current_decision_date and (
        current_decision_date != state.get("last_decision_date")
        or main_sig != state.get("last_decision_signature")
    ))

    alert_tuple = None
    if new_decision:
        alert_tuple = main_tuple
        next_state["last_decision_date"] = current_decision_date
        next_state["last_decision_url"] = decision_item.get("link")
        next_state["last_decision_signature"] = main_sig
        if statement_item and current_statement_date == current_decision_date and statement is not None:
            stmt_tuple = build_statement_update(statement_item, statement)
            next_state["last_statement_date"] = current_statement_date
            next_state["last_statement_url"] = statement_item.get("link")
            next_state["last_statement_signature"] = stmt_tuple[2]["signature"]
    elif statement_item and current_statement_date == current_decision_date and statement is not None:
        stmt_tuple = build_statement_update(statement_item, statement)
        stmt_sig = stmt_tuple[2]["signature"]
        new_statement = bool(
            current_statement_date != state.get("last_statement_date")
            or stmt_sig != state.get("last_statement_signature")
        )
        if new_statement:
            alert_tuple = stmt_tuple
            next_state["last_statement_date"] = current_statement_date
            next_state["last_statement_url"] = statement_item.get("link")
            next_state["last_statement_signature"] = stmt_sig

    PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_status(now, next_state, decision_item, statement_item, bool(alert_tuple), source_errors, sources_ok, "정상" if not source_errors else "정상(일부 소스 대체경로 사용)")

    if alert_tuple:
        title, body, detail = alert_tuple
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body.strip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
