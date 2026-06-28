#!/usr/bin/env python3
"""Full-field compact Telegram renderer for the preopen news radar."""

from __future__ import annotations

import html
import os
import urllib.parse
import urllib.request

import gamejoa_preopen_news_radar_contract_runner as contract


telegram = contract.telegram
base = contract.base


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def enforce_semiconductor_cycle_contract() -> None:
    append_unique(base.QUERIES, [
        ("반도체 가격 사이클", "semiconductor selloff memory price DRAM NAND customer inventory capex valuation guidance Micron Samsung SK Hynix Reuters Bloomberg MarketWatch CNBC"),
        ("반도체 정책 드라이브", "semiconductor R&D tax credit tax deduction chip subsidy investment credit materials equipment components Korea Samsung SK Hynix 소부장 세액공제 Reuters Bloomberg 한국 정부"),
        ("미국 항만 파업", "US East Coast port strike ILA USMX contract expires October port labor negotiations freight rates shipping Reuters Bloomberg CNBC MarketWatch"),
        ("중국 부양 벌크선", "China stimulus iron ore coal dry bulk freight Baltic Dry Index bulk carrier rates Reuters Bloomberg CNBC MarketWatch"),
    ])
    append_unique(base.TERMS, [
        "customer inventory", "dram", "inventory", "memory price", "nand", "oversupply",
        "pricing", "selloff", "stock drop", "valuation",
        "chip subsidy", "component", "equipment", "investment credit", "materials", "r&d",
        "rd tax credit", "semiconductor tax credit", "subsidy", "tax credit", "tax deduction",
        "세액공제", "소부장",
        "baltic dry", "baltic dry index", "bdi", "bulk carrier", "coal", "dockworker",
        "dry bulk", "east coast port", "freight rate", "gulf coast port", "ila", "iron ore",
        "port labor", "port strike", "shipping rate", "stimulus", "strike", "usmx",
    ])
    for idx, (label, keys) in enumerate(base.SECTORS):
        if label == "반도체/AI":
            merged = list(keys)
            append_unique(merged, ["dram", "nand", "memory", "inventory", "valuation", "tax credit", "tax deduction", "subsidy", "materials", "equipment", "component", "세액공제", "소부장"])
            base.SECTORS[idx] = (label, merged)
            break
    if not any(label == "해운/항만/물류" for label, _ in base.SECTORS):
        base.SECTORS.append((
            "해운/항만/물류",
            ["port strike", "port labor", "dockworker", "ila", "usmx", "east coast port", "gulf coast port", "freight rate", "shipping rate"],
        ))
    if not any(label == "중국 경기부양/벌크선" for label, _ in base.SECTORS):
        base.SECTORS.append((
            "중국 경기부양/벌크선",
            ["china", "stimulus", "iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "baltic dry index", "bdi"],
        ))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
        alert = original_classify(row, now)
        port_terms = ["port strike", "port labor", "dockworker", "ila", "usmx", "east coast port", "gulf coast port", "contract expires", "freight rate", "shipping rate"]
        china_bulk_terms = ["china", "stimulus", "iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "baltic dry index", "bdi"]
        is_port_strike = any(base.has(text, term) for term in port_terms) and any(base.has(text, term) for term in ["port", "ila", "usmx", "dockworker"])
        is_china_bulk = base.has(text, "china") and base.has(text, "stimulus") and any(base.has(text, term) for term in ["iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "bdi"])

        if (is_port_strike or is_china_bulk) and not alert:
            age = base.age_hours(row, now)
            sectors = ["해운/항만/물류"] if is_port_strike else ["중국 경기부양/벌크선"]
            if is_china_bulk:
                sectors.append("해운/항만/물류")
            impacts = ["돈 버는 능력", "시간표"] if is_port_strike else ["돈 버는 능력"]
            score = 92 + (10 if age is not None and age <= 12 else 0)
            status = "확정" if row.get("layer") == "official" else "공식 확인 전"
            alert = {
                "score": score,
                "importance": "상" if score >= 100 else "중",
                "status": status,
                "news": base.clean(row.get("title")),
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": impacts,
                "paths": ["이익" if x == "돈 버는 능력" else "정책 타임라인" for x in impacts],
                "sectors": sectors,
                "matched": [],
                "local_dc_policy": False,
                "reflection": "낮음" if age is not None and age <= 6 else "중간",
                "counter": "제목·요약 기반 1차 감지라 원문 세부조건과 공식 문서 확인 전 과대해석 가능",
                "interpretation": "",
                "failed_signal": "",
                "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
            }

        if alert and is_port_strike:
            for impact in ["돈 버는 능력", "시간표"]:
                if impact not in alert["impacts"]:
                    alert["impacts"].append(impact)
            if "의사결정 영향 제한적" in alert["impacts"] and len(alert["impacts"]) > 1:
                alert["impacts"] = [x for x in alert["impacts"] if x != "의사결정 영향 제한적"]
            alert["paths"] = [
                "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
                for x in alert["impacts"]
            ]
            if "해운/항만/물류" not in alert["sectors"]:
                alert["sectors"].append("해운/항만/물류")
            alert["score"] = max(int(alert.get("score", 0)), 102)
            alert["importance"] = "상" if alert["score"] >= 100 else "중"
            alert["port_strike_risk"] = True
            alert["news"] = "미국 항만 파업 가능성: 10월 동부·걸프 항만 계약 만료 리스크"
            alert["interpretation"] = "미국 동부·걸프 항만 노조 계약 만료와 파업 가능성은 컨테이너 운임, 물류비, 납기 리스크를 동시에 흔드는 시간표 재료입니다."
            alert["failed_signal"] = "노사 협상 타결, 파업 유예, 항만 적체·컨테이너 운임 미반응, 우회 물류 차질 제한 시 재료 약화"

        if alert and is_china_bulk:
            if "돈 버는 능력" not in alert["impacts"]:
                alert["impacts"].append("돈 버는 능력")
            if "의사결정 영향 제한적" in alert["impacts"] and len(alert["impacts"]) > 1:
                alert["impacts"] = [x for x in alert["impacts"] if x != "의사결정 영향 제한적"]
            alert["paths"] = [
                "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
                for x in alert["impacts"]
            ]
            for sector in ["중국 경기부양/벌크선", "해운/항만/물류"]:
                if sector not in alert["sectors"]:
                    alert["sectors"].append(sector)
            alert["score"] = max(int(alert.get("score", 0)), 100)
            alert["importance"] = "상" if alert["score"] >= 100 else "중"
            alert["china_stimulus_bulk"] = True
            alert["news"] = "중국 경기부양책: 철광석·석탄 물동량과 벌크선 운임 회복 기대"
            alert["interpretation"] = "중국 추가 부양책은 철광석·석탄 물동량 회복 기대를 통해 벌크선 운임과 해운주 이익 추정에 연결될 수 있습니다."
            alert["failed_signal"] = "부양책이 부동산·인프라 실물 수요로 연결되지 않거나 철광석·석탄 가격, BDI, 벌크선 운임이 동행하지 않으면 기대 약화"

        if alert and "반도체/AI" in alert.get("sectors", []):
            selloff_terms = ["selloff", "stock drop", "memory price", "customer inventory", "oversupply", "valuation"]
            policy_terms = ["tax credit", "tax deduction", "investment credit", "chip subsidy", "subsidy", "r&d", "rd tax credit", "semiconductor tax credit", "세액공제", "소부장"]
            if any(base.has(text, term) for term in policy_terms):
                for impact in ["돈 버는 능력", "시간표"]:
                    if impact not in alert["impacts"]:
                        alert["impacts"].append(impact)
                alert["paths"] = [
                    "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
                    for x in alert["impacts"]
                ]
                alert["score"] = max(int(alert.get("score", 0)), 94)
                alert["importance"] = "상" if alert["score"] >= 100 else "중"
                alert["policy_drive"] = True
                alert["interpretation"] = "반도체 R&D 세액공제 확대는 직접 매출보다 연구개발·투자 현금흐름과 정책 타임라인을 바꾸는 재료입니다. 소부장으로 온기가 확산되는지는 세액공제 대상, 적용 시점, 국내 장비·소재 발주 연결성을 확인해야 합니다."
                alert["failed_signal"] = "세액공제 확대가 법안·시행령·예산으로 확정되지 않거나 소부장 발주·수주·CAPEX 증가로 연결되지 않으면 정책 기대에 그칠 수 있음"
            elif any(base.has(text, term) for term in selloff_terms):
                alert["interpretation"] = (
                    "반도체 급락은 가격 사이클 하나로만 보지 않고 메모리 가격, 고객사 재고, "
                    "설비투자, 밸류에이션 부담이 동시에 흔들리는지 확인합니다."
                )
                alert["failed_signal"] = (
                    "메모리 가격·고객사 재고·CAPEX·밸류에이션 중 복수 축의 악화가 확인되지 않거나 "
                    "SOX/MU/NVDA/삼성전자·SK하이닉스 반응이 제한되면 일회성 조정 가능"
                )
        return alert

    contract.strict.classify = classify


enforce_semiconductor_cycle_contract()


def safe(value: object) -> str:
    return html.escape(str(value or "확인 불가"), quote=False)


def html_link(label: str, url: str) -> str:
    text = html.escape(label or "출처", quote=False)
    if not url:
        return text
    return f'<a href="{html.escape(url, quote=True)}">{text}</a>'


def source_summary(items: list[dict]) -> str:
    grouped: dict[str, dict[str, object]] = {}
    for item in items:
        publisher = item.get("publisher") or "출처 확인 불가"
        if publisher not in grouped:
            grouped[publisher] = {"count": 0, "link": item.get("link") or ""}
        grouped[publisher]["count"] = int(grouped[publisher]["count"]) + 1
        if not grouped[publisher]["link"] and item.get("link"):
            grouped[publisher]["link"] = item.get("link")
    parts = []
    for publisher, meta in grouped.items():
        label = f"{publisher} {meta['count']}건" if int(meta["count"]) > 1 else publisher
        parts.append(html_link(label, str(meta.get("link") or "")))
    return " / ".join(parts) if parts else "출처 확인 불가"


def related_text(alert: dict, fred: dict, te: dict) -> str:
    extra = []
    if "해운/항만/물류" in alert.get("sectors", []):
        extra += ["SCFI", "Drewry WCI", "BDI", "컨테이너 운임", "벌크선 운임"]
    if "중국 경기부양/벌크선" in alert.get("sectors", []):
        extra += ["Iron Ore", "Coal", "BDI", "벌크선 운임", "중국 인프라/부동산 지표"]
    try:
        base_text = base.related(alert, fred, te)
        base_parts = [] if base_text == "확인 가능한 직접 티커 없음" else [part.strip() for part in base_text.split(",") if part.strip()]
        return ", ".join(dict.fromkeys(base_parts + extra)) or "확인 가능한 직접 지표 없음"
    except Exception:
        out = []
        if "데이터센터/전력망/전력기기" in alert.get("sectors", []):
            out += ["VRT", "ETN", "GEV", "CEG", "SMH"]
        if "반도체/AI" in alert.get("sectors", []):
            out += ["NVDA", "MU", "AVGO", "AMD", "TSM", "ASML"]
        out += extra
        if "할인율" in alert.get("impacts", []):
            out += [
                f"DFII10 {fred.get('value') if fred.get('value') is not None else '확인 불가'}",
                f"TE TIPS {te.get('value') if te.get('value') is not None else '확인 불가'}",
                "IWM/SPY",
            ]
        return ", ".join(dict.fromkeys(out)) or "확인 가능한 직접 지표 없음"


def semiconductor_cycle_check(alert: dict) -> str | None:
    if "반도체/AI" not in alert.get("sectors", []):
        return None
    return "메모리 가격·고객사 재고·CAPEX·밸류에이션 부담 동시 악화 여부"


def semiconductor_policy_check(alert: dict) -> str | None:
    if not alert.get("policy_drive"):
        return None
    return "R&D 세액공제 대상·시행 시점·소부장 발주/수주 연결성"


def port_strike_check(alert: dict) -> str | None:
    if not alert.get("port_strike_risk"):
        return None
    return "ILA/USMX 계약 만료·협상 결렬 여부·동부/걸프 항만 차질·컨테이너 운임"


def china_bulk_check(alert: dict) -> str | None:
    if not alert.get("china_stimulus_bulk"):
        return None
    return "중국 부양책 실물 강도·철광석/석탄 물동량·BDI/벌크선 운임 동행"


def display_news(alert: dict) -> str:
    if alert.get("port_strike_risk"):
        return "미국 항만 파업 가능성: 10월 동부·걸프 항만 계약 만료 리스크"
    if alert.get("china_stimulus_bulk"):
        return "중국 경기부양책: 철광석·석탄 물동량과 벌크선 운임 회복 기대"
    return alert.get("news") or "뉴스 제목 확인 불가"


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    examples = alert.get("examples") or []
    count_suffix = f" ({alert['cluster_count']}건 묶음)" if alert.get("cluster_count") else ""
    status = alert.get("status") or ("공식 확인 전" if examples else "확인 불가")
    basis = alert.get("korea_basis") or ("외신/지역 뉴스 확산" if examples else "외신 확산")
    impacts = alert.get("impacts") or ["의사결정 영향 제한적"]
    paths = alert.get("paths") or ["정책 타임라인" if impact == "시간표" else impact for impact in impacts]
    sectors = alert.get("sectors") or ["영향 섹터 확인 불가"]
    published = alert.get("published") or ("여러 건" if examples else "확인 불가")
    reflection = alert.get("reflection") or "중간"
    counter = alert.get("counter") or "원문 세부조건과 공식 문서 확인 전 과대해석 가능"
    interpretation = alert.get("interpretation") or "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는지 확인해야 합니다."
    failed_signal = alert.get("failed_signal") or "관련 가격·수급·공식 후속 확인이 동행하지 않으면 단발성 뉴스"

    lines = [f"{idx}) [{safe(alert.get('importance'))} | {safe(status)}] {safe(display_news(alert))}{html.escape(count_suffix, quote=False)}"]
    if examples:
        lines.append("- 확인: " + safe(" / ".join(item["title"] for item in examples[:4])))
        source_text = source_summary(examples[:4])
    else:
        source_text = html_link(alert.get("publisher") or alert.get("source") or "출처 확인 불가", alert.get("link") or "")

    lines += [
        f"- 기준/타임라인: {safe(basis)} | 원천 {safe(published)} · 확산 {now:%H:%M KST}",
        f"- 영향/경로: {safe('·'.join(impacts))} | {safe('·'.join(paths))}",
        f"- 섹터/지표: {safe(', '.join(sectors))} | {safe(related_text(alert, fred, te))}",
        f"- 반영/반대: {safe(reflection)} | {safe(counter)}",
        f"- 해석: {safe(interpretation)}",
    ]
    semi_check = semiconductor_cycle_check(alert)
    policy_check = semiconductor_policy_check(alert)
    port_check = port_strike_check(alert)
    bulk_check = china_bulk_check(alert)
    if policy_check:
        lines.append(f"- 반도체 정책 체크: {safe(policy_check)}")
    elif semi_check:
        lines.append(f"- 반도체 급락 체크: {safe(semi_check)}")
    if port_check:
        lines.append(f"- 항만 파업 체크: {safe(port_check)}")
    if bulk_check:
        lines.append(f"- 중국 부양·벌크선 체크: {safe(bulk_check)}")
    lines += [
        f"- 실패 신호: {safe(failed_signal)}",
        f"- 출처: {source_text} · 조회 {now:%H:%M KST}",
        "",
    ]
    return "\n".join(lines)


def compact_report(alerts: list[dict], fred: dict, te: dict, now) -> str:
    limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "5"))))
    visible = telegram.display_alerts(alerts, limit)
    title = f"장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
    lines = [title, f"조회: {now:%Y-%m-%d %H:%M KST}", f"선별: 핵심 {len(visible)}건", ""]
    if visible:
        for idx, alert in enumerate(visible, 1):
            lines.append(compact_alert(alert, idx, now, fred, te))
        changed = "·".join(visible[0].get("impacts") or ["명확한 변화 없음"])
    else:
        lines += ["장전 고충격 뉴스 직접 확인 없음", ""]
        changed = "명확한 변화 없음"
    lines += [
        "💡 06:30 장전 뉴스 코멘트",
        f"오늘 핵심 변화는 `{safe(changed)}`입니다. 한국장에서는 관련 해외 티커 반응과 국내 수급 확산 여부를 먼저 확인합니다.",
        f"할인율: {safe(telegram.compact_real_yield(fred, te))}",
        "06:50 투자기상도에서 수치·수급·테마와 재확인 필요.",
        "",
        "투자 조언이 아닌 참고용 뉴스 브리핑입니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:base.TELEGRAM_LIMIT],
        "disable_web_page_preview": "true",
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        resp.read()
    print("Telegram: sent")


telegram.compact_report = compact_report
telegram.send_telegram = send_telegram


if __name__ == "__main__":
    raise SystemExit(telegram.main())
