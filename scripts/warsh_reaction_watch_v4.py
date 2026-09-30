#!/usr/bin/env python3
import html
import json
import re
import sys
from datetime import datetime, timezone

import warsh_reaction_watch_v3 as prev

base = prev.base
_previous_message_for = base.message_for
TRANSLATION_MARKER = "fomc_korean_translation_v1"
PCE_TRANSLATION_MARKER = "pce_korean_translation_v1"


EXACT_TRANSLATIONS = {
    "The Committee decided to raise the target range for the federal funds rate by 1/4 percentage point to 3-3/4 to 4 percent, in support of the Federal Reserve's dual mandate.":
        "위원회는 연방준비제도의 이중 책무 달성을 뒷받침하기 위해 연방기금금리 목표범위를 0.25%포인트 인상해 3.75~4.00%로 결정했습니다.",
    "Economic activity is expanding at a solid pace.":
        "경제활동은 견조한 속도로 확대되고 있습니다.",
    "Economic activity has continued to expand at a solid pace.":
        "경제활동은 견조한 속도로 계속 확대되고 있습니다.",
    "Economic activity has continued to expand at a moderate pace.":
        "경제활동은 완만한 속도로 계속 확대되고 있습니다.",
    "Job gains have kept pace with the workforce, and the unemployment rate has changed little.":
        "고용 증가는 노동력 증가와 보조를 맞추고 있으며, 실업률은 거의 변하지 않았습니다.",
    "Inflation remains elevated.":
        "물가는 여전히 높은 수준입니다.",
    "Inflation remains somewhat elevated.":
        "물가는 여전히 다소 높은 수준입니다.",
    "Inflation has moved up and remains somewhat elevated.":
        "물가는 상승했으며 여전히 다소 높은 수준입니다.",
    "The Committee is strongly committed to returning inflation to its 2 percent objective.":
        "위원회는 물가상승률을 2% 목표로 되돌리는 데 강하게 전념하고 있습니다.",
    "The Committee is strongly committed to supporting maximum employment and returning inflation to its 2 percent objective.":
        "위원회는 최대고용을 뒷받침하고 물가상승률을 2% 목표로 되돌리는 데 강하게 전념하고 있습니다.",
    "The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run.":
        "위원회는 장기적으로 최대고용과 2% 물가상승률 달성을 추구합니다.",
}


