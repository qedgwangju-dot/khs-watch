import pathlib
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_hbm_watch as w
import hbm_delivery as d


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


    def _monthly_pack(self):
        return {
            "month": "202608",
            "hs": w.HBM_HSK10,
            "region_hs": w.HBM_HSK10,
            "icheon_hs": w.REGION_HS6,
            "source_url": w.KCS_SOURCE_PAGE,
            "icheon_public_available": False,
            "malaysia_public_available": False,
            "malaysia_source_url": "https://www.data.go.kr/data/15100475/openapi.do",
            "series": {
                "202608": {
                    "national_amount": 12_220_000_000.0,
                    "national_weight": 123_600.0,
                    "samsung_region_amount": 7_500_000_000.0,
                    "hynix_chungbuk_amount": 1_400_000_000.0,
                    "icheon_amount": None,
                    "malaysia_amount": None,
                    "malaysia_weight": None,
                },
                "202607": {
                    "national_amount": 10_082_508_250.0,
                    "national_weight": 105_500.0,
                    "samsung_region_amount": 5_547_337_278.0,
                    "hynix_chungbuk_amount": 1_592_718_999.0,
                    "icheon_amount": None,
                    "malaysia_amount": None,
                    "malaysia_weight": None,
                },
                "202605": {
                    "national_amount": 9_614_476_790.0,
                    "national_weight": 104_000.0,
                    "samsung_region_amount": 5_036_937_542.0,
                    "hynix_chungbuk_amount": 1_276_207_840.0,
                    "icheon_amount": None,
                    "malaysia_amount": None,
                    "malaysia_weight": None,
                },
                "202508": {
                    "national_amount": 4_602_636_535.0,
                    "national_weight": 80_000.0,
                    "samsung_region_amount": 2_800_000_000.0,
                    "hynix_chungbuk_amount": 1_000_000_000.0,
                    "icheon_amount": None,
                    "malaysia_amount": None,
                    "malaysia_weight": None,
                },
            },
        }

    def test_monthly_alert_frontloads_each_company_direction(self):
        out = w.build_monthly(self.now, 1338.0, "테스트 환율", self._monthly_pack())
        first = out.split(d.MESSAGE_BREAK)[0]
        self.assertIn("삼성전자 vs SK하이닉스 HBM 수출 방향", first)
        self.assertIn("삼성전자 방향(충남)", first)
        self.assertIn("SK하이닉스 방향(충북·청주)", first)
        self.assertIn("▲ 강한 증가", first)
        self.assertIn("▼ 단기 둔화", first)
        self.assertLess(first.index("삼성전자 방향(충남)"), first.index("[삼성전자 방향 — 충남]"))
        self.assertLess(first.index("SK하이닉스 방향(충북·청주)"), first.index("[SK하이닉스 방향 — 충북·청주]"))

    def test_monthly_alert_never_claims_company_direct_exports(self):
        out = w.build_monthly(self.now, 1338.0, "테스트 환율", self._monthly_pack())
        self.assertIn("회사 직접 수출액이 아니라", out)
        self.assertIn("삼성전자 직접 수출액·HBM 매출·점유율로 치환하지 않습니다", out)
        self.assertIn("SK하이닉스 전체 직접 수출액으로 치환하지 않습니다", out)
        self.assertIn("SK하이닉스 전체값으로 합산하지 않습니다", out)
        self.assertIn("회사 점유율로 해석하지 않습니다", out)

    def test_monthly_alert_explicitly_marks_newer_month_as_not_yet_available(self):
        out = w.build_monthly(self.now, 1338.0, "테스트 환율", self._monthly_pack())
        self.assertIn("2026년 9월 시도별 HSK10", out)
        self.assertIn("2026년 8월", out)
        self.assertIn("공식 최신월로 확인되지 않아", out)

    def test_monthly_alert_uses_exact_regional_hsk10_and_safe_chunks(self):
        out = w.build_monthly(self.now, 1338.0, "테스트 환율", self._monthly_pack())
        self.assertGreaterEqual(out.count("HSK10 <b>8542323000</b>"), 3)
        parts = d.chunks(out)
        self.assertGreaterEqual(len(parts), 2)
        self.assertTrue(all(len(x.encode("utf-16-le")) // 2 <= 3600 for x in parts))

    def test_unpublished_month_poll_is_three_hourly(self):
        state = {
            "official_source_health_version": w.OFFICIAL_SOURCE_HEALTH_VERSION,
            "compare_version": w.COMPARE_VERSION,
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
            "compare_version": w.COMPARE_VERSION,
            "last_successful_official_month": "202609",
            "last_official_poll_attempt_kst": (self.now - timedelta(hours=23)).isoformat(),
        }
        due, interval = w._official_poll_due(state, self.now)
        self.assertFalse(due)
        self.assertEqual(interval, 24)


    def test_source_error_retries_hourly(self):
        state = {
            "official_source_health_version": w.OFFICIAL_SOURCE_HEALTH_VERSION,
            "compare_version": w.COMPARE_VERSION,
            "last_successful_official_month": "202608",
            "official_source_health": {"status": "error", "target_month": "202609"},
            "last_official_poll_attempt_kst": (self.now - timedelta(minutes=59)).isoformat(),
        }
        due, interval = w._official_poll_due(state, self.now)
        self.assertFalse(due)
        self.assertEqual(interval, 1)
        state["last_official_poll_attempt_kst"] = (self.now - timedelta(hours=1, minutes=1)).isoformat()
        due, interval = w._official_poll_due(state, self.now)
        self.assertTrue(due)
        self.assertEqual(interval, 1)

    def test_health_version_migration_forces_one_poll(self):
        state = {
            "official_source_health_version": w.OFFICIAL_SOURCE_HEALTH_VERSION - 1,
            "last_successful_official_month": "202608",
            "last_official_poll_attempt_kst": self.now.isoformat(),
        }
        due, interval = w._official_poll_due(state, self.now)
        self.assertTrue(due)
        self.assertEqual(interval, 3)

    def test_compare_version_upgrade_forces_repoll(self):
        state = {
            "official_source_health_version": w.OFFICIAL_SOURCE_HEALTH_VERSION,
            "compare_version": w.COMPARE_VERSION - 1,
            "last_successful_official_month": "202608",
            "last_official_poll_attempt_kst": self.now.isoformat(),
        }
        due, interval = w._official_poll_due(state, self.now)
        self.assertTrue(due)
        self.assertEqual(interval, 3)

    def test_regional_data_go_row_is_exact_hsk10(self):
        xml = """<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
        <body><items><item><priodTitle>2026.09</priodTitle><hsSgn>8542323000</hsSgn>
        <expUsdAmt>2234567</expUsdAmt></item></items></body></response>"""
        with patch.object(w, "_request_with_retry", return_value=_Resp(xml)):
            row, err = w.fetch_data_go_sido_month("202609", "44")
        self.assertEqual(err, "")
        self.assertEqual(row["hs"], "8542323000")
        self.assertEqual(row["scope"], "regional_hsk10_exact")
        self.assertEqual(row["amount_usd"], 2234567000)
        self.assertEqual(row["raw_amount_unit"], "thousand_usd")

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
