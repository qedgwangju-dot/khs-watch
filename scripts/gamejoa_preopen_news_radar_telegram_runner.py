#!/usr/bin/env python3
"""Telegram-first GAMEJOA preopen radar runner.

This keeps source collection in the strict runner, then renders only the
decision-ready Korean core radar for Telegram.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


STRICT_PATH = Path(__file__).with_name("gamejoa_preopen_news_radar_strict_runner.py")
spec = importlib.util.spec_from_file_location("gamejoa_strict_radar", STRICT_PATH)
strict = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(strict)
base = strict.base


def strip_news_suffix(title: str) -> str:
    return re.split(r"\s+-\s+", title or "", maxsplit=1)[0].strip()


def ko_place(value: str) -> str:
    return value.strip().replace(", ", "·").replace(" and ", "·")


def ko_local_dc_title(raw_title: str) -> str:
    title = strip_news_suffix(raw_title)
    patterns = [
        (r"^(?P<place>.+?) residents seek (?:a )?fall vote to block big data centers", "{place} 주민, 대형 데이터센터 차단 위한 가을 주민투표 추진"),
        (r"^(?P<place>.+?) City Council working to ban data centers", "{place} 시의회, 데이터센터 금지 추진"),
        (r"^(?P<place>.+?) City Council votes to pass data center moratorium.*", "{place} 시의회, 데이터센터 모라토리엄 통과"),
        (r"^(?P<place>.+?) to vote on (?P<months>\d+)-month pause for data center development", "{place}, 데이터센터 개발 {months}개월 중단안 표결 예정"),
        (r"^(?P<place>.+?) data center development pause approved by city council", "{place}, 시의회가 데이터센터 개발 일시중단 승인"),
        (r"^Metro Planning Commission backs two bills on data centers", "메트로 계획위원회, 데이터센터 관련 법안 2건 지지"),
        (r"^What.?s in Sen\. Brown.?s proposed .Residents First. data center legislation", "브라운 상원의 '주민 우선' 데이터센터 법안 내용 부각"),
    ]
    for pattern, template in patterns:
        match = re.search(pattern, title, re.I)
        if match:
            return template.format(**{k: ko_place(v) for k, v in match.groupdict().items()})
    if re.search(r"moratorium|pause", title, re.I):
        return "미국 지역 데이터센터 모라토리엄·개발 일시중단 움직임 확인"
    if re.search(r"ban|block", title, re.I):
        return "미국 지역 데이터센터 금지·차단 움직임 확인"
    if re.search(r"planning commission|public hearing|ordinance|permit|zoning", title, re.I):
        return "미국 지역 데이터센터 인허가·조례 일정 확인"
    return "미국 지역 데이터센터 규제 뉴스 확인"


def korean_title(alert: dict) -> str:
    original = alert.get("original_news") or alert.get("news") or ""
    sectors = alert.get("sectors") or []
    if alert.get("local_dc_policy"):
        return ko_local_dc_title(original)
    if "데이터센터/전력망/전력기기" in sectors:
        return "데이터센터·전력망 정책/수급 뉴스 확인"
    if "반도체/AI" in sectors:
        return "반도체·AI 밸류체인 고충격 뉴스 확인"
    if "관세/수출통제" in sectors:
        return "미국 관세·수출통제 정책 뉴스 확인"
    if "방산/정유/해운/지정학" in sectors:
        return "지정학·에너지 공급망 뉴스 확인"
    if "바이오/FDA" in sectors:
        return "바이오·FDA 이벤트 뉴스 확인"
    if "한국 직접 영향" in sectors:
        return "한국 기업 직접 영향 뉴스 확인"
    return strip_news_suffix(original)


def normalize_alert(alert: dict) -> dict:
    alert = dict(alert)
    alert["original_news"] = alert.get("original_news") or alert.get("news") or ""
    alert["news"] = korean_title(alert)
    return alert


def source_summary(items: list[dict]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        publisher = item.get("publisher") or "출처 확인 불가"
        counts[publisher] = counts.get(publisher, 0) + 1
    return " / ".join(f"{name} {count}건" if count > 1 else name for name, count in counts.items())


def compact_real_yield(fred: dict, te: dict) -> str:
    if fred.get("value") is None or te.get("value") is None:
        return "FRED/TE 중 일부 확인 불가"
    mismatch = abs(float(fred["value"]) - float(te["value"])) >= 0.03 or str(fred.get("reference")) != str(te.get("reference"))
    state = "지연/불일치" if mismatch else "교차확인"
    return f"{state}: DFII10 {fred['value']:.2f}%({fred.get('reference')}), TE TIPS {te['value']:.2f}%({te.get('reference')})"


def local_dc_cluster(alerts: list[dict]) -> dict | None:
    local_items = [a for a in alerts if a.get("local_dc_policy")]
    if len(local_items) < 2:
        return None
    examples = [
        {"title": item["news"], "publisher": item.get("publisher") or item.get("source") or "출처 확인 불가", "link": item.get("link") or ""}
        for item in local_items[:4]
    ]
    return {
        "score": max(int(a.get("score", 0)) for a in local_items),
        "importance": "상",
        "news": "미국 지역 데이터센터 금지·모라토리엄 확산",
        "impacts": ["시간표", "할인율"],
        "sectors": ["데이터센터/전력망/전력기기"],
        "interpretation": "지역 조례·주민투표·인허가 보류가 AI 데이터센터 CAPEX의 승인 시간표와 전력망 접속 프리미엄을 건드리는 신호입니다.",
        "counter": "개별 지역 이슈일 수 있어 공식 의사록·조례·투표일 확인 전에는 전국 CAPEX 둔화로 과대해석하지 않습니다.",
        "examples": examples,
        "cluster_count": len(local_items),
    }


def display_alerts(alerts: list[dict], limit: int) -> list[dict]:
    cluster = local_dc_cluster(alerts)
    if not cluster:
        return alerts[:limit]
    non_local = [a for a in alerts if not a.get("local_dc_policy")]
    return ([cluster] + non_local[: max(0, limit - 1)])[:limit]


def compact_alert(alert: dict, idx: int, now) -> str:
    examples = alert.get("examples") or []
    count_suffix = f" ({alert['cluster_count']}건 묶음)" if alert.get("cluster_count") else ""
    lines = [f"{idx}) [{alert['importance']}] {alert['news']}{count_suffix}"]
    if examples:
        lines.append("- 확인: " + " / ".join(item["title"] for item in examples[:4]))
        source_text = source_summary(examples[:4])
    else:
        source_text = alert.get("publisher") or alert.get("source") or "출처 확인 불가"
    lines += [
        f"- 영향: {'·'.join(alert['impacts'])} | 섹터: {', '.join(alert['sectors'])}",
        f"- 해석: {alert['interpretation']}",
        f"- 체크: {alert['counter']}",
        f"- 출처: {source_text} · 조회 {now:%H:%M KST}",
        "",
    ]
    return "\n".join(lines)


def compact_report(alerts: list[dict], fred: dict, te: dict, now) -> str:
    limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "5"))))
    visible = display_alerts(alerts, limit)
    title = f"장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
    lines = [title, f"조회: {now:%Y-%m-%d %H:%M KST}", f"선별: 핵심 {len(visible)}건", ""]
    if visible:
        for idx, alert in enumerate(visible, 1):
            lines.append(compact_alert(alert, idx, now))
        changed = "·".join(visible[0]["impacts"])
    else:
        lines += ["장전 고충격 뉴스 직접 확인 없음", ""]
        changed = "명확한 변화 없음"
    lines += [
        "💡 06:30 장전 뉴스 코멘트",
        f"오늘 핵심 변화는 `{changed}`입니다. 한국장에서는 관련 해외 티커 반응과 국내 수급 확산 여부를 먼저 확인합니다.",
        f"할인율: {compact_real_yield(fred, te)}",
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
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:base.TELEGRAM_LIMIT], "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        resp.read()
    print("Telegram: sent")


def main() -> int:
    now = base.kst_now()
    rows, notes = strict.collect_items(now)
    alerts = [normalize_alert(a) for a in (strict.classify(r, now) for r in rows if base.fresh(r, now)) if a]
    alerts.sort(key=lambda a: (-a["score"], a["published"]))

    deduped, seen = [], set()
    for alert in alerts:
        key = (base.norm(alert["original_news"]), base.norm(alert["publisher"]), alert["published"][:10])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)
        if len(deduped) >= 7:
            break

    local_candidates = [a for a in alerts if a.get("local_dc_policy")]
    for candidate in local_candidates:
        if sum(1 for a in deduped if a.get("local_dc_policy")) >= min(2, len(local_candidates)):
            break
        key = (base.norm(candidate["original_news"]), base.norm(candidate["publisher"]), candidate["published"][:10])
        if key in seen:
            continue
        if len(deduped) < 7:
            deduped.append(candidate)
            seen.add(key)

    deduped.sort(key=lambda a: (-a["score"], a["published"]))
    fred, te = base.collect_dfii10(), base.collect_te()
    report = compact_report(deduped, fred, te, now)

    base.OUT.mkdir(parents=True, exist_ok=True)
    (base.OUT / "gamejoa_preopen_news_radar.md").write_text(report, encoding="utf-8")
    (base.OUT / "gamejoa_preopen_news_radar_title.txt").write_text(report.splitlines()[0] + "\n", encoding="utf-8")
    (base.OUT / "gamejoa_preopen_news_radar.json").write_text(
        json.dumps({"query_time_kst": now.isoformat(timespec="seconds"), "alerts": deduped, "source_notes": notes, "fred_dfii10": fred, "tradingeconomics_tips": te}, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    base.print_utf8(report)
    if os.getenv("TELEGRAM_DRY_RUN", "").lower() in {"1", "true", "yes", "y"}:
        print("Telegram: dry run")
        return 0
    if os.getenv("SEND_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        send_telegram(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
