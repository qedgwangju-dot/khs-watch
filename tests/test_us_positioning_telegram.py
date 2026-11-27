import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import us_positioning_telegram as telegram


ALERT = """🇺🇸 <b>미국 포지셔닝 | 정정·보강</b>

<b>한눈에 보기</b>
• 반도체(SOX): 8,774.86pt | 1D -0.65%
• 통합 기관: 순롱 84,381계약 | 주간 순포지션 변화 +10,486계약 · 순롱 확대
• 통합 헤지펀드성: 순숏 12,468계약 | 주간 순포지션 변화 -25,358계약 · 순롱 → 순숏 전환
• NQ E-mini: 순숏 10,928계약 · 1주 전 대비 순롱 13,967계약 → 순숏 10,928계약 전환
  3년 순숏 16 / 총숏 12백분위 · 10년 순숏 31 / 총숏 28백분위

① 기간 수익률과 현재 추세 | 2026-11-25 마감
🟡 반도체 기간별 방향 혼재 · 주요지수 종합 확인 대기
• SOX 8,774.86pt · 전일 -57.64pt (-0.65%)
• 전일 종가 8,832.50pt | 1거래일 -0.65% | 3거래일 +4.36% | 5거래일 -9.10%
• 1개월 전 대비: -18.60% · 하락
• 3개월 전 대비: -24.28% · 하락
• 나스닥100 26,046.90pt · 전일 -167.27pt (-0.64%)
• 1일 -0.64% / 3일 +4.07% / 5일 -3.94%
• 1개월 -10.05% / 3개월 -10.83%
• S&P500 종가: 확인 대기
• 1일 확인 대기 / 3일 확인 대기 / 5일 확인 대기

② 실제 거래대금 | 미국 주식시장 전체
• 2026-11-25 당일 1.1460조달러 (1,539.74조원)
• 전일 대비 +825.61억달러 (+110.93조원) (+7.76%)
• 5거래일 ↑ 증가 +30.63%
• 1개월 ↑ 증가 +16.87%
• 3개월 ↓ 감소 -7.70%

③ 선물 | 2026-11-17 주간 · 계약
• 나스닥100 통합: 기관 순롱 84,381계약 / 헤지펀드성 순숏 12,468계약
<b>NQ E-mini 헤지펀드성 · 통합과 별도 집계</b>
• 현재 순숏 10,928계약 · 참고 59.02억달러 (7.88조원)
• 1주 전 대비: 순롱 13,967계약 → 순숏 10,928계약 전환
  계약 수 변화의 동일가격 환산: 134.44억달러 (17.95조원)
※ 참고금액: NDX 종가×20.00달러/pt. 거래대금·증거금 아님.

④ 시장 확산·옵션 참고
• 옵션 P/C(2026-11-25): 주식 0.64 / 지수 1.04 / 전체 0.98
• 옵션 전체 거래량: 콜 8,707,205 / 풋 8,519,982계약 · 프리미엄 거래대금 미제공
※ P/C=풋÷콜 거래량. 매수·매도 방향과 가격 반등을 확인한 값은 아님.
<a href="https://github.com/qedgwangju-dot/khs-watch/actions/runs/12345">상세 수치·계산·출처</a>
"""


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload)) + kind + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def tiny_png(width=1, height=1) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\xff\xff\xff" * width
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(row * height))
        + _png_chunk(b"IEND", b"")
    )
    return data


