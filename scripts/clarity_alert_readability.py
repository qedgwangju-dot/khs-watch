#!/usr/bin/env python3
import html
import importlib.util
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
ALERT_JSON = OUT_DIR / "clarity_watch_alert.json"
OUT_HTML = OUT_DIR / "clarity_watch_alert.html"
OUT_CHUNKS = OUT_DIR / "clarity_watch_telegram_chunks.json"

SPEC = importlib.util.spec_from_file_location(
    "clarity_alert_formatter", ROOT / "scripts" / "clarity_alert_formatter.py"
)
FMT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FMT)


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def is_ethics_breakthrough(event):
    return "윤리 합의 진전" in clean(event.get("event_type", ""))


def is_media_text_release(event):
    et = clean(event.get("event_type", ""))
    return bool(event.get("text_release")) or ("문안 공개" in et and "신뢰매체" in et)


def event_rank(event):
    et = clean(event.get("event_type", ""))
    title = clean(event.get("title", "")).lower()
    if "표결 결과" in et or "통과·부결" in et:
        return 200
    if "토론종결" in et or "cloture" in title:
        return 190
    if "원문·핵심 조항 수정" in et or "원문 버전" in et:
        return 180
    if is_media_text_release(event):
        return 178
    if is_ethics_breakthrough(event):
        return 175
    if FMT.rule_stage(event) == "final":
        return 170
    if "본회의 일정" in et:
        return 160
    if FMT.rule_stage(event) == "proposed":
        return 150
    if FMT.is_policy_pressure(event):
        return 120
    if FMT.is_industry_pressure(event):
        return 100
    return 80


def localized(event):
    return FMT.localize_event(event)


def easy_takeaway(event, body_ko):
    meaning = clean(FMT.easy_meaning(event, body_ko))
    if not meaning:
        return ""
    parts = re.split(r"(?<=[.!?。])\s+", meaning)
    if len(parts) <= 2:
        return meaning
    return " ".join(parts[:2]).strip()


def short_change(event, title_ko, body_ko):
    et = clean(event.get("event_type", ""))
    if is_media_text_release(event):
        return "상원 공화당의 CLARITY 최신·최종 초안 공개가 신뢰매체에서 확인됐습니다. 단순 발언이 아니라 법안 문안 자체가 바뀐 상태 변화이며, 공식 Senate/GovInfo 원문으로 조항을 재확인하는 단계입니다."
    if is_ethics_breakthrough(event):
        return "Trump 대통령이 Tillis–Gallego 윤리 절충안의 약 80%를 수용했다는 신뢰 보도가 확인됐고, 60표 확보의 핵심 정치적 장애물이 완화되는 방향으로 바뀌었습니다."
    if "표결 결과" in et:
        return title_ko + ". 단순 발언이 아니라 실제 찬반 결과가 나온 절차 변화입니다."
    if "토론종결" in et:
        return title_ko + ". 본회의 진행 여부를 가르는 절차 관문이 실제로 움직였습니다."
    if "본회의 일정" in et:
        return title_ko + ". 법안의 실제 표결 시간표가 새로 확정되거나 변경됐습니다."
    if "수정" in et or "원문 버전" in et:
        return title_ko + ". 법안 문안 자체가 바뀌어 규제 내용 재평가가 필요한 변화입니다."
    if FMT.rule_stage(event) == "proposed":
        return title_ko + ". 최종 규칙이 아니라 제안규칙이 공개된 단계입니다."
    if FMT.rule_stage(event) == "final":
        return title_ko + ". 사업자 의무에 직접 연결될 수 있는 최종 규칙 단계입니다."
    if FMT.is_policy_pressure(event):
        return title_ko + ". 공식 표결은 아니지만 상원 협상과 시간표에 영향을 주는 정책 압력이 강화됐습니다."
    if FMT.is_industry_pressure(event):
        return title_ko + ". 직접 수혜·규제 대상 사업자의 입법 압력이 강해진 보조 신호입니다."
    first = re.split(r"(?<=[.!?。])\s+", clean(body_ko))[0]
    return first or title_ko


