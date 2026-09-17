#!/usr/bin/env python3
import datetime as dt
import email.utils
import html
import json
import pathlib
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
    for suffix in [source, source.replace("(네이버)", ""), source.replace("(다음)", "")]:
        suffix = suffix.strip()
        if suffix and title.endswith(" - " + suffix):
            title = title[: -(len(suffix) + 3)].strip()
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
    value = value or ""
    if "지연" in value or "병목" in value or "보완" in value:
        return value
    if "진행" in value:
        return "한 단계 진행"
    if "정주" in value or "기반시설" in value or "시간표" in value:
        return value
    return "영향 확인 필요"


def link_line(url: str, label: str = "근거 보기") -> str:
    if not url:
        return ""
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def evidence_lines(item: dict):
    evidence = item.get("evidence_sources") or []
    if not evidence:
        url = item.get("url")
        source = item.get("source") or "근거자료"
        if not url:
            return []
        return [f"• 감지 근거: {esc(source)} · {link_line(url, '근거 보기')}"]
    lines = [f"• 감지 근거: {len(evidence)}곳"]
    for ev in evidence[:3]:
        source = ev.get("source") or "근거자료"
        url = ev.get("url") or ""
        if url:
            lines.append(f"  - {esc(source)} · {link_line(url, '보기')}")
        else:
            lines.append(f"  - {esc(source)}")
    return lines


def build_message(data: dict) -> str:
    official = data.get("official_changes", [])
    news = data.get("new_items", [])
    total = int(data.get("new_count") or len(official) + len(news))

    active = {key: False for key in STAGE_LABELS}
    for item in official:
        stage = item.get("stage")
        if stage in active:
            active[stage] = True
    for item in news:
        for stage in item.get("stages", []):
            if stage in active:
                active[stage] = True

    lines = [
        "🚨 <b>호남 반도체 국가산단</b>",
        f"신규 상태 변화 <b>{total}건</b> · 조회 {esc(fmt_checked(data.get('checked_at_kst', '')))}",
        "• 기준: 주제·사건·공식 상태 변화",
        "• 기사 링크: 감지 근거·교차검증용",
        "",
        "<b>핵심 3단계</b>",
    ]
    for stage, label in CORE_STAGE_LABELS.items():
        status = "<b>변화 감지</b>" if active[stage] else "새 변화 없음"
        lines.append(f"• {label}: {status}")

    lines += ["", "<b>추가 프로젝트 변화</b>"]
    for stage, label in PROJECT_STAGE_LABELS.items():
        status = "<b>변화 감지</b>" if active[stage] else "새 변화 없음"
        lines.append(f"• {label}: {status}")

    for item in official:
        label = item.get("stage_label") or STAGE_LABELS.get(item.get("stage"), "공식자료")
        lines += [
            "",
            f"<b>{esc(label)}</b>",
            f"• 무엇이 달라졌나: {esc(item.get('headline', '공식 핵심정보 변경'))}",
        ]
        detail = (item.get("detail") or "").strip()
        if detail:
            lines.append(f"• 확인 내용: {esc(detail)}")
        reason = (item.get("reason") or "").strip()
        if reason:
            lines.append(f"• 왜 중요: {esc(reason)}")
        lines += [
            f"• 현재 판정: <b>{esc(impact_label(item.get('impact', '')))}</b>",
            f"• 확인도: {esc(item.get('source_status') or '공식자료')}",
        ]
        lines += evidence_lines(item)

    for item in news:
        stages = item.get("stage_labels") or [STAGE_LABELS.get(stage, stage) for stage in item.get("stages", [])]
        label = " · ".join(stages) if stages else "관련 변화"
        source = item.get("source") or "웹 검색"
        title = clean_title(item.get("title", ""), source)
        lines += [
            "",
            f"<b>{esc(label)}</b>",
            f"• 무엇이 달라졌나: {esc(title)}",
        ]
        reason = (item.get("reason") or "").strip()
        if reason:
            lines.append(f"• 왜 중요: {esc(reason)}")
        lines += [
            f"• 현재 판정: <b>{esc(impact_label(item.get('impact', '')))}</b>",
            f"• 확인도: {esc(item.get('source_status') or '보도 단계')}",
        ]
        published = fmt_published(item.get("published", ""))
        if published:
            lines.append(f"• 최초 감지 근거 공개: {esc(published)}")
        lines += evidence_lines(item)

    lines += [
        "",
        "<b>우선 확인 순서</b>",
        "① 수행업체 선정·현지조사 → ② 수량·수질 조사범위 → ③ 람사르 심사 결과",
        "정주·주거, 전력·용수·교통, 기업투자·팹 일정도 별도 중요 변화로 함께 감시",
    ]
    return "\n".join(lines).strip()


def split_message(text: str, limit: int = 3900):
    chunks = []
    current = ""
    for line in text.splitlines(True):
        if len(current) + len(line) > limit and current:
            chunks.append(current.rstrip())
            current = ""
        current += line
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def main():
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    chunks = split_message(build_message(data))
    OUT_PATH.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n--- Telegram preview ---\n")
    print("\n\n".join(chunks))


if __name__ == "__main__":
    main()
