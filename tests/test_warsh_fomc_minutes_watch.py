"""FOMC 의사록: 원문 근거·통계 표기·미래 회의·중복 송출 회귀검증."""
import html
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import warsh_fomc_minutes_watch as watch

MINUTES = """Minutes of the Federal Open Market Committee September 15–16, 2026
Developments in Financial Markets and Open Market Operations
Nominal yields increased around 35 basis points across the 2- to 10-year segment
of the yield curve. Market commentary pointed to geopolitical developments and
competition for capital from heavy private debt issuance to finance the development
of artificial intelligence (AI) infrastructure as also contributing to higher term premiums
and Treasury yields.
Staff Review of the Economic Situation
Participants' Views on Current Conditions and the Economic Outlook
Participants noted that inflation remained elevated and that they had not seen
sufficient progress on lowering inflation in recent months.
They noted that ongoing geopolitical developments, which had pushed up prices for crude
oil and refined fuel products, and surging AI-related investments were contributing
to inflation pressures.
Several participants observed that the rate of price increases in core services
excluding housing remained elevated.
Several participants observed that the rate of price increases in the core goods
category also remained elevated, as effects of the AI buildout appeared to increase
while the effects of tariff increases waned.
A few participants noted that certain items in the PCE price index—software and portfolio
management fees in particular—had made relatively large contributions to recent
PCE inflation readings, and that those contributions would likely be reduced somewhat
with the upcoming changes to the BEA's methodology.
A few participants observed that the 3-month change measure of core PCE inflation
showed a material decline since the start of the year but cautioned that this measure
is more volatile than the 12-month change measure and has shown a strong tendency
to understate inflation in the second half of the year.
Participants judged that market- and survey-based indicators of medium- and longer-term
inflation expectations remained at levels consistent with the Committee's 2 percent objective.
Participants generally assessed inflation risk as skewed to the upside;
some participants remarked that those risks had become more skewed to the upside
in recent months.
Some participants expressed concerns that, after more than five years of inflation
above 2 percent, elevated inflation rates could begin to affect inflation expectations
and wage- and price-setting decisions.
Participants judged that labor market conditions were stable and generally viewed
the labor market as close to maximum employment.
A majority of participants assessed that the labor market had strengthened a bit
recently, pointing to developments such as employment gains modestly outpacing labor
force growth.
Several participants noted that dynamism in the labor market was unusually low,
as reflected by low rates of hiring and layoffs, a low job-finding rate, and a
persistently elevated long-term unemployment rate.
Some participants observed that strong demand for skilled workers in sectors related
to the ongoing AI buildout had been driving strong wage gains for these workers.
However, some participants also commented that aggregate wage growth was moderate.
Participants generally viewed the upside and downside risks to the labor market
as broadly balanced.
Many participants commented that, despite the recent rise in longer-term Treasury yields,
financial conditions appeared to be supportive of economic growth.
A few participants commented that housing was a sector in which financial conditions
did not appear supportive of activity, with mortgage rates remaining at elevated levels.
Participants generally assessed that economic activity was expanding at a solid pace.
Robust business investment and resilient consumer spending had supported economic activity.
Several participants commented that the underlying momentum in the economy appeared
to have increased.
Several participants commented that the scale and pace of the AI buildout had
continued to surprise to the upside.
Several participants observed that stock market gains had provided support to
consumer spending, particularly among higher-income households.
Several participants noted, however, that low- and moderate-income households faced
strains, with higher energy prices weighing disproportionately on their real disposable income.
Participants generally judged that AI-related investments would likely contribute to
stronger gains in productivity and potential output in the coming years but they
noted that there was substantial uncertainty over the magnitude or timing of the effects.
A few participants flagged emerging concerns regarding potential repercussions
associated with rapid adoption of AI, including cybersecurity.
In their consideration of monetary policy at this meeting, all participants
supported raising the target range for the federal funds rate 1/4 percentage point.
Almost all participants assessed that, while inflation risks were tilted to the upside,
risks to the labor market had diminished and were now broadly balanced.
Many participants emphasized that a higher path for the target range would be prudent
on risk-management grounds, providing insurance against inflation remaining
persistently above target.
A number of participants viewed a higher path for the target range as necessary
based on their modal outlooks rather than on risk-management grounds.
A couple of participants remarked on having increased their estimate of the neutral
federal funds rate and thus their view of the appropriate setting.
Several participants stated that they viewed the current policy rate as not restrictive
or only mildly restrictive.
With regard to the outlook for monetary policy beyond the current meeting, most
participants assessed that another increase in the target range for the federal
funds rate would likely be appropriate by year end.
Regarding balance sheet policy, a few participants observed that Treasury markets
had been functioning smoothly but noted the importance of planning for market stress.
They suggested strengthening the Federal Reserve's strategy, communications, and tools
for addressing market dysfunction, should it occur, while limiting the Federal Reserve's
footprint in the Treasury market.
Committee Policy Actions
All members agreed to raise the target range for the federal funds rate and reaffirmed
the FOMC's policy of maintaining ample reserves in the banking system.
Roll over at auction all principal payments from the Federal Reserve's holdings
of Treasury securities. Reinvest all principal payments from the Federal Reserve's
holdings of agency securities into Treasury bills.
At the conclusion, the Committee approved the following statement for release by a 12–0 vote.
"""