def current_status(event):
    et = clean(event.get("event_type", ""))
    verification = clean(event.get("verification_status", ""))
    if is_media_text_release(event):
        return "🟡 문안 변화 확인 — 신뢰매체가 새 초안 공개를 확인했지만, 공식 Senate Banking·GovInfo·Congress.gov 원문을 확보해 실제 조항을 잠그기 전까지는 ‘공식 문안 확정’으로 올리지 않습니다."
    if is_ethics_breakthrough(event):
        return "🟡 협상 진전 — 보좌관·신뢰매체 확인. 백악관 공개 확인과 개정 법안 원문은 아직 대기 중입니다."
    stage = FMT.rule_stage(event)
    if stage == "prerule":
        return "🟡 Prerule(사전규칙 단계) — OIRA 검토에는 들어갔지만 아직 Proposed Rule(제안규칙)·Final Rule(최종규칙)·시행 규정은 아닙니다."
    if stage == "proposed":
        return "🟡 제안 단계 — 공식 제안규칙이지만 아직 최종 의무는 확정되지 않았습니다."
    if stage == "final":
        return "🟢 최종 규칙 — 시행일·준수기한과 실제 사업 영향 확인 단계입니다."
    if "표결 결과" in et:
        return "🟢 실제 표결 — 찬반 결과가 확인된 확정 절차 변화입니다."
    if "토론종결" in et:
        return "🟢 실제 절차표결 — 본회의 진행을 가르는 관문입니다."
    if "본회의 일정" in et:
        return "🟢 공식 일정 — 상원 일정에서 확인된 시간표 변화입니다."
    if "수정" in et or "원문 버전" in et:
        return "🟢 공식 문안 변화 — 새 조문을 이전 문안과 비교해야 합니다."
    if FMT.is_industry_pressure(event):
        return "🔵 업계 압박 — 직접 이해관계자의 발언이며, 공식 표 수·절차 변화와는 구분합니다."
    if FMT.is_policy_pressure(event):
        return "🟡 정책 압력 — 실제 표결·법률 효력은 아니지만 통과 확률과 시간표에 영향을 줄 수 있습니다."
    if verification:
        return "🟡 검증 진행 — " + verification
    return "🟡 변화 확인 — 후속 공식 절차를 추가 확인합니다."


def ethics_investment_lines():
    return [
        "돈 버는 능력 → 아직 변화 없음. Coinbase·Circle의 현재 매출·마진은 법안 통과 전이라 직접 바뀌지 않았습니다.",
        "할인율 ↑ 규제 불확실성 완화 방향. 가장 큰 정치적 리스크 중 하나가 줄어드는 신호입니다.",
        "수급 ↑/△ COIN·CRCL에는 통과 기대가 더 직접적이고 BTC에는 간접적입니다.",
        "시간표 ↑↑ 가장 크게 개선. 60표 확보의 핵심 장애물인 윤리 협상 간극이 줄었습니다.",
    ]


def media_text_investment_lines():
    return [
        "돈 버는 능력 → 아직 직접 변화 없음. 새 초안이 공개돼도 법안 통과·시행 전까지 COIN·CRCL 현재 매출·마진은 그대로입니다.",
        "할인율 ↑/△ 문안 가시성은 규제 불확실성을 줄이는 방향이지만, 공식 원문과 최종 표결 전에는 확정 효과가 아닙니다.",
        "수급 ↑/△ 윤리·DeFi·stablecoin·SEC/CFTC 조항이 시장 기대를 바꿀 수 있어 COIN·CRCL에는 더 직접적이고 BTC에는 간접적입니다.",
        "시간표 ↑ 최신 초안 공개는 60표 절차표결 직전 협상이 실제 문안 단계로 진입했다는 신호입니다. 다음 관문은 공식 원문 확인과 cloture 결과입니다.",
    ]


def investment_lines(event):
    if is_media_text_release(event):
        return media_text_investment_lines()
    if is_ethics_breakthrough(event):
        return ethics_investment_lines()
    return FMT.investment_lines(event)


def impact_snapshot(event):
    et = clean(event.get("event_type", ""))
    if is_media_text_release(event):
        return "시간표 ↑ · 할인율 ↑/△ · 수급 ↑/△ · 돈 버는 능력 →"
    if is_ethics_breakthrough(event):
        return "시간표 ↑↑ · 할인율 ↑ · 수급 ↑/△ · 돈 버는 능력 →"
    if "표결 결과" in et or "토론종결" in et:
        return "시간표 ↑↑ · 할인율 ↑ · 수급 ↑/△ · 돈 버는 능력 →"
    if "본회의 일정" in et:
        return "시간표 ↑ · 할인율 △ · 수급 △ · 돈 버는 능력 →"
    if FMT.rule_stage(event) == "prerule":
        return "시간표 ↑ · 규제 방향 구체화 시작 · 돈 버는 능력은 아직 미확정"
    if FMT.rule_stage(event) == "proposed":
        return "할인율 ↑/△ · 시간표 ↑ · 돈 버는 능력 미확정"
    if FMT.rule_stage(event) == "final":
        return "돈 버는 능력 조항별 변화 · 할인율 ↑ · 시행 시간표 확정"
    if FMT.is_policy_pressure(event):
        return "시간표 ↑ · 할인율 ↑(기대) · 수급 △ · 돈 버는 능력 →"
    if FMT.is_industry_pressure(event):
        return "시간표 △ · 할인율 △ · 수급 △ · 돈 버는 능력 →"
    return "투자 4축 재평가 필요"


