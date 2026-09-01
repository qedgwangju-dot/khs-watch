from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    import korea_grid_policy_watch as base
except ModuleNotFoundError:
    from scripts import korea_grid_policy_watch as base

EVENT_STATE_PATH = Path("data/korea_grid_policy_event_state.json")
KST = base.KST
STALE_DISCOVERY_DAYS = 30


def canonical_title(value: str) -> str:
    text = base.normalize(value).lower()
    text = re.sub(r"\s+-\s+(기후에너지환경부|한국전력|kepco\.co\.kr|국가법령정보센터)\s*$", "", text)
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return " ".join(text.split())


def event_key(item: dict[str, Any]) -> str:
    title = canonical_title(str(item.get("title", "")))
    return base.digest(f"grid-event|{title}")


def source_priority(item: dict[str, Any]) -> int:
    source = str(item.get("source", ""))
    url = str(item.get("url", ""))
    if source in {"기후에너지환경부", "한국전력", "국가법령정보센터"}:
        return 100
    if "mcee.go.kr" in url or "kepco.co.kr" in url or "law.go.kr" in url:
        return 90
    if "공식 검색" in source:
        return 60
    return 10


def collapse_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(event_key(item), []).append(item)

    result: list[dict[str, Any]] = []
    for key, members in grouped.items():
        best = max(
            members,
            key=lambda x: (
                source_priority(x),
                1 if str(x.get("published", "")) else 0,
                int(x.get("stage", 0)),
            ),
        ).copy()
        best["event_key"] = key
        result.append(best)
    return result


def resolve_google_news_url(url: str) -> str:
    url = base.normalize(url)
    if not url or "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import new_decoderv1

        result = new_decoderv1(url, interval=0.15)
        if isinstance(result, dict) and result.get("status") and result.get("decoded_url"):
            return str(result["decoded_url"]).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"grid_google_news_decode_failed={type(exc).__name__}")
    try:
        response = requests.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        if response.url and "news.google.com" not in response.url:
            return response.url
    except Exception as exc:  # noqa: BLE001
        print(f"grid_google_news_redirect_failed={type(exc).__name__}")
    return url


