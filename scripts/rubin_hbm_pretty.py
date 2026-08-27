from __future__ import annotations

import html
import json
import pathlib
import re
import urllib.parse
import urllib.request

ALERT = pathlib.Path("out/rubin_hbm_alert.md")

OFFICIAL_SOURCES = (
    "nvidia", "samsung newsroom", "삼성전자 뉴스룸", "sk hynix", "sk하이닉스 뉴스룸",
    "micron technology", "micron newsroom",
)
TRUSTED_SOURCES = (
    "trendforce", "reuters", "bloomberg", "the information", "semianalysis", "digitimes",
    "tom's hardware", "toms hardware", "financial times", "wall street journal", "wsj", "cnbc",
)

# 자주 나오는 제목은 자동번역보다 수동 번역을 우선해 의미를 고정한다.
MANUAL_TITLE_TRANSLATIONS = {
    "Micron: HBM3E Consumes 3x More Wafer Capacity Than DDR5, and the Gap Will Widen - XenoSpectrum":
        "Micron: HBM3E는 DDR5보다 웨이퍼 생산능력을 3배 더 소모하며, 세대가 갈수록 격차 확대 - XenoSpectrum",
}

# 자동번역 뒤에도 검색·기술 식별이 깨지지 않도록 원문 표기를 복원한다.
IDENTIFIER_RESTORE = {
    "마이크론": "Micron",
    "엔비디아": "NVIDIA",
    "트렌드포스": "TrendForce",
    "루빈 울트라": "Rubin Ultra",
    "베라 루빈": "Vera Rubin",
    "그레이스 블랙웰": "Grace Blackwell",
    "코워스": "CoWoS",
}


