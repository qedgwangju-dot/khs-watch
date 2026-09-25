import json
import pathlib
import tempfile
import unittest
from unittest import mock

import yen_carry_telegram_compact as compact


class YenCarryTelegramCompactTests(unittest.TestCase):
    def test_compacts_long_alert_and_shows_true_cftc_net_direction(self):
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
            "verdict": {"unwind_level": 1, "rebuild_level": 2},
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
            body_path.write_text(body, encoding="utf-8")
            payload_path.write_text(json.dumps(payload), encoding="utf-8")

            with mock.patch.object(compact, "OUT", out),                  mock.patch.object(compact, "BODY", body_path),                  mock.patch.object(compact, "DETAIL", detail_path),                  mock.patch.object(compact, "PAYLOAD", payload_path):
                self.assertEqual(compact.main(), 0)

            result = body_path.read_text(encoding="utf-8")
            self.assertIn("판정", result)
            self.assertIn("핵심 숫자", result)
            self.assertIn("다음 경보", result)
            self.assertIn("USD/JPY 158.68", result)
            self.assertIn("JGB 10년 3.073% → 3% 구조적 경계", result)
            self.assertIn("해외중장기채 2주 +1.19조엔", result)
            self.assertIn("엔화 순롱 +23,170계약", result)
            self.assertNotIn("CFTC 레버리지 엔화 순숏: 0계약", result)
            self.assertLess(len(result), len(body) + 700)
            self.assertEqual(detail_path.read_text(encoding="utf-8").strip(), body.strip())


if __name__ == "__main__":
    unittest.main()
