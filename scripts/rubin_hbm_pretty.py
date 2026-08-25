from __future__ import annotations

import pathlib
import re

ALERT = pathlib.Path("out/rubin_hbm_alert.md")


def find(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else default


def main() -> None:
    if not ALERT.exists():
        return

    original = ALERT.read_text(encoding="utf-8").strip()
    if not original:
        return

    # 이미 시각형 헤더가 붙은 경우 중복 적용하지 않는다.
    if "[한눈에 보기]" in original:
        return

    checked = find(r"조회시각:\s*(.+)", original, "확인 불가")
    count = find(r"신규 핵심 변화:\s*(\d+건)", original, "확인 불가")
    fx = find(r"원화 환산:\s*(.+)", original)

    has_192 = "192GB" in original
    has_validation = "HBM4E 고객 검증·양산" in original
    has_shipments = "Rubin Ultra·NVL576 실제 출하" in original
    has_contract = "2027 HBM 계약가격·물량" in original
    has_migration = "DDR5·SOCAMM2·기업용 eSSD 이동" in original

    quick = [
        "🚨 Rubin/HBM 구조 변화 감시",
        "━━━━━━━━━━━━━━━━",
        "[한눈에 보기]",
        f"• 신규 변화: {count}",
        f"• 조회: {checked}",
        "• 기준선: 일반 Rubin = 288GB HBM4",
        "• 핵심 상쇄선: 288GB → 192GB면 GPU 출하 +50%가 필요",
    ]

    if has_192:
        quick += [
            "",
            "🧮 숫자 체크",
            "• GPU당 HBM: 288GB → 192GB = -33.3%",
            "• 상쇄 조건: GPU 출하량 +50% 이상",
            "• 시스템 예시: 72×288GB = 20.7TB",
            "                 576×192GB = 110.6TB (+433%)",
            "• 주의: +433%는 NVL576이 실제로 대규모 배치될 때만 성립",
        ]

    detected = []
    if has_validation:
        detected.append("HBM4E 고객 검증·양산")
    if has_shipments:
        detected.append("NVL576 실제 출하·도입")
    if has_contract:
        detected.append("2027 HBM 계약가격·물량")
    if has_migration:
        detected.append("DDR5·SOCAMM2·기업용 eSSD 이동")

    if detected:
        quick += ["", "📌 이번 알림에서 확인할 축"]
        quick.extend(f"• {x}" for x in detected)

    quick += [
        "",
        "✅ 판정 원칙",
        "• 192GB만 보고 HBM 수요 붕괴로 단정하지 않음",
        "• GPU 총출하 × GPU당 HBM 용량으로 총 비트 수요를 판단",
        "• HBM4E 인증·양산, 계약가격·물량, NVL576 배치, DDR5/SOCAMM2/eSSD 이동을 함께 확인",
    ]
    if fx:
        quick += ["", f"💱 {fx}"]

    # 기존 본문은 삭제하지 않고 그대로 보존한다.
    body = original
    if body.startswith("🚨 Rubin/HBM 구조 변화 감시"):
        body = body[len("🚨 Rubin/HBM 구조 변화 감시"):].lstrip("\n")

    formatted = "\n".join(quick) + "\n\n━━━━━━━━━━━━━━━━\n[상세 근거]\n" + body + "\n"
    ALERT.write_text(formatted, encoding="utf-8")


if __name__ == "__main__":
    main()
