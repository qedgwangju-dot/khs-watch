#!/usr/bin/env python3
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
GATE_PATH = OUT / "clarity_vote_gate.json"
CHUNKS_PATH = OUT / "clarity_watch_telegram_chunks.json"
HTML_PATH = OUT / "clarity_watch_alert.html"


def fmt_pct(value):
    if value is None:
        return "확인 불가"
    return f"{value:+.2f}%"


def _pretty_kst(value, fallback="확인 불가"):
    raw = str(value or "").strip()
    if not raw:
        return fallback
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(raw)
        return parsed.strftime("%Y년 %m월 %d일 %H:%M KST")
    except Exception:
        return html.escape(raw)


def _procedure_ko(value):
    raw = str(value or "").strip()
    low = raw.lower()
    if "h.r.3633" in low and "motion to proceed" in low and "cloture" in low:
        return "H.R.3633 본회의 심의 진행을 위한 토론종결(cloture) 표결"
    return raw or "H.R.3633 본회의 심의 진행 절차"


def _result_ko(value):
    raw = str(value or "").strip()
    mapping = {
        "rejected": "부결",
        "failed": "부결",
        "agreed": "가결",
        "passed": "가결",
    }
    return mapping.get(raw.lower(), raw or "확인 중")


def build_gate_block(gate):
    roll = gate.get("roll_call") or {}
    reaction = gate.get("market_reaction") or {}

    if roll:
        result = _result_ko(roll.get("result"))
        yeas = roll.get("yeas")
        nays = roll.get("nays")
        nv = roll.get("not_voting")
        vote_time = _pretty_kst(roll.get("vote_time_kst"), "미 상원 공식 표결 완료")
        current_stage = str(gate.get("current_stage") or "")
        next_vote = str(gate.get("next_vote_status") or "공식 새 CLARITY 표결 일정 미확인")
        reconsideration = gate.get("reconsideration") or {}

        lines = [
            "<b>⏱ 현재 의회 상태</b>",
            f"• 절차 │ {html.escape(_procedure_ko(gate.get('procedure')))}",
            f"• 완료 표결 │ {html.escape(vote_time)}",
            f"• 결과 │ {html.escape(result)} — {yeas if yeas is not None else '확인 중'} / {nays if nays is not None else '확인 중'} / {nv if nv is not None else '확인 중'}",
            f"• 필요표 │ {int(gate.get('votes_required') or 60)}표",
            f"• 현재 단계 │ {html.escape(current_stage or '공식 절차 상태 확인 중')}",
        ]
        if reconsideration.get("entered") is True:
            lines.append("• 후속 절차 │ Thom Tillis가 부결된 토론종결 표결의 재고동의를 제출")
        elif reconsideration.get("entered") is None:
            lines.append("• 후속 절차 │ 재고동의 원문 확인 상태를 재점검 중")
        lines.append(f"• 다음 CLARITY 표결 │ {html.escape(next_vote)}")
        lines.append("• 표시 원칙 │ 완료된 9월 16일 표결은 과거 결과로만 표시하고 새 공식 일정이 확인되기 전에는 예정 관문으로 재노출하지 않음")
    else:
        time_kst = str(gate.get("official_time_kst") or "")
        pretty_kst = "2026년 9월 16일 03:15 KST" if time_kst.startswith("2026-09-16T03:15") else html.escape(time_kst)
        lines = [
            "<b>⏱ 표결 관문</b>",
            f"• 절차 │ {html.escape(_procedure_ko(gate.get('procedure')))}",
            f"• 한국시간 │ {pretty_kst}",
            f"• 필요표 │ {int(gate.get('votes_required') or 60)}표",
            f"• 현재 확보 │ {html.escape(str(gate.get('whip_count_status') or '공식 확정표 미공개'))}",
            f"• 최종안 │ {html.escape(str(gate.get('final_draft_context') or ''))}",
        ]
        bottlenecks = gate.get("main_bottlenecks") or []
        if bottlenecks:
            lines.append("• 최대 병목 │ " + html.escape(" · ".join(str(x) for x in bottlenecks[:5])))

    if reaction:
        window = str(gate.get("market_reaction_window") or "즉시")
        heading = "📊 표결 24시간 실측 시장 반응" if "24" in window else "📊 표결창 실측 시장 반응"
        lines.extend(["", f"<b>{heading}</b>"])
        for label in ("BTC", "ETH", "COIN", "CRCL", "Nasdaq", "S&P 500", "DXY", "US10Y"):
            row = reaction.get(label)
            if not row:
                continue
            suffix = "" if label != "US10Y" else " (^TNX 기준)"
            lines.append(f"• {html.escape(label)}{suffix} │ 가격 {fmt_pct(row.get('change_pct'))}")
            if row.get("volume_change_pct") is not None and label in {"BTC", "ETH", "COIN", "CRCL"}:
                lines.append(f"  ↳ 거래량 │ {fmt_pct(row.get('volume_change_pct'))} (동일 시세원 정규장 거래량 기준)")
        lines.append("• 원인 분리 │ 같은 시간 Nasdaq·S&amp;P 500·DXY·미 10년물과 비교해 CLARITY 직접 효과와 거시 효과를 분리")
    return "\n".join(lines)


def inject_first_chunk(chunk, block):
    lines = chunk.splitlines()
    if not lines:
        return block
    insert_at = 0
    if lines and "CLARITY 법안 Watch" in lines[0]:
        insert_at = 1
        if len(lines) > 1 and "표결·규제" in lines[1]:
            insert_at = 2
        if len(lines) > insert_at and set(lines[insert_at].strip()) == {"━"}:
            insert_at += 1
    return "\n".join(lines[:insert_at] + ["", block, ""] + lines[insert_at:])


def main():
    if not GATE_PATH.exists() or not CHUNKS_PATH.exists():
        print("clarity_vote_gate_enrichment=false reason=missing_input")
        return
    gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    if not chunks:
        print("clarity_vote_gate_enrichment=false reason=no_chunks")
        return
    block = build_gate_block(gate)
    chunks[0] = inject_first_chunk(chunks[0], block)
    for tag in ("<i>", "</i>", "<em>", "</em>"):
        chunks = [x.replace(tag, "") for x in chunks]
    CHUNKS_PATH.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if HTML_PATH.exists():
        HTML_PATH.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    print(f"clarity_vote_gate_enrichment=true chunks={len(chunks)} italics=disabled")


if __name__ == "__main__":
    main()
