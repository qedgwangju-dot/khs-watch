#!/usr/bin/env python3
"""Monitor material yen carry-trade rebuild and weak-yen flow catalysts."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from zoneinfo import ZoneInfo

import yen_policy_news_alert as base

UTC = dt.timezone.utc
KST = ZoneInfo("Asia/Seoul")
MAX_ITEM_AGE_HOURS = 12
MAX_ALERT_ITEMS = 3

STATE_PATH = pathlib.Path("data/yen_carry_news_state.json")
PENDING_PATH = pathlib.Path("out/yen_carry_news_pending_state.json")
ALERT_TITLE_PATH = pathlib.Path("out/yen_carry_news_alert_title.txt")
ALERT_BODY_PATH = pathlib.Path("out/yen_carry_news_alert.md")
ALERT_JSON_PATH = pathlib.Path("out/yen_carry_news_alert.json")
CONFIRM_PATH = pathlib.Path("out/yen_carry_news_telegram_confirmed.json")
SUMMARY_PATH = pathlib.Path("out/yen_carry_news_watch.md")

RSS_QUERIES = (
    ("en", '"yen carry trade" intervention rebuild'),
    ("en", '"yen carry trade" intervention interest rate gap'),
    ("en", 'yen intervention gains fade carry trade'),
    ("en", 'Japan investors overseas assets yen intervention'),
    ("en", 'Japanese investors foreign securities yen weakness'),
    ("ja", '円 キャリートレード 再開 為替介入'),
    ("ja", '円安 キャリートレード 金利差 介入'),
    ("ja", '日本 投資家 海外資産 円安 介入'),
)

CARRY_MARKERS = (
    "carry trade",
    "carry trades",
    "yen carry",
    "yen-funded carry",
    "キャリートレード",
    "円キャリー",
    "円キャリートレード",
)

REBUILD_MARKERS = (
    "rebuild",
    "rebuilding",
    "rebuilt",
    "re-establish",
    "reestablish",
    "re-enter",
    "reenter",
    "resume",
    "resumes",
    "resumed",
    "restart",
    "restarted",
    "revive",
    "revived",
    "renewed",
    "return to",
    "returns to",
    "back into",
    "再構築",
    "再開",
    "再び",
    "復活",
    "積み増し",
)

PERSIST_MARKERS = (
    "remains attractive",
    "remain attractive",
    "remains intact",
    "remain intact",
    "still attractive",
    "still alive",
    "persists",
    "persistent",
    "continues",
    "continue to favor",
    "根強い",
    "続く",
    "継続",
)

RATE_GAP_MARKERS = (
    "rate gap",
    "interest rate gap",
    "rate differential",
    "interest-rate differential",
    "yield gap",
    "yield differential",
    "金利差",
    "利回り差",
)

INTERVENTION_MARKERS = (
    "intervention",
    "joint intervention",
    "yen-buying intervention",
    "為替介入",
    "円買い介入",
    "協調介入",
)

WEAKNESS_MARKERS = (
    "yen weakens",
    "yen weakness",
    "yen falls",
    "yen slides",
    "yen sinks",
    "yen resumes decline",
    "resumes slide",
    "gives up gains",
    "relinquishes gains",
    "erases gains",
    "near 160",
    "toward 160",
    "around 160",
    "back to 160",
    "160 per dollar",
    "円安",
    "円下落",
    "円が下落",
    "160円",
)

OUTBOUND_MARKERS = (
    "overseas assets",
    "foreign assets",
    "foreign securities",
    "overseas securities",
    "overseas investment",
    "foreign investment",
    "net purchases of foreign",
    "海外資産",
    "外国資産",
    "外国証券",
    "対外証券",
    "海外投資",
)

JAPAN_INVESTOR_MARKERS = (
    "japanese investors",
    "japan investors",
    "japanese funds",
    "japanese institutions",
    "domestic investors",
    "日本の投資家",
    "国内投資家",
    "日本勢",
)

FLOW_SURGE_MARKERS = (
    "largest in two years",
    "biggest in two years",
    "two-year high",
    "largest since",
    "biggest since",
    "record",
    "surge",
    "surged",
    "jump",
    "jumped",
    "accelerate",
    "accelerated",
    "net buyers",
    "net purchases",
    "2年ぶり",
    "最大",
    "急増",
    "買い越し",
)


def contains(text: str, markers: tuple[str, ...]) -> bool:
    return base.contains_any(text, markers)


def classify(item: base.NewsItem) -> base.ClassifiedItem | None:
    level = base.source_level(item)
    if level == 0:
        return None

    text = item.text
    carry = contains(text, CARRY_MARKERS)
    rebuild = contains(text, REBUILD_MARKERS)
    persists = contains(text, PERSIST_MARKERS)
    rate_gap = contains(text, RATE_GAP_MARKERS)
    intervention = contains(text, INTERVENTION_MARKERS)
    weakness = contains(text, WEAKNESS_MARKERS)
    outbound = contains(text, OUTBOUND_MARKERS)
    japan_investor = contains(text, JAPAN_INVESTOR_MARKERS)
    flow_surge = contains(text, FLOW_SURGE_MARKERS)

    # Strongest signal: investors are explicitly rebuilding/restarting yen-funded carry.
    if carry and rebuild:
        topic, score = "엔캐리 재구축·재확산", 4
    # Carry remains active after intervention and the yen is weakening again.
    elif carry and intervention and weakness:
        topic, score = "엔캐리 재확산·개입 효과 약화", 4
    # Structural carry incentive remains because the rate/yield gap is still wide.
    elif carry and persists and (rate_gap or weakness or intervention):
        topic, score = "엔캐리 지속·재확산 압력", 3
    # Japanese investors materially increase foreign-asset purchases, adding yen-selling flow.
    elif outbound and japan_investor and flow_surge and (weakness or intervention or carry):
        topic, score = "일본 자금 해외투자 재확대·엔화 매도 압력", 4
    elif outbound and japan_investor and weakness:
        topic, score = "일본 자금 해외투자 확대·엔화 매도 압력", 3
    # Intervention fading is only material if a structural rate-gap driver is also present.
    elif intervention and weakness and rate_gap:
        topic, score = "개입 효과 약화·금리차 기반 엔화 약세", 3
    else:
        return None

    return base.ClassifiedItem(
        item=item,
        topic=topic,
        material_score=score,
        source_level=level,
        source_group=base.source_group(item.source, item.text),
    )


def collect_items(current: dt.datetime) -> tuple[list[base.NewsItem], list[str]]:
    unique: dict[str, base.NewsItem] = {}
    errors: list[str] = []
    for language, query in RSS_QUERIES:
        items, error = base.fetch_query(language, query, current)
        if error:
            errors.append(f"{language}:{query}: {error}")
        for item in items:
            unique[item.item_id] = item
    cutoff = current - dt.timedelta(hours=MAX_ITEM_AGE_HOURS)
    return sorted(
        (item for item in unique.values() if cutoff <= item.published <= current + dt.timedelta(minutes=10)),
        key=lambda item: item.published,
        reverse=True,
    ), errors


def axis_lines(topic: str) -> list[str]:
    if topic.startswith("엔캐리"):
        return [
            "수급: 엔화 차입→달러·고금리 자산 매수 재개는 USD/JPY 상승·글로벌 위험자산 유동성에 우호적일 수 있음",
            "할인율: 미·일 금리차가 크게 유지될수록 엔캐리 재구축 유인이 지속",
            "돈 버는 능력: 엔저 재개는 일본 수출주에 우호적이지만 전력·항공·유통 등 수입업종에는 원가 부담",
            "시간표: USD/JPY 160·162선, BOJ 9~10월 회의, CFTC 엔화 숏, 일본 주간 해외증권 매매를 재확인",
        ]
    if topic.startswith("일본 자금 해외투자"):
        return [
            "수급: 일본 투자자의 해외자산 매수 확대는 엔화 매도·외화 매수 수요를 키워 엔화 약세 압력",
            "할인율: 해외 금리 우위가 유지되면 자금 유출 유인이 지속될 수 있음",
            "돈 버는 능력: 엔저는 일본 수출주에는 우호적, 수입 원가 민감 업종에는 부담",
            "시간표: 일본 재무성 주간 대외증권투자와 BOJ 금리 경로에서 반복 여부 확인",
        ]
    return [
        "수급: 개입 효과가 약해지고 금리차 거래가 재개되면 USD/JPY 재상승 압력",
        "할인율: BOJ 인상 속도와 미국 금리 하락 여부가 지속성의 핵심",
        "돈 버는 능력: 엔저 재개 시 일본 수출주 상대 우위·수입업종 비용 부담 가능",
        "시간표: USD/JPY 160·162선과 추가 미·일 개입·BOJ 후속 신호 확인",
    ]


def fallback_korean(topic: str) -> str:
    mapping = {
        "엔캐리 재구축·재확산": "개입 뒤 엔화 반등을 활용해 엔캐리 포지션을 다시 구축하는 움직임이 확산된다는 보도",
        "엔캐리 재확산·개입 효과 약화": "미·일 개입 효과가 약해지는 가운데 엔캐리 거래가 다시 확산된다는 보도",
        "엔캐리 지속·재확산 압력": "미·일 금리차로 엔캐리 유인이 여전히 강하다는 보도",
        "일본 자금 해외투자 재확대·엔화 매도 압력": "일본 투자자의 해외자산 매수가 크게 늘며 엔화 매도 압력이 커졌다는 보도",
        "일본 자금 해외투자 확대·엔화 매도 압력": "일본 투자자의 해외자산 매수 확대가 엔화 약세 압력으로 작용한다는 보도",
        "개입 효과 약화·금리차 기반 엔화 약세": "개입 효과가 약해지고 미·일 금리차가 엔화 약세를 다시 밀어붙인다는 보도",
    }
    return mapping.get(topic, f"{topic} 관련 주요 보도")


def build_message(
    selected: list[tuple[base.ClassifiedItem, int, list[str]]], current: dt.datetime
) -> tuple[str, str, dict]:
    top_rank = max(rank for _, rank, _ in selected)
    prefix = "🚨" if top_rank >= 2 else "⚠️"
    title = f"{prefix} 엔화 수급 촉매 알림 — {base.rank_label(top_rank)}"
    body_lines = [
        f"조회 시각: {current.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "가격 급변 전후의 엔캐리·해외자금 흐름을 별도로 추적하는 수급 경보입니다.",
        "",
    ]
    payload_items: list[dict] = []
    for index, (classified, rank, groups) in enumerate(selected, start=1):
        item = classified.item
        original = base.clean_headline(item.title, item.source)
        headline_ko, translation_status = base.translate_headline_to_korean(
            item.title, item.source, classified.topic, current
        )
        if translation_status == "fallback_korean_summary":
            headline_ko = fallback_korean(classified.topic)
        body_lines.extend(
            [
                f"{index}) {classified.topic} · {base.rank_label(rank)}",
                f"출처: {item.source or classified.source_group} · {item.published.astimezone(KST).strftime('%m-%d %H:%M KST')}",
                f"헤드라인: {headline_ko}",
                f"교차확인: {', '.join(groups)}",
                *axis_lines(classified.topic),
                "",
            ]
        )
        payload_items.append(
            {
                "item_id": item.item_id,
                "topic": classified.topic,
                "material_score": classified.material_score,
                "rank": rank,
                "rank_label": base.rank_label(rank),
                "source": item.source,
                "source_group": classified.source_group,
                "corroborating_groups": groups,
                "headline_original": original,
                "headline_ko": headline_ko,
                "headline_translation_status": translation_status,
                "link": item.link,
                "published_at_kst": item.published.astimezone(KST).isoformat(timespec="seconds"),
            }
        )
    body_lines.append(
        "주의: 단순한 엔화 등락 기사는 제외하고, 캐리 재구축·금리차·해외자금 흐름 같은 구조적 근거가 있을 때만 전송합니다."
    )
    return title, "\n".join(body_lines).strip(), {"items": payload_items}


def pending_state(
    state: dict,
    selected: list[tuple[base.ClassifiedItem, int, list[str]]],
    current: dt.datetime,
) -> dict:
    updated = json.loads(json.dumps(state))
    seen = list(updated.get("seen_item_ids") or [])
    clusters = dict(updated.get("clusters") or {})
    for classified, rank, _groups in selected:
        item = classified.item
        if item.item_id not in seen:
            seen.append(item.item_id)
        clusters[base.topic_key(classified.topic)] = {
            "topic": classified.topic,
            "rank": rank,
            "material_score": classified.material_score,
            "sent_epoch": current.timestamp(),
            "headline": item.title,
            "source_group": classified.source_group,
        }
    updated["seen_item_ids"] = seen[-200:]
    updated["clusters"] = clusters
    updated["updated_at_kst"] = current.astimezone(KST).isoformat(timespec="seconds")
    return updated


def write_summary(status: str, candidates: int, errors: int) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        f"# 엔화 수급 촉매 감시\n- 상태: {status}\n- 유효 후보: {candidates}\n- 소스 오류: {errors}\n",
        encoding="utf-8",
    )


def process(current: dt.datetime | None = None) -> dict:
    current = (current or dt.datetime.now(UTC)).astimezone(UTC)
    items, errors = collect_items(current)
    classified = [result for item in items if (result := classify(item)) is not None]
    state = base.read_state(STATE_PATH)
    selected = base.select_alerts(classified, state, current)[:MAX_ALERT_ITEMS]
    if not selected:
        write_summary("새 수급 촉매 없음", len(classified), len(errors))
        return {"alerted": False, "candidates": len(classified), "errors": len(errors)}

    title, body, payload = build_message(selected, current)
    ALERT_TITLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERT_TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
    payload.update(
        {
            "yen_carry_news_alert": True,
            "checked_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
        }
    )
    base.write_json(ALERT_JSON_PATH, payload)
    base.write_json(PENDING_PATH, pending_state(state, selected, current))
    write_summary("수급 촉매 알림 생성", len(classified), len(errors))
    return {"alerted": True, "items": len(selected), "candidates": len(classified), "errors": len(errors)}


def finalize() -> bool:
    if not PENDING_PATH.exists() or not CONFIRM_PATH.exists():
        print("Yen carry news Telegram confirmation missing; pending state not finalized.")
        return False
    confirmation = base.read_state(CONFIRM_PATH)
    if confirmation.get("status") != "confirmed" or confirmation.get("lane") != "yen_carry_news":
        print("Yen carry news confirmation invalid; pending state not finalized.")
        return False
    pending = base.read_state(PENDING_PATH)
    base.write_json(STATE_PATH, pending)
    print(f"Finalized yen carry news state: {STATE_PATH}")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    result = {"finalized": finalize()} if args.finalize else process()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
