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
    try:
        return base.related(alert, fred, te)
    except Exception:
        out = []
        if "데이터센터/전력망/전력기기" in alert.get("sectors", []):
            out += ["VRT", "ETN", "GEV", "CEG", "SMH"]
        if "반도체/AI" in alert.get("sectors", []):
            out += ["NVDA", "MU", "AVGO", "AMD", "TSM", "ASML"]
        if "할인율" in alert.get("impacts", []):
            out += [
                f"DFII10 {fred.get('value') if fred.get('value') is not None else '확인 불가'}",
                f"TE TIPS {te.get('value') if te.get('value') is not None else '확인 불가'}",
                "IWM/SPY",
            ]
        return ", ".join(dict.fromkeys(out)) or "확인 가능한 직접 지표 없음"


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

    lines = [f"{idx}) [{safe(alert.get('importance'))} | {safe(status)}] {safe(alert.get('news'))}{safe(count_suffix)}"]
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
