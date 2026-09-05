#!/usr/bin/env python3
import calendar
import html as html_lib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import warsh_reaction_watch as base


def _pct(a, b):
    return (a / b - 1.0) * 100.0


def _prev_month(period):
    return base.previous_month(period)


def _month_kr(period):
    return f"{period[1]}월"


def _series_change(series, period):
    prev = _prev_month(period)
    if period not in series or prev not in series:
        return None
    return series[period] - series[prev]


def _three_month_average(series, period):
    changes = []
    cur = period
    for _ in range(3):
        prev = _prev_month(cur)
        if cur not in series or prev not in series:
            return None
        changes.append(series[cur] - series[prev])
        cur = prev
    return sum(changes) / len(changes)


def _release_extras(period):
    out = {"avg12": None, "revision_text": None, "url": base.URLS["employment"]}
    try:
        raw, final = base.fetch(base.URLS["employment"])
        text = base.clean_text(raw)
        out["url"] = final

        m = re.search(r"average monthly gain of\s+([\d,]+)\s+over the prior 12 months", text, re.I)
        if m:
            out["avg12"] = float(m.group(1).replace(",", "")) / 1000.0

        prev1 = _prev_month(period)
        prev2 = _prev_month(prev1)
        revisions = []
        for idx, p in enumerate((prev2, prev1)):
            month_en = calendar.month_name[p[1]]
            if idx == 0:
                pat = rf"employment for\s+{month_en}\s+was revised\s+(up|down)\s+by\s+([\d,]+),\s+from\s+([+-]?[\d,]+)\s+to\s+([+-]?[\d,]+)"
            else:
                pat = rf"the change for\s+{month_en}\s+was revised\s+(up|down)\s+by\s+([\d,]+),\s+from\s+([+-]?[\d,]+)\s+to\s+([+-]?[\d,]+)"
            rm = re.search(pat, text, re.I)
            if rm:
                old = float(rm.group(3).replace(",", "")) / 1000.0
                new = float(rm.group(4).replace(",", "")) / 1000.0
                revisions.append(f"{_month_kr(p)} {old:+.0f}→{new:+.0f}천명")

        cm = re.search(
            r"With these revisions, employment in\s+[A-Za-z]+\s+and\s+[A-Za-z]+\s+combined is\s+([\d,]+)\s+(higher|lower)\s+than previously reported",
            text,
            re.I,
        )
        if revisions:
            suffix = ""
            if cm:
                val = float(cm.group(1).replace(",", "")) / 1000.0
                if cm.group(2).lower() == "lower":
                    val = -val
                suffix = f" · 합계 {val:+.0f}천명"
            out["revision_text"] = " / ".join(revisions) + suffix
    except Exception:
        pass
    return out


def _employment_verdict(details):
    payroll = details.get("payroll_change")
    ur_chg = details.get("unemployment_change")
    emp_chg = details.get("employment_population_change")
    wage_yoy = details.get("wage_yoy")

    if payroll is not None and ur_chg is not None and emp_chg is not None:
        if payroll >= 100 and ur_chg <= 0.1 and emp_chg >= 0:
            verdict = "완전고용 전제 유지·소폭 강화"
        elif (ur_chg >= 0.2 and payroll < 50) or (payroll < 0 and emp_chg < 0):
            verdict = "완전고용 전제 약화"
        else:
            verdict = "완전고용 전제 대체로 유지"
    else:
        verdict = "완전고용 전제 변화 확인 필요"

    if verdict == "완전고용 전제 약화":
        policy = "고용 둔화가 뚜렷해지면 워시의 물가 우선 기조에도 금리 인하 필요성이 커질 수 있습니다. 물가와 함께 재확인합니다."
    elif wage_yoy is not None and wage_yoy >= 4.0:
        policy = "고용이 버티고 임금 압력도 높아 추가긴축 논리가 강화됩니다. 다만 최종 판단은 CPI·PCE 물가 추세와 함께 봅니다."
    else:
        policy = "고용 때문에 금리를 내려야 할 이유는 약화했습니다. 다만 임금 재가속 신호가 강하지 않아 고용만으로 추가 인상을 확정할 수는 없고, CPI·PCE 물가 추세가 다음 핵심입니다."
    return verdict, policy


