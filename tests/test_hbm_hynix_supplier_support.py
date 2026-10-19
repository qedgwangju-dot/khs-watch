import pathlib, sys, unittest
from datetime import datetime
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import hbm_memory_axes as w

class HynixSupplierFinanceTests(unittest.TestCase):
    def item(self,url=None):
        return {"direct_link":url or w.HYNIX_FINANCE_GOV,"source":"산업통상부",
            "title":"SK하이닉스 소부장 수출공급망 강화보증 협약",
            "published_at_kst":"2026-10-19T15:00:00+09:00"}
    def original(self):
        return ("SK하이닉스 한국무역보험공사 국민 신한 우리 하나 4대 은행이 "
            "수출공급망 강화보증 협약을 체결했다. 2조원 보증을 출범하며 "
            "SK하이닉스 은행 공동 1,000억원 출연, 출연금 20배를 보증한다. "
            "1호 보증서 전달. 추천 협력사 우대금리 최대 2.5%p, 3년 보증.")
    def test_official_guarantee_limit_vs_cash(self):
        r=w.parse_hynix_supplier_program(self.item(),self.original())[0]
        self.assertEqual(r["value"]["ceiling_krw"],2000000000000)
        self.assertEqual(r["value"]["contribution_krw"],100000000000)
        self.assertFalse(r["value"]["is_cash_grant"])
        self.assertIsNone(r["value"]["guaranteed_loan_drawn_krw"])
        self.assertEqual(r["evidence"],"official")
    def test_yonhap_original_is_report_not_official(self):
        rec=w.parse_hynix_supplier_program(self.item(w.HYNIX_FINANCE_YNA),self.original())[0]
        self.assertEqual(rec["evidence"],"reported")
    def test_guarantee_notified_once(self):
        rec=w.parse_hynix_supplier_program(self.item(),self.original())[0]
        now=datetime(2026,10,20,1,0)
        first=w.update_state({},[rec],now,[])
        self.assertIn(rec["key"],first["pending"])
        first["last_notified"][rec["key"]]=rec
        first["pending"].clear()
        self.assertNotIn(rec["key"],w.update_state(first,[rec],now,[])["pending"])
    def test_stage_cannot_downgrade(self):
        old={"axis":"hynix_supplier_guarantee","value":{"stage":"first_certificate","ceiling_krw":2000000000000}}
        new={"axis":"hynix_supplier_guarantee","value":{"stage":"agreement","ceiling_krw":2000000000000}}
        self.assertEqual(w.comparison(old,new),[])
    def test_historical_support_silent(self):
        import json
        root=pathlib.Path(__file__).resolve().parents[1]
        rows=json.loads((root/"data"/"hbm_memory_baselines.json").read_text(encoding="utf-8"))["records"]
        seeds=[r for r in rows if r["axis"] in ("hynix_supplier_rnd","hynix_trinity_fab")]
        self.assertEqual(len(seeds),2)
        self.assertEqual(w.update_state({},seeds,datetime(2026,10,20),seeds)["pending"],{})
    def test_render_scope_warning(self):
        rec=w.parse_hynix_supplier_program(self.item(),self.original())[0]
        txt=w.render({"record":rec,"old":None,"reasons":["출범"]})
        self.assertIn("보증",txt)
        self.assertIn("href=",txt)
        self.assertIn("매출",txt)

if __name__=="__main__": unittest.main()
