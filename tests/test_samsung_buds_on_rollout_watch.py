#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

FILE=pathlib.Path(__file__).resolve().parents[1]/"scripts"/"samsung_buds_on_rollout_watch.py"
spec=importlib.util.spec_from_file_location("buds_on_rollout",FILE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class GalaxyBudsOnRolloutTests(unittest.TestCase):
    def row(self,title,source="Samsung Newsroom",date="2026-10-28T10:00:00+09:00",
            source_url="https://news.samsung.com/kr"):
        return {"title":title,"description":"","source":source,
                "source_url":source_url,
                "published_at_kst":date,"link":source_url+"/example","id":"abc"}
    def state(self,status=None):
        return {"metrics":{**m.BASELINE, **({"status":status} if status else {})}}

    def test_baseline_is_future_launch_not_sales(self):
        self.assertEqual(m.BASELINE["korean_price_krw"],299000)
        self.assertEqual(m.BASELINE["korean_retail_launch"],"2026-10-27")
        self.assertIsNone(m.BASELINE["units_sold"])
        self.assertIn("전",m.BASELINE["status"])

    def test_verified_official_product_page(self):
        self.assertTrue(m._official_baseline_present(
            "<p>갤럭시 버즈 온을 오는 10월 27일 출시하며 가격은 299,000원이다</p>"
        ))
        self.assertFalse(m._official_baseline_present("<p>갤럭시 버즈 온 향후 출시</p>"))

    def test_20th_briefing_not_second_launch(self):
        item=self.row("Samsung Galaxy Buds On briefing, October 20 memory alloy",
                      date="2026-10-20T11:30:00+09:00")
        self.assertIsNone(m._signal(item,self.state()))

    def test_27th_official_sales_launch_alert(self):
        item=self.row("삼성전자 갤럭시 버즈 온 국내 정식 출시 및 판매 시작",
                      date="2026-10-27T10:00:00+09:00")
        self.assertEqual(m._signal(item,self.state())["kind"],"launch")

    def test_27th_republication_not_official(self):
        item=self.row("삼성전자 갤럭시 버즈 온 국내 정식 출시 및 판매 시작",
                      source="Yonhap", source_url="https://en.yna.co.kr")
        self.assertIsNone(m._signal(item,self.state()))

    def test_existing_sales_launch_not_realert(self):
        item=self.row("삼성전자 갤럭시 버즈 온 국내 판매 시작")
        self.assertIsNone(m._signal(item,self.state("국내 정식판매 확인")))

    def test_known_price_does_not_retrigger(self):
        item=self.row("갤럭시 버즈 온 공식 가격 변경 299,000원")
        self.assertIsNone(m._signal(item,self.state()))

    def test_official_material_reprice(self):
        item=self.row("갤럭시 버즈 온 공식 가격 인상 새 가격 329,000원")
        self.assertEqual(m._signal(item,self.state())["value"],329000)

    def test_unknown_publisher_not_promoted(self):
        item=self.row("갤럭시 버즈 온 공식 가격 인상 329,000원",source="Rumor Daily",
                      source_url="https://example.com")
        self.assertIsNone(m._signal(item,self.state()))

    def test_concurrent_merge_preserves_confirmed_launch(self):
        remote={"updated_at_kst":"2026-10-27T12:00:00+09:00",
                "metrics":{"status":"국내 정식판매 확인"},"seen_ids":["r"],
                "initial_alert_sent":True}
        local={"updated_at_kst":"2026-10-27T11:00:00+09:00",
               "metrics":{"status":"공식 공개·판매 시작 전"},"seen_ids":["l"],
               "initial_alert_sent":True}
        out=m._merge_buds_state(remote,local)
        self.assertEqual(out["metrics"]["status"],"국내 정식판매 확인")
        self.assertEqual(set(out["seen_ids"]),{"l","r"})

if __name__=="__main__":
    t=unittest.defaultTestLoader.loadTestsFromTestCase(GalaxyBudsOnRolloutTests)
    r=unittest.TextTestRunner(verbosity=2).run(t)
    if not r.wasSuccessful():
        sys.exit(1)
