#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import re
from pathlib import Path

ALERT = Path("out/us_data_center_time_to_power_alert.txt")

HEADINGS = [
    "<b>⚡ 전력 인가 실행판</b>",
    "<b>🔌 800V DC·SiC/GaN 실행판</b>",
    "<b>🔄 800V DC·SiC/GaN 기준 변경</b>",
    "<b>🏛️ 주정부 인허가·비용부담 실행판</b>",
    "<b>🔄 주정부 인허가·비용부담 기준 변경</b>",
    "<b>🧠 유연부하·수요반응 실행판</b>",
    "<b>🔄 유연부하 숫자 변경</b>",
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


def _first_matching(rows: list[str], prefixes: tuple[str, ...]) -> list[str]:
    picked = []
    for row in rows:
        plain = strip_tags(row)
        if any(plain.startswith(prefix) for prefix in prefixes):
            picked.append(row)
    return picked


def _compact_policy(rows: list[str]) -> list[str]:
    picked = []
    for prefix in ("• Massachusetts", "• Pennsylvania", "• Virginia"):
        match = next((row for row in rows if strip_tags(row).startswith(prefix)), None)
        if match:
            picked.append(match)
    return picked


def _compact_800v(rows: list[str]) -> list[str]:
    keep = []
    for prefix in ("• NVIDIA 시간표", "• 공식 공급 검증", "• DIGITIMES Research"):
        row = next((x for x in rows if strip_tags(x).startswith(prefix)), None)
        if row:
            keep.append(row)
    return keep[:3]


def _compact_flexible(rows: list[str]) -> list[str]:
    keep = []
    for prefix in ("• Google 상업 계약", "• 부하감축 성능", "• 계통접속 적체"):
        row = next((x for x in rows if strip_tags(x).startswith(prefix)), None)
        if row:
            keep.append(row)
    return keep[:3]


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
    semi = section(lines, "<b>🔌 800V DC·SiC/GaN 실행판</b>")
    semi_changes = section(lines, "<b>🔄 800V DC·SiC/GaN 기준 변경</b>")
    policy = section(lines, "<b>🏛️ 주정부 인허가·비용부담 실행판</b>")
    policy_changes = section(lines, "<b>🔄 주정부 인허가·비용부담 기준 변경</b>")
    flexible = section(lines, "<b>🧠 유연부하·수요반응 실행판</b>")
    flexible_changes = section(lines, "<b>🔄 유연부하 숫자 변경</b>")

    summary, items, hidden = parse_new_items(new_rows)
    is_upgrade = "업그레이드 완료" in strip_tags(headline) or "확장 완료" in strip_tags(headline)

    out = [headline, "", "<b>🧭 핵심</b>"]
    if policy_changes:
        first = strip_tags(policy_changes[0]).lstrip("• ")
        if "Pennsylvania 신규 전력인프라 전액 부담" in first and "False" in first and "True" in first:
            out.append("• <b>정정</b> │ Pennsylvania의 프로젝트 유발 전력비용 100% 부담은 <b>새 정책 변화가 아니라 기존 공식 기준 재검증</b>")
        else:
            out.append(f"• <b>변화</b> │ {html.escape(first)}")
    elif metric:
        out.append(f"• <b>변화</b> │ {html.escape(strip_tags(metric[0]).lstrip('• '))}")
    elif semi_changes:
        out.append(f"• <b>변화</b> │ {html.escape(strip_tags(semi_changes[0]).lstrip('• '))}")
    elif flexible_changes:
        out.append(f"• <b>변화</b> │ {html.escape(strip_tags(flexible_changes[0]).lstrip('• '))}")
    elif items:
        out.append(f"• <b>변화</b> │ {items[0][3]}")
    elif is_upgrade:
        out.append("• <b>변화</b> │ 알림을 현재 숫자·새 변화·투자 의미·실패모드 중심으로 압축")
    else:
        out.append("• <b>변화</b> │ 공식 실행 단계 변화 확인")
    out.append("• <b>판정</b> │ 계획 GW보다 GIA → 착공 → 전원 인가 → 상업운전 전환을 우선")

    compact_dash = format_dashboard(dash)
    # Keep the four execution anchors only; detailed technology mix remains in state/artifacts.
    selected_dash = []
    for row in compact_dash:
        plain = strip_tags(row)
        if plain.startswith(("• PJM", "• MISO", "• ERCOT", "• FERC")):
            selected_dash.append(row)
        elif plain.startswith("↳ 제5차") or plain.startswith("↳제5차"):
            if selected_dash and "MISO" in strip_tags(selected_dash[-1]):
                selected_dash.append(row)
    if selected_dash:
        out += ["", "<b>⚡ 현재 실행 숫자</b>"] + selected_dash[:5]

    show_policy = bool(policy_changes) or is_upgrade
    show_semi = bool(semi_changes)
    show_flexible = bool(flexible_changes)

    if show_policy and policy:
        out += ["", "<b>🏛️ 주정부 규제</b>"] + _compact_policy(policy)
        out.append("• <b>구분</b> │ 주별 규정이며 미국 전체 단일 의무로 일반화하지 않음")
    if show_semi and semi:
        out += ["", "<b>🔌 800V DC·SiC/GaN</b>"] + _compact_800v(semi)
    if show_flexible and flexible:
        out += ["", "<b>🧠 유연부하</b>"] + _compact_flexible(flexible)

    changes = []
    for group in (metric, policy_changes, semi_changes, flexible_changes):
        for row in group:
            plain = strip_tags(row).lstrip("• ")
            if "False" in plain and "True" in plain and "Pennsylvania 신규 전력인프라 전액 부담" in plain:
                continue
            changes.append(f"• {html.escape(plain)}")
    if changes:
        out += ["", "<b>🔄 이번 변화</b>"] + changes[:6]

    if items:
        out += ["", "<b>🆕 신규 자료</b>"]
        for idx, (theme, badge, source, linked) in enumerate(items[:4], 1):
            source_ko = source.replace("Federal Register", "미국 연방관보")
            out.append(f"{idx}. {linked}")
            out.append(f"   <i>{html.escape(theme)} · {badge} · {html.escape(source_ko)}</i>")
        if len(items) > 4 or hidden:
            out.append(f"• 추가 자료는 중복방지 상태에 저장해 다음 단계 변화 판정에 반영")

    out += [
        "",
        "<b>📊 투자 의미</b>",
        "• <b>매출 연결</b> │ GIA·착공·전원 인가·상업운전으로 내려와야 실적 전환",
        "• <b>실패모드</b> │ 발전원과 부하 위치 불일치·변전소·송전선·허가 지연이 먼저 비용과 일정에 반영",
    ]

    fx_rows = format_fx(fx)
    if fx_rows:
        out += ["", "<b>💱 환율</b>", fx_rows[0]]

    # Source URLs are intentionally removed from the body: the existing Telegram
    # inline buttons remain the canonical navigation path. This keeps one alert on one screen.
    text = "\n".join(out).strip() + "\n"
    visible = strip_tags(text)
    if len(visible) > 3000:
        raise RuntimeError(f"compact time-to-power alert too long: {len(visible)} chars")
    ALERT.write_text(text, encoding="utf-8")
    print(
        f"time_to_power_compact chars={len(visible)} items={len(items)} "
        f"metric={len(metric)} policy={len(policy_changes)} semi={len(semi_changes)} flex={len(flexible_changes)}"
    )


if __name__ == "__main__":
    main()
