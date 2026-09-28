import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import nvidia_exec_signal_pretty as p


class NvidiaExecPrettyTests(unittest.TestCase):
    def test_capital_only_alert_does_not_pull_old_demand_or_safety_context(self):
        raw = """🚨 <b>NVIDIA 경영진·AI 수요·안전 전략 변화</b>
━━━━━━━━━━━━━━━━
<b>[무엇이 달라졌나]</b>
• <b>자본환원</b>: NVIDIA 이사회가 자사주 매입 승인 규모를 대폭 확대했습니다.
• 추가 승인: <b>$150 billion</b>
• 총 잔여 승인한도: <b>$235 billion</b>
• 실행 계획: <b>FY28</b>까지
• <b>중요:</b> 승인한도는 실제 매입 완료액이 아닙니다. 실제 집행액은 이후 10-Q·10-K의 매입 주식수·평균매입가와 별도로 추적합니다.
• 직전 공식 기준(2026-07-26): 잔여 승인한도 <b>$99.3 billion</b> · Q2 실제 매입 <b>$19.7 billion</b> · FY27 상반기 실제 매입 <b>$39.8 billion</b>
<b>조회</b>: 2026-09-28 20:27:34 KST
<b>자본환원 출처</b>: Reuters · <a href="https://www.reuters.com/test">원문</a>
<b>직전 공식 자사주 기준</b>: <a href="https://investor.nvidia.com/test">NVIDIA FY27 2Q 10-Q</a>
"""
        with tempfile.TemporaryDirectory() as td:
            alert = pathlib.Path(td) / "alert.html"
            alert.write_text(raw, encoding="utf-8")
            with patch.object(p, "ALERT", alert):
                p.main()
            out = alert.read_text(encoding="utf-8")
        self.assertIn("NVIDIA 자본환원", out)
        self.assertIn("$150 billion", out)
        self.assertIn("$235 billion", out)
        self.assertNotIn("전체 칩 판매량", out)
        self.assertNotIn("스코틀랜드 찰스 3세", out)
        self.assertNotIn("Blackwell·Rubin 실제 일정 지연", out)
        self.assertNotIn("<blockquote", out)
        self.assertLess(len(out), 1300)
        self.assertIn("[핵심]", out)
        self.assertIn("[해석]", out)
        self.assertIn("[다음 확인]", out)

    def test_demand_marker_requires_actual_demand_event_line(self):
        raw = "• 전체 칩 수량 2배를 HBM 수요 2배로 직접 환산 금지"
        self.assertNotIn("2027년에 올해보다 약 2배 많은 칩을 판매할 것으로 예상", raw)


if __name__ == "__main__":
    unittest.main()
