import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_alert_visual_polish", ROOT / "scripts" / "clarity_alert_visual_polish.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityAlertVisualPolishTest(unittest.TestCase):
    def test_polish_improves_scanability_without_dropping_detail(self):
        original = (
            "<b>🔔 CLARITY 법안 Watch — 표결·규제·BTC/COIN/Circle 영향</b>\n\n"
            "<b>한눈에 보기</b>\n"
            "• Trump 대통령이 Tillis–Gallego 윤리 절충안의 약 80%를 수용했습니다.\n"
            "  ↳ 시간표 ↑↑ · 할인율 ↑ · 수급 ↑/△ · 돈 버는 능력 →\n\n"
            "<b>1. Trump 대통령, 윤리안 핵심 조항 수용</b>\n\n"
            "<b>🧭 무엇이 달라졌나</b>\n"
            "60표 확보의 핵심 정치적 장애물이 완화됐습니다.\n\n"
            "<b>📍 현재 판정</b>\n"
            "🟡 협상 진전\n\n"
            "<b>💰 투자 의미</b>\n"
            "• 돈 버는 능력 → 아직 변화 없음.\n"
            "• 할인율 ↑ 규제 불확실성 완화.\n"
            "• 수급 ↑/△ COIN·CRCL에 더 직접적.\n"
            "• 시간표 ↑↑ 가장 크게 개선.\n\n"
            "<b>✅ 확인된 사실</b>\n"
            "• 주 법무장관 집행권이 포함됐습니다.\n\n"
            "<b>⚠️ 아직 미확정</b>\n"
            "• 개정 법안 원문은 대기 중입니다.\n\n"
            "<b>⏱ 다음 확인</b>\n"
            "• 60표 cloture 결과\n\n"
            "<b>🔎 근거</b>\n"
            "검증 근거: Associated Press · Reuters\n"
            "<a href=\"https://apnews.com/example\">원문</a>\n\n"
            "<b>📊 시장 반응·원인 분리</b>\n"
            "BTC·ETH·COIN·CRCL과 금리·달러·Nasdaq을 분리합니다.\n\n"
            "<b>핵심 한 줄 요약</b>\n"
            "시간표·할인율 개선이 핵심입니다."
        )
        polished = MOD.polish_chunk(original)

        self.assertIn("<b>🔔 CLARITY 법안 Watch</b>", polished)
        self.assertIn("<i>표결·규제·BTC/COIN/Circle 영향</i>", polished)
        self.assertIn("<b>👀 한눈에 보기</b>", polished)
        self.assertIn("↳ <b>4축</b> 시간표 ↑↑", polished)
        self.assertIn("• 💵 <b>돈 버는 능력</b> → 아직 변화 없음.", polished)
        self.assertIn("• 📉 <b>할인율</b> ↑ 규제 불확실성 완화.", polished)
        self.assertIn("• 🌊 <b>수급</b> ↑/△ COIN·CRCL에 더 직접적.", polished)
        self.assertIn("• ⏱ <b>시간표</b> ↑↑ 가장 크게 개선.", polished)
        self.assertIn("🔗 <a href=\"https://apnews.com/example\">원문</a>", polished)
        self.assertIn("🎯 <b>핵심 한 줄 요약</b>", polished)

        # Detail must remain; visual polishing is not a shortening pass.
        self.assertIn("60표 확보의 핵심 정치적 장애물이 완화됐습니다.", polished)
        self.assertIn("주 법무장관 집행권이 포함됐습니다.", polished)
        self.assertIn("개정 법안 원문은 대기 중입니다.", polished)
        self.assertIn("BTC·ETH·COIN·CRCL과 금리·달러·Nasdaq을 분리합니다.", polished)


if __name__ == "__main__":
    unittest.main()
