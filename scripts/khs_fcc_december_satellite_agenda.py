#!/usr/bin/env python3
"""Render a source-linked, one-time FCC December satellite agenda supplement."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
OUT_DIR = Path("out")
TITLE_PATH = OUT_DIR / "khs_fcc_satellite_agenda_title.txt"
BODY_PATH = OUT_DIR / "khs_fcc_satellite_agenda_alert.md"

AGENDA_URL = "https://docs.fcc.gov/public/attachments/DOC-427531A1.txt"
RECIPROCITY_URL = "https://docs.fcc.gov/public/attachments/DOC-427537A1.txt"
LIGHT_LICENSING_URL = "https://docs.fcc.gov/public/attachments/DOC-427543A1.txt"


def build_message(now: dt.datetime | None = None) -> tuple[str, str]:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(KST)
    meeting_et = dt.datetime(2026, 12, 17, 10, 30, tzinfo=ET)
    meeting_kst = meeting_et.astimezone(KST)
    title = "정책 워치: FCC 12월 위성 안건 보충"
    body = f"""정책 워치 · {now:%Y년 %m월 %d일 %H:%M KST}
FCC가 11월 24일 공개한 잠정 의제와 안건별 초안의 핵심입니다. 12월 회의에 올릴 예정인 두 안건이며, 표결·최종 규칙·발효가 확정된 것은 아닙니다.

1. [잠정 의제] FCC, 위성 시장접근 상호주의·주파수 공유 두 안건 심의 예정
- 핵심: FCC는 외국의 위성시장 제한에 대응할 미국 내 허가 기준과 위성 주파수 공유용 ‘라이트 라이선싱’ 체계를 12월 회의에서 심의할 예정입니다. 아직 확정 규칙이나 특정 사업자 제재·장비 발주는 없습니다.
- 시장접근 상호주의: 규칙제정안(NPRM)은 해외 규제가 미국 허가 사업자의 진출을 불리하게 하는지 살펴보고, 외국 사업자의 미국 진입 심사에 쓰는 상호주의 추정을 유지·수정·폐지할지 의견을 구합니다. 외국 위성사업자 전체에 대한 현재의 영업 금지 조치는 아닙니다.
- 주파수 공유: 제안은 전국 단위·비현장 면허를 받은 뒤 FCC 승인 제3자 포털에 개별 시설·링크를 등록하는 절차입니다. 포털은 현장별 녹색·노란색·빨간색으로 조정 필요성을 표시하고, 먼저 등록한 이용자에게 우선권을 주는 구상입니다. 어떤 대역·서비스를 추가할지는 후속 의견수렴 대상으로, 특정 대역 개방이나 장비 수요가 확정된 것은 아닙니다.
- 시장 영향: 위성사업자의 미국 진입 심사와 공유 주파수 이용 절차가 달라질 가능성이 변수입니다. 실제 영향은 FCC 채택 여부, 적용 대역·서비스와 시행 일정에 달렸으며 현재 매출·수주 효과로 계산할 근거는 없습니다.
- 타임라인:
  • 2026년 11월 24일: FCC가 잠정 의제와 공개 초안을 발표했습니다. 안건은 변경되거나 회의에서 다뤄지지 않을 수 있습니다.
  • {meeting_et:%Y년 %m월 %d일 %H:%M} 미국 동부시간 = {meeting_kst:%Y년 %m월 %d일 %H:%M} 한국시간: 공개회의 예정 시각이며, 표결·채택 여부는 미확정입니다.
  • 회의 후: 실제 표결, 정식 결정문, 의견 제출·회신 기한 및 발효일을 FCC 후속 공고로 확인해야 합니다.
- 출처: <a href="{AGENDA_URL}">원문</a> · FCC 12월 잠정 의제
- 출처: <a href="{RECIPROCITY_URL}">원문</a> · FCC 시장접근 상호주의 공개 초안
- 출처: <a href="{LIGHT_LICENSING_URL}">원문</a> · FCC 라이트 라이선싱 공개 초안
"""
    return title, body


def self_test() -> None:
    fixed_now = dt.datetime(2026, 11, 26, 3, 0, tzinfo=dt.timezone.utc)
    title, body = build_message(fixed_now)
    required = (
        "2026년 11월 24일",
        "2026년 12월 17일 10:30 미국 동부시간 = 2026년 12월 18일 00:30 한국시간",
        "잠정 의제",
        "외국 위성사업자 전체에 대한 현재의 영업 금지 조치는 아닙니다",
        "먼저 등록한 이용자에게 우선권",
        "특정 대역 개방이나 장비 수요가 확정된 것은 아닙니다",
        AGENDA_URL,
        RECIPROCITY_URL,
        LIGHT_LICENSING_URL,
    )
    assert title.startswith("정책 워치:")
    assert all(marker in body for marker in required), [marker for marker in required if marker not in body]
    assert "표결·채택 여부는 미확정입니다" in body
    assert body.count('- 출처: <a href="') == 3
    try:
        from khs_policy_telegram_formatter import format_policy_message, validate_final_policy_message
    except ImportError:
        from scripts.khs_policy_telegram_formatter import format_policy_message, validate_final_policy_message

    final_title, final_body = format_policy_message(title, body, now=fixed_now.astimezone(KST))
    assert validate_final_policy_message(final_title, final_body) == []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("fcc_december_satellite_agenda_self_test=passed")
    if args.build:
        self_test()
        title, body = build_message()
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        BODY_PATH.write_text(body, encoding="utf-8")
        print(f"fcc_december_satellite_agenda_built title={TITLE_PATH} body={BODY_PATH}")
    if not args.self_test and not args.build:
        parser.error("use --self-test or --build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
