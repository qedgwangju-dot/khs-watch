#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import re
from pathlib import Path

ALERT = Path("out/us_data_center_time_to_power_alert.txt")

HEADINGS = [
    "<b>⚡ 전력 인가 실행판</b>",
    "<b>🔄 실행 숫자 변경</b>",
    "<b>🆕 핵심 신규 변화</b>",
    "<b>👀 새 감시 범위</b>",
    "<b>📊 투자 해석</b>",
    "<b>💱 환율</b>",
    "<b>🔗 공식 원문</b>",
]


def strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def section(lines: list[str], heading: str) -> list[str]:
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return []
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i] in HEADINGS:
            end = i
            break
    return [x for x in lines[start:end] if x.strip()]


def format_dashboard(rows: list[str]) -> list[str]:
    out = []
    for row in rows:
        plain = strip_tags(row)
        if plain.startswith("• PJM"):
            m = re.search(r"(\d[\d,]*)MW", plain)
            mw = m.group(1) if m else "확인 중"
            out.append(f"• <b>PJM</b>  │ 부족 <b>{mw}MW</b> │ RBP·IRAS")
        elif plain.startswith("• MISO") and "ERAS 누적" in plain:
            m = re.search(r"ERAS 누적 약 ([0-9.]+)GW.*GIA 완료 약 ([0-9.]+)GW.*\(([0-9.]+)%\)", plain)
            if m:
                out.append(f"• <b>MISO</b> │ ERAS <b>{m.group(1)}GW</b> → GIA <b>{m.group(2)}GW</b> │ <b>{m.group(3)}%</b>")
            else:
                out.append(row)
        elif plain.startswith("↳ 제5차") or plain.startswith("↳제5차"):
            m = re.search(r"제5차\s+(\d+)개·([0-9,.]+)MW\s*=\s*가스\s*([0-9,.]+)MW\s*\+\s*BESS\s*([0-9,.]+)MW\s*\+\s*태양광\s*([0-9,.]+)MW\s*\+\s*풍력\s*([0-9,.]+)MW", plain)
            if m:
                out.append(
                    f"   ↳ 제5차 <b>{m.group(1)}개·{m.group(2)}MW</b> │ 가스 {m.group(3)} · BESS {m.group(4)} · 태양광 {m.group(5)} · 풍력 {m.group(6)}MW"
                )
            else:
                out.append(row)
        elif plain.startswith("• ERCOT"):
            out.append("• <b>ERCOT</b> │ Batch Zero │ 조건부 → 검증 → 확정 → 접속")
        elif plain.startswith("• FERC"):
            out.append("• <b>FERC</b>  │ 6개 전력시장 │ 접속·비용배분 규칙")
        elif plain.startswith("• 800V DC"):
            out.append("• <b>800V DC</b> │ 고객 채택·수주·양산·인증 때만 알림")
        else:
            out.append(row)
    return out


def parse_new_items(rows: list[str]) -> tuple[str | None, list[tuple[str, str, str, str]], str | None]:
    summary = None
    hidden = None
    items: list[tuple[str, str, str, str]] = []
    i = 0
    meta_re = re.compile(r"^• <b>(.*?)</b> · \[(공식|보도)\] (.*)$")
    link_re = re.compile(r'^\s*↳ 🔗 <a href="([^"]+)">(.*?)</a>(.*)$')
    while i < len(rows):
        row = rows[i]
        if row.startswith("• 새 자료 "):
            summary = row
            i += 1
            continue
        if "나머지" in row and "중복방지" in row:
            hidden = row
            i += 1
            continue
        m = meta_re.match(row)
        if m and i + 1 < len(rows):
            lm = link_re.match(rows[i + 1])
            if lm:
                theme, badge, source = m.group(1), m.group(2), m.group(3)
                url = html.unescape(lm.group(1))
                title = lm.group(2)
                suffix = lm.group(3)
                items.append((theme, badge, source, f'<a href="{html.escape(url, quote=True)}">{title}</a>{suffix}'))
                i += 2
                continue
        i += 1
    return summary, items, hidden


def format_fx(rows: list[str]) -> list[str]:
    out = []
    for row in rows:
        plain = strip_tags(row)
        m = re.search(r"1달러\s*=\s*([0-9,.]+)원\s*·\s*([^·]+)\s*·\s*([0-9T:+-]+)\s*UTC", plain)
        if not m:
            if "외화 금액" in plain:
                out.append("• 외화 금액은 <b>같은 줄에 원화 환산</b>을 붙입니다.")
            else:
                out.append(row)
            continue
        try:
            utc = dt.datetime.fromisoformat(m.group(3))
            if utc.tzinfo is None:
                utc = utc.replace(tzinfo=dt.timezone.utc)
            kst = utc.astimezone(dt.timezone(dt.timedelta(hours=9)))
            when = kst.strftime("%Y-%m-%d %H:%M KST")
        except Exception:
            when = m.group(3) + " UTC"
        out.append(f"• <b>1달러 = {m.group(1)}원</b> │ {html.escape(m.group(2).strip())} │ {when}")
    return out


