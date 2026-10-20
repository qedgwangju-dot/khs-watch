"""Investor display and subgroup rules shared by intraday index alerts.

Investment trusts are a subset of institutions. Keep the three disjoint
top-level groups for reconciliation and leadership, and observe trusts
separately without adding them to their parent.
"""
from __future__ import annotations
import math

PRIMARY_ACTORS = ("외국인", "기관", "개인")
ALERT_ACTORS = (*PRIMARY_ACTORS, "투신")
TRUST_NOTE = "투신은 기관계에 포함됩니다. 기관·투신을 합산하거나 독립된 두 집단의 동조로 세지 않습니다."
LEADER_NOTE = "최다매도 비교는 외국인·기관·개인 기준이며 투신은 기관 내 별도 관측입니다."


def actor_label(actor: str) -> str:
    return "투신(기관 내)" if actor == "투신" else actor


def trust_value(block: dict | None) -> float | None:
    def number(value):
        try:
            if value is None or isinstance(value, bool) or not str(value).strip():
                return None
            result = float(str(value).replace(',', ''))
            return result if math.isfinite(result) else None
        except (ValueError, TypeError, OverflowError):
            return None
    block = block or {}
    value = number(block.get('투신'))
    if block.get('source_tr') == 't8463':
        row = block.get('source_row') or {}
        volume = number(row.get('invmsvol'))
        if (str((block.get('summary') or {}).get('invcode') or '').strip() != '0003'
                or value != number(row.get('invmsamt'))
                or volume is None or not volume.is_integer()):
            return None
    elif block.get('source_tr') == 't1602' and 'source_row' in block:
        if value != number((block.get('source_row') or {}).get('sv_03')):
            return None
    return value


def trust_direction_lines(spot: dict | None, futures: dict | None = None) -> list[str]:
    """Missing subgroup endpoints remain missing, even when its parent exists."""
    def direction(block):
        value = trust_value(block)
        if value is None:
            return "확인 보류(투신 기준점·원값 부족)"
        return "순매도" if value < 0 else "순매수" if value > 0 else "중립"
    parts = ["현물 " + direction(spot)]
    if futures is not None:
        parts.append("선물 " + direction(futures))
    return ["• 투신(기관 내) 방향: " + " · ".join(parts), "• " + TRUST_NOTE]
