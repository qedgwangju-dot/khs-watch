from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from yen_carry_telegram_format import render_telegram_html  # noqa: E402


class YenCarryTelegramFormatTests(unittest.TestCase):
    def test_fx_shock_highlights_key_values_without_dropping_content(self):
        title = "🚨 USD/JPY 엔화 강세 1단계 — 고점 대비 -1.17%·427분 지속 하락"
        body = "\n".join(
            [
                "조회 시각: 2026-09-07 18:46:42 KST",
                "시장 데이터 시각: 2026-09-07 18:46:41 KST",
                "방향 읽는 법: USD/JPY 하락 = 엔화 강세 / 상승 = 엔화 약세",
                "",
                "현재 상태: 지속 하락 중 — 최근 고점 이후 427분, -1.17% 하락",
                "알림 사유: 신규 하락 경보",
                "감지 경로: 가변 구간 지속 하락",
                "USD/JPY 현재가: 154.405",
                "",
                "빠른 급락 감지",
                "15분(18:30→18:46): 154.281 → 154.405, +0.08% | 사실상 보합 | 빠른 급락 기준 미충족",
                "30분(18:15→18:46): 154.446 → 154.405, -0.03% | 사실상 보합 | 빠른 급락 기준 미충족",
                "",
                "지속 하락 감지 — 90분처럼 고정하지 않고 실제 고점부터 자동 계산",
                "가변 구간(11:40→18:46, 427분): 156.228 → 154.405, -1.17% | 구간 저점 154.156, 저점 대비 반등 0.16% | 1단계·주의 지속 하락",
                "",
                "60분 단순 비교 — 참고용",
                "60분 참고(17:45→18:46): 154.466 → 154.405, -0.04% | 사실상 보합 | 충격 잔존 기준 미충족",
                "",
                "최종 판정: USD/JPY 엔화 강세 경보 1단계·주의",
                "빠른 급락 단계: 0 / 지속 하락 단계: 1",
                "같은 단계 재알림 최소 간격: 20분",
                "",
                "산업·업종 영향",
                "실제 업종 반응: 각 업종에 맞는 기준지수(TOPIX·KOSPI 200·KOSDAQ 150) 대비 상대수익률",
                "• 한국 자동차 대형주: +1.71% / KOSPI 200 +4.82% → 상대 -3.11%p(당일, 종가) · 확산 0% · 예상과 반대",
                "• 한국 반도체 장비·소재·부품: +3.62% / KOSDAQ 150 +1.52% → 상대 +2.10%p(당일, 종가) · 확산 88% · 환율 직접 영향 판단 보류",
                "종합 판정: 엔화 강세 연동 가능성 미확인",
                "주의: 상대수익률은 연동 가능성을 보여줄 뿐, 환율이 유일한 원인임을 뜻하지 않습니다.",
            ]
        )
        rendered = render_telegram_html(title, body, "fx_shock")

        self.assertIn(f"<b>{title}</b>", rendered)
        self.assertIn("<b>현재 상태: 지속 하락 중", rendered)
        self.assertIn("<b>USD/JPY 현재가: 154.405</b>", rendered)
        self.assertIn("<b>15분(18:30→18:46)</b>", rendered)
        self.assertIn("<b>+0.08%</b>", rendered)
        self.assertIn("<b>가변 구간(11:40→18:46, 427분)", rendered)
        self.assertIn("<b>최종 판정: USD/JPY 엔화 강세 경보 1단계·주의</b>", rendered)
        self.assertIn("• <b>한국 자동차 대형주</b>:", rendered)
        self.assertIn("<b>상대 -3.11%p</b>", rendered)
        self.assertIn("<b>예상과 반대</b>", rendered)
        self.assertIn("<b>종합 판정: 엔화 강세 연동 가능성 미확인</b>", rendered)

        for original in body.splitlines():
            if original:
                self.assertIn(original.split(":", 1)[0].replace("• ", ""), rendered)

    def test_non_fx_lane_is_html_escaped_but_not_reformatted(self):
        rendered = render_telegram_html("일반 알림", "A&B < C", "yen_carry")
        self.assertEqual(rendered, "일반 알림\n\nA&amp;B &lt; C")

    def test_user_controlled_html_cannot_break_parse_mode(self):
        rendered = render_telegram_html(
            "🚨 <위험>",
            "현재 상태: A&B <script>alert(1)</script>",
            "fx_shock",
        )
        self.assertIn("&lt;위험&gt;", rendered)
        self.assertIn("A&amp;B &lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>", rendered)


if __name__ == "__main__":
    unittest.main()
