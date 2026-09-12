#!/usr/bin/env python3
import calendar
import html as html_lib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import warsh_reaction_watch_v2 as prev

base = prev.base
PCE_TREND_STATE = Path("data/warsh_pce_trend_watch_state.json")
FED_WARSH_URL = "https://www.federalreserve.gov/newsevents/speech/warsh20260828a.htm"
BEA_PCE_DATA_URL = "https://www.bea.gov/data/personal-consumption-expenditures-price-index"
BLS_RELEASE_SCHEDULE_URL = "https://www.bls.gov/schedule/"
BEA_RELEASE_SCHEDULE_URL = "https://www.bea.gov/news/schedule"


def _safe(value):
    return html_lib.escape(str(value), quote=False)


def _link(label, url):
    return f'<a href="{html_lib.escape(url, quote=True)}">{html_lib.escape(label, quote=False)}</a>'


def _signed(direction, value):
    value = float(value)
    return -value if direction.lower().startswith("decreas") else value


def _latest_unemployment_path():
    now = datetime.now(timezone.utc)
    data = base.post_json(base.URLS["bls_api"], {
        "seriesid": ["LNS14000000"],
        "startyear": str(now.year - 1),
        "endyear": str(now.year),
    })
    if data.get("status") != "REQUEST_SUCCEEDED":
        return []
    series = data.get("Results", {}).get("series", [])
    if not series:
        return []
    values = base.series_values(series[0])
    periods = sorted(values)[-3:]
    return [(p, values[p]) for p in periods]