def _normalize_sentence(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _fractional_number(value):
    value = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    m = re.fullmatch(r"(\d+)-(\d+)/(\d+)", value)
    if m:
        return float(m.group(1)) + float(m.group(2)) / float(m.group(3))
    m = re.fullmatch(r"(\d+)/(\d+)", value)
    if m:
        return float(m.group(1)) / float(m.group(2))
    return None


def _fmt_rate(value):
    num = _fractional_number(value)
    if num is None:
        return str(value)
    return f"{num:.2f}"


def _translate_rate_decision(sentence):
    s = _normalize_sentence(sentence)
    m = re.search(
        r"The Committee decided to (raise|lower) the target range for the federal funds rate by ([\d./-]+) percentage point(?:s)? to ([\d./-]+) to ([\d./-]+) percent",
        s,
        re.I,
    )
    if m:
        direction = "인상" if m.group(1).lower() == "raise" else "인하"
        move = _fractional_number(m.group(2))
        move_text = f"{move:.2f}%포인트" if move is not None else f"{m.group(2)}%포인트"
        lo, hi = _fmt_rate(m.group(3)), _fmt_rate(m.group(4))
        tail = " 연방준비제도의 이중 책무 달성을 뒷받침하기 위한 결정입니다." if "dual mandate" in s.lower() else ""
        return f"위원회는 연방기금금리 목표범위를 {move_text} {direction}해 {lo}~{hi}%로 결정했습니다.{tail}".strip()

    m = re.search(
        r"The Committee decided to maintain the target range for the federal funds rate at ([\d./-]+) to ([\d./-]+) percent",
        s,
        re.I,
    )
    if m:
        return f"위원회는 연방기금금리 목표범위를 {_fmt_rate(m.group(1))}~{_fmt_rate(m.group(2))}%로 유지하기로 결정했습니다."
    return None


def _translate_fomc_sentence(sentence):
    s = _normalize_sentence(sentence)
    if not s:
        return ""
    if s in EXACT_TRANSLATIONS:
        return EXACT_TRANSLATIONS[s]

    rate = _translate_rate_decision(s)
    if rate:
        return rate

    low = s.lower()
    if "economic activity" in low:
        if "solid pace" in low:
            return "경제활동은 견조한 속도로 확대되고 있습니다."
        if "moderate pace" in low:
            return "경제활동은 완만한 속도로 확대되고 있습니다."
        if "expanded" in low or "expanding" in low:
            return "경제활동은 확대되고 있습니다."
        return "경제활동에 관한 연준의 평가가 새로 제시됐습니다."

    if "job gains" in low or "unemployment rate" in low or "labor market" in low:
        if "kept pace with the workforce" in low and "changed little" in low:
            return "고용 증가는 노동력 증가와 보조를 맞추고 있으며, 실업률은 거의 변하지 않았습니다."
        if "job gains have slowed" in low and "unemployment rate" in low:
            return "고용 증가는 둔화했으며, 연준은 실업률 변화와 노동시장 여건을 함께 주시하고 있습니다."
        if "labor market conditions remain solid" in low:
            return "노동시장 여건은 여전히 견조합니다."
        return "연준은 고용 증가와 실업률 등 노동시장 여건을 계속 점검하고 있습니다."

    if "inflation" in low:
        if "remains elevated" in low:
            return "물가는 여전히 높은 수준입니다."
        if "remains somewhat elevated" in low:
            return "물가는 여전히 다소 높은 수준입니다."
        if "2 percent" in low and ("return" in low or "objective" in low or "goal" in low):
            return "위원회는 물가상승률을 2% 목표로 되돌리는 데 전념하고 있습니다."
        return "연준은 물가가 여전히 목표와 일치하는 경로에 있는지 계속 점검하고 있습니다."

    if "uncertainty" in low and "geopolitical" in low:
        return "지정학적 상황 등의 영향으로 불확실성은 여전히 높은 수준입니다."
    if "domestic spending" in low and "resilient" in low:
        return "미국 내 지출은 회복력을 유지하고 있습니다."
    if "productivity growth" in low and "strong" in low:
        return "생산성 증가는 강한 흐름을 보이고 있습니다."
    if "capital investment" in low and "robust" in low:
        return "설비투자는 견조합니다."

    # 새 문구가 나와도 원문 영어 문장이 Telegram 본문으로 그대로 유출되지 않게 막는다.
    return "연준 성명에 기존 자동 번역 규칙과 다른 새 문구가 포함됐습니다. 해당 문장은 원문 링크에서 확인하고 번역 규칙을 보강해야 합니다."


def _date_ko(value):
    s = _normalize_sentence(value)
    for fmt in ("%B %d, %Y", "%A, %B %d, %Y"):
        try:
            d = datetime.strptime(s, fmt)
            return f"{d.year}년 {d.month}월 {d.day}일"
        except ValueError:
            pass
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", s)
    if m:
        return f"{int(m.group(1))}년 {int(m.group(2))}월 {int(m.group(3))}일"
    return s


def _link(label, url):
    return f'<a href="{html.escape(str(url), quote=True)}">{html.escape(label, quote=False)}</a>'


def _month_ko(name):
    try:
        return datetime.strptime(str(name), "%B").month
    except Exception:
        return None


def _pce_values_from_summary(snap):
    out = {
        "period_month": None,
        "dpi_billion": None, "dpi_pct": None,
        "pce_spend_billion": None, "pce_spend_pct": None,
        "headline_mom": None, "core_mom": None,
        "headline_yoy": None, "core_yoy": None,
    }
    lines = [_normalize_sentence(x) for x in (snap.get("summary") or [])]
    for line in lines:
        m = re.search(
            r"Disposable personal income.*?increased \$([\d,.]+) billion \(([\d.]+) percent\).*?"
            r"personal consumption expenditures \(PCE\) increased \$([\d,.]+) billion \(([\d.]+) percent\)",
            line, re.I,
        )
        if m:
            out["dpi_billion"] = float(m.group(1).replace(",", ""))
            out["dpi_pct"] = float(m.group(2))
            out["pce_spend_billion"] = float(m.group(3).replace(",", ""))
            out["pce_spend_pct"] = float(m.group(4))

        m = re.search(
            r"From the preceding month, the PCE price index for\s+([A-Za-z]+)\s+(?:increased|decreased)\s+([\d.]+)\s+percent",
            line, re.I,
        )
        if m:
            out["period_month"] = m.group(1)
            val = float(m.group(2))
            out["headline_mom"] = -val if "decreased" in line.lower() else val
            continue

        m = re.search(
            r"From the same month one year ago, the PCE price index for\s+([A-Za-z]+)\s+(?:increased|decreased)\s+([\d.]+)\s+percent",
            line, re.I,
        )
        if m:
            out["period_month"] = out["period_month"] or m.group(1)
            val = float(m.group(2))
            out["headline_yoy"] = -val if "decreased" in line.lower() else val
            continue

        m = re.search(
            r"Excluding food and energy, the PCE price index\s+(?:increased|decreased)\s+([\d.]+)\s+percent from one year ago",
            line, re.I,
        )
        if m:
            val = float(m.group(1))
            out["core_yoy"] = -val if "decreased" in line.lower() else val
            continue

        m = re.search(
            r"Excluding food and energy, the PCE price index(?: also)?\s+(?:increased|decreased)\s+([\d.]+)\s+percent",
            line, re.I,
        )
        if m and out["core_mom"] is None:
            val = float(m.group(1))
            out["core_mom"] = -val if "decreased" in line.lower() else val
    return out


def _fmt_signed_pct(value):
    return "확인 불가" if value is None else f"{value:+.1f}%"


def _yoy_direction(cur, prev_value):
    if cur is None or prev_value is None:
        return ""
    delta = float(cur) - float(prev_value)
    if abs(delta) < 0.05:
        return f" · 전월과 비슷"
    return f" · 상승률 {'확대' if delta > 0 else '둔화'}"


def pce_message_ko(snap):
    v = _pce_values_from_summary(snap)

    # 이 watcher가 PCE 추세 watcher보다 먼저 실행되므로, 여기의 저장값은 직전월 기준선입니다.
    prev_state = {}
    try:
        prev_state = json.loads(prev.PCE_TREND_STATE.read_text(encoding="utf-8"))
    except Exception:
        prev_state = {}

    release_year = None
    m = re.search(r"(20\d{2})", str(snap.get("key") or ""))
    if m:
        release_year = int(m.group(1))
    if release_year is None:
        m = re.search(r"/(20\d{2})/", str(snap.get("url") or ""))
        if m:
            release_year = int(m.group(1))

    month_num = _month_ko(v.get("period_month"))
    period_text = f"{release_year}년 {month_num}월" if release_year and month_num else "최신 기준월"
    release_text = _date_ko(snap.get("key", ""))

    headline_yoy_prev = prev_state.get("headline_yoy")
    core_yoy_prev = prev_state.get("core_yoy")

    lines = [
        "[Warsh 반응함수 변화 감지] BEA PCE(개인소비지출 물가지수)",
        f"기준: {period_text} · 발표 {release_text}",
        "",
        "<b>한눈에 보기</b>",
        f"• <b>종합 PCE</b> | 전월 대비 {_fmt_signed_pct(v.get('headline_mom'))}(상승) · 전년 대비 {_fmt_signed_pct(v.get('headline_yoy'))}"
        f"{_yoy_direction(v.get('headline_yoy'), headline_yoy_prev)}",
        f"• <b>근원 PCE</b> | 전월 대비 {_fmt_signed_pct(v.get('core_mom'))}(상승) · 전년 대비 {_fmt_signed_pct(v.get('core_yoy'))}"
        f"{_yoy_direction(v.get('core_yoy'), core_yoy_prev)}",
    ]

    if v.get("dpi_pct") is not None or v.get("pce_spend_pct") is not None:
        dpi = "확인 불가" if v.get("dpi_pct") is None else f"+{v['dpi_pct']:.1f}%"
        spend = "확인 불가" if v.get("pce_spend_pct") is None else f"+{v['pce_spend_pct']:.1f}%"
        lines.append(f"• <b>소득·소비</b> | 가처분개인소득 {dpi} · 명목 개인소비지출 {spend}")

    lines += [
        "",
        "<b>워시 기준</b>",
        "• 한 달 수치 하나보다 3개월·6개월 물가 추세가 2% 목표로 충분히 빠르게 내려가는지를 별도로 확인합니다.",
        "• 이 알림은 BEA 월간 발표의 현재 수치를 번역한 것이며, 3개월·6개월 연율 판정은 뒤의 PCE 추세 감시가 담당합니다.",
        "",
        _link("BEA 원문", snap.get("url", "")),
    ]
    return "\n".join(lines)


def fomc_message_ko(snap):
    translated = []
    for raw in (snap.get("summary") or [])[:7]:
        line = _translate_fomc_sentence(raw)
        if line and line not in translated:
            translated.append(line)

    if not translated:
        translated.append("연방공개시장위원회가 새로운 통화정책 결정을 발표했습니다. 세부 내용은 공식 원문에서 확인할 수 있습니다.")

    lines = [
        "[Warsh 반응함수 변화 감지] FOMC(연방공개시장위원회) 결정",
        f"기준: {_date_ko(snap.get('key', ''))}",
        "",
    ]
    lines.extend(f"• {html.escape(line, quote=False)}" for line in translated)
    lines += [
        "",
        _link("원천", snap.get("url", "")),
        "",
        "판정: 완전고용 전제, 물가 2%로의 충분한 둔화, 추가긴축 가능성이 강화·약화되는지 확인",
    ]
    return "\n".join(lines)


def message_for_v4(name, snap):
    if name == "fomc":
        return fomc_message_ko(snap)
    if name == "pce":
        return pce_message_ko(snap)
    return _previous_message_for(name, snap)


def _latest_pce_snapshot():
    schedule_html, _ = base.fetch(base.URLS["bea_schedule"])
    url = base.find_latest_pce(schedule_html)
    if not url:
        raise RuntimeError("최신 BEA PCE 발표 링크를 찾지 못했습니다.")
    return base.html_snapshot(url, base.KEYWORDS["pce"])


def _send_pce_translation_migration_once():
    state = base.load_state()
    if state.get(PCE_TRANSLATION_MARKER):
        return False

    snap = _latest_pce_snapshot()
    message_id = base.telegram_send(pce_message_ko(snap))
    state[PCE_TRANSLATION_MARKER] = {
        "sent": True,
        "key": snap.get("key"),
        "url": snap.get("url"),
        "message_id": message_id,
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    base.save_state(state)
    print(json.dumps({
        "pce_korean_translation_correction_sent": True,
        "message_id": message_id,
        "key": snap.get("key"),
        "url": snap.get("url"),
    }, ensure_ascii=False))
    return True


def _latest_fomc_snapshot():
    calendar_html, _ = base.fetch(base.URLS["fomc_calendar"])
    url = base.find_latest_fomc_statement(calendar_html)
    if not url:
        raise RuntimeError("최신 FOMC 성명 링크를 찾지 못했습니다.")
    return base.html_snapshot(url, base.KEYWORDS["fomc"])


def _send_translation_migration_once():
    state = base.load_state()
    if state.get(TRANSLATION_MARKER):
        return False

    snap = _latest_fomc_snapshot()
    base.telegram_send(fomc_message_ko(snap))
    state[TRANSLATION_MARKER] = {
        "sent": True,
        "key": snap.get("key"),
        "url": snap.get("url"),
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    base.save_state(state)
    print(json.dumps({"fomc_korean_translation_correction_sent": True, "key": snap.get("key"), "url": snap.get("url")}, ensure_ascii=False))
    return True


base.message_for = message_for_v4
base.telegram_send = prev.prev.telegram_send_html


if __name__ == "__main__":
    try:
        _send_translation_migration_once()
        _send_pce_translation_migration_once()
        raise SystemExit(base.main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
