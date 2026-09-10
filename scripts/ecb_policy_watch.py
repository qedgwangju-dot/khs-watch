#!/usr/bin/env python3
"""ECB monetary-policy / press-conference watcher with readable Korean Telegram output.

Primary sources are ECB official RSS, monetary-policy decisions and press-conference
transcripts. The watcher intentionally separates:
- what changed,
- what ECB is,
- Lagarde / ECB transmission path,
- what has actually happened vs. what is only a risk,
- market implications and the next confirmation points.

State is finalized only after confirmed Telegram delivery by the workflow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import json
import pathlib
import re
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
MEETINGS = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
UA = "khs-watch-ecb-policy/1.0"


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml,*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


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
        })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items


def latest_matching(items: list[dict], pattern: str) -> dict | None:
    rx = re.compile(pattern, re.I)
    for item in items:
        if rx.search(item.get("title") or ""):
            return item
    return None


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
    action = "변경"
    bp = number_after(r"(?:raise|increase|lower|reduce|cut)[^\.]{0,100}?by\s+([0-9]+(?:\.[0-9]+)?)\s+basis points", plain)
    lower = plain.lower()
    if "decided to raise" in lower or "decided to increase" in lower:
        action = "인상"
    elif "decided to lower" in lower or "decided to reduce" in lower or "decided to cut" in lower:
        action = "인하"
    elif "keep the three key ecb interest rates unchanged" in lower or "remain unchanged" in lower:
        action = "동결"
        bp = 0.0

    rate_match = re.search(
        r"deposit facility,\s*the main refinancing operations and the marginal lending facility[^\.]{0,260}?"
        r"(?:increased|decreased|set|remain)[^\.]{0,120}?to\s*([0-9]+(?:\.[0-9]+)?)%\s*,?\s*"
        r"([0-9]+(?:\.[0-9]+)?)%\s*(?:and|,)?\s*([0-9]+(?:\.[0-9]+)?)%",
        plain,
        re.I,
    )
    deposit = main_refi = marginal = None
    if rate_match:
        deposit, main_refi, marginal = map(float, rate_match.groups())
    else:
        deposit = number_after(r"deposit facility[^\.]{0,120}?(?:to|at)\s*([0-9]+(?:\.[0-9]+)?)%", plain)
        main_refi = number_after(r"main refinancing operations[^\.]{0,120}?(?:to|at)\s*([0-9]+(?:\.[0-9]+)?)%", plain)
        marginal = number_after(r"marginal lending facility[^\.]{0,120}?(?:to|at)\s*([0-9]+(?:\.[0-9]+)?)%", plain)

    if deposit is not None and bp is not None:
        step = bp / 100.0
        previous_deposit = deposit - step if action == "인상" else deposit + step if action == "인하" else deposit
    else:
        previous_deposit = None

    headline = []
    core = []
    mh = re.search(r"headline inflation averaging\s+([0-9.]+)%\s+in\s+(20\d{2}),\s*([0-9.]+)%\s+in\s+(20\d{2})\s+and\s+([0-9.]+)%\s+in\s+(20\d{2})", plain, re.I)
    if mh:
        headline = [(mh.group(2), float(mh.group(1))), (mh.group(4), float(mh.group(3))), (mh.group(6), float(mh.group(5)))]
    mc = re.search(r"inflation excluding energy and food[^\.]{0,120}?(?:foresees|average(?: of)?)\s+([0-9.]+)%?\s+in\s+(20\d{2}),\s*([0-9.]+)%?\s+in\s+(20\d{2})\s+and\s+([0-9.]+)%?\s+in\s+(20\d{2})", plain, re.I)
    if mc:
        core = [(mc.group(2), float(mc.group(1))), (mc.group(4), float(mc.group(3))), (mc.group(6), float(mc.group(5)))]

    return {
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
        "mentions_above_target": "above target" in lower,
        "plain": plain,
    }


def parse_statement(text: str) -> dict:
    plain = strip_html(text)
    lower = plain.lower()
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
    }


def fmt_rate(v: float | None) -> str:
    return "확인 불가" if v is None else f"{v:.2f}%"


def projection_line(values: list[tuple[str, float]], label: str) -> str | None:
    if not values:
        return None
    return f"• {label}: " + " → ".join(f"{y}년 {v:.1f}%" for y, v in values)


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
        "유럽중앙은행(European Central Bank). 유로화를 사용하는 국가들의 단일 통화정책을 결정하며, 미국의 Fed에 해당합니다.",
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
        if statement.get("duration") and statement.get("energy"):
            lines.append("• 에너지 충격이 길어질수록 비에너지 물가로 번질 위험이 커진다는 판단입니다.")
        if statement.get("food"):
            lines.append("• 식료품 가격: 에너지 → 비료·운송·생산비 → 식료품 가격으로 전달되는 ‘간접 파급’을 확인합니다.")
        if statement.get("second_round") or statement.get("wages") or statement.get("expectations"):
            lines.append("• 2차 파급: 높은 체감물가가 기대인플레이션·임금 요구·기업 가격설정으로 이어져 물가가 고착되는지가 핵심입니다.")
        if statement.get("gas"):
            lines.append("• 가스 가격과 재고도 별도 위험요인으로 봅니다. 유가만 보면 에너지 충격을 과소평가할 수 있습니다.")
        lines.append("• 구분: 식료품 상승 자체를 곧바로 ‘2차 파급’으로 부르지 않고, 임금·기대·가격설정까지 번질 때 2차 파급으로 판단합니다.")
    else:
        lines += ["", "■ 총재 발언", "• 기자회견 공식 원문이 아직 확인되지 않았습니다. 공개되면 별도 업데이트합니다."]

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
    return f"ECB {action} {fmt_rate(dep)}", "\n".join(lines), detail


def build_statement_update(item: dict, statement: dict) -> tuple[str, str, dict]:
    lines = [
        "🔔 [ECB 총재 발언 업데이트] 라가르드 — 에너지 충격의 장기화·파급 경로 점검",
        "",
        "🇪🇺 ECB는?",
        "유럽중앙은행(European Central Bank). 유로화를 사용하는 국가들의 통화정책을 결정하며 미국의 Fed에 해당합니다.",
        "",
        "■ 핵심 발언·판단",
    ]
    if statement.get("duration") and statement.get("energy"):
        lines.append("• 에너지 충격이 예상보다 길어질수록 더 넓은 물가 항목으로 번질 가능성이 커집니다.")
    if statement.get("food"):
        lines.append("• 식료품: 에너지 비용 상승이 비료·운송·생산비를 통해 식료품 가격에 전달되는 간접 파급을 봅니다.")
    if statement.get("gas"):
        lines.append("• 가스 가격·재고도 핵심 위험요인입니다. 유가만으로 에너지 충격을 판단하지 않습니다.")
    if statement.get("second_round") or statement.get("wages") or statement.get("expectations"):
        lines.append("• 2차 파급: 높은 물가가 기대인플레이션·임금·기업 가격설정으로 고착되는지 확인해야 합니다.")
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
    return "ECB 라가르드 발언 업데이트", "\n".join(lines), {
        "kind": "statement",
        "date": item.get("date"),
        "statement_url": item.get("link"),
        "statement_signals": {k: v for k, v in statement.items() if k != "plain"},
    }


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize()

    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, TITLE, DETAIL, CONFIRMED):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    now = dt.datetime.now(KST)
    state = load_json(STATE, {})
    try:
        items = rss_items(fetch(RSS))
    except Exception as exc:
        STATUS.write_text(
            f"# ECB 정책 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 확인 불가 — RSS {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        return 2

    decision_item = latest_matching(items, r"^Monetary policy decisions$")
    statement_item = latest_matching(items, r"Monetary policy statement")
    if not decision_item:
        STATUS.write_text(
            f"# ECB 정책 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 확인 불가 — 최신 통화정책 결정 항목 미탐지\n",
            encoding="utf-8",
        )
        return 2

    current_decision_date = decision_item.get("date") or ""
    current_statement_date = (statement_item or {}).get("date") or ""
    new_decision = bool(current_decision_date and current_decision_date != state.get("last_decision_date"))
    new_statement = bool(current_statement_date and current_statement_date != state.get("last_statement_date"))

    next_state = dict(state)
    next_state["last_checked_kst"] = now.isoformat(timespec="seconds")
    alert_tuple = None

    decision = None
    statement = None
    if new_decision:
        decision = parse_decision(fetch(decision_item["link"]))
        if statement_item and current_statement_date == current_decision_date:
            try:
                statement = parse_statement(fetch(statement_item["link"]))
            except Exception:
                statement = None
        alert_tuple = build_main_alert(decision_item, decision, statement_item if current_statement_date == current_decision_date else None, statement)
        next_state["last_decision_date"] = current_decision_date
        next_state["last_decision_url"] = decision_item.get("link")
        if statement_item and current_statement_date == current_decision_date and statement is not None:
            next_state["last_statement_date"] = current_statement_date
            next_state["last_statement_url"] = statement_item.get("link")
    elif new_statement:
        statement = parse_statement(fetch(statement_item["link"]))
        alert_tuple = build_statement_update(statement_item, statement)
        next_state["last_statement_date"] = current_statement_date
        next_state["last_statement_url"] = statement_item.get("link")

    PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# ECB 정책 감시\n\n"
        f"- 조회: {now.isoformat(timespec='seconds')}\n"
        f"- 최신 통화정책 결정일: {current_decision_date or '확인 불가'}\n"
        f"- 최신 기자회견일: {current_statement_date or '확인 불가'}\n"
        f"- 신규 알림: {'예' if alert_tuple else '아니오'}\n",
        encoding="utf-8",
    )

    if alert_tuple:
        title, body, detail = alert_tuple
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body.strip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
