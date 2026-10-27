import datetime as dt
import importlib.util
import pathlib
import unittest
from zoneinfo import ZoneInfo
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("credit",pathlib.Path(__file__).parents[1]/"scripts/korea_credit_spread_watch.py")
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

def sample(cp_cd=20,credit=60,n=12):
    rows=[]; day=dt.date(2026,9,1)
    for _ in range(n):
        while day.weekday()>=5: day+=dt.timedelta(days=1)
        rates={"cp":3+cp_cd/100,"cd":3,"corp":3.5+credit/100,"gov":3.5}
        rows.append({"date":day.strftime('%Y%m%d'),"rates":rates,"cp_cd":cp_cd,
                     "credit":credit,"rank":c.level(cp_cd,credit)})
        day+=dt.timedelta(days=1)
    return rows

class CreditWatchTests(unittest.TestCase):
    def test_exact_boundary_levels(self):
        for p in ((29.99,69.99,0),(30,0,1),(0,70,1),(49.9,79.9,1),
                  (50,0,2),(0,80,2),(70,0,3),(0,90,3),(100,0,4),(0,120,4)):
            self.assertEqual(c.level(p[0],p[1]),p[2])
    def test_first_baseline(self):
        x=c.decide(sample(),{})
        self.assertTrue(x['send']);self.assertEqual(x['transition'],'최초 기준선')
        y=c.decide(sample(),{'notified_rank':0,'last_alert_signature':x['signature']})
        self.assertFalse(y['send'])
    def test_worsening_immediately(self):
        rows=sample();rows[-1]['rank']=4;rows[-1]['cp_cd']=100
        x=c.decide(rows,{'notified_rank':0})
        self.assertEqual((x['rank'],x['transition']),(4,'위험 상승'))
    def test_severe_three_consecutive(self):
        rows=sample(110,125)
        for i in (1,2): rows[-i].update(cp_cd=70,credit=95,rank=3)
        self.assertEqual(c.recovery(4,rows),4)
        rows[-3].update(cp_cd=70,credit=95,rank=3)
        self.assertEqual(c.recovery(4,rows),3)
    def test_stable_five_days(self):
        rows=sample(45,74)
        for i in range(1,5): rows[-i].update(cp_cd=20,credit=60,rank=0)
        self.assertEqual(c.recovery(1,rows),1)
        rows[-5].update(cp_cd=20,credit=60,rank=0)
        self.assertEqual(c.recovery(1,rows),0)
    def test_both_spreads_must_recover(self):
        self.assertEqual(c.recovery(3,sample(20,85)),3)
    def test_early_signal_once(self):
        rows=sample();rows[-1]['cp_cd']=31
        self.assertTrue(any('10bp' in s for s in c.early(rows)))
        rows[-2]['cp_cd']=32
        self.assertFalse(any('10bp' in s for s in c.early(rows)))
    def test_cp_absolute_threshold(self):
        rows=sample();rows[-2]['rates']['cp']=3.79;rows[-1]['rates']['cp']=4.0
        self.assertTrue(any('4.00%' in s for s in c.early(rows)))
    def test_unique_four_series_only(self):
        rows=[{'ITEM_NAME1':name,'ITEM_CODE1':code} for name,code in
              [('CP(91일)','a1'),('CD(91일)','cd1'),('회사채(3년, AA-)','aa'),('국고채(3년)','gov')]]
        with self.assertRaises(ValueError): c.codes_for(rows)
        for i,r in enumerate(rows): r['ITEM_CODE1']=str(i+1)
        self.assertEqual(set(c.codes_for(rows)),{'cp','cd','corp','gov'})
        with self.assertRaises(ValueError):c.codes_for(rows+[{'ITEM_NAME1':'CP(91일)','ITEM_CODE1':'999'}])
    def test_no_misaligned_dates(self):
        rates={k:{f'202610{d:02d}':3 for d in range(1,12)} for k in c.KINDS}
        rates['cp']={'20261016':4}
        with self.assertRaises(ValueError):
            c.aligned(rates,dt.datetime(2026,10,19,18,tzinfo=ZoneInfo('Asia/Seoul')))
    def test_stale_source(self):
        rates={k:{f'202609{d:02d}':3 for d in range(1,13)} for k in c.KINDS}
        with self.assertRaises(ValueError):
            c.aligned(rates,dt.datetime(2026,10,19,18,tzinfo=ZoneInfo('Asia/Seoul')))
    def test_message_includes_all_and_status(self):
        rows=sample(60,85)
        decision=c.decide(rows,{})
        msg=c.render(rows,decision,dt.datetime(2026,10,19,18,tzinfo=ZoneInfo('Asia/Seoul')))
        for word in ('CP–CD','회사채','국고채','하향:','다음 경계','817Y002'):
            self.assertIn(word,msg)

    def test_exact_oct19_actual_values_and_direction(self):
        rows=sample(36,68.1)
        rows[-6].update(date="20261012",rates={"cp":3.600,"cd":3.240,"corp":4.602,"gov":3.921},
                        cp_cd=36.0,credit=68.1,rank=1)
        rows[-2].update(date="20261016",rates={"cp":3.710,"cd":3.250,"corp":4.541,"gov":3.854},
                        cp_cd=46.0,credit=68.7,rank=1)
        rows[-1].update(date="20261019",rates={"cp":3.720,"cd":3.250,"corp":4.560,"gov":3.877},
                        cp_cd=47.0,credit=68.3,rank=1)
        d=c.direction_overview(rows)
        self.assertEqual(d['summary'],'단기 악화↑ · 회사채 보합→')
        self.assertAlmostEqual(d['cp_delta'],11.0)
        self.assertAlmostEqual(d['aa_delta'],0.2)
        a=c.decide(rows,{})
        m=c.render(rows,a,dt.datetime(2026,10,19,19,46,tzinfo=ZoneInfo('Asia/Seoul')))
        for text in ('방향: 단기 악화↑ · 회사채 보합→',
                     'CP–CD <b>47.0bp</b> ↑ 확대',
                     'AA- 회사채–국고채 <b>68.3bp</b> → 보합',
                     '전일 +1.0 / 5일 +11.0bp',
                     '전일 -0.4 / 5일 +0.2bp',
                     'CP 91일 3.720% | +1.0/+12.0bp',
                     'CD 91일 3.250% | +0.0/+1.0bp',
                     '회사채 AA- 3년 4.560% | +1.9/-4.2bp',
                     '국고채 3년 3.877% | +2.3/-4.4bp',
                     '50bp(+3.0bp)','80bp(+11.7bp)',
                     '확산은 아직 확인되지 않음'):
            self.assertIn(text,m)
        self.assertNotIn('CP(A1',m)
        self.assertLess(len(m),c.MAX_MESSAGE_CHARS)
        self.assertEqual(m.count('<b>'),m.count('</b>'))
        self.assertNotIn('<br',m)
        self.assertIn('단계는 자체 감시 기준',m)
        # CP와 CD의 뜻은 누구나 한눈에 읽을 수 있도록 핵심 지표 바로 아래에 각각 괄호로 표시한다.
        cp_explain='CP(기업어음: 기업의 단기 자금조달)'
        cd_explain='CD(양도성예금증서: 은행의 단기 자금조달)'
        self.assertIn(cp_explain,m)
        self.assertIn(cd_explain,m)
        self.assertEqual(m.count(cp_explain),1)
        self.assertEqual(m.count(cd_explain),1)
        self.assertLess(m.index('① 핵심 신용스프레드'),m.index(cp_explain))
        self.assertLess(m.index(cp_explain),m.index(cd_explain))
        self.assertLess(m.index(cd_explain),m.index('CP–CD <b>47.0bp</b>'))
        self.assertLess(len(m),c.MAX_MESSAGE_CHARS)

    def test_direction_not_confused_with_absolute_rate(self):
        self.assertEqual(c.direction(1.99)[0],'보합')
        self.assertEqual(c.direction(-1.99)[0],'보합')
        self.assertEqual(c.direction(2)[0],'악화')
        self.assertEqual(c.direction(-2)[0],'개선')
        self.assertEqual(c.direction_overview(sample(20,60))['summary'],'단기 보합→ · 회사채 보합→')
        rows=sample(20,60)
        rows[-1]['cp_cd']=15
        rows[-1]['credit']=55
        self.assertEqual(c.direction_overview(rows)['summary'],'단기 개선↓ · 회사채 개선↓')

    def test_message_hysteresis_clearly_separates_observed_and_notified(self):
        rows=sample(80,95)
        # 실측은 관찰 단계로 낮아졌지만 3영업일 회복 확인에는 아직 이르다.
        for i,(cp,aa) in zip((2,1),((20,60),(35,65))):
            rows[-i].update(cp_cd=cp,credit=aa,rank=c.level(cp,aa),
                            rates={"cp":3+cp/100,"cd":3,"corp":3.5+aa/100,"gov":3.5})
        action=c.decide(rows,{"notified_rank":3})
        self.assertEqual(action["rank"],3)
        self.assertEqual(action["transition"],"유지")
        msg=c.render(rows,action,dt.datetime(2026,10,19,19,tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertIn("실측 관찰 / 경보 악화(회복 연속 확인 중)",msg)
        self.assertIn("현재 2/3",msg)

    def test_number_display_no_negative_zero(self):
        self.assertEqual(c.signed(-0.001),'+0.0')
        self.assertEqual(c.signed(0),'+0.0')
        self.assertEqual(c.signed(-1.234),'-1.2')
        self.assertEqual(c.telegram_plaintext('<b>알림</b> <b>47bp</b>'),'알림 47bp')
        with self.assertRaises(ValueError):
            c.telegram_plaintext('<script>broken</script>')

    def test_sample_is_explicit_not_a_live_alert(self):
        rows=sample(47,68.3)
        action=c.decide(rows,{'notified_rank':1})
        msg=c.render(rows,action,dt.datetime(2026,10,19,20,tzinfo=ZoneInfo('Asia/Seoul')),sample=True)
        self.assertIn('[양식 검증 · 새 경보가 아닙니다]',msg)
        self.assertIn('단계',msg)
        self.assertIn('방향:',msg)
        self.assertLess(len(msg),c.MAX_MESSAGE_CHARS)

    def test_daily_reversal_not_mistaken_for_five_day_trend(self):
        rows=sample(36,60)
        rows[-2].update(cp_cd=50,rates={"cp":3.50,"cd":3,"corp":4.10,"gov":3.5})
        rows[-1].update(cp_cd=47,rates={"cp":3.47,"cd":3,"corp":4.10,"gov":3.5},rank=1)
        msg=c.render(rows,c.decide(rows,{}),
                     dt.datetime(2026,10,19,20,4,tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertIn("5영업일 방향: 단기 악화↑ · 회사채 보합→",msg)
        self.assertIn("전일: CP–CD -3.0bp 축소 / AA-금리차 +0.0bp 불변",msg)
        self.assertLessEqual(len(msg.splitlines()),28)
        self.assertIn("5영업일 방향",msg.splitlines()[1])
        self.assertIn("전일:",msg.splitlines()[2])

    def test_mixed_official_publication_dates_are_never_silently_used(self):
        base={f'202610{d:02d}':3.0 for d in range(8,20) if dt.date(2026,10,d).weekday()<5}
        series={k:dict(base) for k in c.KINDS}
        series['cp']['20261020']=3.2
        with self.assertRaisesRegex(ValueError,"최신 공식 기준일 불일치"):
            c.aligned(series,dt.datetime(2026,10,20,20,tzinfo=ZoneInfo('Asia/Seoul')))

    def test_successful_source_health_snapshot_is_deterministic(self):
        rows=sample(52,68.7)
        now=dt.datetime(2026,10,27,7,37,tzinfo=ZoneInfo("Asia/Seoul"))
        act=c.decide(rows,{"notified_rank":2})
        codes={"cp":"010503000","cd":"010502000","corp":"010300000","gov":"010200000"}
        a=c.verified_health_snapshot(rows,codes,now,act)
        b=c.verified_health_snapshot(rows,codes,now+dt.timedelta(hours=1),act)
        self.assertEqual(a["fingerprint"],b["fingerprint"])
        self.assertEqual(a["official_date"],rows[-1]["date"])
        self.assertEqual(a["rate_values"]["cp_cd_bp"],52)
        self.assertEqual(a["rate_values"]["aa_spread_bp"],68.7)
        self.assertEqual(a["alert_rank"],2)
        self.assertNotEqual(a["verified_at_kst"],b["verified_at_kst"])

    def test_weekday_close_does_not_reuse_yesterday_as_today(self):
        end=dt.date(2026,10,23)
        days=[end-dt.timedelta(days=i) for i in range(15,-1,-1)
              if (end-dt.timedelta(days=i)).weekday()<5]
        series={kind:{day.strftime("%Y%m%d"):3.0 for day in days} for kind in c.KINDS}
        with self.assertRaisesRegex(ValueError,"공식 금리 기준일 지연"):
            c.aligned(series,dt.datetime(2026,10,26,19,0,tzinfo=ZoneInfo("Asia/Seoul")))
        good=c.aligned(series,dt.datetime(2026,10,26,7,37,tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertEqual(good[-1]["date"],"20261023")

    def test_authorization_probe_does_not_send_a_message(self):
        calls=[]
        def fake(url,params=None):
            action=url.rsplit("/",1)[-1]
            calls.append(action)
            if action=="getMe":
                return {"ok":True,"result":{"username":c.BOT}}
            if action=="getChat":
                self.assertEqual(params,{"chat_id":"-1234567"})
                return {"ok":True,"result":{"id":-1234567}}
            raise AssertionError("Unauthorized Telegram API operation: "+action)
        with patch.dict(c.os.environ,{"TELEGRAM_BOT_TOKEN":"TESTONLY","TELEGRAM_CHAT_ID":"-1234567"}):
            with patch.object(c,"telegram",side_effect=fake):
                c.verify_telegram_route()
        self.assertEqual(calls,["getMe","getChat"])

    def test_auth_probe_rejects_wrong_bot_or_wrong_chat(self):
        with patch.dict(c.os.environ,{"TELEGRAM_BOT_TOKEN":"TESTONLY","TELEGRAM_CHAT_ID":"12345"}):
            with patch.object(c,"telegram",return_value={"ok":True,"result":{"username":"bad_bot"}}):
                with self.assertRaisesRegex(RuntimeError,"예상 텔레그램 봇"):
                    c.verify_telegram_route()
            seq=[{"ok":True,"result":{"username":c.BOT}},
                 {"ok":True,"result":{"id":67890}}]
            with patch.object(c,"telegram",side_effect=seq):
                with self.assertRaisesRegex(RuntimeError,"대화방 ID 불일치"):
                    c.verify_telegram_route()

    def test_utc_cron_mapping_and_health_persistence_declared(self):
        path=pathlib.Path(__file__).parents[1]/".github/workflows/korea-credit-spread-telegram-watch.yml"
        workflow=path.read_text(encoding="utf-8")
        self.assertIn('cron: "10 9-12 * * 1-5"',workflow)
        self.assertIn('cron: "37 13 * * 1-5"',workflow)
        self.assertIn('cron: "37 22 * * 1-5"',workflow)
        self.assertNotIn('timezone: "Asia/Seoul"',workflow)
        self.assertIn("credit_spread_watch_health_pending.json",workflow)
        self.assertIn("--probe",workflow)
        self.assertIn("DRY_RUN != 'true'",workflow)

if __name__=='__main__':unittest.main()
