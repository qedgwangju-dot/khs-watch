#!/usr/bin/env python3
"""Memory antitrust/class-action overlay for the preopen radar."""

from __future__ import annotations

import gamejoa_preopen_news_radar_korea_nuclear_siting_runner as current


runner = current.runner
base = current.base
contract = current.contract
telegram = current.telegram

MEMORY_ANTITRUST_SECTOR = "메모리/반독점 소송"
MEMORY_ANTITRUST_QUERY = (
    "메모리 반독점 집단소송",
    "Samsung SK Hynix Micron DRAM memory antitrust class action lawsuit price fixing collusion Justia docket California federal court HBM DDR3 DDR4",
)
MEMORY_ANTITRUST_COMPANY_TERMS = [
    "samsung", "samsung electronics", "삼성", "삼성전자",
    "sk hynix", "sk하이닉스", "sk 하이닉스", "hynix", "하이닉스",
    "micron", "마이크론",
]
MEMORY_ANTITRUST_MEMORY_TERMS = [
    "dram", "ddr3", "ddr4", "hbm", "memory", "memory price", "메모리", "디램",
]
MEMORY_ANTITRUST_LEGAL_TERMS = [
    "antitrust", "class action", "collusion", "colluding", "complaint", "lawsuit",
    "litigation", "price fixing", "sherman act", "15 u.s.c", "담합", "가격 고정",
    "가격담합", "반독점", "소송", "소송장", "집단소송",
]
MEMORY_ANTITRUST_DOCKET_TERMS = [
    "5:2026cv06345", "5:26-cv-06345", "candce", "california federal court",
    "courtlistener", "docket", "federal court", "justia", "n.d. cal", "pacer",
    "garciaguirre", "도켓", "법원", "연방법원",
]
MEMORY_ANTITRUST_CHECK = (
    "도켓/사건번호·피고·청구근거 확인, 담합 주장은 원고 측 주장으로 분리, "
    "DOJ/FTC 확산·DRAM 가격 정상화·기업 가이던스 영향 확인"
)
MEMORY_ANTITRUST_EXTRA_COMMENT = (
    "D램 담합 소송은 단기 실적 훼손 요인이라기보다 과점 공급 조절에 대한 규제 리스크가 "
    "재부각된 이벤트입니다. 과거 2018년 유사 소송은 기각됐기 때문에 현재 단계에서 과도한 "
    "악재 반영은 경계하되, 규제기관 조사나 직접 구매자 소송으로 확대될 경우 메모리 업체들의 "
    "밸류에이션 멀티플에는 부담이 될 수 있습니다."
)


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def has_memory_antitrust_text(text: str) -> bool:
    has_samsung = has_any(text, ["samsung", "samsung electronics", "삼성", "삼성전자"])
    has_hynix = has_any(text, ["sk hynix", "sk하이닉스", "sk 하이닉스", "hynix", "하이닉스"])
    has_micron = has_any(text, ["micron", "마이크론"])
    return (
        has_samsung
        and has_hynix
        and has_micron
        and has_any(text, MEMORY_ANTITRUST_MEMORY_TERMS)
        and has_any(text, MEMORY_ANTITRUST_LEGAL_TERMS)
    )


def has_memory_antitrust_docket(text: str) -> bool:
    return has_any(text, MEMORY_ANTITRUST_DOCKET_TERMS)


def is_memory_antitrust_row(row: dict) -> bool:
    text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')} {row.get('link')}")
    return has_memory_antitrust_text(text)