def extract_official_date(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    patterns = (
        r"(?:작성일|작성일자|등록일|등록일자|게시일|공고일)\s*[:：]?\s*(20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})",
        r"(20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def article_text(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    for node in soup.select("script, style, noscript, nav, footer, header, aside"):
        node.decompose()
    candidates: list[str] = []
    for selector in ("article", "#content", ".view_cont", ".board_view", ".view-content", "main"):
        for node in soup.select(selector):
            text = " ".join(node.get_text(" ", strip=True).split())
            if len(text) > len(" ".join(candidates)):
                candidates = [text]
    if candidates:
        return candidates[0]
    return " ".join(soup.get_text(" ", strip=True).split())


def normalize_source_from_url(url: str, fallback: str) -> str:
    host = urlparse(url).netloc.lower()
    if "mcee.go.kr" in host or "me.go.kr" in host:
        return "기후에너지환경부"
    if "kepco.co.kr" in host:
        return "한국전력"
    if "law.go.kr" in host:
        return "국가법령정보센터"
    return fallback.replace(" 공식 검색", "")


def enrich_item(item: dict[str, Any], session: requests.Session) -> dict[str, Any]:
    result = item.copy()
    original_url = str(result.get("url", ""))
    resolved = resolve_google_news_url(original_url)
    if resolved:
        result["url"] = resolved
        result["source"] = normalize_source_from_url(resolved, str(result.get("source", "")))
    if resolved and "news.google.com" not in resolved:
        try:
            response = session.get(resolved, timeout=20, allow_redirects=True)
            response.raise_for_status()
            if response.url:
                result["url"] = response.url
                result["source"] = normalize_source_from_url(response.url, str(result.get("source", "")))
            official_date = extract_official_date(response.text)
            if official_date:
                result["published"] = official_date
            result["article_text"] = article_text(response.text)
        except requests.RequestException as exc:
            result["enrich_error"] = type(exc).__name__
    return result


def load_event_state() -> dict[str, Any]:
    if not EVENT_STATE_PATH.exists():
        return {"seen_events": {}, "initialized": False}
    try:
        data = json.loads(EVENT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"seen_events": {}, "initialized": False}
    data.setdefault("seen_events", {})
    data.setdefault("initialized", True)
    return data


def save_event_state(seen_events: dict[str, str]) -> None:
    EVENT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENT_STATE_PATH.write_text(
        json.dumps(
            {
                "initialized": True,
                "seen_events": seen_events,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _source_link(item: dict[str, Any]) -> str:
    source = html.escape(base.normalize(str(item.get("source", ""))).replace(" 공식 검색", ""))
    url = base.normalize(str(item.get("url", "")))
    if url:
        return f'<a href="{html.escape(url, quote=True)}"><b>{source}</b></a>'
    return source


def _generic_detail(category: str) -> list[str]:
    mapping = {
        "최종 대책": (
            "정부 검토안이 실제 집행 단계로 올라왔다는 뜻",
            "세부 노선·지중화 구간·비용 분담·착공일",
        ),
        "법령·고시 개정": (
            "인허가·주민협의·보상 규칙이 바뀌어 같은 사업이라도 착공 속도와 비용이 달라질 수 있음",
            "시행일·경과조치·한전 내부규정 반영",
        ),
        "실제 발주·착공": (
            "정책 기대가 실제 케이블·변압기·GIS·전력구·설계·시공 발주로 넘어간 단계",
            "낙찰사·계약금액·공사기간·전원 인가 시점",
        ),
        "보상·이익공유": (
            "주민 수용성 비용을 늘려 장기 지연 위험을 줄이려는 정책",
            "지원 대상·단가·재원 분담·실제 지급 개시일",
        ),
        "노선·지중화": (
            "가공철탑과 지중 케이블·전력구 사이에서 설비투자 품목 비중이 바뀌는 단계",
            "전압·km·지중화 길이·총사업비·착공일",
        ),
    }
    easy, nxt = mapping.get(
        category,
        ("전력망 운영·건설 방식이 바뀌어 설비 사양과 발주 조건이 달라질 수 있음", "세부 규정·발주 규격·사업자 선정"),
    )
    return [
        "<b>쉽게 풀면</b>",
        f"• {easy}",
        "",
        "<b>다음 확인</b>",
        f"• {nxt}",
    ]


def _gfm_detail(item: dict[str, Any]) -> list[str]:
    body = str(item.get("article_text", ""))
    lower = body.lower()
    lines = [
        "<b>핵심 변화</b>",
        "• 장주기 BESS가 단순히 전기를 저장·방전하는 설비에서 <b>전압과 주파수를 스스로 형성해 전력망을 안정시키는 설비</b>로 역할이 확대됨",
    ]
    if "2027" in lower and "12월" in body:
        lines.append("• 적용 시작: <b>2027년 12월 상업운전 예정 중앙계약시장 장주기 BESS부터</b>")
    if all(term in lower for term in ("540mw", "600mw")):
        lines.extend(
            [
                "",
                "<b>도입 물량</b>",
                "• 2027년 <b>540MW</b> → 2028년 <b>540MW</b> → 2029년 <b>600MW</b>",
                "• 3년 합계 <b>1.68GW</b>가 그리드포밍 성능 적용 대상 물량으로 이어질 계획",
            ]
        )
    lines.extend(
        [
            "",
            "<b>쉽게 풀면</b>",
            "• 기존 그리드팔로잉 인버터는 이미 만들어진 계통의 전압·주파수를 따라가지만, 그리드포밍은 <b>인버터가 기준 전압·주파수를 직접 만들어 유지</b>함",
            "• 재생에너지가 늘수록 동기발전기에서 얻던 관성이 줄어들 수 있는데, BESS의 PCS·인버터가 이 안정화 기능을 일부 보완하는 구조",
            "",
            "<b>설비투자에서 달라지는 것</b>",
            "• 배터리 셀 용량뿐 아니라 <b>PCS·인버터 제어 알고리즘, 계통해석, 시험·검증 능력</b>이 입찰 경쟁력의 핵심으로 올라감",
            "• 사업자는 ‘송·배전용 전기설비 이용규정’과 ‘전력시장운영규칙’의 성능·운영 기준을 맞춰야 함",
            "",
            "<b>확정 당사자</b>",
            "• 기후에너지환경부: 성능 요건·정책",
            "• 한국전력: 송전계통 연계기술 기준",
            "• 한국전력거래소: 전력시장·계통 운영 기준",
            "• <b>개별 PCS·인버터 공급사는 이번 공식자료에서 공개되지 않음</b>",
            "",
            "<b>다음 확인</b>",
            "• 세부 성능시험 기준 → 중앙계약시장 입찰 규격 → 우선협상대상자 → PCS·인버터 공급사 → 2027년 12월 상업운전 순으로 확인",
            "",
            "<b>숨은 역풍</b>",
            "• 기술을 보유했다는 것과 실제 중앙계약시장 수주는 별개. 성능시험·계통연계 검증에서 탈락하거나 프로젝트 준공이 늦어지면 매출 인식도 지연됨",
        ]
    )
    return lines


def render_report(items: list[dict[str, Any]], errors: list[str]) -> str:
    lines = ["<b>전력망 정책·발주 새 공식 변화</b>"]
    for index, item in enumerate(items[:6], start=1):
        category = str(item.get("category") or "전력망 정책")
        published = base.format_korean_date(str(item.get("published") or ""))
        title = html.escape(base.normalize(str(item.get("title") or "")))
        lines.extend(
            [
                f"\n<b>{index}. {title}</b>",
                f"<b>단계</b>  {html.escape(category)}",
                f"<b>발표일</b>  {published}",
                f"<b>출처</b>  {_source_link(item)}",
                "",
            ]
        )
        key = canonical_title(str(item.get("title", "")))
        if "그리드포밍" in key and ("에너지저장장치" in key or "bess" in key):
            lines.extend(_gfm_detail(item))
        else:
            lines.extend(_generic_detail(category))
        lines.extend(
            [
                "",
                "<b>투자 의미</b>",
                f"• {html.escape(base.investment_meaning(category))}",
            ]
        )
    if len(items) > 6:
        lines.append(f"\n같은 실행에서 추가 확인된 공식 변화 {len(items) - 6}건")
    if errors:
        print(f"grid_source_errors={len(errors)}")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-notify", action="store_true")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "khs-watch-korea-grid-policy-v2/1.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
    )

    raw_items, versions, errors = base.collect(session)
    items = collapse_events(raw_items)
    event_state = load_event_state()
    seen_events: dict[str, str] = {str(k): str(v) for k, v in event_state.get("seen_events", {}).items()}

    # 최초 전환 시에는 현재 검색창에 잡혀 있는 과거 문서를 기준선으로만 저장해
    # 기존 문서가 새 알림처럼 재전송되는 것을 막는다.
    if not event_state.get("initialized"):
        for item in items:
            seen_events[event_key(item)] = str(item.get("published", ""))
        save_event_state(seen_events)
        # 기존 법령 페이지 버전 기준선은 원래 상태 파일에 계속 유지한다.
        old = base.load_state()
        base.write_state(
            {
                "version": 1,
                "seen_items": old.get("seen_items", []),
                "page_versions": {**old.get("page_versions", {}), **versions},
                "updated_at": now.isoformat(),
                "last_source_errors": errors[-20:],
            }
        )
        print("전력망 정책 v2 이벤트 기준선 저장 완료")
        base.output("changed", "false")
        return 0

    new_items: list[dict[str, Any]] = []
    for item in items:
        key = event_key(item)
        if key in seen_events:
            continue
        enriched = enrich_item(item, session)
        published = base.parse_date(str(enriched.get("published", "")))
        # Google News가 수개월 뒤 재색인한 과거 공식자료를 '새 변화'로 오인하지 않는다.
        if published and now - published > timedelta(days=STALE_DISCOVERY_DAYS):
            seen_events[key] = str(enriched.get("published", ""))
            print(
                "grid_stale_index_suppressed="
                f"{base.format_korean_date(str(enriched.get('published', '')))}|{enriched.get('title', '')}"
            )
            continue
        enriched["event_key"] = key
        new_items.append(enriched)
        seen_events[key] = str(enriched.get("published", ""))

    # 법령 페이지의 실제 버전 변경은 별도로 계속 추적한다.
    old_state = base.load_state()
    old_versions = {str(k): str(v) for k, v in dict(old_state.get("page_versions", {})).items()}
    law_changes: list[dict[str, Any]] = []
    for page in base.LAW_PAGES:
        name = str(page["name"])
        new_version = versions.get(name)
        old_version = old_versions.get(name)
        if new_version and old_version and new_version != old_version:
            category, stage = base.classify_item(f"{name} 개정 고시")
            law_item = {
                "id": base.digest(f"law-change|{name}|{new_version}"),
                "title": f"{name} 버전 변경 감지",
                "source": "국가법령정보센터",
                "url": str(page["url"]),
                "published": "",
                "category": category,
                "stage": stage,
            }
            lk = event_key(law_item)
            if lk not in seen_events:
                law_item["event_key"] = lk
                law_changes.append(law_item)
                seen_events[lk] = new_version

    save_event_state(seen_events)
    base.write_state(
        {
            "version": 1,
            "seen_items": old_state.get("seen_items", []),
            "page_versions": {**old_versions, **versions},
            "updated_at": now.isoformat(),
            "last_source_errors": errors[-20:],
        }
    )

    base.OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.force_notify:
        report_path = base.OUT_DIR / now.strftime("%Y%m%dT%H%M%SZ-korea-grid-policy-route.md")
        report_path.write_text(base.setup_report(), encoding="utf-8")
        base.output("changed", "true")
        base.output("report_path", str(report_path))
        base.output("report_title", f"전력망 정책 알림 봇 경로 확인 {now.astimezone(KST):%Y-%m-%d}")
        return 0

    notify_items = sorted(
        law_changes + new_items,
        key=lambda item: (int(item.get("stage", 0)), str(item.get("published", ""))),
        reverse=True,
    )
    if not notify_items:
        print("전력망 정책·발주 신규 공식 변화 없음")
        base.output("changed", "false")
        return 0

    report_path = base.OUT_DIR / now.strftime("%Y%m%dT%H%M%SZ-korea-grid-policy.md")
    report_path.write_text(render_report(notify_items, errors), encoding="utf-8")
    base.output("changed", "true")
    base.output("report_path", str(report_path))
    base.output("report_title", f"전력망 정책 공식 변화 {now.astimezone(KST):%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
