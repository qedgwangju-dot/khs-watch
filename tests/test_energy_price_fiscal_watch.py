#!/usr/bin/env python3
import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import energy_price_fiscal_watch as w

class PriceFiscalTests(unittest.TestCase):
    def test_price_cap_classification(self):
        self.assertEqual(w.category("(참고자료)12차 최고가격, 11차 수준으로 동결"),"oil_cap")
        self.assertEqual(w.category("석유 최고가격제 손실보전 금액은 아직 결정되지 않았습니다"),"oil_compensation")
        self.assertEqual(w.category("2026년 4분기 연료비조정단가 산정내역"),"electric_tariff")
        self.assertEqual(w.category("한전, ’26년 3분기(누계, 1~9월) 결산실적 발표"),"kepco_financial")
        self.assertIsNone(w.category("행복나눔 프로그램에 임직원 참여"))

    def test_legal_state_before_numbers(self):
        x={"category":"oil_compensation","title":"석유 최고가격제 손실보전 재정지원 금액은 아직 결정되지 않았습니다"}
        self.assertIn("미확정",w.stage(x))
        x["title"]="석유 손실보전 정산액 확정"
        self.assertIn("결정 발표",w.stage(x))
        x["title"]="석유 최고가격제 손실보전 지급 완료"
        self.assertIn("지급",w.stage(x))

    def test_prices_have_supply_price_scope(self):
        t="<html><body>리터당 휘발유 1,784원, 경유 1,773원, 등유 1,380원</body></html>"
        self.assertEqual(w.prices(t),{"휘발유":1784,"경유":1773,"등유":1380})

    def test_official_list_filters_foreign_url(self):
        t="""<html><body><a href="/kor/article/ATCL3f49a5a8c/172406/view">12차 최고가격, 11차 수준으로 동결</a>
        <a href="/kor/article/ATCL3f49a5a8c/172405/view">일반 기술규제 수출 소식</a>
        <a href="https://evil.example/kor/article/ATCL3f49a5a8c/172407/view">석유 보전금 확정</a></body></html>"""
        a=w.candidates(t,w.SOURCES["motir_press"][0],"motir_press")
        self.assertEqual(len(a),2)
        self.assertEqual([x["category"] for x in a],["oil_cap",None])

    def test_identifier_strict_exact_official(self):
        self.assertEqual(w.official_id("https://www.kepco.co.kr/home/media/newsroom/pr/boardView.do?boardMngNo=15&boardNo=3115","kepco_press"),"kepco:3115")
        self.assertEqual(w.official_id("https://www.kogas.or.kr/site/koGas/bbs/View.do?Key=1010202000000&boardIdx=47869&cbIdx=41","kogas_press"),"kogas:47869")
        self.assertIsNone(w.official_id("https://evil.example/kor/article/ATCL3f49a5a8c/172406/view","motir_press"))

    def test_date_parser_uses_article_head_not_historical_context(self):
        t="<html><body>등록일 2026-11-13 이전 정책은 1997년에 시작했다.</body></html>"
        self.assertEqual(w.published_date(t),"2026-11-13")
        with self.assertRaises(ValueError):w.published_date("<html><body>2027년 예산</body></html>")

    def test_initial_bootstrap_no_backfill(self):
        now=dt.datetime(2026,11,16,9,0,tzinfo=w.KST)
        d={"id":"motir:ATCL3f49a5a8c:172406","published":"2026-11-13","source":"motir_press"}
        state,events=w.transition({},{"motir_press":[d]},now)
        self.assertEqual(events,[])
        self.assertEqual(state["seeded_date"],"2026-11-16")
        second,more=w.transition(state,{"motir_press":[d]},now)
        self.assertEqual(more,[])
        self.assertEqual(second["seen"],state["seen"])

    def test_new_official_publication_once(self):
        now=dt.datetime(2026,11,30,12,tzinfo=w.KST)
        old={"initialized":True,"seeded_date":"2026-11-16","seen":{"motir_press":["old"]},"sources":{}}
        d={"id":"new","published":"2026-11-30","source":"motir_press"}
        nxt,items=w.transition(old,{"motir_press":[d]},now)
        self.assertEqual(items,[d])
        _,again=w.transition(nxt,{"motir_press":[d]},now)
        self.assertFalse(again)

    def test_late_indexed_old_article_no_false_alert(self):
        now=dt.datetime(2026,12,1,12,tzinfo=w.KST)
        old={"initialized":True,"seeded_date":"2026-11-16","seen":{},"sources":{}}
        _,items=w.transition(old,{"motir_clarification":[{"id":"new_in_index","published":"2026-10-29"}]},now)
        self.assertEqual(items,[])

    def test_partial_source_error_preserves_history(self):
        now=dt.datetime(2026,11,30,12,tzinfo=w.KST)
        old={"initialized":True,"seeded_date":"2026-11-16","seen":{"kogas_press":["kogas:4444"]},"sources":{}}
        nxt,_=w.transition(old,{"motir_press":[]},now)
        self.assertEqual(nxt["seen"]["kogas_press"],["kogas:4444"])

    def test_render_does_not_label_government_payment_as_done(self):
        now=dt.datetime(2026,11,30,12,tzinfo=w.KST)
        ev={"id":"x","published":"2026-11-30","source":"motir_press","category":"oil_compensation",
            "title":"정유사 손실보전 심의 계속","stage":"금액 미확정","url":"https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/9999/view"}
        msg=w.render([ev],now,{})
        self.assertIn("정부 인정액·실제 지급액은 별개",msg)
        self.assertIn("금액 미확정",msg)

if __name__=="__main__":
    unittest.main()
