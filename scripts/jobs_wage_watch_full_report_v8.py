from __future__ import annotations

import re
import urllib.parse

from bs4 import BeautifulSoup

import jobs_wage_watch_full_report as base
import jobs_wage_watch_full_report_v7 as v7

FED_MONETARY_POLICY = "https://www.federalreserve.gov/monetarypolicy.htm"


def _latest_fomc_statement_context() -> dict:
    """Read the latest official FOMC statement from federalreserve.gov.

    This is deliberately limited to Committee-level official wording. Individual
    speeches are useful context but are not substituted for the FOMC's policy
    stance in the automated reaction function.
    """
    try:
        html = base._fetch(FED_MONETARY_POLICY, timeout=15).decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        candidates = []
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "")
            m = re.search(r"/newsevents/pressreleases/monetary(\d{8})a\.htm", href, re.I)
            if m:
                candidates.append((m.group(1), urllib.parse.urljoin(FED_MONETARY_POLICY, href)))
        if not candidates:
            raise RuntimeError("latest FOMC statement link not found")

        date_key, url = sorted(set(candidates), reverse=True)[0]
        statement_html = base._fetch(url, timeout=15).decode("utf-8", errors="replace")
        text = " ".join(BeautifulSoup(statement_html, "html.parser").stripped_strings)
        lower = text.lower()

        target = None
        m = re.search(
            r"target range for the federal funds rate at\s+([0-9\-\u2010-\u2015/]+)\s+to\s+([0-9\-\u2010-\u2015/]+)\s+percent",
            text,
            re.I,
        )
        if m:
            target = f"{m.group(1)}~{m.group(2)}%"

        return {
            "date": f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}",
            "url": url,
            "target_range": target,
            "inflation_elevated": (
                "inflation remains elevated" in lower
                or "inflation remains somewhat elevated" in lower
                or "inflation is elevated" in lower
            ),
            "jobs_stable": (
                "job gains have kept pace with the workforce" in lower
                or "unemployment rate has changed little" in lower
                or "labor market conditions remain solid" in lower
            ),
            "price_stability_commitment": (
                "deliver price stability" in lower
                or "returning inflation to its 2 percent objective" in lower
                or "return inflation to 2 percent" in lower
            ),
            "status": "FOMC 공식 성명 직접 조회",
        }
    except Exception as e:
        return {
            "date": None,
            "url": FED_MONETARY_POLICY,
            "target_range": None,
            "inflation_elevated": None,
            "jobs_stable": None,
            "price_stability_commitment": None,
            "status": f"FOMC 공식 성명 확인 불가 ({type(e).__name__})",
        }


def _fed_section_v8(signals: dict, bls: dict, period: str, latest: dict) -> str:
    ahe = base._yoy_change(bls, "ahe", period)
    unemployment = base._value(bls["unemployment_rate"], period)
    nfp = base._change_jobs(bls, "nfp_level", period)
    participation = base._value(bls["participation_rate"], period)

    claims = latest.get("weekly_claims")
    initial = claims.metrics.get("initial_claims") if claims else None
    continuing = claims.metrics.get("continuing_claims") if claims else None

    fed = _latest_fomc_statement_context()

    weak_hiring = bool(signals.get("weak_hiring"))
    wage_soft = ahe is not None and ahe < 3.5
    wage_sticky = ahe is not None and ahe >= 3.5

    # Give the user the immediate policy-direction read first, then the caveat.
    # This is deliberately a directional signal, not a claim that the FOMC has
    # already decided to move rates.
    if weak_hiring and wage_soft:
        direction_label = "인하 쪽"
        labor_axis = "고용이 약하고 임금도 둔화해 고용축은 분명히 인하 쪽입니다."
    elif weak_hiring and wage_sticky:
        direction_label = "인하 쪽 신호 있으나 제한적"
        labor_axis = "고용 약화는 인하 쪽이지만 임금 강세가 동결·인상 쪽으로 맞서고 있습니다."
    elif (not weak_hiring) and wage_sticky:
        direction_label = "동결·인상 쪽"
        labor_axis = "고용이 버티고 임금도 강해 인하 필요성이 낮습니다."
    else:
        direction_label = "중립"
        labor_axis = "고용과 임금이 한 방향으로 충분히 정렬되지 않았습니다."

    if fed.get("inflation_elevated") and fed.get("price_stability_commitment"):
        if weak_hiring and wage_soft:
            policy_judgment = (
                "고용만 보면 인하 쪽입니다. 다만 최신 FOMC는 물가가 2% 목표보다 높다고 보고 있어, "
                "실제 정책 결론은 다음 CPI·PCE에서 디스인플레이션이 이어지는지까지 확인해야 합니다."
            )
        elif weak_hiring and wage_sticky:
            policy_judgment = (
                "고용은 인하 쪽, 임금·물가는 동결·인상 쪽입니다. 따라서 지금은 인하 신호가 생겼지만 "
                "확신은 낮고, 다음 물가가 식어야 인하 논리가 우세해집니다."
            )
        else:
            policy_judgment = (
                "현재는 인하보다 동결·물가 확인 쪽입니다. 최신 FOMC 공식 문구상 물가 제약이 남아 있어 "
                "고용이 버티는 동안에는 2% 복귀 확인이 우선됩니다."
            )
    else:
        policy_judgment = (
            f"고용·임금 조합의 1차 방향은 {direction_label}입니다. 다만 FOMC 최종 결정은 최대고용과 "
            "2% 물가안정을 함께 보므로 물가·기대인플레이션까지 확인해야 합니다."
        )

    backdrop_parts = []
    if fed.get("date"):
        backdrop_parts.append(f"성명 {fed['date']}")
    if fed.get("target_range"):
        backdrop_parts.append(f"정책금리 {fed['target_range']}")
    if fed.get("jobs_stable") is True:
        backdrop_parts.append("고용은 안정적으로 묘사")
    if fed.get("inflation_elevated") is True:
        backdrop_parts.append("물가는 2% 목표보다 높음")
    backdrop = " · ".join(backdrop_parts) if backdrop_parts else fed.get("status")

    return (
        "- 공식 기준 | 최대고용 + 2% PCE 물가안정. 최대고용은 고정 숫자가 아니며 실업률·참가율·고용 폭·임금 등 여러 지표를 함께 봅니다.\n"
        f"- 현재 FOMC 배경 | {backdrop} | {fed.get('status')}\n"
        f"- 방향 한눈에 | {direction_label} — {labor_axis}\n"
        f"- 이번 고용축 | NFP {base._fmt_int(nfp)}명 · 실업률 {base._fmt_pct(unemployment)} · 참가율 {base._fmt_pct(participation)} · AHE YoY {base._fmt_pct(ahe)}\n"
        f"- 실업수당 보조축 | Initial {base._fmt_level(initial)}건 · Continuing {base._fmt_level(continuing)}건. Initial이 낮고 Continuing이 높으면 '해고 급증'보다 '재취업 지연'에 가깝습니다.\n"
        f"- 최종 반응함수 | {policy_judgment}\n"
        "- 강화·무효화 | 약한 고용+임금·CPI·PCE 동반 둔화가 반복되면 인하 논리 강화. 반대로 물가 재가속 또는 고용 급반등이면 인하 해석을 약화·무효화합니다."
    )


# Override only the Fed reaction-function section. v7 continues to handle the
# readable Telegram layout, no-# formatting, market grouping, and overview.
base._fed_section = _fed_section_v8


def build_report(new_releases):
    report = v7.build_report(new_releases)
    return report.replace("7) 연준 반응함수 보조 프레임", "7) 연준 반응함수")