class AlertImageContractTests(unittest.TestCase):
    def test_alert_is_reorganized_into_a_visual_korean_report(self):
        document = telegram.render_alert_document(ALERT)
        self.assertIn('<html lang="ko">', document)
        self.assertIn("Noto Sans CJK KR", document)
        self.assertIn('class="report-header"', document)
        self.assertIn('class="summary-grid"', document)
        self.assertIn('class="asset-card"', document)
        self.assertIn('class="return-chart"', document)
        self.assertIn('class="options-grid"', document)
        self.assertNotIn(ALERT, document)
        self.assertIn("2026-11-25", document)
        self.assertIn("+4.36%", document)
        self.assertIn("-9.10%", document)
        self.assertIn("10년 순숏 31 / 총숏 28백분위", document)
        self.assertIn("KRW 액면 환산은 확인 불가", document)
        self.assertIn("17.95조원", document)
        self.assertIn("확인 대기", document)
        self.assertEqual(document.count('class="asset-card"'), 3)
        parsed = telegram.parse_alert_fragment(ALERT)
        self.assertIn("NQ E-mini: 순숏 10,928계약", parsed["visible_text"])
        self.assertEqual(
            parsed["links"],
            ["https://github.com/qedgwangju-dot/khs-watch/actions/runs/12345"],
        )

    def test_incomplete_section_contract_fails_closed_instead_of_making_a_text_poster(self):
        with self.assertRaisesRegex(ValueError, "four numbered report sections"):
            telegram.render_alert_document("🇺🇸 <b>미국 포지셔닝</b>\n\n<b>한눈에 보기</b>\n• SOX: 100pt")

    def test_fragment_rejects_unbalanced_and_untrusted_html(self):
        for text in ("<b>unterminated", "<script>alert(1)</script>", '<a href="https://evil.example/x">x</a>'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                telegram.parse_alert_fragment(text)

    def test_photo_caption_contains_report_title_and_clickable_detail_url(self):
        caption = telegram.build_caption(ALERT)
        self.assertIn("미국 포지셔닝 | 정정·보강", caption)
        self.assertIn("https://github.com/qedgwangju-dot/khs-watch/actions/runs/12345", caption)
        self.assertLessEqual(len(telegram.parse_alert_fragment(caption)["visible_text"]), 1024)

    def test_png_structure_and_telegram_dimension_limits_are_checked(self):
        data = tiny_png(1280, 3333)
        self.assertEqual(telegram.png_dimensions(data), (1280, 3333))
        self.assertEqual(telegram.validate_photo_bytes(data)["bytes"], len(data))
        with self.assertRaisesRegex(ValueError, "dimensions"):
            telegram.validate_photo_bytes(tiny_png(9000, 2000))
        broken = bytearray(data)
        broken[-5] ^= 0x01
        with self.assertRaisesRegex(ValueError, "checksum"):
            telegram.png_dimensions(bytes(broken))

    def test_success_receipt_requires_correct_chat_message_and_photo(self):
        photo = telegram.validate_photo_bytes(tiny_png())
        guard = {
            "attempt_id": "attempt-1",
            "alert_text_sha256": "abc",
            "caption_sha256": "def",
        }
        payload = {
            "ok": True,
            "result": {
                "message_id": 345,
                "chat": {"id": -100123, "type": "channel"},
                "photo": [{"width": 100, "height": 100}, {"width": 1280, "height": 3333}],
            },
        }
        receipt = telegram.build_send_photo_receipt(payload, 200, "-100123", photo, guard, "watch_bot")
        self.assertEqual(receipt["delivery_method"], "sendPhoto")
        self.assertEqual(receipt["message_id"], 345)
        self.assertEqual(receipt["telegram_photo_height"], 3333)
        self.assertTrue(receipt["chat_id_match"])
        for bad in (
            {**payload, "result": {**payload["result"], "chat": {"id": -100999}}},
            {**payload, "result": {**payload["result"], "photo": []}},
            {**payload, "result": {**payload["result"], "message_id": None}},
            {**payload, "result": "malformed"},
            {**payload, "result": {**payload["result"], "chat": "malformed"}},
            {**payload, "result": {**payload["result"], "photo": ["malformed"]}},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                telegram.build_send_photo_receipt(bad, 200, "-100123", photo, guard, "watch_bot")

    def test_guard_blocks_ambiguous_results_but_allows_confirmed_or_explicit_rejection(self):
        self.assertFalse(telegram.guard_blocks_send(None))
        self.assertFalse(telegram.guard_blocks_send({"status": "confirmed"}))
        self.assertFalse(telegram.guard_blocks_send({"status": "retry_safe"}))
        self.assertTrue(telegram.guard_blocks_send({"status": "unconfirmed"}))
        self.assertTrue(telegram.guard_blocks_send({"status": "unknown"}))

    def test_attempt_records_hashes_not_raw_recipient_and_detects_file_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            alert = root / "alert.html"
            image = root / "alert.png"
            guard = root / "guard.json"
            attempt = root / "attempt.json"
            alert.write_text(ALERT, encoding="utf-8")
            image.write_bytes(tiny_png())
            result = telegram.prepare_attempt(
                alert, image, guard, attempt, "99", "deadbeef", "watch_bot", "-100123"
            )
            self.assertEqual(result["status"], "unconfirmed")
            self.assertEqual(result["delivery_method"], "sendPhoto")
            self.assertNotIn("chat_id", result)
            self.assertEqual(result["recipient_sha256"], hashlib.sha256(b"-100123").hexdigest())
            self.assertTrue(telegram.attempt_matches_files(result, alert, image))
            image.write_bytes(tiny_png() + b"x")
            self.assertFalse(telegram.attempt_matches_files(result, alert, image))

    def test_attempt_is_bound_to_its_configured_recipient_and_caption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            alert = root / "alert.html"
            image = root / "alert.png"
            guard = root / "guard.json"
            attempt = root / "attempt.json"
            alert.write_text(ALERT, encoding="utf-8")
            image.write_bytes(tiny_png())
            result = telegram.prepare_attempt(
                alert, image, guard, attempt, "99", "deadbeef", "watch_bot", "-100123"
            )
            self.assertEqual(result["bot_username"], "watch_bot")
            guard_data = json.loads(attempt.read_text(encoding="utf-8"))
            guard_data["caption_sha256"] = "wrong"
            self.assertFalse(telegram.attempt_matches_files(guard_data, alert, image))
            self.assertNotEqual(
                result["recipient_sha256"], hashlib.sha256(b"-100999").hexdigest()
            )

    def test_confirm_guard_requires_matching_success_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guard_path = root / "guard.json"
            receipt_path = root / "receipt.json"
            guard = {"status": "unconfirmed", "attempt_id": "same"}
            receipt = {
                "status": "confirmed",
                "delivery_method": "sendPhoto",
                "attempt_id": "same",
                "chat_id_match": True,
                "message_id": 345,
                "photo_sizes_returned": 2,
                "confirmed_at_utc": "2026-11-27T00:00:00+00:00",
            }
            guard_path.write_text(json.dumps(guard), encoding="utf-8")
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            result = telegram.confirm_guard(guard_path, receipt_path)
            self.assertEqual(result["status"], "confirmed")
            self.assertEqual(result["telegram_message_id"], 345)
            guard_path.write_text(json.dumps({"status": "unconfirmed", "attempt_id": "same"}), encoding="utf-8")
            receipt["attempt_id"] = "different"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                telegram.confirm_guard(guard_path, receipt_path)
            guard_path.write_text(json.dumps({"status": "unconfirmed", "attempt_id": "same"}), encoding="utf-8")
            receipt["attempt_id"] = "same"
            receipt["image_sha256"] = "wrong"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "image_sha256"):
                telegram.confirm_guard(guard_path, receipt_path)

    def test_only_explicit_rejection_marks_a_photo_attempt_safe_to_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guard_path = root / "guard.json"
            rejection_path = root / "rejection.json"
            guard_path.write_text(json.dumps({"status": "unconfirmed", "attempt_id": "same"}), encoding="utf-8")
            rejection_path.write_text(json.dumps({
                "status": "retry_safe",
                "attempt_id": "same",
                "rejection_kind": "telegram_api_rejected",
                "error_code": 400,
                "recorded_at_utc": "2026-11-27T00:00:00+00:00",
            }), encoding="utf-8")
            result = telegram.mark_retry_safe(guard_path, rejection_path)
            self.assertEqual(result["status"], "retry_safe")
            self.assertFalse(telegram.guard_blocks_send(result))
            guard_path.write_text(json.dumps({"status": "unconfirmed", "attempt_id": "same"}), encoding="utf-8")
            rejection_path.write_text(json.dumps({
                "status": "retry_safe", "attempt_id": "different",
                "rejection_kind": "telegram_api_rejected",
                "recorded_at_utc": "2026-11-27T00:00:00+00:00",
            }), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                telegram.mark_retry_safe(guard_path, rejection_path)


if __name__ == "__main__":
    unittest.main()
