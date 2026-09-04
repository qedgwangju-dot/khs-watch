from __future__ import annotations

import jobs_wage_watch_full_report as base
import jobs_wage_watch_full_report_v8 as v8
import jobs_wage_watch_full_report_v7 as v7


def _fed_section_v9(signals: dict, bls: dict, period: str, latest: dict) -> str:
    ahe = base._yoy_change(bls, "ahe", period)
    weak_hiring = bool(signals.get("weak_hiring"))

    if weak_hiring and ahe is not None and ahe < 3.5:
        direction = "인하 쪽 — 고용이 약하고 임금도 둔화해 고용축은 완화 방향입니다."
    elif weak_hiring and ahe is not None and ahe >= 3.5:
        direction = "인하 쪽 신호는 있으나 제한적 — 고용은 약하지만 임금이 강해 물가 제약이 남습니다."
    elif (not weak_hiring) and ahe is not None and ahe >= 3.5:
        direction = "동결·인상 쪽 — 고용이 버티고 임금도 강하면 완화 필요성이 약합니다."
    else:
        direction = "중립 — 고용과 임금 방향이 충분히 정렬되지 않아 금리 방향을 단정하지 않습니다."

    detail = v8._fed_section_v8(signals, bls, period, latest)
    return f"- 방향 한눈에 | {direction}\n" + detail


# Persistent policy for Jobs Wage Watch:
# 1) Always show the labor-data rate direction first in plain language.
# 2) Then separate the final Fed policy judgment using inflation/FOMC context.
# 3) Never equate '고용축 인하 쪽' with an assured Fed rate cut.
base._fed_section = _fed_section_v9


def build_report(new_releases):
    report = v7.build_report(new_releases)
    return report.replace("7) 연준 반응함수 보조 프레임", "7) 연준 반응함수")
