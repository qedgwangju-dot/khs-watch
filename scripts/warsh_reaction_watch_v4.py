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
    return _previous_message_for(name, snap)


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
        raise SystemExit(base.main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
