"""Offline, no-send regression tests for the existing Hormuz alert renderer."""

from html.parser import HTMLParser
import unittest

from scripts.iran_hormuz_telegram_format import (
    render_telegram_html,
    telegram_visible_length,
)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.words = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs).get("href"))

    def handle_data(self, data):
        self.words.append(data)


class HormuzTelegramFormatTests(unittest.TestCase):
    def test_bernstein_all_facts_and_three_clickable_links(self):
        body = "\n".join((
            "[Bernstein | 글로벌 석유 수급 전망 변화]",
            "보도일: 2026년 11월 23일 · 분석가 Neil Beveridge 등",
            "자료 단계: 차이롄서가 인용한 Bernstein 보고서 · 보고서 전문 직접 확인 전",
            "2026년: 미국·이란 전쟁 중 공급 부족 약 130만 배럴/일(회사 추정)",
            "2027년: 공급 증가가 수요를 웃돌아 250만 배럴/일 초과 공급 과잉 예상",
            "변화: 2026년 공급 부족 → 2027년 공급 과잉(예측, 확정 통계 아님)",
            "2027년 브렌트유 연평균 전망: 80달러(약 107,648원)/배럴",
            "2028년 브렌트유 연평균 전망: 75달러(약 100,920원)/배럴",
            "2027년 연간 누적 공급 과잉: 약 10억 배럴에 접근 가능(회사 전망)",
            "흡수 요인: 전략비축유 재확보 및 해상에 보관된 원유 재고 증가",
            "기간 정정: 2030년대 말이 아니라 이번 10년 말(2029년 무렵)까지",
            "주의: 브렌트 연평균 전망은 연말 목표가·실제 체결가격이 아님",
            "독립 참고: IEA 2026년 11월 보고서도 2027년 공급 회복·과잉 방향을 전망",
            "그러나 IEA가 Bernstein의 250만·80달러·75달러 수치를 검증한 것은 아님",
            "역풍: 호르무즈 재차 봉쇄·정제유 병목·OPEC+ 감산 시 가격 재상승 위험",
            "다음 확인: 중동 실물 출하·상업/전략비축유 재고·OPEC+ 결정·차기 IEA 보고",
            "환산 기준: 1달러=1,345.60원 · 2026-11-23 10:50:41 KST 은행 고시",
            "환율 근거: https://www.knbank.co.kr/ib20/mnu/PEBQCS070100000?DUP_CHK=N",
            "기사 원문: https://api3.cls.cn/share/article/2541328?app=&os=CailianpressWeb&sv=830",
            "IEA 참고: https://www.iea.org/reports/oil-market-report-november-2026",
        ))
        html_result = render_telegram_html("Bernstein 글로벌 석유 공급 과잉 전망", body)
        parsed = _Links()
        parsed.feed(html_result)
        self.assertEqual(len(parsed.links), 3)
        self.assertIn("?app=&os=CailianpressWeb&sv=830", parsed.links[1])
        self.assertIn('href="https://api3.cls.cn/share/article/2541328?app=&amp;os=', html_result)
        visible = "".join(parsed.words)
        for required in (
            "130만", "250만", "10억", "2027년", "2028년", "2029년",
            "80달러", "75달러", "107,648원", "100,920원", "1,345.60원",
            "독립 참고", "전문 직접 확인 전", "IEA가 Bernstein", "역풍",
            "다음 확인", "보도 원문", "해상에 보관된", "전쟁",
        ):
            self.assertIn(required, visible)
        self.assertLess(telegram_visible_length(html_result), 1100)

    def test_merged_old_alert_is_preserved_without_leaking_raw_markup(self):
        old = "[기존 알림]\nBrent 93 & WTI 90\n원문: https://example.com/?x=1&y=2"
        bern = "[Bernstein | 글로벌 석유 수급 전망 변화]\n2027년: 250만 배럴 과잉"
        result = render_telegram_html("기존 경보", old + "\n\n" + bern)
        self.assertIn("Brent 93 &amp; WTI 90", result)
        self.assertIn("<b>[기존 알림]</b>", result)
        self.assertIn("<b>Bernstein | 글로벌 석유 수급 전망 변화</b>", result)
        self.assertIn('href="https://example.com/?x=1&amp;y=2"', result)
        self.assertIn("2027년", result)

    def test_old_alert_format_and_untrusted_url_fallback(self):
        normal = "[호르무즈]\n변화: <script>&\n원문: https://example.com/news"
        out = render_telegram_html("호르무즈 경보", normal)
        self.assertIn("&lt;script&gt;&amp;", out)
        self.assertIn('<a href="https://example.com/news">원문 보기</a>', out)
        malicious = render_telegram_html("기사", "기사 원문: javascript:alert(1)")
        self.assertNotIn("<a ", malicious)
        self.assertIn("javascript:alert(1)", malicious)


if __name__ == "__main__":
    unittest.main()
