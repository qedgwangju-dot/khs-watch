from __future__ import annotations

import html
import pathlib
import re

ALERT = pathlib.Path("out/rubin_hbm_alert.md")


def find(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else default


def section_present(title: str, text: str) -> bool:
    return bool(re.search(rf"^■\s*{re.escape(title)}\s*$", text, re.M))


def emphasize_metrics(line: str) -> str:
    escaped = html.escape(line, quote=False)
    patterns = [
        r"(?<![\w])([+-]?\d+(?:\.\d+)?%)",
        r"(?<![\w])(\d+(?:\.\d+)?\s*(?:GB|TB|Gbps|TB/s|GB/s|W|GW))\b",
        r"(?<![\w])(\$\s*\d+(?:\.\d+)?\s*(?:billion|million|B|M)?)\b",
        r"(?<![\w])(20\d{2})\b",
    ]
    for pattern in patterns:
        escaped = re.sub(pattern, r"<b>\1</b>", escaped, flags=re.I)
    return escaped


def detected_axes(original: str) -> list[str]:
    checks = [
        ("Rubin Ultra 최종 HBM 사양", "Rubin Ultra 최종 HBM 사양"),
        ("HBM4E 고객 검증·양산", "HBM4E 고객 검증·양산"),
        ("Rubin Ultra·NVL576 실제 출하", "NVL576 실제 출하·도입"),
        ("2027 HBM 계약가격·물량", "2027 HBM 계약가격·물량"),
        ("DDR5·SOCAMM2·기업용 eSSD 이동", "DDR5·SOCAMM2·기업용 eSSD 이동"),
    ]
    return [label for section, label in checks if section_present(section, original)]


def event_summaries(original: str) -> list[tuple[str, str]]:
    lines = original.splitlines()
    out: list[tuple[str, str]] = []
    title = ""
    verdict = ""
    for line in lines:
        if line.startswith("■ 자동 판정 원칙"):
            break
        m_title = re.match(r"^\d+\.\s+(.+)$", line)
        if m_title:
            if title:
                out.append((title, verdict))
            title = m_title.group(1).strip()
            verdict = ""
            continue
        m_verdict = re.match(r"^\s*•\s*판정:\s*(.+)$", line)
        if m_verdict and title:
            verdict = m_verdict.group(1).strip()
    if title:
        out.append((title, verdict))
    return out[:12]


def htmlify_lines(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            out.append("")
            continue

        m_source = re.match(r"\s*-\s*출처:\s*(.+?)\s*/\s*(.+)$", line)
        if m_source:
            source = m_source.group(1).strip()
            verification = m_source.group(2).strip()
            out.append(
                f"<b>근거</b>  {html.escape(source)} · <b>{html.escape(verification)}</b>"
            )
            continue

        m_time = re.match(r"\s*-\s*공개시각:\s*(.+)$", line)
        if m_time:
            out.append(f"<b>공개</b>  {emphasize_metrics(m_time.group(1).strip())}")
            continue

        m_link = re.match(r"\s*-\s*원문:\s*(https?://\S+)\s*$", line)
        if m_link:
            url = html.escape(m_link.group(1), quote=True)
            out.append(f'<a href="{url}"><b>원문</b></a>')
            continue

        m_title = re.match(r"^(\d+)\.\s+(.+)$", line)
        if m_title:
            out.append("")
            out.append(f'<b>{m_title.group(1)}. {html.escape(m_title.group(2), quote=False)}</b>')
            continue

        m_verdict = re.match(r"^\s*•\s*판정:\s*(.+)$", line)
        if m_verdict:
            out.append(f"<b>판정</b>  {emphasize_metrics(m_verdict.group(1).strip())}")
            continue

        if line.startswith("■ "):
            out.append("")
            out.append(f"<b>{html.escape(line, quote=False)}</b>")
            continue

        out.append(emphasize_metrics(line))
    return "\n".join(out).strip()


def strip_repeated_header(body: str) -> str:
    drop_patterns = (
        r"^조회시각:\s*.*$",
        r"^신규 핵심 변화:\s*.*$",
        r"^기준선:\s*.*$",
        r"^원화 환산:\s*.*$",
    )
    lines = []
    for line in body.splitlines():
        if any(re.match(p, line) for p in drop_patterns):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> None:
    if not ALERT.exists():
        return

    original = ALERT.read_text(encoding="utf-8").strip()
    if not original:
        return

    # 이미 시각화된 알림은 재처리하지 않는다.
    if "[이번 변화]" in original:
        return

    checked = find(r"조회시각:\s*(.+)", original, "확인 불가")
    count = find(r"신규 핵심 변화:\s*(\d+건)", original, "확인 불가")
    fx = find(r"원화 환산:\s*(.+)", original)
    axes = detected_axes(original)
    summaries = event_summaries(original)

    has_rubin_spec = section_present("Rubin Ultra 최종 HBM 사양", original)
    has_192 = has_rubin_spec and "192GB" in original

    quick: list[str] = [
        "🚨 <b>Rubin/HBM 구조 변화 감시</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[이번 변화]</b>",
        f"• 신규 변화 <b>{html.escape(count)}</b> · 조회 {html.escape(checked)}",
    ]
    if axes:
        quick.append("• 감지 축  " + " · ".join(f"<b>{html.escape(x)}</b>" for x in axes))
    if fx:
        quick.append(f"• 환율  {html.escape(fx)}")

    if summaries:
        quick += [""]
        for idx, (title, verdict) in enumerate(summaries, 1):
            quick.append(f"<b>{idx}. {html.escape(title, quote=False)}</b>")
            if verdict:
                quick.append(f"   {emphasize_metrics(verdict)}")

    quick += [
        "",
        "<b>[핵심 숫자]</b>",
        "• 일반 Rubin  <b>288GB HBM4</b>",
        "• 288GB → 192GB  <b>-33.3%</b>",
        "• 디스펙 상쇄선  <b>GPU 출하 +50%</b>",
    ]
    if has_192:
        quick += [
            "• 72×288GB  <b>20.7TB</b>",
            "• 576×192GB  <b>110.6TB (+433%)</b>",
            "  단, NVL576 실제 대규모 배치가 전제",
        ]

    # 자주 반복되는 기준은 핵심만 먼저 노출하고 설명은 접어서 보존한다.
    quick += [
        "",
        "<b>[HBM 방향 체크]</b>",
        "🟢 <b>좋아짐</b>  가격↑+물량↑ · HBM4E 인증→양산 · GPU +50%↑ · 대역폭 유지 · DDR5/SOCAMM2/eSSD↑",
        "🔴 <b>나빠짐</b>  192GB+GPU&lt;50% · 인증 지연 · 가격/물량↓ · NVL576 지연 · 기타 메모리 주문↓",
        "",
        "<blockquote expandable><b>판정 기준 자세히</b>\n"
        "1) 2027 HBM 계약가격 상승 + 계약물량 유지·증가\n"
        "→ 가격만 오르는 것이 아니라 비트 출하도 같이 늘어야 진짜 호재\n\n"
        "2) HBM4E 고객 인증 완료 → 양산 일정 확정\n"
        "→ 샘플 출하보다 고객 승인·대량생산 개시가 중요\n\n"
        "3) Rubin Ultra가 192GB라도 GPU 출하 +50% 이상 또는 NVL576 대규모 배치\n"
        "→ GPU당 -33.3%를 전체 GPU 수 증가가 상쇄\n\n"
        "4) HBM 대역폭 유지·상승\n"
        "→ 용량은 줄어도 21~22TB/s급 대역폭을 지키면 핵심 역할 유지\n\n"
        "5) DDR5·SOCAMM2·기업용 eSSD 수요 동반 증가\n"
        "→ HBM에서 밀린 용량이 다른 메모리 계층으로 이동하는지 확인\n\n"
        "6) 삼성·SK하이닉스 HBM 출하 대용지표와 실제 HBM 매출 동반 상승\n"
        "→ 기사보다 실제 출하·매출이 최종 확인\n\n"
        "약세 조건: GPU당 192GB 확정+GPU 출하 증가 +50% 미만 / HBM4E 인증·양산 반복 지연 / 2027 계약가격 하락·계약물량 축소 / NVL576 도입 지연·축소 / DDR5·SOCAMM2·eSSD 주문 둔화\n\n"
        "판정 원칙: 192GB만 보고 HBM 수요 붕괴로 단정하지 않으며 GPU 총출하×GPU당 HBM 용량으로 총 비트 수요를 판단합니다.</blockquote>",
    ]

    body = original
    if body.startswith("🚨 Rubin/HBM 구조 변화 감시"):
        body = body[len("🚨 Rubin/HBM 구조 변화 감시"):].lstrip("\n")
    body = strip_repeated_header(body)

    formatted = (
        "\n".join(quick)
        + "\n\n━━━━━━━━━━━━━━━━\n<b>[상세 근거]</b>\n"
        + htmlify_lines(body)
        + "\n"
    )
    ALERT.write_text(formatted, encoding="utf-8")


if __name__ == "__main__":
    main()
