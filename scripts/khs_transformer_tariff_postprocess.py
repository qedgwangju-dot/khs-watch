#!/usr/bin/env python3
"""Clean known policy false positives and render focused policy overrides."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from khs_policy_alert_explainer import ensure_explained, explanation_lines


KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")
DATA_DIR = Path("data")
REPORT_PATH = OUT_DIR / "khs_policy_watch.md"
ALERT_PATH = OUT_DIR / "khs_policy_watch_alert.md"
TITLE_PATH = OUT_DIR / "khs_policy_watch_alert_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"
SEEN_PATH = DATA_DIR / "khs_policy_watch_seen.json"

TITLE = "미국, 대형 변압기 관세 25%→15% 인하 보도·공식근거 체크"
SECTORS = ["전력기기/변압기", "관세/수출주", "전력망/데이터센터"]


def identity_text(item: dict) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in (
            "source",
            "title",
            "original_title",
            "source_title",
            "link",
        )
    ).lower()


def known_false_positive_reason(item: dict) -> str:
    text = identity_text(item)

    # FCC E-Rate debarment notices are administrative enforcement actions against
    # specific participants, not a new telecom policy/CAPEX catalyst.
    if "notice of debarment" in text and "e-rate" in text:
        return "fcc_e_rate_debarment"

    # This White House item is about veterans' benefits/employment record sharing
    # and IT modernization. Do not promote it to a broad market-policy signal.
    if (
        "accelerates veterans" in text
        and "benefits" in text
        and "employment opportunities" in text
    ):
        return "whitehouse_veterans_benefits"

    # A batch bill-signing notice must be parsed bill-by-bill before it can be
    # mapped to energy/land/industry sectors. The generic notice itself is not a
    # safe high-impact alert.
    if "congressional bills" in text and "signed into law" in text:
        return "whitehouse_batch_bill_signing"

    return ""


def is_canada_retaliation_fact_sheet(item: dict) -> bool:
    text = identity_text(item)
    return (
        "white house" in text
        and "responds to canada" in text
        and "retaliation" in text
    )


def normalize_canada_retaliation(item: dict) -> None:
    """Keep the Sep. 8 Canada action precise and out of the generic Trump profile."""
    item["importance"] = "상"
    item["title_ko"] = "백악관, 캐나다 보복조치 대응해 일부 캐나다산 수입금지·추가부과 범위 조정"
    item["matched"] = {"presidential_action": ["Section 338", "수입금지", "추가 세율 조정"]}
    item["impacts"] = ["돈 버는 능력", "할인율", "시간표"]
    item["paths"] = ["무역비용", "공급망", "정책 시간표", "연방조달"]
    item["sectors"] = ["북미 자동차/부품", "주류/식품", "철강/농기계", "연방조달"]
    item["korea_value_chain"] = ["북미 자동차/부품", "주류/식품", "철강/농기계", "연방조달"]
    item["policy_plain_summary"] = (
        "백악관은 9월 8일 캐나다가 약 200억달러 규모 미국산 수출품에 보복성 추가부과를 시행한 데 대응해 "
        "Section 338 포고문 5건을 서명하고, 일부 캐나다산 제품의 수입금지와 기존 추가부과 적용 범위를 조정했습니다."
    )
    item["investment_view"] = (
        "북미 자동차·주류·유제품·철강·농기계의 조달비용과 가격전가, 캐나다 생산거점 경쟁력에 영향을 줄 수 있습니다. "
        "품목별 수입금지와 추가 세율 범위를 구분해 봐야 합니다."
    )
    item["korea_market_impact"] = (
        "국내 증시에서는 현대차·기아와 부품사의 캐나다 생산·조달 노출, 북미 가격경쟁 구도를 우선 확인합니다. "
        "국내 생산품에 동일 조치가 적용된다는 뜻은 아닙니다."
    )
    item["priced_in"] = (
        "낮음~중간. 북미 자동차·산업재에는 즉시 반영될 수 있지만 개별 기업 영향은 생산지·품목코드·조달 구조에 따라 달라집니다."
    )
    item["counter"] = (
        "일부 품목은 기존 조치의 범위 조정이고, 캐나다의 추가 대응이나 협상으로 적용 범위가 다시 달라질 수 있습니다."
    )
    item["failure_signal"] = (
        "미 세관 품목코드, 실제 수입금지·추가 세율 적용, 캐나다 대응, 국내 기업의 북미 판매가격·조달 변화가 확인되지 않으면 직접 영향은 제한적입니다."
    )

    # The shared explainer promotes any White House item containing both the
    # President's name and broad market keywords into one generic Trump profile.
    # Keep source identity/title/link, but remove detector prose so this verified
    # event-specific profile survives repeated ensure_explained() calls.
    for key in ("summary", "source_abstract", "source_body", "core", "point", "impact"):
        item[key] = ""


def stage_ignored_seen(ignored: list[tuple[dict, str]], now: dt.datetime) -> None:
    """Stage ignored fingerprints in the working tree.

    The workflow only commits the watch state after a confirmed Telegram outcome,
    so these suppressions persist only alongside a successful real delivery.
    """
    if not ignored:
        return
    try:
        state = json.loads(SEEN_PATH.read_text(encoding="utf-8")) if SEEN_PATH.exists() else {"seen": {}}
    except Exception:
        state = {"seen": {}}
    if not isinstance(state, dict):
        state = {"seen": {}}
    seen = state.setdefault("seen", {})
    if not isinstance(seen, dict):
        seen = {}
        state["seen"] = seen

    staged = 0
    for item, reason in ignored:
        fingerprint = str(item.get("fingerprint") or "").strip()
        if not fingerprint:
            continue
        seen[fingerprint] = {
            "first_seen_kst": str(item.get("published_kst") or now.isoformat()),
            "importance": str(item.get("importance") or ""),
            "link": str(item.get("link") or ""),
            "source": str(item.get("source") or ""),
            "title": str(item.get("title") or ""),
            "ignored_reason": reason,
            "ignored_at_kst": now.isoformat(),
        }
        staged += 1
    if not staged:
        return
    DATA_DIR.mkdir(exist_ok=True)
    SEEN_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"policy_postprocess_ignored_staged={staged} commit_requires_confirmed_delivery=true")


def is_transformer_alert(item: dict) -> bool:
    return bool(item.get("transformer_tariff_policy_watch")) or "transformer_tariff_policy" in (item.get("matched") or {})


def render(alerts: list[dict], now: dt.datetime) -> str:
    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    for idx, alert in enumerate(alerts, 1):
        matched_terms = sorted({term for terms in (alert.get("matched") or {}).values() for term in terms})
        matched_keys = ", ".join((alert.get("matched") or {}).keys()) or "정책/규제"
        lines.extend([
            f"## {idx}. [{alert.get('importance', '중')}·{alert.get('status', '확정')}] {str(alert.get('title') or '').strip()}",
            f"- 상태 변화: {matched_keys} 신호 확인 ({', '.join(matched_terms[:8])})",
            f"- 원문/출처: [{alert.get('source', 'source')}]({alert.get('link', '')}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
            *explanation_lines(alert),
            *([f"- 변압기 관세 체크: {alert.get('transformer_tariff_check')}"] if alert.get("transformer_tariff_check") else []),
            *([f"- 체크할 리스크: {alert.get('transformer_tariff_risk_table')}"] if alert.get("transformer_tariff_risk_table") else []),
            *([f"- 구조 변화: {alert.get('transformer_tariff_structure_note')}"] if alert.get("transformer_tariff_structure_note") else []),
            "- 즉시 체크: 품목코드, 시행일, 원산지 요건, 한국 전력기기 밸류체인 노출, 관련 해외 티커·ETF 반응",
            "",
        ])
    lines.extend([
        "💡 워치 판단: 이번 실행은 변압기 관세율과 미국 전력망 투자 수혜 기대가 돈 버는 능력·수급·시간표를 바꿀 수 있는지 우선 감지했습니다.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    if not ALERTS_JSON_PATH.exists():
        return 0
    try:
        alerts = json.loads(ALERTS_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(alerts, list):
        return 0

    now = dt.datetime.now(tz=KST)
    filtered: list[dict] = []
    ignored: list[tuple[dict, str]] = []
    normalized = 0
    for item in alerts:
        reason = known_false_positive_reason(item)
        if reason:
            ignored.append((item, reason))
            print(
                "policy_postprocess_drop "
                f"reason={reason} source={item.get('source')!r} title={item.get('title')!r}"
            )
            continue
        if is_canada_retaliation_fact_sheet(item):
            normalize_canada_retaliation(item)
            normalized += 1
            print("policy_postprocess_normalized=whitehouse_canada_retaliation")
        filtered.append(item)
    alerts = filtered

    if ignored:
        ALERTS_JSON_PATH.write_text(
            json.dumps(alerts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        stage_ignored_seen(ignored, now)
        print(f"policy_postprocess=cleaned removed={len(ignored)} remaining={len(alerts)}")
    elif normalized:
        ALERTS_JSON_PATH.write_text(
            json.dumps(alerts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    has_transformer = any(is_transformer_alert(item) for item in alerts)
    if not has_transformer:
        return 0

    for item in alerts:
        if is_transformer_alert(item):
            item["title"] = TITLE
            item["sectors"] = SECTORS[:]
            ensure_explained(item)

    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = render(alerts, now)
    REPORT_PATH.write_text(report, encoding="utf-8")
    ALERT_PATH.write_text(report, encoding="utf-8")
    TITLE_PATH.write_text(f"KHS 정책 워치: [상] {TITLE}\n", encoding="utf-8")
    print("transformer_tariff_postprocess=rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
