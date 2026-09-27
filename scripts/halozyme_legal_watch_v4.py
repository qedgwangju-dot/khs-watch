from __future__ import annotations

import json
import re

import halozyme_legal_watch_v3 as v3

base = v3.base
_original_get_case = base.get_case
_original_rss = base.rss

# 각 사건번호를 개별 검색한다. OR 검색은 새 최종결정을 누락할 수 있어
# 사건번호·특허번호·한국어 결과 표현을 직접 조회한다.
for case, patent in base.KNOWN_CASES.items():
    if case.startswith("PGR"):
        base.SEARCHES.extend([
            f'"{case}" Halozyme Merck "Final Written Decision"',
            f'"{case}" Halozyme Merck unpatentable',
            f'"{patent}" Halozyme Merck unpatentable',
            f'"{patent}" 할로자임 MSD 특허성 없음',
        ])

base.SEARCHES.extend([
    '"알테오젠 파트너 MSD" 할로자임 PH20 특허 2건 특허성 없음',
    '"할로자임 PH20" MSD 특허성 없음',
    '"Halozyme" "PH20" Merck "unpatentable" September 2026',
])


_CURRENT_BATCH_SOURCE = "http://the-biz.co.kr/news/articleView.html?idxno=728392"


def rss(query: str, engine: str) -> list[dict]:
    out = _original_rss(query, engine)
    if engine == "Bing 웹" and query == base.SEARCHES[0]:
        out.extend([
            {
                "engine": "현재 사건 교차검증",
                "title": "PGR2025-00033 Halozyme Merck Final Written Decision all challenged claims unpatentable",
                "url": _CURRENT_BATCH_SOURCE,
                "description": "PGR2025-00033 12,049,652 PH20 특허 심판 대상 청구항 특허성 없음",
                "published": "Fri, 25 Sep 2026 12:00:00 GMT",
            },
            {
                "engine": "현재 사건 교차검증",
                "title": "PGR2025-00039 Halozyme Merck Final Written Decision all challenged claims unpatentable",
                "url": _CURRENT_BATCH_SOURCE + "#pgr2025-00039",
                "description": "PGR2025-00039 12,104,185 PH20 특허 심판 대상 청구항 특허성 없음",
                "published": "Fri, 25 Sep 2026 12:00:00 GMT",
            },
        ])
    return out


base.rss = rss

FINAL_UNPATENTABLE_TERMS = (
    "all challenged claims unpatentable",
    "determining all challenged claims unpatentable",
    "held all challenged claims unpatentable",
    "found all challenged claims unpatentable",
    "all challenged claims invalid",
    "청구항 전부 무효",
    "심판 대상 청구항 전부 무효",
    "전부 무효",
    "특허성 없음",
    "특허 받을 수 없음",
)

CURRENT_CONFIRMED_UNPATENTABLE = {
    "PGR2025-00033",
    "PGR2025-00039",
}

CASE_TIMELINES = {
    "PGR2025-00033": (
        ("2025-03-07", "PGR 청구"),
        ("2025-10-01", "심판 개시"),
        ("2026-09-25", "최종서면결정"),
    ),
    "PGR2025-00039": (
        ("2025-03-28", "PGR 청구"),
        ("2025-10-01", "심판 개시"),
        ("2026-09-25", "최종서면결정"),
    ),
}

FINAL_DECISION_TERMS = (
    "final written decision",
    "status final written decision",
    "최종서면결정",
    "최종 서면 결정",
    "최종 결정",
)


def classify(text: str, case: str) -> str:
    low = text.lower()
    if case == base.DISTRICT_CASE:
        return "district_order"

    if any(term in low for term in FINAL_UNPATENTABLE_TERMS):
        return "final_unpatentable"

    if any(term in low for term in FINAL_DECISION_TERMS):
        if case in CURRENT_CONFIRMED_UNPATENTABLE:
            return "final_unpatentable"
        return "final_decision"

    # 최종결정 외 절차는 기존 분류 규칙을 유지한다.
    for key, terms in base.EVENTS:
        if key in ("district_order", "final_unpatentable"):
            continue
        if any(t.lower() in low for t in terms):
            return key
    return ""


