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

STAGE_LABELS = {
    "1_용역선정_현지조사": "① 용역업체 선정·현지조사",
    "2_수량수질_조사범위": "② 장록습지 수량·수질",
    "3_람사르_심사결과": "③ 람사르 등록 심사",
}


def esc(value):
    return html.escape(str(value or ""), quote=True)


def clean_title(title: str, source: str) -> str:
    title = (title or "").strip()
    source = (source or "").strip()
    if source and title.endswith(" - " + source):
        title = title[: -(len(source) + 3)].strip()
    return title


def fmt_checked(value: str) -> str:
    try:
        d = dt.datetime.fromisoformat(value)
        return d.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return value


def fmt_published(value: str) -> str:
    if not value:
        return ""
    try:
        d = email.utils.parsedate_to_datetime(value)
        return d.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return value


def impact_label(value: str) -> str:
    value = value or ""
    if "지연" in value or "보완" in value:
        return "지연 위험"
    if "진행" in value:
        return "한 단계 진행"
    return "영향 확인 필요"


def link_line(url: str) -> str:
    if not url:
        return ""
    return f'<a href="{esc(url)}">원문</a>'


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
        "🚨 <b>호남 반도체 국가산단 · 장록습지</b>",
        f"신규 변화 <b>{total}건</b> · 조회 {esc(fmt_checked(data.get('checked_at_kst', '')))}",
        "",
        "<b>한눈에 보기</b>",
    ]
    for stage, label in STAGE_LABELS.items():
        status = "<b>변화 감지</b>" if active[stage] else "새 변화 없음"
        lines.append(f"• {label}: {status}")

    for item in official:
        label = item.get("stage_label") or STAGE_LABELS.get(item.get("stage"), "공식자료")
        lines += [
            "",
            f"<b>{esc(label)}</b>",
            f"• 변화: {esc(item.get('headline', '공식 핵심정보 변경'))}",
        ]
        detail = (item.get("detail") or "").strip()
        if detail:
            lines.append(f"• 확인: {esc(detail)}")
        lines += [
            f"• 일정 영향: <b>{esc(impact_label(item.get('impact', '')))}</b>",
            "• 출처: LH 공식",
        ]
        if item.get("url"):
            lines.append(link_line(item["url"]))

    for item in news:
        stages = item.get("stage_labels") or [STAGE_LABELS.get(s, s) for s in item.get("stages", [])]
        label = " · ".join(stages) if stages else "관련 변화"
        source = item.get("source") or "웹 검색"
        title = clean_title(item.get("title", ""), source)
        lines += [
            "",
            f"<b>{esc(label)}</b>",
            f"• 변화: {esc(title)}",
            f"• 일정 영향: <b>{esc(impact_label(item.get('impact', '')))}</b>",
            f"• 출처: {esc(source)}",
        ]
        published = fmt_published(item.get("published", ""))
        if published:
            lines.append(f"• 공개: {esc(published)}")
        if item.get("url"):
            lines.append(link_line(item["url"]))

    lines += [
        "",
        "<b>확인 순서</b>",
        "① 수행업체 선정·현지조사 착수 → ② 수량·수질 조사범위 → ③ 람사르 심사 결과",
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