def sentence_bullets(text):
    text = clean(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def pending_lines(event):
    lines = []
    verification = clean(event.get("verification_status", ""))
    if verification:
        for part in re.split(r"\s*/\s*", verification):
            if part:
                lines.append(part)
    if is_media_text_release(event):
        lines.extend([
            "Senate Banking·GovInfo·Congress.gov에 올라온 실제 개정 원문",
            "윤리·State AG 집행권·DeFi·stablecoin rewards·SEC/CFTC 권한의 최종 문구",
            "새 초안이 60표 확보에 충분한지 여부",
        ])
    elif is_ethics_breakthrough(event):
        lines.extend([
            "White House의 공개 확인 여부",
            "개정 CLARITY 법안 원문에 실제로 들어간 윤리 조항 문구",
            "60표 확보 여부와 실제 절차표결 결과",
        ])
    elif FMT.rule_stage(event) == "prerule":
        lines.extend([
            "실제 규칙 본문과 적용 대상",
            "현물·파생·레버리지·마진·거래소 등록 가운데 무엇을 규율하는지",
            "OIRA 검토 종료 뒤 Proposed Rule(제안규칙) 단계로 넘어가는지 여부",
        ])
    elif FMT.rule_stage(event) == "proposed":
        lines.extend(["의견수렴 후 최종 문안", "최종 채택 여부·시행일·준수기한"])
    elif FMT.is_policy_pressure(event):
        lines.extend(["실제 상원 표 수 변화", "공식 표결 일정·절차 결과"])
    elif FMT.is_industry_pressure(event):
        lines.extend(["실제 의원 표 수 변화", "공식 일정 변경 여부"])
    return list(dict.fromkeys(lines))


def next_check_lines(event):
    et = clean(event.get("event_type", ""))
    if is_media_text_release(event):
        return ["공식 개정 법안 PDF·텍스트 확보", "직전 버전과 조문별 diff", "상원 cloture·motion to proceed 60표 결과"]
    if is_ethics_breakthrough(event):
        return ["백악관 공개 확인", "개정 법안 원문 공개", "상원 cloture·motion to proceed 및 찬반 숫자"]
    if "본회의 일정" in et:
        return ["예정 시각 실제 개회 여부", "cloture/motion to proceed 결과", "최종 본회의 표결 일정"]
    if "표결 결과" in et:
        return ["다음 의회 절차", "수정 문안 여부", "하원 재처리·대통령 조치"]
    if FMT.rule_stage(event) == "prerule":
        return ["OIRA Pending Review(검토 중) 종료", "CFTC 공개 문안", "NPRM(정식 제안규칙 공고) 여부"]
    if FMT.rule_stage(event) == "proposed":
        return ["의견수렴 마감", "최종규칙 채택 여부", "시행일·준수기한"]
    if FMT.rule_stage(event) == "final":
        return ["시행일", "전환기간·준수기한", "소송·시행유예 여부"]
    if FMT.is_policy_pressure(event) or FMT.is_industry_pressure(event):
        return ["상원 공식 일정", "motion to proceed·cloture", "실제 표결 결과"]
    return ["다음 공식 문서·표결·일정 변화"]


def evidence_block(event):
    evidence = event.get("evidence_sources") or []
    if not evidence:
        source = clean(event.get("source", ""))
        evidence = [source] if source else []
    lines = []
    if evidence:
        lines.append("검증 근거: " + " · ".join(html.escape(clean(x)) for x in evidence))
    if event.get("date"):
        formatted, converted = FMT.format_event_date_korean(event.get("date", ""))
        label = "공식/보도 시각(한국시간)" if converted else "공식 날짜"
        lines.append(f"{label}: {html.escape(formatted)}")
    url = clean(event.get("url", ""))
    if url:
        lines.append(f'<a href="{html.escape(url, quote=True)}">원문</a>')
    return lines


def ethics_core_summary():
    return (
        "Trump의 Tillis–Gallego 윤리안 대폭 수용으로 실제 개선된 축은 시간표·규제 할인율이며 COIN·CRCL에는 호재 방향이지만, "
        "백악관 공개 확인·개정 원문·실제 60표가 아직 남아 있어 현재 돈 버는 능력은 그대로이고 표결 실패·문안 후퇴가 핵심 실패 경로입니다."
    )


def media_text_core_summary():
    return (
        "상원 공화당의 최신 CLARITY 초안 공개 보도는 기사 자체가 아니라 법안 문안이 바뀐 상태 변화로, 시간표·규제 할인율에는 긍정적이지만 현재 돈 버는 능력은 아직 그대로이며 "
        "공식 원문에서 윤리·DeFi·stablecoin·SEC/CFTC 조항을 확인하고 실제 60표를 확보하지 못하면 기대 효과가 되돌려지는 것이 핵심 실패 경로입니다."
    )


def core_summary(event):
    if is_media_text_release(event):
        return media_text_core_summary()
    return ethics_core_summary() if is_ethics_breakthrough(event) else FMT.core_summary(event)


def event_block(event, index):
    title_ko, body_ko = localized(event)
    takeaway = easy_takeaway(event, body_ko)
    lines = [
        f"<b>{index}. {html.escape(title_ko)}</b>",
    ]
    if takeaway:
        lines.extend([
            "",
            "<b>🧩 한마디로</b>",
            html.escape(takeaway),
        ])
    lines.extend([
        "",
        "<b>🧭 무엇이 달라졌나</b>",
        html.escape(short_change(event, title_ko, body_ko)),
        "",
        "<b>📍 현재 판정</b>",
        html.escape(current_status(event)),
        "",
        "<b>💰 투자 의미</b>",
    ])
    for line in investment_lines(event):
        lines.append("• " + html.escape(line))

    facts = sentence_bullets(body_ko)
    if facts:
        lines.extend(["", "<b>✅ 확인된 사실</b>"])
        for fact in facts:
            lines.append("• " + html.escape(fact))

    pending = pending_lines(event)
    if pending:
        lines.extend(["", "<b>⚠️ 아직 미확정</b>"])
        for item in pending:
            lines.append("• " + html.escape(item))

    next_lines = next_check_lines(event)
    if next_lines:
        lines.extend(["", "<b>⏱ 다음 확인</b>"])
        for item in next_lines:
            lines.append("• " + html.escape(item))

    evidence = evidence_block(event)
    if evidence:
        lines.extend(["", "<b>🔎 근거</b>"] + evidence)
    return "\n".join(lines)


def paragraph_split(text, limit=3900):
    paragraphs = text.split("\n\n")
    chunks, current = [], ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= limit:
            current = paragraph
            continue
        lines, buf = paragraph.splitlines(), ""
        for line in lines:
            candidate = line if not buf else buf + "\n" + line
            if len(candidate) <= limit:
                buf = candidate
            else:
                if buf:
                    chunks.append(buf)
                buf = line
        current = buf
    if current:
        chunks.append(current)
    return chunks


def build_readable(events):
    events = sorted(events, key=event_rank, reverse=True)
    header = "<b>🔔 CLARITY 법안 Watch — 표결·규제·BTC/COIN/Circle 영향</b>"
    overview = ["<b>한눈에 보기</b>"]
    for event in events:
        title_ko, body_ko = localized(event)
        takeaway = easy_takeaway(event, body_ko)
        overview.append("• " + html.escape(takeaway or short_change(event, title_ko, body_ko)))
        overview.append("  ↳ " + html.escape(impact_snapshot(event)))

    blocks = [event_block(event, i) for i, event in enumerate(events, 1)]
    primary = events[0]
    tail = [
        "<b>📊 시장 반응·원인 분리</b>",
        "BTC·ETH·COIN·CRCL이 움직였더라도 이번 사건 때문이라고 바로 단정하지 않습니다. 의미 있는 가격·거래량 변화가 확인되면 미국 국채금리·달러·Nasdaq/S&P 500과 같은 시간대를 비교해 CLARITY 직접 효과와 거시 효과를 분리합니다.",
        "",
        "<b>핵심 한 줄 요약</b>",
        html.escape(core_summary(primary)),
    ]
    full = header + "\n\n" + "\n".join(overview) + "\n\n" + "\n\n".join(blocks) + "\n\n" + "\n".join(tail)
    return paragraph_split(full)


def main():
    if not ALERT_JSON.exists():
        print("clarity_readability=false reason=no_alert_json")
        return
    events = json.loads(ALERT_JSON.read_text(encoding="utf-8"))
    events = FMT.filter_alertable_events(events)
    if not events:
        print("clarity_readability=false reason=no_fresh_event")
        return
    chunks = build_readable(events)
    OUT_CHUNKS.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_HTML.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    print(f"clarity_readability=true events={len(events)} chunks={len(chunks)}")


if __name__ == "__main__":
    main()