def find(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else default


def section_present(title: str, text: str) -> bool:
    return bool(re.search(rf"^■\s*{re.escape(title)}\s*$", text, re.M))


def source_label(source: str) -> str:
    low = source.lower().strip()
    if any(k in low for k in OFFICIAL_SOURCES):
        return "공식·회사자료"
    if any(k in low for k in TRUSTED_SOURCES):
        return "신뢰 리서치·보도"
    return "일반 보도 — 추가 교차검증 필요"


def has_korean(value: str) -> bool:
    return bool(re.search(r"[가-힣]", value or ""))


def translate_title_ko(title: str) -> str:
    """영문 기사 제목의 설명어는 한국어로 옮기고 기술 식별어는 원문을 유지한다."""
    title = html.unescape(title or "").strip()
    if not title or has_korean(title):
        return title
    if title in MANUAL_TITLE_TRANSLATIONS:
        return MANUAL_TITLE_TRANSLATIONS[title]

    # Google 공개 번역 엔드포인트를 보조적으로 사용한다. 실패 시 제목을 그대로 노출하지 않고
    # 해당 섹션의 상세 근거와 원문 링크로 확인할 수 있도록 한국어 안내문으로 대체한다.
    try:
        params = urllib.parse.urlencode({
            "client": "gtx",
            "sl": "en",
            "tl": "ko",
            "dt": "t",
            "q": title,
        })
        req = urllib.request.Request(
            f"https://translate.googleapis.com/translate_a/single?{params}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            obj = json.loads(r.read().decode("utf-8"))
        translated = "".join(seg[0] for seg in (obj[0] or []) if seg and seg[0]).strip()
        for ko, original in IDENTIFIER_RESTORE.items():
            translated = translated.replace(ko, original)
        if translated and has_korean(translated):
            return translated
    except Exception:
        pass

    return "관련 신규 보도 — 제목 자동번역 확인 필요"


def emphasize_metrics(line: str) -> str:
    """정보를 줄이지 않고 핵심 숫자만 굵게 만들어 눈에 바로 들어오게 한다."""
    escaped = html.escape(line, quote=False)
    patterns = [
        r"(?<![\w])([+-]?\d+(?:\.\d+)?%)",
        r"(?<![\w])(\d+(?:\.\d+)?\s*(?:GB|TB|Gbps|TB/s|GB/s|W|GW))\b",
        r"(?<![\w])(\$\s*\d+(?:\.\d+)?\s*(?:B|M)?)\b",
        r"(?<![\w])(20\d{2})\b",
    ]
    for pattern in patterns:
        escaped = re.sub(pattern, r"<b>\1</b>", escaped, flags=re.I)
    return escaped


def htmlify_lines(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        m_source = re.match(r"\s*-\s*출처:\s*(.+?)\s*/\s*.+$", line)
        if m_source:
            source = m_source.group(1).strip()
            label = source_label(source)
            out.append(f"- <b>출처</b>: {html.escape(source)} / <b>{html.escape(label)}</b>")
            continue

        m_time = re.match(r"\s*-\s*공개시각:\s*(.+)$", line)
        if m_time:
            out.append(f"- <b>공개시각</b>: {emphasize_metrics(m_time.group(1).strip())}")
            continue

        m_judge = re.match(r"\s*•\s*판정 기준:\s*(.+)$", line)
        if m_judge:
            out.append(f"• <b>판정 기준</b>: {emphasize_metrics(m_judge.group(1).strip())}")
            continue

        m_link = re.match(r"\s*-\s*원문:\s*(https?://\S+)\s*$", line)
        if m_link:
            url = html.escape(m_link.group(1), quote=True)
            out.append(f'<a href="{url}">원문</a>')
            continue

        m_title = re.match(r"^(\d+)\.\s+(.+)$", line)
        if m_title:
            title_ko = translate_title_ko(m_title.group(2))
            out.append(f'{m_title.group(1)}. <b>{html.escape(title_ko, quote=False)}</b>')
            continue

        if line.startswith("■ "):
            out.append(f"<b>{html.escape(line, quote=False)}</b>")
            continue

        out.append(emphasize_metrics(line))
    return "\n".join(out)


def main() -> None:
    if not ALERT.exists():
        return

    original = ALERT.read_text(encoding="utf-8").strip()
    if not original:
        return

    if "[HBM 좋아지는 조건]" in original:
        return

    checked = find(r"조회시각:\s*(.+)", original, "확인 불가")
    count = find(r"신규 핵심 변화:\s*(\d+건)", original, "확인 불가")
    fx = find(r"원화 환산:\s*(.+)", original)

    has_rubin_spec = section_present("Rubin Ultra 최종 HBM 사양", original)
    has_validation = section_present("HBM4E 고객 검증·양산", original)
    has_shipments = section_present("Rubin Ultra·NVL576 실제 출하", original)
    has_contract = section_present("2027 HBM 계약가격·물량", original)
    has_migration = section_present("DDR5·SOCAMM2·기업용 eSSD 이동", original)
    has_192 = has_rubin_spec and "192GB" in original

    # 가독성은 '정보 삭제'가 아니라 '시각적 우선순위'로 만든다.
    # 상세 근거는 아래에 원문 그대로 보존한다.
    quick = [
        "🚨 <b>Rubin/HBM 구조 변화 감시</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[한눈에 보기]</b>",
        f"• 신규 변화: <b>{html.escape(count)}</b>",
        f"• 조회: {html.escape(checked)}",
        "• 기준선: 일반 Rubin = <b>288GB HBM4</b>",
        "• 핵심 상쇄선: <b>288GB → 192GB면 GPU 출하 +50%</b>가 필요",
    ]

    if has_192:
        quick += [
            "",
            "🧮 <b>숫자 체크</b>",
            "• GPU당 HBM: <b>288GB → 192GB = -33.3%</b>",
            "• 상쇄 조건: <b>GPU 출하량 +50% 이상</b>",
            "• 시스템 예시: 72×288GB = <b>20.7TB</b>",
            "                 576×192GB = <b>110.6TB (+433%)</b>",
            "• 단, +433%는 <b>NVL576 실제 대규모 배치</b>가 전제",
        ]

    quick += [
        "",
        "🟢 <b>[HBM 좋아지는 조건]</b>",
        "1) <b>2027 HBM 계약가격 상승 + 계약물량 유지·증가</b>",
        "   → 가격만 오르는 것이 아니라 비트 출하도 같이 늘어야 진짜 호재",
        "2) <b>HBM4E 고객 인증 완료 → 양산 일정 확정</b>",
        "   → 샘플 출하보다 고객 승인·대량생산 개시가 중요",
        "3) Rubin Ultra가 192GB라도 <b>GPU 출하 +50% 이상</b> 또는 NVL576 대규모 배치",
        "   → GPU당 -33.3%를 전체 GPU 수 증가가 상쇄",
        "4) <b>HBM 대역폭 유지·상승</b>",
        "   → 용량은 줄어도 21~22TB/s급 대역폭을 지키면 HBM 핵심 역할은 유지",
        "5) <b>DDR5·SOCAMM2·기업용 eSSD 수요 동반 증가</b>",
        "   → HBM에서 밀린 용량이 다른 메모리 계층으로 이동하는지 확인",
        "6) <b>삼성·SK하이닉스 HBM 출하 대용지표와 실제 HBM 매출 동반 상승</b>",
        "   → 기사보다 실제 출하·매출이 최종 확인",
        "",
        "🔴 <b>[HBM 나빠지는 조건]</b>",
        "• GPU당 HBM 192GB 확정 + GPU 출하 증가가 <b>+50% 미만</b>",
        "• HBM4E 인증·양산 반복 지연",
        "• 2027 HBM 계약가격 하락 또는 계약물량 축소",
        "• NVL576 고객 도입 지연·축소",
        "• DDR5·SOCAMM2·eSSD까지 주문 둔화",
    ]

    detected = []
    if has_rubin_spec:
        detected.append("Rubin Ultra 최종 HBM 사양")
    if has_validation:
        detected.append("HBM4E 고객 검증·양산")
    if has_shipments:
        detected.append("NVL576 실제 출하·도입")
    if has_contract:
        detected.append("2027 HBM 계약가격·물량")
    if has_migration:
        detected.append("DDR5·SOCAMM2·기업용 eSSD 이동")

    if detected:
        quick += ["", "📌 <b>이번 알림에서 실제로 감지된 축</b>"]
        quick.extend(f"• {html.escape(x)}" for x in detected)

    quick += [
        "",
        "✅ <b>판정 원칙</b>",
        "• 192GB만 보고 HBM 수요 붕괴로 단정하지 않음",
        "• <b>GPU 총출하 × GPU당 HBM 용량</b>으로 총 비트 수요 판단",
        "• 가격·물량·인증·실제 출하가 같이 좋아질 때만 강한 호재로 판정",
    ]
    if fx:
        quick += ["", f"💱 {html.escape(fx)}"]

    body = original
    if body.startswith("🚨 Rubin/HBM 구조 변화 감시"):
        body = body[len("🚨 Rubin/HBM 구조 변화 감시"):].lstrip("\n")

    formatted = (
        "\n".join(quick)
        + "\n\n━━━━━━━━━━━━━━━━\n<b>[상세 근거]</b>\n"
        + htmlify_lines(body)
        + "\n"
    )
    ALERT.write_text(formatted, encoding="utf-8")


if __name__ == "__main__":
    main()