def enforce_memory_antitrust_watch() -> None:
    append_unique(base.QUERIES, [MEMORY_ANTITRUST_QUERY])
    append_unique(
        base.TERMS,
        MEMORY_ANTITRUST_COMPANY_TERMS
        + MEMORY_ANTITRUST_MEMORY_TERMS
        + MEMORY_ANTITRUST_LEGAL_TERMS
        + MEMORY_ANTITRUST_DOCKET_TERMS,
    )
    append_unique(base.TRUSTED, ["courtlistener", "justia", "law360", "law.com"])
    if not any(label == MEMORY_ANTITRUST_SECTOR for label, _ in base.SECTORS):
        base.SECTORS.append((
            MEMORY_ANTITRUST_SECTOR,
            MEMORY_ANTITRUST_COMPANY_TERMS + MEMORY_ANTITRUST_MEMORY_TERMS + MEMORY_ANTITRUST_LEGAL_TERMS + MEMORY_ANTITRUST_DOCKET_TERMS,
        ))

    original_collect_items = contract.strict.collect_items

    def collect_items(now):
        rows, notes = original_collect_items(now)
        text, err = base.fetch(base.google_url(f"{MEMORY_ANTITRUST_QUERY[1]} when:{max(1, base.MAX_AGE_HOURS // 24)}d"))
        if err:
            notes.append(f"Trusted news {MEMORY_ANTITRUST_QUERY[0]}: 확인 불가 ({err})")
            return rows, notes
        existing_links = {row.get("link") for row in rows if row.get("link")}
        parsed = [
            row for row in base.parse_rss(text or "", f"Trusted news {MEMORY_ANTITRUST_QUERY[0]}", "trusted")
            if base.fresh(row, now) and is_memory_antitrust_row(row) and row.get("link") not in existing_links
        ]
        notes.append(f"Trusted news {MEMORY_ANTITRUST_QUERY[0]}: {len(parsed)}건")
        rows.extend(parsed)
        return rows, notes

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        alert = original_classify(row, now)
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')} {row.get('link')}")
        if not has_memory_antitrust_text(text):
            return alert

        docketed = (
            has_memory_antitrust_docket(text)
            or row.get("layer") == "official"
            or base.trusted(row.get("publisher") or row.get("source"))
        )
        age = base.age_hours(row, now)
        if not alert:
            alert = {
                "score": 112 if docketed else 104,
                "importance": "상",
                "status": "확정" if docketed else "공식 확인 전",
                "news": "메모리 반독점 소송: 삼성전자·SK하이닉스·Micron DRAM 가격담합 집단소송",
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": ["돈 버는 능력", "할인율", "시간표"],
                "paths": ["이익", "할인율", "정책/소송 타임라인"],
                "sectors": [MEMORY_ANTITRUST_SECTOR, "반도체/AI", "한국 직접 영향"],
                "matched": [],
                "local_dc_policy": False,
                "reflection": "낮음" if age is not None and age <= 6 else "중간",
                "counter": "",
                "interpretation": "",
                "failed_signal": "",
                "korea_basis": "새 뉴스",
            }

        alert["memory_antitrust_lawsuit"] = True
        alert["memory_antitrust_docketed"] = docketed
        alert["news"] = "메모리 반독점 소송: 삼성전자·SK하이닉스·Micron DRAM 가격담합 집단소송"
        alert["score"] = max(int(alert.get("score", 0)), 112 if docketed else 104)
        alert["importance"] = "상" if int(alert["score"]) >= 100 else "중"
        alert["status"] = "확정" if docketed else "공식 확인 전"
        alert["korea_basis"] = "새 뉴스"
        alert["impacts"] = ["돈 버는 능력", "할인율", "시간표"]
        alert["paths"] = ["이익", "할인율", "정책/소송 타임라인"]
        alert["sectors"] = [MEMORY_ANTITRUST_SECTOR, "반도체/AI", "한국 직접 영향"]
        alert["counter"] = (
            "소장 제기는 확인 가능한 이벤트지만 담합·가격고정은 원고 측 주장입니다. "
            "법원 판단, DOJ/FTC 조사, 가격 정상화로 바로 연결된 것은 아닙니다."
        )
        alert["interpretation"] = (
            "HBM 전환을 이유로 범용 DRAM 공급을 낮게 유지했다는 집단소송은 메모리 슈퍼사이클의 "
            "마진 지속성 논리를 법적 리스크로 되묻는 재료입니다. 소송 자체보다 도켓, DOJ/FTC 확산 여부, "
            "DRAM 가격과 MU·삼성전자·SK하이닉스 반응을 함께 봐야 합니다."
        )
        alert["failed_signal"] = (
            "Justia/PACER/CourtListener 도켓 확인이 없거나 소송 각하·합의 지연, DOJ/FTC 미확산, "
            "DRAM 현물/계약가격과 MU·삼성전자·SK하이닉스 주가 반응이 없으면 단기 재료 약화"
        )
        alert["memory_antitrust_check"] = MEMORY_ANTITRUST_CHECK
        alert["memory_antitrust_extra_comment"] = MEMORY_ANTITRUST_EXTRA_COMMENT
        return alert

    contract.strict.collect_items = collect_items
    contract.strict.classify = classify


ORIGINAL_RELATED_TEXT = runner.related_text
ORIGINAL_DISPLAY_NEWS = runner.display_news
ORIGINAL_COMPACT_ALERT = runner.compact_alert


def related_text(alert: dict, fred: dict, te: dict) -> str:
    text = ORIGINAL_RELATED_TEXT(alert, fred, te)
    if alert.get("memory_antitrust_lawsuit") or MEMORY_ANTITRUST_SECTOR in alert.get("sectors", []):
        extra = [
            "005930.KS 삼성전자", "000660.KS SK하이닉스", "MU", "DRAM 현물/계약가격",
            "TrendForce/DRAMeXchange", "Justia/PACER", "DOJ/FTC",
        ]
        empty_markers = {"확인 가능한 직접 티커 없음", "확인 가능한 직접 지표 없음"}
        parts = [] if text in empty_markers else [part.strip() for part in text.split(",") if part.strip() and part.strip() not in empty_markers]
        return ", ".join(dict.fromkeys(parts + extra))
    return text


def display_news(alert: dict) -> str:
    if alert.get("memory_antitrust_lawsuit"):
        return "메모리 반독점 소송: 삼성전자·SK하이닉스·Micron DRAM 가격담합 집단소송"
    return ORIGINAL_DISPLAY_NEWS(alert)


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    text = ORIGINAL_COMPACT_ALERT(alert, idx, now, fred, te)
    if alert.get("memory_antitrust_lawsuit") and "메모리 반독점 체크:" not in text:
        marker = "\n- 실패 신호:"
        check = f"\n- 메모리 반독점 체크: {alert.get('memory_antitrust_check') or MEMORY_ANTITRUST_CHECK}"
        extra = f"\n- 추가 코멘트: {alert.get('memory_antitrust_extra_comment') or MEMORY_ANTITRUST_EXTRA_COMMENT}"
        return text.replace(marker, check + extra + marker, 1)
    if alert.get("memory_antitrust_lawsuit") and "추가 코멘트:" not in text:
        marker = "\n- 실패 신호:"
        extra = f"\n- 추가 코멘트: {alert.get('memory_antitrust_extra_comment') or MEMORY_ANTITRUST_EXTRA_COMMENT}"
        return text.replace(marker, extra + marker, 1)
    return text


enforce_memory_antitrust_watch()
runner.related_text = related_text
runner.display_news = display_news
runner.compact_alert = compact_alert


if __name__ == "__main__":
    raise SystemExit(telegram.main())
