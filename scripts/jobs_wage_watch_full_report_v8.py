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

    if weak_hiring and wage_soft:
        labor_axis = "완화 방향 — 채용 약화와 임금 둔화가 함께 나타나 최대고용 하방 위험이 커집니다."
    elif weak_hiring and wage_sticky:
        labor_axis = "혼합 — 채용은 약하지만 임금이 끈적해 고용 하방과 물가 상방이 충돌합니다."
    elif (not weak_hiring) and wage_sticky:
        labor_axis = "동결·긴축 방향 — 고용이 버티는 가운데 임금 압력도 남아 있으면 완화 필요성이 약합니다."
    else:
        labor_axis = "중립 — 고용과 임금이 한 방향으로 충분히 정렬되지 않았습니다."

    if fed.get("inflation_elevated") and fed.get("price_stability_commitment"):
        if weak_hiring and wage_soft:
            policy_judgment = (
                "고용축만 보면 완화 쪽이지만 금리 인하로 바로 연결하면 안 됩니다. "
                "최신 FOMC 공식 문구가 물가의 2% 목표 상회와 가격안정 의지를 함께 명시하고 있으므로, "
                "다음 CPI·PCE와 임금에서 디스인플레이션이 재확인돼야 완화 논리가 강해집니다."
            )
        elif weak_hiring and wage_sticky:
            policy_judgment = (
                "현재는 인하 확신이 약한 충돌 구간입니다. 고용 약화만으로는 부족하고, "
                "임금·서비스 물가가 식지 않으면 동결 또는 더 긴 제약적 정책이 유지될 수 있습니다."
            )
        else:
            policy_judgment = (
                "현재 FOMC 공식 문구상 물가 제약이 남아 있습니다. 고용이 버티면 정책 완화보다 "
                "물가의 2% 복귀 확인이 우선됩니다."
            )
    else:
        policy_judgment = (
            "FOMC는 최대고용과 2% 물가안정을 함께 봅니다. 고용 한 지표만으로 금리 방향을 확정하지 않고 "
            "물가·기대인플레이션·금융여건과 함께 판단해야 합니다."
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
        f"- 이번 고용축 | NFP {base._fmt_int(nfp)}명 · 실업률 {base._fmt_pct(unemployment)} · 참가율 {base._fmt_pct(participation)} · AHE YoY {base._fmt_pct(ahe)} → {labor_axis}\n"
        f"- 실업수당 보조축 | Initial {base._fmt_level(initial)}건 · Continuing {base._fmt_level(continuing)}건. Initial이 낮고 Continuing이 높으면 '해고 급증'보다 '재취업 지연'에 가깝습니다.\n"
        f"- 최종 반응함수 | {policy_judgment}\n"
        "- 강화·무효화 | 약한 고용+임금·CPI·PCE 동반 둔화가 반복되면 완화 논리 강화. 반대로 물가 재가속 또는 고용 급반등이면 완화 해석을 무효화합니다."
    )


# Override only the Fed reaction-function section. v7 continues to handle the
# readable Telegram layout, no-# formatting, market grouping, and overview.
base._fed_section = _fed_section_v8


def build_report(new_releases):
    report = v7.build_report(new_releases)
    return report.replace("7) 연준 반응함수 보조 프레임", "7) 연준 반응함수")
