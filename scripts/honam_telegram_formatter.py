#!/usr/bin/env python3
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "out" / "honam_semiconductor_alert.json"
OUT_PATH = ROOT / "out" / "honam_semiconductor_telegram_chunks.json"

CORE_STAGE_LABELS = {
    "1_용역선정_현지조사": "① 용역업체 선정·현지조사",
    "2_수량수질_조사범위": "② 장록습지 수량·수질",
    "3_람사르_심사결과": "③ 람사르 등록 심사",
}

PROJECT_STAGE_LABELS = {
    "4_정주주거_배후도시": "④ 정주·주거·배후도시",
    "5_기반시설_생활SOC": "⑤ 전력·용수·교통·생활 인프라",
    "6_산단투자_기업일정": "⑥ 산단·기업투자·팹 일정",
}

STAGE_LABELS = {**CORE_STAGE_LABELS, **PROJECT_STAGE_LABELS}


def esc(value):
    return html.escape(str(value or ""), quote=True)


def clean_title(title: str, source: str) -> str:
    title = (title or "").strip()
    source = (source or "").strip()
    candidates = [
        source,
        source.replace("(네이버)", ""),
        source.replace("(다음)", ""),
        source.replace("Google 뉴스 경유 · ", ""),
    ]
    for suffix in candidates:
        suffix = suffix.strip()
        if suffix and title.endswith(" - " + suffix):
            return title[: -(len(suffix) + 3)].strip()

    # Google News RSS는 같은 원문을 뉴스1 / news1.kr처럼 다른 매체표기로
    # 붙이는 경우가 있어 마지막 매체 꼬리표는 표시용 제목에서 제거한다.
    if source.startswith("Google 뉴스 경유") and " - " in title:
        tail = title.rsplit(" - ", 1)[1].strip()
        if len(tail) <= 40:
            return title.rsplit(" - ", 1)[0].strip()
    return title


