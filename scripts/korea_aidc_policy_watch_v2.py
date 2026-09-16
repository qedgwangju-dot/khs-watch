#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

try:
    import korea_aidc_policy_watch as base
except ModuleNotFoundError:
    from scripts import korea_aidc_policy_watch as base

try:
    from googlenewsdecoder import new_decoderv1
except Exception:  # pragma: no cover
    new_decoderv1 = None

STATE = base.STATE
OUT = base.OUT
ALERT = base.ALERT
PENDING = base.PENDING
STATUS = base.STATUS
META = OUT / "korea_aidc_policy_alert_meta.json"
KST = base.KST
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}
MAX_AGE_DAYS = base.MAX_AGE_DAYS


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def semantic_key(row: dict[str, Any]) -> str:
    title = base.norm(str(row.get("title", ""))).lower()
    if "알박기" in title and ("93%" in title or "신청 물량" in title or "신청물량" in title):
        return "aidc|anti-hoarding|queue-evidence"
    if "알박기" in title and ("법 개정" in title or "매매 제한" in title or "매각" in title):
        return "aidc|anti-hoarding|legal-limit"
    if "입법예고" in title:
        return "aidc|decree-preannouncement"
    if any(x in title for x in ("시행령 확정", "시행령 제정", "국무회의", "공포")):
        return "aidc|decree-final"
    if any(x in title for x in ("하위법령", "공개토론회", "밑그림")) and "입법예고" not in title:
        return "aidc|subordinate-rules-design"
    if "전력계통영향평가" in title or "전력 특례" in title:
        return "aidc|power-special"
    if "특구" in title:
        return "aidc|special-zone"
    cleaned = re.sub(r"\s+-\s+[^-]{1,60}$", "", title)
    cleaned = re.sub(r"[^0-9a-z가-힣]+", " ", cleaned)
    return f"aidc|fact|{digest(' '.join(cleaned.split()))[:16]}"


def event_level(row: dict[str, Any]) -> int:
    return base.event_level(row)