def enhanced_bls_snapshots():
    now = datetime.now(timezone.utc)
    series_ids = [
        "CES0000000001",  # 비농업 고용
        "CES0500000001",  # 민간 고용
        "LNS14000000",    # 실업률
        "LNS11300000",    # 경제활동참가율
        "LNS12300000",    # 고용률
        "CES0500000003",  # 시간당 평균임금
        "CES0500000002",  # 주당 평균근로시간
        "CUSR0000SA0",
        "CUSR0000SA0L1E",
    ]
    data = base.post_json(base.URLS["bls_api"], {
        "seriesid": series_ids,
        "startyear": str(now.year - 1),
        "endyear": str(now.year),
    })
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API failed: {data.get('message')}")
    by_id = {s["seriesID"]: base.series_values(s) for s in data.get("Results", {}).get("series", [])}

    payroll = by_id.get("CES0000000001", {})
    private = by_id.get("CES0500000001", {})
    urate = by_id.get("LNS14000000", {})
    participation = by_id.get("LNS11300000", {})
    emp_pop = by_id.get("LNS12300000", {})
    wages = by_id.get("CES0500000003", {})
    hours = by_id.get("CES0500000002", {})

    common_emp = sorted(set(payroll) & set(urate))
    if not common_emp:
        raise RuntimeError("BLS employment series have no common month")
    ep = common_emp[-1]
    eprev = _prev_month(ep)
    eyago = (ep[0] - 1, ep[1])

    payroll_change = _series_change(payroll, ep)
    private_change = _series_change(private, ep)
    government_change = None
    if payroll_change is not None and private_change is not None:
        government_change = payroll_change - private_change

    unemployment_change = _series_change(urate, ep)
    participation_change = _series_change(participation, ep)
    employment_population_change = _series_change(emp_pop, ep)
    three_month_avg = _three_month_average(payroll, ep)

    wage_mom = _pct(wages[ep], wages[eprev]) if ep in wages and eprev in wages else None
    wage_yoy = _pct(wages[ep], wages[eyago]) if ep in wages and eyago in wages else None
    hours_change = _series_change(hours, ep)

    extras = _release_extras(ep)
    details = {
        "payroll_change": payroll_change,
        "private_change": private_change,
        "government_change": government_change,
        "unemployment_rate": urate.get(ep),
        "unemployment_change": unemployment_change,
        "participation_rate": participation.get(ep),
        "participation_change": participation_change,
        "employment_population_ratio": emp_pop.get(ep),
        "employment_population_change": employment_population_change,
        "three_month_avg": three_month_avg,
        "prior_12m_avg": extras.get("avg12"),
        "wage_level": wages.get(ep),
        "wage_mom": wage_mom,
        "wage_yoy": wage_yoy,
        "hours": hours.get(ep),
        "hours_change": hours_change,
        "revision_text": extras.get("revision_text"),
    }
    verdict, policy = _employment_verdict(details)
    details["verdict"] = verdict
    details["policy"] = policy

    # 기존 기준선과 동일한 지문을 유지해 서식 변경만으로 중복 알림이 나가지 않게 한다.
    emp_payload = {
        "period": ep,
        "payroll": payroll.get(ep),
        "payroll_change": payroll_change,
        "unemployment_rate": urate.get(ep),
    }

    cpi = by_id.get("CUSR0000SA0", {})
    core = by_id.get("CUSR0000SA0L1E", {})
    common_cpi = sorted(set(cpi) & set(core))
    if not common_cpi:
        raise RuntimeError("BLS CPI series have no common month")
    cp = common_cpi[-1]
    cprev = _prev_month(cp)
    cyago = (cp[0] - 1, cp[1])
    cpi_mom = _pct(cpi[cp], cpi[cprev]) if cprev in cpi else None
    cpi_yoy = _pct(cpi[cp], cpi[cyago]) if cyago in cpi else None
    core_mom = _pct(core[cp], core[cprev]) if cprev in core else None
    core_yoy = _pct(core[cp], core[cyago]) if cyago in core else None
    cpi_payload = {
        "period": cp,
        "cpi": cpi[cp],
        "core": core[cp],
        "cpi_mom": cpi_mom,
        "cpi_yoy": cpi_yoy,
        "core_mom": core_mom,
        "core_yoy": core_yoy,
    }
    cpi_summary = []
    if cpi_mom is not None and cpi_yoy is not None:
        cpi_summary.append(f"종합 CPI {cpi_mom:+.1f}% 전월 대비 / {cpi_yoy:+.1f}% 전년 대비")
    if core_mom is not None and core_yoy is not None:
        cpi_summary.append(f"근원 CPI {core_mom:+.1f}% 전월 대비 / {core_yoy:+.1f}% 전년 대비")
    cpi_summary.append("워시 기준: 2% 목표로 명확하고 충분한 속도로 둔화하는지 확인")

    return {
        "employment": {
            "url": extras.get("url") or base.URLS["employment"],
            "key": f"{ep[0]}-{ep[1]:02d}",
            "fingerprint": base.fingerprint_obj(emp_payload),
            "summary": [],
            "details": details,
        },
        "cpi": {
            "url": base.URLS["cpi"],
            "key": f"{cp[0]}-{cp[1]:02d}",
            "fingerprint": base.fingerprint_obj(cpi_payload),
            "summary": cpi_summary,
        },
    }


def _safe(value):
    return html_lib.escape(str(value), quote=False)


def _source_link(url):
    return f'<a href="{html_lib.escape(url, quote=True)}">원천</a>'


