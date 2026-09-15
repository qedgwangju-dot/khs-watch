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


def build_gate_block(gate):
    time_kst = str(gate.get("official_time_kst") or "")
    pretty_kst = "2026년 9월 16일 03:15 KST" if time_kst.startswith("2026-09-16T03:15") else html.escape(time_kst)
    lines = [
        "<b>⏱ 표결 관문</b>",
        f"• 절차 │ {html.escape(str(gate.get('procedure') or 'H.R.3633 motion to proceed cloture'))}",
        f"• 한국시간 │ {pretty_kst}",
        f"• 필요표 │ {int(gate.get('votes_required') or 60)}표",
        f"• 현재 확보 │ {html.escape(str(gate.get('whip_count_status') or '공식 확정표 미공개'))}",
        f"• 최종안 │ {html.escape(str(gate.get('final_draft_context') or ''))}",
    ]
    bottlenecks = gate.get("main_bottlenecks") or []
    if bottlenecks:
        lines.append("• 최대 병목 │ " + html.escape(" · ".join(str(x) for x in bottlenecks[:5])))

    roll = gate.get("roll_call") or {}
    if roll:
        result = str(roll.get("result") or "확인 중")
        yeas = roll.get("yeas")
        nays = roll.get("nays")
        nv = roll.get("not_voting")
        lines.extend([
            "",
            "<b>🗳 실제 표결 결과</b>",
            f"• 판정 │ {html.escape(result)}",
            f"• 찬성/반대/불참 │ {yeas if yeas is not None else '확인 중'} / {nays if nays is not None else '확인 중'} / {nv if nv is not None else '확인 중'}",
            "• 의미 │ 최종 통과표결이 아니라 본회의 심의를 계속하기 위한 cloture 관문",
        ])

    reaction = gate.get("market_reaction") or {}
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
                lines.append(f"  ↳ 거래량 │ {fmt_pct(row.get('volume_change_pct'))} (동일 시세원 regularMarketVolume 비교)")
        lines.append("• 원인 분리 │ 같은 시간 Nasdaq·S&P 500·DXY·미 10년물과 비교해 CLARITY 직접 효과와 거시 효과를 분리")
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
