import datetime as dt
import importlib.util
import pathlib
import unittest
from zoneinfo import ZoneInfo

p=pathlib.Path(__file__).parents[1]/"scripts/spx_put_vix_joint_stress_watch.py"
spec=importlib.util.spec_from_file_location("spx_joint",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def data(date="2026-10-23",ratio=1.25,vix=19.45):
    c=2000000
    return dict(date=date,ratio=ratio,vix=vix,puts=int(round(c*ratio)),
      calls=c,oi_puts=14117301,oi_calls=9566355,
      source=m.CBOE_URL.format(date=date))

def page(date="23 October 2026",calls="2,199,681",puts="2,745,718",total="4,945,399",
         published_ratio="1.25",has_date=True):
    return ('<html><body>'+(f'<input value="{date}">' if has_date else '')+
      f'<div>SPX + SPXW PUT/CALL RATIO {published_ratio}</div>'
      '<h1>INDEX OPTIONS</h1><h1>CBOE VOLATILITY INDEX (VIX)</h1>'
      '<h2>SPX + SPXW</h2>'+
      f'<table><tr><td>VOLUME</td><td>{calls}</td><td>{puts}</td><td>{total}</td></tr>'
      '<tr><td>OPEN INTEREST</td><td>9,566,355</td><td>14,117,301</td><td>23,683,656</td></tr></table>'
      '<h2>OEX</h2></body></html>')

class TestSpxOfficialAndRisks(unittest.TestCase):
    def test_real_official_oct_23_numbers(self):
        d=m.parse_cboe_page(page(),dt.date(2026,10,23))
        self.assertEqual((d["calls"],d["puts"],d["total"],d["oi_puts"]),
                         (2199681,2745718,4945399,14117301))
        self.assertAlmostEqual(d["ratio"],1.2482,3)
        self.assertIn("dt=2026-10-23",d["source"])
    def test_missing_date_or_wrong_date_rejected(self):
        for h in (page(has_date=False),page(date="22 October 2026")):
            with self.assertRaisesRegex(ValueError,"화면 기준일"):m.parse_cboe_page(h,"2026-10-23")
    def test_mismatched_counts_and_ratio_rejected(self):
        with self.assertRaisesRegex(ValueError,"내부 합계"):
            m.parse_cboe_page(page(total="4,945,400"),"2026-10-23")
        with self.assertRaisesRegex(ValueError,"비율과 계약"):
            m.parse_cboe_page(page(published_ratio="1.60"),"2026-10-23")
    def test_vix_two_date_formats(self):
        rows=["DATE,OPEN,HIGH,LOW,CLOSE"]
        rows += [(dt.date(2026,9,15)+dt.timedelta(days=i)).isoformat()+",18,20,18,19.45" for i in range(31)]
        out=m.parse_vix_csv("\n".join(rows))
        self.assertEqual(out["2026-10-15"],19.45)
        rows[-1]="10/23/2026,19.18,20.66,18.87,19.45"
        out=m.parse_vix_csv("\n".join(rows))
        self.assertEqual(out["2026-10-23"],19.45)
    def test_invalid_or_small_vix_rejected(self):
        with self.assertRaisesRegex(ValueError,"표본 부족"):
            m.parse_vix_csv("DATE,OPEN,HIGH,LOW,CLOSE\n2026-10-23,19,19,19,19")
    def test_exact_joint_thresholds(self):
        checks=[(1.25,19.45,0),(1.80,19.45,0),
                (1.40,24.99,0),(1.40,25.0,1),
                (1.69,29.99,1),(1.70,30,2),
                (2.0,39.99,2),(2.0,40,3)]
        for ratio,vix,want in checks:self.assertEqual(m.stage(ratio,vix),want)
    def test_recovery_needs_three_sessions(self):
        old=2
        series=[data(date=f"2026-10-{i:02d}",ratio=1.4,vix=26) for i in (19,20)]
        self.assertEqual(m.choose_stage(series,old),(old,"회복 검증 부족"))
        series.append(data(date="2026-10-21",ratio=1.4,vix=26))
        self.assertEqual(m.choose_stage(series,old),(1,"정상화 확인"))
        self.assertEqual(m.choose_stage([data(date=f"2026-10-{i:02d}",ratio=1.24,vix=19) for i in (19,20,21)],2),(0,"정상화 확인"))
    def test_absent_joint_signal_creates_no_alert(self):
        x=data()
        self.assertEqual(m.choose_stage([x],0),(0,"유지"))
        self.assertEqual(m.render(x,[x],0,0,"유지",dt.datetime(2026,10,25,22,tzinfo=ZoneInfo("Asia/Seoul"))),"")
    def test_sample_labels_not_a_new_crisis_and_does_not_claim_notional(self):
        x=data()
        s=m.render(x,[data(date="2026-10-22",ratio=1.23),x],0,0,"유지",
             dt.datetime(2026,10,25,22,tzinfo=ZoneInfo("Asia/Seoul")),sample=True)
        for phrase in ("전송 양식 검증: 새 시장 경보 아님","2,745,718계약",
            "풋 명목금액 최고치 주장: 산식·공식 원자료 불명","VIX(30일 예상 변동성)","Cboe 옵션:"):
            self.assertIn(phrase,s)
        self.assertLess(len(s),m.MAX_CHARS)
        self.assertEqual(s.count("<b>"),s.count("</b>"))
        self.assertNotIn("2008년 금융위기 재발 확정",s)
    def test_notional_is_not_misclassified_as_put_purchases(self):
        x=data(ratio=2.5,vix=19.45)
        self.assertEqual(m.stage(x["ratio"],x["vix"]),0)

if __name__=="__main__":unittest.main()