class TestMinutes(unittest.TestCase):
    def test_calendar_release_requires_explicit_posting(self):
        cal = '<a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a> (Released October 07, 2026)'
        self.assertEqual(watch.official_release_date(cal,'2026-09-16'),'2026-10-07')
        self.assertIsNone(watch.official_release_date(
            '<a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a>',
            '2026-09-16'))

    def test_participant_categories_are_anchored_and_complete(self):
        sig = watch.extract_signals(MINUTES,'2026-09-16')
        for name in ('all_support','unanimous_vote','most_yearend','many_risk','number_modal',
                     'few_treasury','treasury_stress','strengthen_tools','limit_footprint',
                     'core_services_ex_housing','ai_core_goods','pce_3m_warning','pce_methodology',
                     'inflation_upside_more','employment_majority','employment_low_dynamism',
                     'employment_low_hire_layoff_find','employment_ai_skilled_wages',
                     'employment_moderate_wages','employment_outlook_balanced',
                     'growth_solid','financial_supportive','housing_exception',
                     'consumer_high_income','consumer_low_income','productivity_future_uncertain',
                     'ai_private_debt_term_premium','yields_2y10y_35bp'):
            self.assertTrue(sig[name],name)

    def test_missing_most_is_not_silently_substituted(self):
        mutated=MINUTES.replace('most\nparticipants assessed that another increase',
                                'several\nparticipants assessed that another increase')
        with self.assertRaisesRegex(RuntimeError,'필수 근거'):
            watch.extract_signals(mutated,'2026-09-16')

    def test_full_alert_is_korean_and_fits_telegram(self):
        sig=watch.extract_signals(MINUTES,'2026-09-16')
        with patch.object(watch,'load',return_value={}):
            msg=watch.message('2026-09-16',watch.minutes_url('2026-09-16'),
                              'https://www.federalreserve.gov/newsevents/pressreleases/monetary20261007a.htm',
                              '2026-10-07',sig,upgraded=True)
        for txt in ('연말 경로','대차대조표','물가 · 공급과 수요','고용 · 전체와 AI',
                    '성장 · AI','저·중소득층','시장보고','근원 PCE','2~10년',
                    '사이버보안','10월 27~28일','FOMC 표결'):
            self.assertIn(txt,msg)
        self.assertNotIn('Many participants',msg)
        self.assertNotIn('A majority of participants',msg)
        self.assertLessEqual(len(re.sub(r'<[^>]+>', '',html.unescape(msg))),3900)

    def test_future_meeting_is_not_labeled_as_september(self):
        sig={key:False for key in watch.extract_signals(MINUTES,'2026-10-28')}
        with patch.object(watch,'load',return_value={}):
            msg=watch.message('2026-10-28','https://example.com/minutes',
                              'https://example.com/press','2026-11-18',sig)
        self.assertNotIn('10월 27~28일 FOMC',msg)
        self.assertNotIn('3.75~4.00%',msg)
        self.assertIn('다음 FOMC',msg)

    def test_format_upgrade_only_once(self):
        today = datetime.now(watch.ET)
        rel=today.date().isoformat()
        cal = ('<a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a> '
               '(Released '+today.strftime('%B %d, %Y')+')')
        key='2026-09-16|'+rel
        state={'last_minutes_url':watch.minutes_url('2026-09-16'),
               'last_sent_key':key,'sent':True,'last_sent_format_version':2,
               'message_id':64,'delivery_status':'confirmed'}
        def load(path):
            return dict(state) if path==watch.STATE else {}
        def save(payload):
            state.clear();state.update(payload)
        def fetch(url,timeout=18):
            return (cal if url==watch.FED_CAL else MINUTES),url
        with patch.object(watch,'load',side_effect=load), \
             patch.object(watch,'save',side_effect=save), \
             patch.object(watch,'fetch',side_effect=fetch), \
             patch.object(watch,'latest_statement_date',return_value='2026-09-16'), \
             patch.object(watch,'verify_official_publication',return_value=(MINUTES,'https://example.com/press')), \
             patch.object(watch,'send',return_value=101) as sender:
            watch.main()
            watch.main()
        self.assertEqual(sender.call_count,1)
        self.assertEqual(state['message_id'],101)
        self.assertEqual(state['previous_message_id'],64)
        self.assertEqual(state['last_sent_format_version'],3)
        self.assertIsNone(state['pending_key'])
        self.assertEqual(state['delivery_status'],'confirmed')

    def test_failed_or_ambiguous_delivery_does_not_repeat(self):
        today=datetime.now(watch.ET)
        rel=today.date().isoformat()
        cal='<a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a> (Released '+today.strftime('%B %d, %Y')+')'
        key='2026-09-16|'+rel
        state={'last_sent_key':key,'sent':False,'pending_key':key,
               'delivery_status':'sending'}
        with patch.object(watch,'load',return_value=state), \
             patch.object(watch,'fetch',return_value=(cal,'https://example.com/page')), \
             patch.object(watch,'latest_statement_date',return_value='2026-09-16'), \
             patch.object(watch,'verify_official_publication',return_value=(MINUTES,'https://example.com/press')), \
             patch.object(watch,'send') as sender:
            with self.assertRaisesRegex(RuntimeError,'재전송 중단'):
                watch.main()
            sender.assert_not_called()


if __name__ == '__main__':
    unittest.main()