def _fmt_change(value, decimals=1, suffix=""):
    if value is None:
        return "확인 불가"
    return f"{value:+.{decimals}f}{suffix}"


def enhanced_message_for(name, snap):
    if name == "employment" and snap.get("details"):
        d = snap["details"]
        lines = [
            "[Warsh 반응함수 변화 감지] BLS 고용",
            f"기준: {_safe(snap.get('key', ''))}",
            "",
            "<b>한눈에 보기</b>",
            f"• <b>판정</b> | {_safe(d.get('verdict'))}",
        ]

        payroll = d.get("payroll_change")
        avg3 = d.get("three_month_avg")
        avg12 = d.get("prior_12m_avg")
        employment_bits = []
        if payroll is not None:
            employment_bits.append(f"{payroll:+.0f}천명")
        if avg3 is not None:
            employment_bits.append(f"최근 3개월 평균 {avg3:+.0f}천명")
        if avg12 is not None:
            employment_bits.append(f"직전 12개월 월평균 {avg12:+.0f}천명")
        lines.append(f"• <b>비농업 고용</b> | {_safe(' · '.join(employment_bits))}")

        if d.get("private_change") is not None and d.get("government_change") is not None:
            lines.append(
                f"• <b>고용 구성</b> | 민간 {d['private_change']:+.0f}천명 · 정부 {d['government_change']:+.0f}천명"
            )

        household = []
        if d.get("unemployment_rate") is not None:
            household.append(
                f"실업률 {d['unemployment_rate']:.1f}% ({_fmt_change(d.get('unemployment_change'), 1, '%p')})"
            )
        if d.get("participation_rate") is not None:
            household.append(
                f"참가율 {d['participation_rate']:.1f}% ({_fmt_change(d.get('participation_change'), 1, '%p')})"
            )
        if d.get("employment_population_ratio") is not None:
            household.append(
                f"고용률 {d['employment_population_ratio']:.1f}% ({_fmt_change(d.get('employment_population_change'), 1, '%p')})"
            )
        lines.append(f"• <b>가계조사</b> | {_safe(' · '.join(household))}")

        wage_bits = []
        if d.get("wage_level") is not None:
            wage_bits.append(f"시간당임금 ${d['wage_level']:.2f}")
        if d.get("wage_mom") is not None:
            wage_bits.append(f"전월 대비 {d['wage_mom']:+.1f}%")
        if d.get("wage_yoy") is not None:
            wage_bits.append(f"전년 대비 {d['wage_yoy']:+.1f}%")
        if d.get("hours") is not None:
            wage_bits.append(f"주당근로 {d['hours']:.1f}시간 ({_fmt_change(d.get('hours_change'), 1, '시간')})")
        lines.append(f"• <b>임금·근로시간</b> | {_safe(' · '.join(wage_bits))}")

        if d.get("revision_text"):
            lines.append(f"• <b>이전 2개월 수정</b> | {_safe(d['revision_text'])}")

        lines += [
            "",
            "<b>해석</b>",
            "• 실업률이 오르지 않았고 고용·참가율·고용률이 함께 개선돼 노동시장 급랭 신호는 아닙니다.",
            "• 워시의 ‘현재 노동시장은 완전고용에 부합’ 전제를 약화시키지 않습니다. 따라서 고용만 놓고 보면 금리 인하 필요성은 낮아졌습니다.",
            f"• {_safe(d.get('policy'))}",
            "",
            _source_link(snap["url"]),
        ]
        return "\n".join(lines)

    lines = [
        f"[Warsh 반응함수 변화 감지] {_safe(base.label(name))}",
        f"기준: {_safe(snap.get('key', ''))}",
    ]
    if snap.get("summary"):
        lines.append("")
        lines.extend(f"• {_safe(s)}" for s in snap["summary"][:7])
    lines += [
        "",
        _source_link(snap["url"]),
        "",
        "판정: 완전고용 전제, 물가 2%로의 충분한 둔화, 추가긴축 가능성이 강화·약화되는지 확인",
    ]
    return "\n".join(lines)


def telegram_send_html(text):
    if not base.TOKEN or not base.CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID secret is missing")
    bot_user = base.get_bot_username()
    if base.EXPECTED_BOT and bot_user.lower() != base.EXPECTED_BOT.lower():
        raise RuntimeError(f"Telegram bot mismatch: token=@{bot_user}, expected=@{base.EXPECTED_BOT}")
    payload = urllib.parse.urlencode({
        "chat_id": base.CHAT_ID,
        "text": text[:4090],
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{base.TOKEN}/sendMessage", data=payload)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {data}")


base.bls_snapshots = enhanced_bls_snapshots
base.message_for = enhanced_message_for
base.telegram_send = telegram_send_html


if __name__ == "__main__":
    try:
        raise SystemExit(base.main())
    except Exception as e:
        import sys
        print(f"ERROR: {e}", file=sys.stderr)
        raise