def collapse(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(semantic_key(row), []).append(row)
    result: list[dict[str, Any]] = []
    for key, members in grouped.items():
        best = max(
            members,
            key=lambda r: (
                event_level(r),
                base.source_score(r),
                len(re.findall(r"\d+(?:\.\d+)?(?:gw|mw|%|년|일)?", str(r.get("title", "")).lower())),
                str(r.get("published", "")),
            ),
        ).copy()
        best["event_key"] = key
        best["members"] = members
        result.append(best)
    result.sort(
        key=lambda r: (
            event_level(r),
            base.parse_date(str(r.get("published", ""))) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return result


def resolve_url(url: str) -> str:
    url = str(url or "").strip()
    if not url or "news.google.com" not in url:
        return url
    if new_decoderv1 is not None:
        try:
            decoded = new_decoderv1(url, interval=0.15)
            if isinstance(decoded, dict) and decoded.get("status") and decoded.get("decoded_url"):
                return str(decoded["decoded_url"]).strip()
        except Exception as exc:  # noqa: BLE001
            print(f"aidc_google_news_decode_failed={type(exc).__name__}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        response.raise_for_status()
        if response.url and "news.google.com" not in response.url:
            return response.url
    except Exception as exc:  # noqa: BLE001
        print(f"aidc_google_news_redirect_failed={type(exc).__name__}")
    return url


def clean_paragraph(text: str) -> str:
    value = " ".join(str(text or "").split())
    noise = ("재판매 및 db 금지", "무단전재", "copyright", "기사제보", "많이 본", "관련기사")
    if any(x in value.lower() for x in noise):
        return ""
    return value


def enrich(row: dict[str, Any], session: requests.Session) -> dict[str, Any]:
    result = row.copy()
    resolved = resolve_url(str(row.get("url", "")))
    if resolved:
        result["url"] = resolved
    if not resolved or "news.google.com" in resolved:
        result["article_body"] = ""
        return result
    try:
        response = session.get(resolved, headers=HEADERS, timeout=20, allow_redirects=True)
        response.raise_for_status()
        if response.url:
            result["url"] = response.url
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup.select("script, style, noscript, nav, footer, header, aside"):
            node.decompose()
        selectors = (
            "article p", "#articleBody p", "#article_body p", "#textBody p",
            ".articleBody p", ".article-body p", ".article_view p", ".article-view p",
            ".view_text p", ".viewer p", ".news_body p", ".news-body p", "main p",
        )
        best: list[str] = []
        for selector in selectors:
            paragraphs = [clean_paragraph(n.get_text(" ", strip=True)) for n in soup.select(selector)]
            paragraphs = [x for x in paragraphs if len(x) >= 35]
            if sum(map(len, paragraphs)) > sum(map(len, best)):
                best = paragraphs
        if sum(map(len, best)) < 400:
            fallback = [clean_paragraph(n.get_text(" ", strip=True)) for n in soup.find_all("p")]
            fallback = [x for x in fallback if len(x) >= 45]
            if sum(map(len, fallback)) > sum(map(len, best)):
                best = fallback
        unique: list[str] = []
        seen: set[str] = set()
        for paragraph in best:
            if paragraph and paragraph not in seen:
                unique.append(paragraph)
                seen.add(paragraph)
        result["article_body"] = "\n".join(unique)
    except Exception as exc:  # noqa: BLE001
        result["article_body"] = ""
        result["enrich_error"] = type(exc).__name__
    return result


def has(body: str, *terms: str) -> bool:
    lower = body.lower()
    return any(term.lower() in lower for term in terms)


def fact_lines(row: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    key = str(row.get("event_key", ""))
    body = str(row.get("article_body", ""))
    lower = body.lower()

    if key == "aidc|anti-hoarding|queue-evidence":
        new = [
            "• 이번 변화의 핵심은 하위법령 논의 자체가 아니라 <b>전력 선점 문제가 실제 물량으로 확인됐다는 점</b>",
        ]
        if "67.4gw" in lower and "62.8gw" in lower and "93%" in lower:
            new.append("• 전력계통영향평가 신청 <b>67.4GW</b> 가운데 데이터센터가 <b>62.8GW·93%</b>를 차지")
        if "39.9gw" in lower and "7gw" in lower:
            new.append("• 1차 심사 공급가능 물량은 <b>39.9GW</b>지만 본심사 완료는 <b>7GW</b>에 그쳐, 약 <b>33GW</b>가 중간 단계에 머물러 있음")
        if has(body, "기한 근거", "추진해야 하는지"):
            new.append("• 시행령 구성 초안에는 AIDC 인정 뒤 <b>언제까지 실제 사업을 추진해야 하는지에 대한 기한 근거가 없는 것</b>으로 보도됨")
        changed = [
            "• 9월 9일의 ‘하위법령을 만든다’에서 한 단계 나아가, <b>특례가 계통 선점·허수 수요를 키울 수 있다는 정량 근거</b>가 추가됨",
            "• 따라서 전력 특례의 크기뿐 아니라 <b>미추진 사업 회수·유효기간·실수요 검증 장치</b>가 중요해짐",
        ]
        invest = [
            "• 실제 착공 프로젝트에는 계통 확보 경쟁이 더 중요해지고, <b>변압기·개폐기·케이블·UPS·BESS 발주는 ‘신청 GW’보다 본심사·전원 인가 GW</b>를 봐야 함",
            "• 허수 물량 정리가 강화되면 실수요 프로젝트의 접속 여력이 개선될 수 있지만, 규제가 약하면 계통 병목이 장기화될 수 있음",
        ]
        return new, changed, invest

    if key == "aidc|anti-hoarding|legal-limit":
        new = [
            "• 전력계통영향평가 면제를 받아도 <b>전력 공급이 자동 보장되는 것은 아니라는 점</b>이 확인됨",
            "• 연구반은 설계전력·AI 장비 전력·한전 계약전력의 <b>정합성을 신고 단계에서 확인</b>해 허수 사업자를 걸러내는 방향을 검토",
        ]
        if has(body, "매각 금지", "매매 제한", "법률상 근거"):
            new.append("• 사업권 매각·매매 자체를 막으려면 재산권 제한 문제가 있어 <b>시행령만으로는 어렵고 법률 개정 근거가 필요</b>하다는 연구반 설명")
        if "300" in lower and "확정" in lower:
            new.append("• 일각의 <b>300kW 기준은 확정된 수치가 아니며</b>, AIDC 인정 기준과 AI 장비 전력 비율도 계속 논의 중")
        changed = [
            "• 9월 9일 공개토론회의 큰 틀에서 새로 나온 것은 <b>‘알박기’를 시행령만으로 완전히 막기 어렵다는 법적 한계</b>",
            "• 즉 특례 확대와 함께 진성 사업자 검증·법 개정 여부가 별도 정책 변수로 생김",
        ]
        invest = [
            "• 전력 특례 수혜 여부보다 <b>한전 계약전력·실제 공급 가능 용량·착공 의지</b>가 프로젝트 가치 판단에서 더 중요해짐",
            "• 사업권 거래 제한이 법 개정으로 강화되면 단순 부지·계통 선점 가치보다 실제 개발 능력을 가진 사업자의 상대가치가 커질 수 있음",
        ]
        return new, changed, invest

    if key == "aidc|subordinate-rules-design":
        new = [
            "• 2027년 3월 10일 특별법 시행 전 <b>AIDC 인정 범위·신고·인허가 일괄처리·전력 특례·비수도권 특구</b>의 세부 기준을 만드는 단계",
            "• 이 단계에서는 구체 시행령 조문이 확정된 것이 아니라 연구반 구성안과 이해관계자 의견을 모으는 중",
        ]
        changed = [
            "• 특별법이 이미 공포된 상태에서 <b>누가 실제 특례 대상이 되고 어떤 절차를 줄일지</b>를 정하는 실행 규칙 단계로 이동",
        ]
        invest = [
            "• 실제 돈은 시행령·전력 기준 확정 → 전원 인가 → 착공 이후 <b>변압기·개폐기·케이블·UPS·BESS·냉각·건설</b> 발주로 연결",
            "• 가장 중요한 미확정은 AIDC 인정 기준과 전력계통영향평가 특례·면제의 구체 범위",
        ]
        return new, changed, invest

    if key == "aidc|decree-preannouncement":
        return (
            ["• 정부 시행령 초안이 공개돼 <b>AIDC 인정·전력·인허가 특례 문구를 실제 조문으로 검증할 수 있는 단계</b>"],
            ["• 토론회·연구반 의견 수준에서 <b>공식 입법예고안</b>으로 단계가 올라감"],
            ["• 숫자·면제 범위가 구체화되면 실제 프로젝트별 전원 인가·착공 가능성을 다시 평가해야 함"],
        )

    if key == "aidc|decree-final":
        return (
            ["• 시행령·하위규칙이 확정돼 <b>실제 적용 기준이 법적 효력을 갖는 단계</b>로 이동"],
            ["• 입법예고안과 최종 조문 사이에서 바뀐 숫자·대상·경과조치를 확인해야 함"],
            ["• 이제 정책 기대보다 실제 전원 인가·특구 지정·착공·발주가 실적 연결의 핵심"],
        )

    title = html.escape(base.norm(str(row.get("title", ""))))
    return (
        [f"• 새로 확인된 변화: {title}"],
        ["• 기존 정책 흐름과 비교해 새 숫자·공식화·적용대상 변화가 있는지 후속 확인"],
        ["• 실제 전원 인가·착공·발주로 이어지는지 확인 전에는 기대감과 확정 매출을 구분"],
    )


def source_link(row: dict[str, Any]) -> str:
    label = html.escape(str(row.get("publisher") or row.get("source") or "원문"))
    url = html.escape(str(row.get("url") or ""), quote=True)
    return f'<a href="{url}"><b>{label}</b></a>' if url else label


def render(row: dict[str, Any]) -> str:
    title = html.escape(base.norm(str(row.get("title", ""))))
    category = html.escape(str(row.get("category", "AIDC 특별법")))
    new, changed, invest = fact_lines(row)
    return "\n".join([
        "<b>한국 AIDC 정책·전력 특례 새 변화</b>",
        "",
        "<b>한눈에 보기</b>",
        f"• <b>현재 단계</b>  {category}",
        f"• <b>이번 핵심</b>  {re.sub('<[^>]+>', '', new[0]).removeprefix('• ').strip()}",
        "• <b>알림 기준</b>  같은 기사 재노출이 아니라 새 숫자·법적 제약·공식화·사업단계 변화가 생길 때만 전송",
        "",
        f"<b>{title}</b>",
        f"<b>발표일</b>  {base.kdate(str(row.get('published', '')))}",
        f"<b>출처</b>  {source_link(row)}",
        "",
        "<b>이번에 새로 추가된 사실</b>",
        *new,
        "",
        "<b>기존 알림과 달라진 점</b>",
        *changed,
        "",
        "<b>투자 연결</b>",
        *invest,
        "",
        "<b>다음 확인</b>",
        "• 입법예고·시행령 확정 여부와 최종 조문",
        "• 전력계통영향평가 특례·면제의 실제 MW·적용 조건",
        "• 계통 신청 → 본심사 → 전원 인가 → 착공으로 실제 전환되는 GW",
        "• 미추진 사업 회수·유효기간·사업권 거래 제한에 대한 추가 법 개정 여부",
    ]).rstrip() + "\n"


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for path in (ALERT, PENDING, STATUS, META):
        if path.exists():
            path.unlink()

    state = base.load_state()
    last_state_time = parse_iso(str(state.get("updated_at", "")))
    now = datetime.now(timezone.utc)
    session = requests.Session()
    session.headers.update(HEADERS)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for source, official, url in base.RSS_SOURCES:
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            rows.extend(base.parse_rss(response.text, source, official))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {type(exc).__name__}")

    recent: list[dict[str, Any]] = []
    for row in rows:
        dt = base.parse_date(str(row.get("published", "")))
        if dt and now - dt.astimezone(timezone.utc) > timedelta(days=MAX_AGE_DAYS):
            continue
        recent.append(row)

    events = collapse(recent)
    seen = {str(k): int(v) for k, v in dict(state.get("seen_events", {})).items()}
    notify: list[dict[str, Any]] = []

    for row in events:
        key = str(row["event_key"])
        current = event_level(row)
        previous = int(seen.get(key, 0))
        published = base.parse_date(str(row.get("published", "")))
        published_utc = published.astimezone(timezone.utc) if published else None

        should_notify = current > previous
        # v2 전환 시 이미 과거에 처리한 기사들을 새 semantic key 때문에 재전송하지 않는다.
        if previous == 0 and last_state_time and published_utc and published_utc <= last_state_time:
            should_notify = False

        if should_notify:
            notify.append(row)
        seen[key] = max(previous, current)

    pending = {
        "initialized": True,
        "seen_events": seen,
        "updated_at": now.isoformat(),
        "source_errors": errors,
        "dedupe_version": 2,
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if notify:
        selected = enrich(notify[0], session)
        ALERT.write_text(render(selected), encoding="utf-8")
        meta = {
            "event_key": str(selected["event_key"]),
            "event_level": event_level(selected),
            "title": str(selected.get("title", "")),
            "fingerprint": digest(str(selected.get("event_key", "")) + "|" + str(event_level(selected))),
        }
        META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    STATUS.write_text(
        "# 한국 AIDC 정책·전력 특례 감시 v2\n\n"
        f"- 정책 이벤트: **{len(events)}건**\n"
        f"- 신규 사실 알림: **{'예' if notify else '아니오'}**\n"
        f"- 중복 기준: **기사 URL이 아니라 정책 사실·단계**\n"
        f"- 원천 오류: **{len(errors)}곳**\n",
        encoding="utf-8",
    )
    print(f"aidc_v2_events={len(events)} notify={bool(notify)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