def fmt_checked(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(value)
        return parsed.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return value


def fmt_published(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return value


def impact_label(value: str) -> str:
    # Do not discard a specific funding or supply warning into a generic label.
    return str(value or "").strip()


def link_line(url: str, label: str = "원문 보기") -> str:
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def source_name(value):
    text = re.sub(r"^Google 뉴스 경유\s*·\s*", "", str(value or "").strip(), flags=re.I)
    text = re.sub(r"\s+on\s+MSN$", "", text, flags=re.I)
    text = re.sub(r"\((?:네이버|다음)\)$", "", text).strip()
    return {"yna.co.kr": "연합뉴스", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
            "namdonews.com": "남도일보", "mdilbo.com": "무등일보"}.get(text.casefold(), text or "근거자료")


def evidence_lines(item: dict):
    evidence = item.get("evidence_sources") or [{
        "source": item.get("source"), "url": item.get("url"),
        "published": item.get("published"), "body_status": item.get("body_status")
    }]
    groups = {}
    seen = set()
    for ev in evidence:
        url = str(ev.get("url") or "")
        name = source_name(ev.get("source"))
        if not link_line(url) or (name, url) in seen:
            continue
        seen.add((name, url))
        groups.setdefault(name, []).append(ev)
    if not groups:
        return []
    lines = ["<b>출처</b>"]
    for name, refs in groups.items():
        # Different articles by the same publisher remain separate links,
        # without presenting a syndicated copy as an independent publisher.
        for ev in refs:
            url = ev["url"]
            host = (urlparse(url).hostname or "").lower()
            if host == "news.google.com" or host.endswith(".bing.com") or host == "bing.com":
                label = "검색 경유 링크(원문 미확보)"
            elif host == "msn.com" or host.endswith(".msn.com"):
                label = "재게시 링크"
            elif "미확보" in str(ev.get("body_status") or ""):
                label = "발행사 링크(본문 미확보)"
            else:
                label = "원문 보기"
            when = fmt_published(ev.get("published") or "")
            # A feed timestamp is not a verified publication time.
            if when and item.get("intake_verified") and ev.get("body_status") == "등록된 출처별 검증 메모":
                when = when.replace("2026-", "").replace(" KST", "")
                label = f"{when} · {label}"
            elif when and not item.get("intake_verified"):
                label += f" · RSS {when}(송고시각 미확인)"
            lines.append(f"• {esc(name)} · {link_line(url, label)}")
    return lines


def _fact_parts(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return []
    # Split complete sentences only, without changing number/date strings.
    return [part.strip() for part in re.split(r"(?<=[.!?。])\s+(?=[가-힣A-Z0-9\[])", text) if part.strip()]


def _fact_identity(value):
    return re.sub(r"[\s·•\"'“”‘’]+", "", str(value or "")).strip(" .。").casefold()


def fact_display(item):
    lines, seen = [], set()
    # Reviewed structured facts are the report; raw article copies remain
    # evidence rather than being printed a second time.
    reviewed = bool(item.get("summary_lines") or item.get("detail_lines"))
    fields = list(item.get("summary_lines") or []) + list(item.get("detail_lines") or [])
    if not reviewed:
        fields += list(item.get("fact_lines") or [])
        if not fields and item.get("detail"):
            fields.append(item["detail"])
        if fields and item.get("fact_lines"):
            lines.append("<b>본문 확인 사항(자동 발췌)</b>")
    for field in fields:
        if re.fullmatch(r"【[^】]+】", str(field).strip()):
            title = str(field).strip()[1:-1]
            lines.extend(["", f"<b>{esc(title)}</b>"])
            continue
        for part in _fact_parts(field):
            key = _fact_identity(part)
            if not key or key in seen:
                continue
            seen.add(key)
            # Short explicit labels make values easier to find on a phone.
            labeled = re.match(r"^([^:：]{1,24})[:：]\s*(.+)$", part)
            if labeled:
                lines.append(f"• <b>{esc(labeled.group(1))}</b>: {esc(labeled.group(2))}")
            else:
                lines.append(f"• {esc(part)}")
    return lines


def event_stages(item):
    stages = [stage for stage in item.get("stages", []) if stage in STAGE_LABELS]
    if not stages and item.get("stage") in STAGE_LABELS:
        stages = [item["stage"]]
    return list(dict.fromkeys(stages))


def _event_block(item, index, official=False):
    title = clean_title(item.get("title") or item.get("headline") or "관련 변화", item.get("source", ""))
    stages = event_stages(item)
    labels = " · ".join(STAGE_LABELS[key] for key in stages) or "관련 변화"
    if item.get("recovery"):
        title = re.sub(r"^\d+월\s*\d+일\s*누락 보완:\s*", "", title)
    lead = item.get("alert_type") == "선행경보"
    verification = str(item.get("verification_status") or item.get("source_status") or ("공식자료" if official else "보도 단계"))
    if lead:
        verification = verification.replace(" · 실행·계약 확정 아님", "")
        phase = "선행경보 · 검토/계획/보도(실행 확정 아님)"
    else:
        phase = "신규 상태 변화"
    lines = [
        f"<b>■ {index}. {esc(title)}</b>",
        f"{esc(labels)} | <b>{esc(phase)}</b>",
        f"확인도: {esc(verification)}" + (" · 누락 보완" if item.get("recovery") else ""),
    ]
    if item.get("verification_upgrade"):
        lines.append("검증 변화: 기존 보도보다 확인 단계 상승")
    facts = fact_display(item)
    if facts:
        lines.extend(["", *facts])
    body_status = str(item.get("body_status") or "")
    if "미확보" in body_status:
        lines.extend(["", f"원천 한계: {esc(body_status)}"])
    elif not facts and not official and not item.get("intake_verified"):
        lines.extend(["", "세부 내용: 확인된 원문 핵심 수치·일정 없음(추가 확인 필요)"])
    note = str(item.get("verification_note") or "").strip()
    if note:
        lines.extend(["", f"검증 범위: {esc(note)}"])
    impact = impact_label(item.get("impact", ""))
    reason = str(item.get("reason") or "").strip()
    if impact and impact != "영향 확인 필요":
        lines.extend(["", f"<b>의미</b>: {esc(impact)}"])
    if reason and _fact_identity(reason) != _fact_identity(impact):
        lines.append(f"후속 확인: {esc(reason)}")
    sources = evidence_lines(item)
    if sources:
        lines.extend(["", *sources])
    return "\n".join(lines)


def build_message(data: dict) -> str:
    official = list(data.get("official_changes") or [])
    news = list(data.get("new_items") or [])
    events = [(item, True) for item in official] + [(item, False) for item in news]
    total = len(events)
    lead_count = sum(item.get("alert_type") == "선행경보" for item, _ in events)
    active = {key: set() for key in STAGE_LABELS}
    for item, _ in events:
        for stage in event_stages(item):
            active[stage].add("선행경보" if item.get("alert_type") == "선행경보" else "상태 변화")
    header = [
        "<b>호남 반도체 국가산단</b>",
        f"신규 변화 <b>{total - lead_count}건</b> · 선행경보 <b>{lead_count}건</b>",
        f"조회: {esc(fmt_checked(data.get('checked_at_kst', '')))}",
    ]
    blocks = ["\n".join(header)]
    for index, (item, is_official) in enumerate(events, 1):
        blocks.append(_event_block(item, index, is_official))
    partial = bool(data.get("rss_failed_queries") or data.get("official_source_partial_failure"))
    # Unchanged items are summarized once at the bottom, not interposed
    # between the headline and the facts that the user needs to read.
    footer = ["<b>감시 상태</b>"]
    for stages, title in ((CORE_STAGE_LABELS, "환경 3단계"), (PROJECT_STAGE_LABELS, "사업 3단계")):
        changed = [f"{label}({('/'.join(sorted(active[key])))})" for key, label in stages.items() if active[key]]
        unchanged = [label for key, label in stages.items() if not active[key]]
        if changed:
            footer.append(f"• {title} 감지: {esc(' · '.join(changed))}")
        if unchanged:
            status = "미확인(일부 원천 조회 실패)" if partial else "조회 범위 내 변화 미감지"
            footer.append(f"• {esc(status)}: {esc(' · '.join(unchanged))}")
    if partial:
        footer.append("※ 조회 실패를 신규 발표 없음으로 판단하지 않음.")
    blocks.append("\n".join(footer))
    return "\n\n".join(blocks).strip()


def split_message(text: str, limit: int = 3900):
    if not text.strip():
        return []
    if len(text) <= limit:
        return [text]
    budget = limit - 80
    if budget < 100:
        raise ValueError("호남 알림 길이 설정 오류")
    # Prefer complete event blocks. If a single event is long, split
    # only between complete lines, and retain its heading on continuation.
    blocks = re.split(r"\n\n(?=<b>(?:■ \d+\. |감시 상태</b>))", text)
    chunks, current = [], ""
    for block in blocks:
        if len(block) <= budget:
            joined = current + "\n\n" + block if current else block
            if len(joined) <= budget:
                current = joined
            else:
                if current:
                    chunks.append(current)
                current = block
            continue
        if current:
            chunks.append(current)
            current = ""
        heading = block.split("\n", 1)[0]
        continuation = heading[:-4] + " (계속)</b>" if heading.startswith("<b>■ ") and heading.endswith("</b>") else "<b>호남 반도체 상세(계속)</b>"
        for line in block.split("\n"):
            if len(line) > budget - len(continuation) - 1:
                raise ValueError("호남 알림 단일 행 길이 초과: 내용 임의 절단 금지")
            joined = current + "\n" + line if current else line
            if len(joined) > budget:
                chunks.append(current.rstrip())
                current = continuation + "\n" + line
            else:
                current = joined
    if current.strip():
        chunks.append(current.rstrip())
    result = [f"<b>호남 반도체 알림 {idx}/{len(chunks)}</b>\n{chunk}" for idx, chunk in enumerate(chunks, 1)]
    if any(len(chunk) > limit for chunk in result):
        raise ValueError("호남 알림 분할 길이 오류")
    return result

def main():
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    chunks = split_message(build_message(data))
    OUT_PATH.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n--- Telegram preview ---\n")
    print("\n\n".join(chunks))


if __name__ == "__main__":
    main()
