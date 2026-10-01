import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_hbm_watch as w
import hbm_delivery as d

class KBHBMAndCapitalReturnTests(unittest.TestCase):
    def event(self, title, desc, source="한국경제"):
        return {"id":"kb-event","title":title,"description":desc,"source":source,"published_at_kst":"2026-10-01T07:27:00+09:00","direct_link":"https://www.hankyung.com/article/2026100162116"}

    def test_kb_is_recognized_broker(self):
        self.assertEqual(w._share_institution("KB증권 삼성전자 HBM 전망"), "kb")
        self.assertEqual(w._broker_label("kb"), "KB증권")

    def test_hbm_asp_floor_and_mix(self):
        text="KB증권 삼성전자. 삼성전자의 HBM4 매출 비중은 올해 40%에서 내년 80%로 두 배 확대될 전망. 이에 따라 내년 HBM 판매 가격은 전년 대비 100% 이상 상승할 것으로 전망한다."
        with mock.patch.object(w, "_broker_page_text", return_value=text):
            rows=w.extract_broker_hbm_forecasts(self.event("삼성전자 HBM KB증권", text))
        self.assertEqual(len(rows),1)
        obs=rows[0]
        self.assertEqual(obs["key"],"kb|samsung|2027")
        self.assertEqual(obs["asp_yoy_pct"],100.0)
        self.assertTrue(obs["asp_is_floor"])
        self.assertEqual(obs["hbm4_revenue_mix_current_pct"],40.0)
        self.assertEqual(obs["hbm4_revenue_mix_next_pct"],80.0)

    def test_kb_current_baseline_is_silent(self):
        old=dict(w.BROKER_FORECAST_BASELINES["kb|samsung|2027"])
        material,reasons=w._broker_material_change(old,dict(old))
        self.assertFalse(material); self.assertEqual(reasons,[])

    def test_kb_mix_revision_alerts(self):
        old=dict(w.BROKER_FORECAST_BASELINES["kb|samsung|2027"])
        material,reasons=w._broker_material_change(old,dict(old,hbm4_revenue_mix_next_pct=70.0))
        self.assertTrue(material); self.assertTrue(any("HBM4 내년 매출 비중" in x for x in reasons))

    def test_capital_return_baseline_math(self):
        st=dict(w.CAPITAL_RETURN_BASELINE)
        self.assertEqual(st["broker_next_3y_return_krw_trn"]/(st["broker_assumed_fcf_return_pct"]/100),1200.0)

    def test_capital_return_revision_threshold(self):
        reasons=w._capital_return_changes(dict(w.CAPITAL_RETURN_BASELINE),{"broker_next_3y_return_krw_trn":660.0})
        self.assertTrue(any("차기 3년 주주환원 전망" in x for x in reasons))

    def test_capital_return_is_separate_message(self):
        cap=w.capital_return_change_event({"title":"KB 삼성전자 주주환원","source":"한국경제","source_url":"https://example.com","observed_at":"2026-10-01T07:27:00+09:00"},dict(w.CAPITAL_RETURN_BASELINE),["차기 3년 주주환원 전망 600.0조→660.0조"])
        hbm={"id":"hbm","title":"HBM test","description":"","source":"KB증권","published_at_kst":"2026-10-01T07:28:00+09:00","direct_link":"https://example.com/hbm","broker_forecast_change":{"institution":"KB증권","company":"삼성전자","period":"2027","asp_yoy_pct":110.0,"asp_is_floor":False,"previous_state_asp_yoy_pct":100.0,"report_previous_asp_yoy_pct":None,"hbm4_revenue_mix_current_pct":40.0,"hbm4_revenue_mix_next_pct":80.0,"old_hbm4_revenue_mix_current_pct":40.0,"old_hbm4_revenue_mix_next_pct":80.0,"stack_mainstream":"","old_stack_mainstream":"","contract_stage":"","old_contract_stage":"","eps_revision_pct":{},"fx_headwind":False,"reasons":["ASP +10%p"]}}
        out=w.build_event_alert([hbm,cap],w.datetime(2026,10,1,8,0,tzinfo=w.ZoneInfo("Asia/Seoul")))
        parts=d.chunks(out)
        self.assertEqual(len(parts),2)
        self.assertIn("HBM 상태 변화",parts[0])
        self.assertIn("주주환원·FCF 변화",parts[1])
        self.assertIn("1,200조원",parts[1])

if __name__=="__main__":
    unittest.main()
