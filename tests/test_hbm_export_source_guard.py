import pathlib
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_hbm_watch as w


class _Resp:
    def __init__(self, text: str, status_code: int = 200):
        self.content = text.encode("utf-8")
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class HBMExportSourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 7, 19, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    def test_unpublished_month_poll_is_three_hourly(self):
        state = {
            "official_source_health_version": w.OFFICIAL_SOURCE_HEALTH_VERSION,
            "last_successful_official_month": "202608",
            "last_official_poll_attempt_kst": (self.now - timedelta(hours=2)).isoformat(),
        }
        due, interval = w._official_poll_due(state, self.now)
        self.assertFalse(due)
        self.assertEqual(interval, 3)
        state["last_official_poll_attempt_kst"] = (self.now - timedelta(hours=3, minutes=1)).isoformat()
        due, interval = w._official_poll_due(state, self.now)
        self.assertTrue(due)
        self.assertEqual(interval, 3)

    def test_published_month_revision_poll_is_daily(self):
        state = {
            "official_source_health_version": w.OFFICIAL_SOURCE_HEALTH_VERSION,
            "last_successful_official_month": "202609",
            "last_official_poll_attempt_kst": (self.now - timedelta(hours=23)).isoformat(),
        }
        due, interval = w._official_poll_due(state, self.now)
        self.assertFalse(due)
        self.assertEqual(interval, 24)

    def test_health_version_migration_forces_one_poll(self):
        state = {
            "official_source_health_version": w.OFFICIAL_SOURCE_HEALTH_VERSION - 1,
            "last_successful_official_month": "202608",
            "last_official_poll_attempt_kst": self.now.isoformat(),
        }
        due, interval = w._official_poll_due(state, self.now)
        self.assertTrue(due)
        self.assertEqual(interval, 3)

    def test_regional_data_go_row_is_exact_hsk10(self):
        xml = """<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
        <body><items><item><priodTitle>2026.09</priodTitle><hsSgn>8542323000</hsSgn>
        <expUsdAmt>123456789</expUsdAmt></item></items></body></response>"""
        with patch.object(w, "_request_with_retry", return_value=_Resp(xml)):
            row, err = w.fetch_data_go_sido_month("202609", "44")
        self.assertEqual(err, "")
        self.assertEqual(row["hs"], "8542323000")
        self.assertEqual(row["scope"], "regional_hsk10_exact")
        self.assertEqual(row["amount_usd"], 123456789)

    def test_hs6_fallback_cannot_be_promoted_to_exact_regional_metric(self):
        national = {
            "month": "202609", "amount_usd": 1000.0, "weight_kg": 10.0,
            "hs": w.HBM_HSK10, "source": "official", "api": True,
        }
        hs6 = {
            "month": "202609", "amount_usd": 500.0, "weight_kg": None,
            "hs": w.REGION_HS6, "source": "official fallback", "scope": "regional_hs6_fallback",
        }
        with patch.object(w, "fetch_data_go_item_month", return_value=(national, "")), \
             patch.object(w, "fetch_data_go_sido_month", return_value=(None, "공공데이터포털 시도 API 실패: ConnectTimeout")), \
             patch.object(w, "fetch_kcs_region_month", return_value=(hs6, "")), \
             patch.object(w, "fetch_data_go_country_item_month", return_value=(None, "공공데이터포털 국가별 품목 API MY 실패: ConnectTimeout")):
            pack, errors = w.fetch_official_hbm_pack(self.now)
        self.assertIsNone(pack)
        self.assertTrue(any("ConnectTimeout" in x for x in errors))

    def test_source_health_alert_never_substitutes_stale_value(self):
        errors = [
            "공공데이터포털 전국 API 실패: ConnectTimeout",
            "공공데이터포털 시도 API 실패: ConnectTimeout",
        ]
        out = w.build_official_source_health_alert(self.now, "202609", errors)
        self.assertIn("원자료 조회 장애", out)
        self.assertIn("이전 월 수치", out)
        self.assertIn("대체 사용하지 않습니다", out)
        self.assertIn("연결시간초과", out)

    def test_error_signature_is_stable_for_same_failure_class(self):
        a = w._official_health_signature("202609", [
            "공공데이터포털 전국 API 실패: ConnectTimeout",
            "충남 202609 KCS 조회 실패: ConnectTimeout",
        ])
        b = w._official_health_signature("202609", [
            "충북 202609 KCS 조회 실패: ConnectTimeout",
        ])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