def main() -> None:
    if not ALERT.exists():
        return
    raw = ALERT.read_text(encoding="utf-8").strip()
    if not raw:
        return
    lines = raw.splitlines()
    headline = lines[0] if lines else "<b>🚨 미국 데이터센터 전력 인가 실행 변화</b>"

    dash = section(lines, "<b>⚡ 전력 인가 실행판</b>")
    metric = section(lines, "<b>🔄 실행 숫자 변경</b>")
    new_rows = section(lines, "<b>🆕 핵심 신규 변화</b>")
    watch_rows = section(lines, "<b>👀 새 감시 범위</b>")
    invest = section(lines, "<b>📊 투자 해석</b>")
    fx = section(lines, "<b>💱 환율</b>")

    summary, items, hidden = parse_new_items(new_rows)

    out = [headline, "", "<b>🧭 한눈에</b>"]
    if metric:
        first = strip_tags(metric[0]).lstrip("• ")
        out.append(f"• <b>이번 핵심 변화</b> │ {html.escape(first)}")
    elif items:
        out.append(f"• <b>이번 핵심 변화</b> │ {items[0][3]}")
    elif watch_rows:
        out.append("• <b>이번 핵심 변화</b> │ 미국 데이터센터 전력 인가 감시 범위 확대")
    else:
        out.append("• <b>이번 핵심 변화</b> │ 공식 실행 단계 변화 확인")
    out.append("• <b>판단 기준</b> │ 발표 GW보다 GIA → 착공 → 전원 인가 → 상업운전 전환을 우선")

    out += ["", "<b>⚡ 전력 인가 실행판</b>"] + format_dashboard(dash)

    if metric:
        out += ["", "<b>🔄 이번에 바뀐 실행 숫자</b>"]
        for row in metric[:6]:
            plain = strip_tags(row).lstrip("• ")
            # State repair should never be presented as a real project withdrawal.
            if "제외·철회 가능성" in plain:
                out.append(f"• <i>기준값 재검증 항목</i> │ {html.escape(plain.replace('제외·철회 가능성:', '').strip())}")
            else:
                out.append(f"• <b>{html.escape(plain)}</b>")

    if items or summary:
        out += ["", "<b>🆕 핵심 신규 자료</b>"]
        if summary:
            # Keep counts, but make them visually secondary.
            out.append(summary.replace("• 새 자료", "• 전체 신규"))
        for idx, (theme, badge, source, linked) in enumerate(items, 1):
            source_ko = source.replace("Federal Register", "미국 연방관보")
            out.append(f"{idx}. {linked}")
            out.append(f"   <i>{html.escape(theme)} · {badge} · {html.escape(source_ko)}</i>")
        if hidden:
            out.append(hidden)

    if watch_rows:
        out += ["", "<b>👀 새 감시 범위</b>"] + watch_rows

    if invest:
        out += ["", "<b>📊 투자 판단</b>"]
        for row in invest:
            plain = strip_tags(row)
            if plain.startswith("• 핵심 순서:"):
                out.append("• <b>실행순서</b> │ 계획 → 심사 → GIA → 착공 → 상업운전")
            elif "발표 용량이 늘어도" in plain:
                out.append("• <b>매출 연결</b> │ GIA·착공·전원 인가로 내려와야 실적 전환으로 판단")
            elif "500MW 이상" in plain:
                out.append("• <b>알림 우선순위</b> │ 500MW 이상 신규·취소·용량 변경·단계 전환")
            elif "발전·BESS와 부하 위치" in plain:
                out.append("• <b>다음 병목</b> │ 발전·BESS와 부하 위치가 다르면 변전소·송전선 비용 확인")
            else:
                out.append(row)

    out += ["", "<b>💱 환율</b>"] + format_fx(fx)
    out += ["", "<b>🔗 원문</b>", "• 위 신규 자료는 <b>한국어 제목 자체를 누르면 원문으로 이동</b>합니다.", "• FERC·MISO·ERCOT 공식 페이지는 아래 버튼에서 바로 열 수 있습니다."]

    text = "\n".join(out).strip() + "\n"
    ALERT.write_text(text, encoding="utf-8")
    print(f"time_to_power_readability items={len(items)} metric_changes={len(metric)}")


if __name__ == "__main__":
    main()