def _parse_date_label(value):
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _next_bls_release(kind):
    try:
        url = base.URLS["employment"] if kind == "employment" else base.URLS["cpi"]
        raw, _ = base.fetch(url)
        text = base.clean_text(raw)
        if kind == "employment":
            patterns = [
                r"Employment Situation for [A-Za-z]+ \d{4} is scheduled to be published on ([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})",
                r"Employment Situation for [A-Za-z]+ \d{4} is scheduled to be released on ([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})",
            ]
        else:
            patterns = [
                r"Consumer Price Index(?: news release)? for [A-Za-z]+ \d{4} is scheduled to be published on ([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})",
                r"Consumer Price Index(?: news release)? for [A-Za-z]+ \d{4} is scheduled to be released on ([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})",
            ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                return _parse_date_label(m.group(1))
    except Exception:
        pass
    return None


def _next_fomc_meeting():
    try:
        raw, _ = base.fetch(base.URLS["fomc_calendar"])
        text = base.clean_text(raw)
        today = datetime.now(timezone.utc).date()
        month_re = "|".join(calendar.month_name[1:])
        candidates = []
        for year in (today.year, today.year + 1):
            start = text.find(f"{year} FOMC Meetings")
            if start < 0:
                continue
            end = text.find(f"{year + 1} FOMC Meetings", start + 1)
            section = text[start:end if end >= 0 else None]
            for m in re.finditer(
                rf"\b({month_re})\s+(\d{{1,2}})(?:-(\d{{1,2}}))?\*?",
                section,
                re.I,
            ):
                month = list(calendar.month_name).index(m.group(1).capitalize())
                day = int(m.group(3) or m.group(2))
                try:
                    d = datetime(year, month, day).date()
                except ValueError:
                    continue
                if d >= today:
                    candidates.append(d)
        return min(candidates) if candidates else None
    except Exception:
        return None


def _date_kr(value):
    return f"{value.month}월 {value.day}일" if value else None


def _next_check_lines(pce):
    checks = []
    fomc = _next_fomc_meeting()
    pce_next = pce.get("next_release")
    employment = _next_bls_release("employment")
    cpi = _next_bls_release("cpi")

    if fomc:
        checks.append((fomc, "FOMC 결정·기자회견"))
    if pce_next:
        checks.append((pce_next, "PCE"))
    if employment:
        checks.append((employment, "BLS 고용보고서"))
    if cpi:
        checks.append((cpi, "CPI"))

    if not checks:
        return ["• 공식 일정 자동 확인 실패 — BLS·BEA·FOMC 일정 원문 재조회 필요"]

    checks.sort(key=lambda x: x[0])
    return [f"• {_date_kr(d)}(미국 현지일): {label}" for d, label in checks[:4]]


def _latest_pce_official():
    out = {
        "url": BEA_PCE_DATA_URL,
        "period": None,
        "headline_mom": None,
        "headline_yoy": None,
        "core_mom": None,
        "core_yoy": None,
        "next_release": None,
    }
    try:
        schedule_html, _ = base.fetch(base.URLS["bea_schedule"])
        release_url = base.find_latest_pce(schedule_html)
        if not release_url:
            return out
        raw, final = base.fetch(release_url)
        text = base.clean_text(raw)
        out["url"] = final

        m = re.search(
            r"From the preceding month, the PCE price index for\s+([A-Za-z]+)\s+(increased|decreased)\s+([\d.]+)\s+percent",
            text,
            re.I,
        )
        if m:
            out["period"] = m.group(1)
            out["headline_mom"] = _signed(m.group(2), m.group(3))

        m = re.search(
            r"Excluding food and energy, the PCE price index(?: also)?\s+(increased|decreased)\s+([\d.]+)\s+percent",
            text,
            re.I,
        )
        if m:
            out["core_mom"] = _signed(m.group(1), m.group(2))

        m = re.search(
            r"From the same month one year ago, the PCE price index for\s+[A-Za-z]+\s+(increased|decreased)\s+([\d.]+)\s+percent",
            text,
            re.I,
        )
        if m:
            out["headline_yoy"] = _signed(m.group(1), m.group(2))

        m = re.search(
            r"Excluding food and energy, the PCE price index\s+(increased|decreased)\s+([\d.]+)\s+percent from one year ago",
            text,
            re.I,
        )
        if m:
            out["core_yoy"] = _signed(m.group(1), m.group(2))

        m = re.search(r"Next release:\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
        if m:
            out["next_release"] = _parse_date_label(m.group(1))
    except Exception:
        pass
    return out


def _load_pce_trend():
    try:
        data = json.loads(PCE_TREND_STATE.read_text(encoding="utf-8"))
        return {
            "headline_3m_ann": data.get("headline_3m_ann"),
            "headline_6m_ann": data.get("headline_6m_ann"),
            "core_3m_ann": data.get("core_3m_ann"),
            "core_6m_ann": data.get("core_6m_ann"),
            "regime": data.get("regime"),
        }
    except Exception:
        return {}


def _parse_cpi_snapshot(snap):
    out = {"headline_mom": None, "headline_yoy": None, "core_mom": None, "core_yoy": None, "period": snap.get("key")}
    for line in snap.get("summary", []):
        m = re.search(r"종합 CPI\s+([+-]?[\d.]+)% 전월 대비 / ([+-]?[\d.]+)% 전년 대비", line)
        if m:
            out["headline_mom"] = float(m.group(1))
            out["headline_yoy"] = float(m.group(2))
        m = re.search(r"근원 CPI\s+([+-]?[\d.]+)% 전월 대비 / ([+-]?[\d.]+)% 전년 대비", line)
        if m:
            out["core_mom"] = float(m.group(1))
            out["core_yoy"] = float(m.group(2))
    return out


def _employment_premise(details, ur_path):
    payroll = details.get("payroll_change")
    avg3 = details.get("three_month_avg")
    if len(ur_path) >= 3:
        ur_first = ur_path[0][1]
        ur_last = ur_path[-1][1]
        ur_delta = ur_last - ur_first
    else:
        ur_delta = details.get("unemployment_change")

    if payroll is not None and avg3 is not None and ur_delta is not None:
        if payroll >= 100 and avg3 >= 50 and ur_delta <= 0:
            return "강화"
        if (payroll < 0 and avg3 < 50) or (ur_delta >= 0.2 and avg3 < 50):
            return "약화"
        return "유지"
    return "유지"


def _inflation_path(cpi, pce, trend):
    if pce.get("core_yoy") is None and not trend:
        return "고용자료만으로 판정 유보"

    core_cpi_mom = cpi.get("core_mom")
    core_cpi_yoy = cpi.get("core_yoy")
    core_pce_mom = pce.get("core_mom")
    core_pce_yoy = pce.get("core_yoy")
    pce_core_3m = trend.get("core_3m_ann")
    pce_core_6m = trend.get("core_6m_ann")
    pce_head_6m = trend.get("headline_6m_ann")

    strong_to_2 = (
        core_cpi_yoy is not None and core_cpi_yoy <= 2.5 and
        core_pce_yoy is not None and core_pce_yoy <= 2.5 and
        core_cpi_mom is not None and core_cpi_mom <= 0.2 and
        core_pce_mom is not None and core_pce_mom <= 0.2 and
        (pce_core_6m is None or pce_core_6m <= 2.5)
    )
    worsening = (
        (core_cpi_mom is not None and core_cpi_mom >= 0.3 and core_pce_mom is not None and core_pce_mom >= 0.3) or
        (pce_core_3m is not None and pce_core_3m >= 3.5) or
        (pce_core_6m is not None and pce_core_6m >= 3.5 and pce_head_6m is not None and pce_head_6m >= 3.5)
    )
    if strong_to_2:
        return "강화"
    if worsening:
        return "약화"
    return "유지"


def _tightening_verdict(emp, inflation):
    if inflation == "고용자료만으로 판정 유보":
        return "중립"
    if emp == "강화" and inflation in ("유지", "약화"):
        return "강화"
    if emp == "약화" and inflation == "강화":
        return "약화"
    if emp == "약화" and inflation == "유지":
        return "중립"
    if inflation == "약화" and emp != "약화":
        return "강화"
    if inflation == "강화" and emp != "강화":
        return "약화"
    return "중립"


def _period_line(ur_path):
    if not ur_path:
        return "확인 불가"
    return " → ".join(f"{p[1]}월 {v:.1f}%" for p, v in ur_path)


def _fmt_num(value, decimals=1, suffix="%"):
    if value is None:
        return "확인 불가"
    return f"{value:.{decimals}f}{suffix}"


def _employment_message(snap, cpi_snap):
    d = snap.get("details", {})
    ur_path = _latest_unemployment_path()
    pce = _latest_pce_official()
    trend = _load_pce_trend()
    cpi = _parse_cpi_snapshot(cpi_snap or {})

    emp_verdict = _employment_premise(d, ur_path)
    inflation_verdict = _inflation_path(cpi, pce, trend)
    tightening = _tightening_verdict(emp_verdict, inflation_verdict)

    lines = [
        f"[Warsh 반응함수 변화 감지] BLS 고용 — {_safe(snap.get('key', ''))}",
        "",
        "<b>핵심 판정</b>",
        f"• <b>완전고용 전제</b>: {emp_verdict}",
        f"• <b>물가 2% 경로</b>: {inflation_verdict}",
        f"• <b>추가긴축 가능성</b>: {tightening} <i>(종합 해석)</i>",
        "",
        "<b>왜 이렇게 봤나</b>",
        f"• <b>실업률 3개월</b> | {_safe(_period_line(ur_path))}",
    ]

    payroll = d.get("payroll_change")
    avg3 = d.get("three_month_avg")
    payroll_bits = []
    if payroll is not None:
        payroll_bits.append(f"당월 {payroll:+.0f}천명")
    if avg3 is not None:
        payroll_bits.append(f"최근 3개월 평균 {avg3:+.0f}천명")
    if d.get("prior_12m_avg") is not None:
        payroll_bits.append(f"직전 12개월 월평균 {d['prior_12m_avg']:+.0f}천명")
    lines.append(f"• <b>비농업 고용</b> | {_safe(' · '.join(payroll_bits))}")

    if d.get("revision_text"):
        lines.append(f"• <b>이전 2개월 수정</b> | {_safe(d['revision_text'])}")

    household_bits = []
    if d.get("participation_rate") is not None:
        household_bits.append(f"참가율 {d['participation_rate']:.1f}% ({d.get('participation_change', 0):+.1f}%p)")
    if d.get("employment_population_ratio") is not None:
        household_bits.append(f"고용률 {d['employment_population_ratio']:.1f}% ({d.get('employment_population_change', 0):+.1f}%p)")
    if household_bits:
        lines.append(f"• <b>보조 확인</b> | {_safe(' · '.join(household_bits))}")

    cpi_bits = []
    if cpi.get("headline_mom") is not None:
        cpi_bits.append(f"종합 {cpi['headline_mom']:+.1f}% 전월 / {cpi['headline_yoy']:.1f}% 전년")
    if cpi.get("core_mom") is not None:
        cpi_bits.append(f"근원 {cpi['core_mom']:+.1f}% 전월 / {cpi['core_yoy']:.1f}% 전년")
    lines.append(f"• <b>최신 CPI</b> | {_safe(' · '.join(cpi_bits) if cpi_bits else '확인 불가')}")

    pce_bits = []
    if pce.get("headline_mom") is not None:
        pce_bits.append(f"종합 {pce['headline_mom']:+.1f}% 전월 / {pce['headline_yoy']:.1f}% 전년")
    if pce.get("core_mom") is not None:
        pce_bits.append(f"근원 {pce['core_mom']:+.1f}% 전월 / {pce['core_yoy']:.1f}% 전년")
    lines.append(f"• <b>최신 PCE</b> | {_safe(' · '.join(pce_bits) if pce_bits else '확인 불가')}")

    if trend.get("core_3m_ann") is not None and trend.get("core_6m_ann") is not None:
        lines.append(
            f"• <b>근원 PCE 추세</b> | 3개월 연율 {trend['core_3m_ann']:.2f}% · 6개월 연율 {trend['core_6m_ann']:.2f}%"
        )

    lines += [
        "",
        "<b>해석</b>",
        "• 고용은 한 달 수치만 보지 않고 실업률 3개월 방향, 당월 고용, 이전 2개월 수정, 최근 3개월 평균을 함께 봅니다.",
        "• 물가 판단은 고용보고서에서 억지로 하지 않고 BLS CPI와 BEA PCE를 별도로 확인합니다.",
    ]

    if emp_verdict == "강화":
        evidence = []
        if ur_path:
            evidence.append(f"실업률 {_period_line(ur_path)}")
        if payroll is not None:
            evidence.append(f"당월 고용 {payroll:+.0f}천명")
        if avg3 is not None:
            evidence.append(f"3개월 평균 {avg3:+.0f}천명")
        lines.append(f"• <b>완전고용 전제</b>는 강화됐습니다. {_safe(' · '.join(evidence))}")
    elif emp_verdict == "약화":
        lines.append("• <b>완전고용 전제</b>는 약화됐습니다. 고용·실업률의 여러 달 흐름이 함께 나빠졌습니다.")
    else:
        lines.append("• <b>완전고용 전제</b>는 대체로 유지입니다. 한 달 변동만으로 워시의 기존 판단이 바뀌었다고 보기 어렵습니다.")

    inflation_evidence = []
    if cpi.get("headline_yoy") is not None:
        inflation_evidence.append(f"종합 CPI {cpi['headline_yoy']:.1f}%")
    if cpi.get("core_yoy") is not None:
        inflation_evidence.append(f"근원 CPI {cpi['core_yoy']:.1f}%")
    if pce.get("headline_yoy") is not None:
        inflation_evidence.append(f"종합 PCE {pce['headline_yoy']:.1f}%")
    if pce.get("core_yoy") is not None:
        inflation_evidence.append(f"근원 PCE {pce['core_yoy']:.1f}%")
    inflation_now = " · ".join(inflation_evidence)

    if inflation_verdict == "유지":
        suffix = f" 현재 {_safe(inflation_now)}로, " if inflation_now else " "
        lines.append(f"• <b>물가 2% 경로</b>는 유지입니다.{suffix}2% 목표로 충분히 수렴했다고 보기에는 아직 근거가 부족합니다.")
    elif inflation_verdict == "강화":
        suffix = f" 현재 {_safe(inflation_now)}. " if inflation_now else " "
        lines.append(f"• <b>물가 2% 경로</b>는 강화됐습니다.{suffix}CPI·PCE의 근원과 단기 추세가 함께 2% 쪽으로 내려오는 신호가 확인됩니다.")
    elif inflation_verdict == "약화":
        suffix = f" 현재 {_safe(inflation_now)}. " if inflation_now else " "
        lines.append(f"• <b>물가 2% 경로</b>는 약화됐습니다.{suffix}단기 물가 추세가 다시 높아져 워시의 물가 우선 논리를 강화합니다.")
    else:
        lines.append("• <b>물가 2% 경로</b>는 고용자료만으로 판정하지 않습니다. CPI·PCE 공식자료가 필요합니다.")

    if tightening == "강화":
        lines.append("• <b>추가긴축 가능성</b>은 강화로 해석합니다. 고용은 버티고 있는데 물가가 아직 2%로 충분히 내려오지 않았기 때문입니다. 다만 이는 현재 데이터의 종합 해석이지 워시가 특정 회의 인상을 약속했다는 뜻은 아닙니다.")
    elif tightening == "약화":
        lines.append("• <b>추가긴축 가능성</b>은 약화로 해석합니다. 고용 또는 물가 쪽에서 워시가 추가 대응을 서두를 이유가 줄었습니다.")
    else:
        lines.append("• <b>추가긴축 가능성</b>은 중립입니다. 고용과 물가 신호가 엇갈려 한쪽으로 단정하기 어렵습니다.")

    lines += [
        "",
        "<b>워시 직접 기준과 해석 구분</b>",
        "• 워시 직접 발언: 8월 28일 당시 노동시장은 완전고용에 부합하고, PCE 2%는 확고하고 고정된 목표라고 설명했습니다.",
        "• 위 ‘강화·유지·약화’와 ‘추가긴축 가능성’은 최신 공식지표를 그 기준에 대입한 종합 해석입니다.",
        "",
        "<b>다음 확인</b>",
    ]
    lines += _next_check_lines(pce)
    lines += [
        "",
        "<b>원천</b>",
        f"{_link('BLS 고용보고서', snap['url'])} · {_link('BLS CPI', base.URLS['cpi'])}",
        f"{_link('BEA PCE', pce.get('url') or BEA_PCE_DATA_URL)} · {_link('Federal Reserve Warsh 8/28 연설', FED_WARSH_URL)}",
        f"{_link('BLS 발표일정', BLS_RELEASE_SCHEDULE_URL)} · {_link('BEA 발표일정', BEA_RELEASE_SCHEDULE_URL)} · {_link('FOMC 회의일정', base.URLS['fomc_calendar'])}",
    ]
    return "\n".join(lines)


def tri_axis_message_for(name, snap):
    if name == "employment" and snap.get("details"):
        try:
            all_snaps = enhanced_bls_snapshots_cache[0] if enhanced_bls_snapshots_cache else None
            cpi_snap = all_snaps.get("cpi") if all_snaps else None
        except Exception:
            cpi_snap = None
        return _employment_message(snap, cpi_snap)
    return prev.enhanced_message_for(name, snap)


enhanced_bls_snapshots_cache = []
_original_enhanced_bls_snapshots = prev.enhanced_bls_snapshots


def enhanced_bls_snapshots_v3():
    snaps = _original_enhanced_bls_snapshots()
    enhanced_bls_snapshots_cache[:] = [snaps]
    return snaps


base.bls_snapshots = enhanced_bls_snapshots_v3
base.message_for = tri_axis_message_for
base.telegram_send = prev.telegram_send_html


if __name__ == "__main__":
    try:
        raise SystemExit(base.main())
    except Exception as e:
        import sys
        print(f"ERROR: {e}", file=sys.stderr)
        raise
