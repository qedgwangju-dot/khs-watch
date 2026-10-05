import json
import pathlib
import tempfile
import unittest
from unittest import mock

import yen_carry_telegram_compact as compact


class YenCarryTelegramCompactTests(unittest.TestCase):
    def test_compacts_long_alert_and_makes_direction_obvious(self):
        body = """조회 시각: 2026-09-25 10:50:04 KST

판정
- 캐리 청산 위험: 🟡 구조적 취약성·경계
- 엔화 재약세·캐리 재구축: 🟠 엔화 재약세·캐리 재구축 압력 강화
※ 두 판정은 서로 다른 질문입니다.

이번 변화
- JGB 10년 3% 구조적 경계 진입

구조적 경계·자금환류
- 일본 10년 JGB(재무성 공식 종가) 3.073% (2026/9/24) → 3% 구조적 경계 위
- 해외중장기채: 최근 2주 +1.19조엔 / 직전 2주 -2.80조엔 / 연초 이후 -1.54조엔 → 해외채권 순매수

긴축 경로·레버리지
- 일본 2년 JGB 재가격: +6.3bp / 미·일 2년 금리차 변화: +4.7bp
- FX 실현변동성: 이전 구간 대비 1.00배 → 낮음·안정
- CFTC 레버리지 엔화 순숏: 0계약 (0.0% OI)

주식시장 영향
- 현재 USD/JPY: 158.68
"""
        payload = {
            "verdict": {
                "unwind_level": 1,
                "rebuild_level": 2,
                "evidence": {
                    "rebuild::USD/JPY 상승·엔화 재약세": True,
                    "rebuild::미·일 2년 금리차 여전히 넓음": True,
                },
            },
            "refined_risk": {"level": 1, "rebuild_level": 2},
            "cftc": {
                "leveraged_long": 110302,
                "leveraged_short": 87132,
                "report_date": "2026-09-15",
            },
        }
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td)
            body_path = out / "yen_carry_composite_alert.md"
            detail_path = out / "yen_carry_composite_alert_detail.md"
            payload_path = out / "yen_carry_composite_alert.json"
            title_path = out / "yen_carry_composite_alert_title.txt"
            body_path.write_text(body, encoding="utf-8")
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            title_path.write_text("🟡 엔캐리 복합 수급 알림\n", encoding="utf-8")

            with (
                mock.patch.object(compact, "OUT", out),
                mock.patch.object(compact, "BODY", body_path),
                mock.patch.object(compact, "DETAIL", detail_path),
                mock.patch.object(compact, "PAYLOAD", payload_path),
                mock.patch.object(compact, "TITLE", title_path),
            ):
                self.assertEqual(compact.main(), 0)

            result = body_path.read_text(encoding="utf-8")
            title = title_path.read_text(encoding="utf-8")
            self.assertIn("🟡 엔캐리 | ↗ 유지·재구축", title)
            self.assertIn("▶ 현재 방향 │ ↗ 엔화 약세·캐리 유지·재구축 우세", result)
            self.assertIn("▶ 청산 위험 │ 🟡 구조적 취약성·경계", result)
            self.assertIn("▶ 시장 영향 │ 🟢 위험자산 수급 단기 우호", result)
            self.assertIn("핵심 근거", result)
            self.assertIn("반전 조건", result)
            self.assertIn("USD/JPY 158.68", result)
            self.assertIn("미·일 2년 금리차 +4.7bp 확대 → 캐리 유지·재구축 쪽", result)
            self.assertIn("JGB 10년 3.073% → 🟡 구조적 경계, 자동 청산선 아님", result)
            self.assertIn("해외중장기채 2주 +1.19조엔", result)
            self.assertIn("순매수·본국회귀 압력 약함", result)
            self.assertIn("FX 변동성 낮음·안정 → 강제청산 신호 약함", result)
            self.assertIn("엔화 순롱 +23,170계약", result)
            self.assertNotIn("CFTC 레버리지 엔화 순숏: 0계약", result)
            self.assertLess(len(result), len(body) + 500)
            self.assertEqual(detail_path.read_text(encoding="utf-8").strip(), body.strip())

    def test_structural_yellow_floor_never_forces_unwind_arrow(self):
        body = """조회 시각: 2026-10-05 11:17:23 KST

판정
- 캐리 청산 위험: 🟡 구조적 취약성·경계
- 엔화 재약세·캐리 재구축: 🟢 엔화 재약세·캐리 재구축 미확인

이번 변화
- JGB 10년 3% 이상 2영업일 지속 확인

구조적 경계·자금환류
- 일본 10년 JGB(재무성 공식 종가) 3.097% (2026/10/2) → 3% 이상 / 연속 2영업일
- 해외중장기채: 최근 2주 -2.59조엔 / 직전 2주 +1.21조엔 / 연초 이후 -4.12조엔 → 해외채권 순매도·환류 압력

긴축 경로·레버리지
- 일본 2년 JGB 재가격: -2.0bp / 미·일 2년 금리차 변화: +7.0bp
- FX 실현변동성: 이전 구간 대비 1.51배 → 상승

미·일 정책공조·시장 영향
- 정책 단계: Bessent 발언은 <b>구두개입·정책정보 우위 경고</b>입니다.
- 주식시장: <b>질서 있는 엔 강세</b>와 강제청산을 구분합니다.
"""
        payload = {
            "verdict": {
                "unwind_level": 0,
                "rebuild_level": 0,
                "evidence": {
                    "unwind::USD/JPY 급락·엔화 급등": False,
                    "unwind::미·일 2년 금리차 축소": False,
                    "unwind::일본 단기금리 상승": False,
                    "unwind::FX 실현변동성 상승": True,
                    "unwind::레버리지 펀드 엔화 순숏": True,
                    "rebuild::USD/JPY 상승·엔화 재약세": False,
                    "rebuild::USD/JPY 완만한 상승 방향": True,
                    "rebuild::미·일 2년 금리차 재확대": False,
                    "rebuild::미·일 2년 금리차 여전히 넓음": True,
                },
            },
            "refined_risk": {
                "level": 1,
                "label": "구조적 취약성·경계",
                "rebuild_level": 0,
                "structural_floor": "JGB 10년 3% 이상 공식 종가",
                "signals": {},
            },
        }
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td)
            body_path = out / "yen_carry_composite_alert.md"
            detail_path = out / "yen_carry_composite_alert_detail.md"
            payload_path = out / "yen_carry_composite_alert.json"
            title_path = out / "yen_carry_composite_alert_title.txt"
            body_path.write_text(body, encoding="utf-8")
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            title_path.write_text("🟡 엔캐리 복합 수급 알림\n", encoding="utf-8")

            with (
                mock.patch.object(compact, "OUT", out),
                mock.patch.object(compact, "BODY", body_path),
                mock.patch.object(compact, "DETAIL", detail_path),
                mock.patch.object(compact, "PAYLOAD", payload_path),
                mock.patch.object(compact, "TITLE", title_path),
            ):
                self.assertEqual(compact.main(), 0)

            result = body_path.read_text(encoding="utf-8")
            title = title_path.read_text(encoding="utf-8")
            self.assertIn("🟡 엔캐리 | ↗ 유지 우세·구조 경계", title)
            self.assertIn("▶ 현재 방향 │ ↗ 캐리 유지·재구축 쪽으로 기울기", result)
            self.assertIn("▶ 청산 위험 │ 🟡 구조적 취약성·경계", result)
            self.assertIn("▶ 시장 영향 │ 🟡 중립~소폭 우호 / 구조 변동성 주의", result)
            self.assertNotIn("↘ 청산", result)
            self.assertNotIn("<b>", result)
            self.assertNotIn("</b>", result)

    def test_structural_floor_without_direction_is_neutral(self):
        payload = {
            "verdict": {"unwind_level": 0, "rebuild_level": 0, "evidence": {}},
            "refined_risk": {
                "level": 1,
                "structural_floor": "JGB 10년 3% 이상 공식 종가",
                "signals": {},
            },
        }
        title, direction, impact = compact.direction_call(payload)
        self.assertIn("↔ 중립·구조 경계", title)
        self.assertEqual(direction, "↔ 중립·방향 확인 대기")
        self.assertEqual(impact, "🟡 중립 / 구조 변동성 주의")


if __name__ == "__main__":
    unittest.main()