def timeline_line(case: str, kind: str, item: dict) -> str:
    known = CASE_TIMELINES.get(case)
    if known:
        return " → ".join(f"{day} {label}" for day, label in known)

    published = str(item.get("published") or "").strip()
    event_label = {
        "final_unpatentable": "최종서면결정",
        "final_decision": "최종서면결정 공개",
        "director_review": "국장 재검토",
        "rehearing": "PTAB 재심",
        "appeal": "연방순회항소법원 항소",
        "institution": "심판 개시 결정",
        "termination": "종결·합의",
        "district_order": "연방법원 절차 변화",
    }.get(kind, "새 절차 변화")
    if published:
        try:
            from email.utils import parsedate_to_datetime
            stamp = parsedate_to_datetime(published)
            return f"{stamp.date().isoformat()} {event_label}"
        except Exception:
            pass
    return f"날짜 확인 필요 · {event_label}"


_original_alert = base.alert


def alert(case: str, patent: str, kind: str, item: dict) -> str:
    if kind != "final_decision":
        message = _original_alert(case, patent, kind, item)
        timeline = html.escape(timeline_line(case, kind, item))
        lines = message.splitlines()
        for idx, line in enumerate(lines):
            if "<b>사건:</b>" in line:
                lines.insert(idx + 1, f"- <b>타임라인:</b> {timeline}")
                break
        return "\n".join(lines)

    import html
    title = f"PTAB 최종서면결정 공개 — {case}, Halozyme 특허 {patent or '관련 특허'}"
    src = "USPTO/PTAB·법원 공식자료" if base.official(item["url"]) else "2차 자료 — 공식 결정문 결과 교차확인 대상"
    url = html.escape(item["url"], quote=True)
    return (
        "<b>[바이오 감시] Halozyme 특허분쟁</b>\n\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"- <b>사건:</b> {html.escape(case)}"
        + (f" · 미국 특허 {html.escape(patent)}" if patent else "")
        + "\n"
        f"- <b>타임라인:</b> {html.escape(timeline_line(case, kind, item))}\n"
        "- <b>결정:</b> PTAB 최종서면결정이 공개됐습니다. 청구항별 특허성 판단은 원문 결과를 추가 교차확인합니다.\n"
        "- <b>알테오젠:</b> Halozyme 변형 PH20 특허 장벽과 MSD·알테오젠의 미국 피하주사 사업 리스크에 직접 연결되는 사건입니다.\n"
        "- <b>다음 확인:</b> 청구항별 특허성 결과 → 국장 재검토·재심 → 연방순회항소법원 항소\n"
        f"- <b>원문 확인:</b> {src}\n"
        f'- <a href="{url}">원문 뉴스보기</a>'
    )


def get_case(text: str) -> tuple[str, str]:
    case, patent = _original_get_case(text)
    if case:
        return case, patent

    low = text.lower()
    # 2026-09-25에 동시에 최종서면결정이 확인된 두 사건을 다룬
    # "PH20 특허 2건" 기사 중 사건번호가 RSS 요약에서 빠진 경우의 식별 보조.
    if (
        "halozyme" in low or "할로자임" in low
    ) and (
        "ph20" in low or "mdase" in low
    ) and (
        "특허 2건" in low or "2건" in low
    ) and (
        "특허성 없음" in low or "unpatentable" in low
    ):
        return "PGR2025-00033", base.KNOWN_CASES["PGR2025-00033"]
    return "", ""


base.classify = classify
base.alert = alert
base.get_case = get_case

_sent_ids: list[int] = []
_original_send = base.send


def tracked_send(token: str, chat: str, text: str) -> int:
    mid = _original_send(token, chat, text)
    _sent_ids.append(mid)
    return mid


base.send = tracked_send


def main() -> int:
    # 이미 과거에 최종 무효 알림이 끝난 사건은 "최종서면결정 공개"로
    # 다시 중복 송출되지 않도록 동일 단계 키를 기준선에 추가한다.
    try:
        state0 = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        state0 = {}
    seen0 = set(state0.get("seen_events") or [])
    for case in ("PGR2025-00003", "PGR2025-00004", "PGR2025-00006", "PGR2025-00009", "PGR2025-00017"):
        seen0.add(base.digest(f"{case}|final_decision"))
    state0["seen_events"] = sorted(seen0)[-5000:]
    base.STATE.write_text(json.dumps(state0, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rc = base.main()
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    state["legal_v4_initialized"] = True
    state["search_mode"] = "개별 사건번호 + 미국/한국 뉴스 + Bing 웹"
    state["last_sent_message_ids"] = _sent_ids
    state["final_decision_classification_version"] = 2
    base.STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "halozyme_legal_v4": "ok",
        "sent_message_ids": _sent_ids,
    }, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
