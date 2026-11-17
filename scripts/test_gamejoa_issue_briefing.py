#!/usr/bin/env python3
import base64
import datetime as dt
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import gamejoa_issue_briefing as b
import gamejoa_market_materiality as materiality


def now(value):
    return dt.datetime.fromisoformat(value).astimezone(b.KST)


class IssueBriefingTests(unittest.TestCase):
    def test_nonoverlapping_windows(self):
        morning = b.briefing_window("preopen", now("2026-11-17T06:35:00+09:00"))
        self.assertEqual(tuple(x.isoformat() for x in morning),
                         ("2026-11-16T16:30:00+09:00", "2026-11-17T06:30:00+09:00"))
        close = b.briefing_window("close", now("2026-11-17T16:30:00+09:00"))
        self.assertEqual(close[0], morning[1])
        self.assertEqual(close[1].isoformat(), "2026-11-17T16:30:00+09:00")
        next_morning = b.briefing_window("preopen", now("2026-11-18T06:30:00+09:00"))
        self.assertEqual(close[1], next_morning[0])
        self.assertTrue(b.in_window("2026-11-17T16:00:00+09:00", *close))
        self.assertFalse(b.in_window("2026-11-17T16:00:00+09:00", *next_morning))
        self.assertFalse(b.in_window("2026-11-17T06:30:00+09:00", *morning))
        self.assertTrue(b.in_window("2026-11-17T06:30:00+09:00", *close))
        self.assertFalse(b.in_window("2026-11-17T06:31:00", *close))

    def test_unique_sample_removes_tracking_but_not_article_ids(self):
        start, end = b.briefing_window("preopen", now("2026-11-17T06:30:00+09:00"))
        rows = [
            {"link": "https://x.test/news/1?utm_source=a&id=1", "published": "2026-11-16T17:00:00+09:00"},
            {"link": "https://x.test/news/1?id=1&utm_medium=b", "published": "2026-11-16T17:00:00+09:00", "body_verified": True},
            {"link": "https://x.test/news/1?id=2", "published": "2026-11-16T17:01:00+09:00"},
            {"link": "https://x.test/news/3", "published": "2026-11-17T06:30:00+09:00"},
        ]
        sample = b.unique_sample(rows, start, end)
        self.assertEqual(len(sample), 2)
        self.assertTrue(sample[0]["body_verified"])

    def test_krx_list_validation_and_ambiguous_names(self):
        rows = ["<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th></tr>"]
        rows += [f"<tr><td>회사{i}</td><td>코스닥</td><td>{i:06d}</td></tr>" for i in range(101)]
        rows += ["<tr><td>삼성전자</td><td>유가</td><td>005930</td></tr>",
                 "<tr><td>회사1</td><td>코스닥</td><td>111111</td></tr></table>"]
        result = b.parse_krx_list("".join(rows).encode("euc-kr"))
        self.assertEqual(result["삼성전자"], "005930")
        self.assertNotIn("회사1", result)
        with self.assertRaises(ValueError):
            b.parse_krx_list(b"<html>no list</html>")

    def test_quote_does_not_treat_intraday_as_close(self):
        xml = ('<protocol><chartdata symbol="005930" name="삼성전자">'
               '<item data="20261113|1|1|1|209000|5"/>'
               '<item data="20261116|1|1|1|195000|5"/>'
               '<item data="20261117|1|1|1|190000|5"/>'
               '</chartdata></protocol>').encode()
        result = b.parse_daily_quote(xml, "005930", "삼성전자", now("2026-11-17T06:30:00+09:00"))
        self.assertEqual(result["date"], "2026-11-16")
        self.assertEqual(result["previous_close"], "209000")
        self.assertEqual(result["change_pct"], "-6.70")
        close = b.parse_daily_quote(xml, "005930", "삼성전자", now("2026-11-17T16:30:00+09:00"))
        self.assertEqual(close["date"], "2026-11-17")
        xml_euc = ('<?xml version="1.0" encoding="EUC-KR"?>' + xml.decode()).encode("euc-kr")
        self.assertEqual(b.parse_daily_quote(xml_euc, "005930", "삼성전자", now("2026-11-17T06:30:00+09:00"))["date"], "2026-11-16")
        with self.assertRaises(ValueError):
            b.parse_daily_quote(xml, "000660", "삼성전자", now("2026-11-17T16:30:00+09:00"))
        with self.assertRaises(ValueError):
            b.parse_daily_quote(xml, "005930", "다른회사", now("2026-11-17T16:30:00+09:00"))
        with self.assertRaises(ValueError):
            b.parse_daily_quote(xml.replace(b"195000|5", b"195000|0"), "005930", "삼성전자", now("2026-11-17T06:30:00+09:00"))

    def test_company_names_are_not_substrings(self):
        listing = {"한화": "000880", "한화오션": "042660", "삼성전자": "005930"}
        self.assertEqual(b.company_mentions("한화오션이 삼성전자를 제치고 수주했다.", listing),
                         [("한화오션", "042660"), ("삼성전자", "005930")])
        self.assertEqual(b.company_mentions("대한화학 관련", listing), [])
        self.assertEqual(b.company_mentions("지슨은 장비를 만든다.", {"지슨": "123456"}), [])
        self.assertEqual(b.company_mentions("지슨 주가가 상승했다.", {"지슨": "123456"}), [("지슨", "123456")])

    def test_social_theme_requires_verified_direct_market_sentence(self):
        listing = {"지슨": "123456"}
        row = {"title": "AI 커닝 관련주 지슨 주가 상승", "body_verified": True,
               "source_body": "AI 커닝 관련주 지슨 주가가 20% 상승했다. 정부도 대책을 논의했다."}
        self.assertEqual(b.ai_cheating_market_observation(row, listing)["core"], "AI 커닝 관련주 지슨 주가가 20% 상승했다.")
        self.assertFalse(b.ai_cheating_market_observation({**row, "body_verified": False}, listing))
        self.assertFalse(b.ai_cheating_market_observation({**row, "source_body": "AI 커닝이 확산했다. 지슨은 제품을 만든다."}, listing))
        self.assertFalse(b.ai_cheating_market_observation({**row, "title": "AI 박물관 체험"}, listing))
        adjacent = {"title": "AI 커닝 충격에 보안·카메라주 솟구쳐", "body_verified": True,
                    "source_body": "나무가와 지슨 등 보안 관련주가 상한가를 기록했다. 최근 생성형 인공지능(AI)을 이용한 부정행위를 시인했다. 다른기업은 별도의 실적 개선으로 상한가를 기록했다."}
        observation = b.ai_cheating_market_observation(adjacent, {"나무가": "190510", "지슨": "123456", "다른기업": "111111"})
        self.assertEqual(observation["core"], "최근 생성형 인공지능(AI)을 이용한 부정행위를 시인했다.")
        self.assertEqual(observation["companies"], [("나무가", "190510"), ("지슨", "123456")])
        unrelated = {**adjacent, "source_body": "최근 생성형 인공지능(AI)을 이용한 부정행위를 시인했다. 다른기업은 별도의 실적 개선으로 상한가를 기록했다."}
        self.assertFalse(b.ai_cheating_market_observation(unrelated, {"다른기업": "111111"}))

    def test_social_theme_source_alignment_with_separate_stock_sentence(self):
        import gamejoa_preopen_news_radar_fda_quality_runner as pipeline
        runner = pipeline.runner
        title = "'AI 커닝', 증시도 흔들었다…AI안경·카메라株 뛰고 보안株는 희비 엇갈려"
        body = ("올해 세무사 시험 수석 합격자의 인공지능(AI) 부정행위 자백으로 국내 증시에서 관련 테마주가 장중 일제히 들썩였다. "
                "정부는 시험장 보안 대책에 착수했다. "
                "전파 탐지 전문기업 지슨은 전 거래일 대비 29.97% 올라 상한가를 기록했다.")
        row = {"title": title, "source_title": title, "source_body": body, "body_verified": True}
        observation = b.ai_cheating_market_observation(row, {"지슨": "446840"})
        self.assertEqual(observation["companies"], [("지슨", "446840")])
        item = {"source_title": title, "news": title, "source_body": body, "source_abstract": body,
                "telegram_core_fact": observation["core"], "policy_plain_summary": observation["core"],
                "body_verified": True, "korean_business_news": True, "publisher": "뉴시스",
                "link": "https://www.newsis.com/view/NISX20261116_0003869829"}
        self.assertTrue(b.social_observation_verified(item, observation, runner), runner.source_core_fact_errors(item))
        self.assertFalse(b.social_observation_verified(item, {**observation, "company_evidence": "지슨이 급등했다."}, runner))
        stamp = now("2026-11-16T16:30:00+09:00")
        start, end = b.briefing_window("close", stamp)
        row.update(link=item["link"], publisher="뉴시스", published=now("2026-11-16T16:02:00+09:00"))
        telegram = SimpleNamespace(filter_previously_seen_alerts=lambda alerts, when, lane: (alerts, []))
        groups = b.add_social_evidence([], [row], {"지슨": "446840"}, start, end, stamp, runner, telegram)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["explicit_companies"], [("지슨", "446840")])

    def test_relevant_sample_coverage_can_affect_order_without_promoting_unverified_story(self):
        single = {"rank": 4, "priority": 3, "stats": {"articles": 1, "late": 1}}
        repeated = {"rank": 3, "priority": 2, "stats": {"articles": 5, "late": 3}}
        self.assertGreater(b.group_sort_key(repeated), b.group_sort_key(single))

    def test_issue_statistics_are_sample_counts_not_social_metrics(self):
        start, end = b.briefing_window("preopen", now("2026-11-17T06:30:00+09:00"))
        sample = [{"title": "AI 커닝 확산", "publisher": "A", "published": "2026-11-16T17:00:00+09:00"},
                  {"title": "인공지능 부정행위 대책", "publisher": "B", "published": "2026-11-17T04:00:00+09:00"},
                  {"title": "전기차 판매", "publisher": "C", "published": "2026-11-17T04:00:00+09:00"}]
        self.assertEqual(b.topic_statistics("AI 커닝 수능 대책", sample, start, end, materiality),
                         {"articles": 2, "publishers": 2, "early": 1, "late": 1})

    def test_theme_dedup_does_not_include_unverified_or_non_korean_content(self):
        stamp = now("2026-11-17T06:30:00+09:00")
        start, end = b.briefing_window("preopen", stamp)
        def alert(title, core, url, verified=True):
            return {"source_title": title, "news": title, "telegram_core_fact": core,
                    "body_verified": verified, "link": url,
                    "market_materiality": {"priority": 3, "news_value_rank": 4}}
        first = alert("AI 커닝 관련주 지슨 주가 상승", "AI 커닝 관련주 지슨이 상승했다.", "https://x.test/1")
        repeat = alert("인공지능 부정행위 관련주 급등", "인공지능 부정행위 관련주가 올랐다.", "https://x.test/2")
        unverified = alert("삼성 실적 발표", "삼성이 실적을 발표했다.", "https://x.test/3", False)
        english = alert("Company announces results", "Revenue increased.", "https://x.test/4")
        sample = [{"title": first["source_title"], "publisher": "A", "published": "2026-11-16T17:00:00+09:00"},
                  {"title": repeat["source_title"], "publisher": "B", "published": "2026-11-17T05:00:00+09:00"}]
        groups = b.group_alerts([first, repeat, unverified, english], sample, start, end, materiality)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["stats"]["articles"], 2)
        recap = b.digest_groups([], [first, repeat], sample, start, end, materiality)
        self.assertEqual(len(recap), 1)
        self.assertTrue(recap[0]["previously_sent"])
        self.assertEqual(b.digest_groups([], [first], sample[:1], start, end, materiality), [])
        fresh = b.digest_groups([first], [repeat], sample, start, end, materiality)
        self.assertEqual(len(fresh), 1)
        self.assertNotIn("previously_sent", fresh[0])

    def test_actual_acquisition_headline_does_not_use_revenue_forecast_as_core(self):
        class Runner:
            @staticmethod
            def korean_title_core_aligned(title, core): return "에게티스" in core and "인수" in core
            @staticmethod
            def clean_article_summary_text(value): return value.strip()
            @staticmethod
            def core_sentence_is_complete(value): return value.endswith(".")
            @staticmethod
            def core_has_ui_garbage(value): return False
        alert = {
            "source_title": "ANI 파마슈티컬스, 에게티스 5억6000만 달러 인수..매출 가이던스 유지",
            "telegram_core_fact": "증권가 컨센서스에 따르면 2026년 매출은 10억9791만 달러로 증가할 전망이다.",
            "source_body": "매출이 늘었다. 회사는 에게티스를 약 5억6000만 달러에 인수하는 공개매수 조건을 발표했다.",
        }
        self.assertFalse(b.action_core_aligned(alert["source_title"], alert["telegram_core_fact"], Runner()))
        self.assertEqual(b.headline_backed_core(alert, Runner()),
                         "회사는 에게티스를 약 5억6000만 달러에 인수하는 공개매수 조건을 발표했다.")
        altered = {**alert, "source_body": "에게티스 인수 가이던스는 발표하지 않았다."}
        self.assertEqual(b.headline_backed_core(altered, Runner()), "")
        fabricated = {**alert, "telegram_core_fact": "에게티스를 5억6000만 달러에 인수 완료했다.",
                      "source_body": "에게티스 인수 제안만 검토했다."}
        self.assertEqual(b.headline_backed_core(fabricated, Runner()), "")

    def test_same_us_revenue_report_is_one_topic_despite_different_headline_figures(self):
        import gamejoa_market_materiality as actual_materiality
        start, end = b.briefing_window("preopen", now("2026-11-17T06:30:00+09:00"))
        title_a = "SK하이닉스, 美 매출 1년 새 102조원 증가…엔비디아 추정 매출 35조"
        title_b = "SK하이닉스, 美 매출 148조원…전체 62.5% 차지"
        core_a = "SK하이닉스의 올해 1~3분기 미국 매출이 지난해 같은 기간보다 102조원 이상 증가하며 전체 매출의 62.5%를 차지했다."
        core_b = "SK하이닉스가 공시한 분기보고서에 따르면 올해 1~3분기 누적 지역별 매출 합계 236조5105억원 가운데 미국 매출은 147조7392억원으로 전체의 62.5%를 차지했다."
        def row(title, core, link, publisher):
            return {"source_title": title, "title": title, "telegram_core_fact": core, "source_body": core,
                    "body_verified": True, "link": link, "publisher": publisher,
                    "published": "2026-11-16T19:00:00+09:00", "market_materiality": {"priority": 3, "news_value_rank": 4}}
        sample = [row(title_a, core_a, "https://a.test/1", "A"), row(title_b, core_b, "https://b.test/2", "B")]
        groups = b.group_alerts(sample, sample, start, end, actual_materiality)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["stats"]["articles"], 2)
        self.assertEqual(len(b.digest_groups(sample[:1], sample[1:], sample, start, end, actual_materiality)), 1)
        self.assertFalse(b.same_regional_result("SK하이닉스 美 2분기 매출 62.5%", "SK하이닉스 美 3분기 매출 62.5%", "", ""))
        self.assertFalse(b.same_regional_result("SK하이닉스 中 매출 62.5%", title_b, "", core_b))
        self.assertFalse(b.same_regional_result("삼성전자 美 매출 62.5%", title_b, "", core_b))

    def test_acquisition_guard_with_real_radar_alignment(self):
        import gamejoa_preopen_news_radar_fda_quality_runner as pipeline
        runner = pipeline.runner
        title = "ANI 파마슈티컬스, 에게티스 5억6000만 달러 인수..매출 가이던스 유지"
        actual = "ANI 파마슈티컬스가 에게티스를 약 5억6000만 달러에 인수하는 공개매수 조건을 발표했다."
        wrong = "증권가 컨센서스에 따르면 매출액은 10억9791만 달러로 증가할 전망이다."
        item = {"source_title": title, "news": title, "source_body": actual + " " + wrong,
                "source_abstract": actual + " " + wrong, "telegram_core_fact": wrong,
                "policy_plain_summary": wrong, "body_verified": True, "korean_business_news": True,
                "publisher": "매일경제", "link": "https://www.mk.co.kr/news/stock/12210416"}
        fixed = b.headline_backed_core(item, runner)
        self.assertEqual(fixed, actual)
        item.update(telegram_core_fact=fixed, policy_plain_summary=fixed)
        # The legacy guard still interprets the secondary guidance as focus.
        # In that disagreement the briefing must suppress, not weaken the guard.
        self.assertFalse(runner.source_output_aligned(item))

    def test_quarterly_headline_rejects_annual_consensus_and_tiny_foreign_results(self):
        import gamejoa_preopen_news_radar_fda_quality_runner as pipeline
        runner, telegram = pipeline.runner, pipeline.telegram
        title = "포엣 테크놀러지스, 3분기 매출액 103만달러..전년비 244% 증가"
        wrong = "증권가 컨센서스에 따르면 2026년 연간 매출은 327만6000달러로 증가할 전망이다."
        actual = "포엣 테크놀러지스는 3분기 매출액이 103만달러로 전년비 244% 증가했다고 발표했다."
        alert = {"source_title": title, "news": title, "source_body": actual + " " + wrong,
                 "telegram_core_fact": wrong, "body_verified": True}
        self.assertFalse(b.action_core_aligned(title, wrong, runner))
        self.assertEqual(b.headline_backed_core(alert, runner), actual)
        self.assertTrue(b.low_materiality_foreign_earnings(alert, {}, runner, telegram))
        major = {**alert, "source_title": "엔비디아 3분기 매출 103만달러 증가"}
        self.assertFalse(b.low_materiality_foreign_earnings(major, {}, runner, telegram))

    def test_source_sentence_with_subject_preferred_to_subjectless_fragment(self):
        import gamejoa_preopen_news_radar_fda_quality_runner as pipeline
        runner = pipeline.runner
        title = "두나무마저 적자 전환…코인 거래소들 '버티기' 한계"
        actual = "16일 금융감독원 전자공시시스템에 따르면 업비트를 운영하는 두나무는 올해 3분기 연결 기준 매출 1517억원, 영업손실 35억원을 기록했다."
        fragment = "당기순손실도 186억원을 기록하며 적자 전환했다."
        alert = {"source_title": title, "telegram_core_fact": fragment, "source_body": actual + " " + fragment}
        self.assertEqual(b.headline_backed_core(alert, runner), actual)
        self.assertEqual(b.headline_backed_core({**alert, "source_body": fragment}, runner), fragment)

    def test_all_foreign_amount_occurrences_are_converted_without_nested_brackets(self):
        import gamejoa_preopen_news_radar_fda_quality_runner as pipeline
        runner = pipeline.runner
        conversion = {"amounts": [{"original": "100달러", "krw_value": 140000, "krw_text": "14만원"}]}
        self.assertEqual(b.converted_field("100달러와 100달러다.", conversion, runner),
                         "100달러(약 14만원)와 100달러(약 14만원)다.")
        self.assertIsNone(b.converted_field("100달러와 200달러다.", conversion, runner))
        self.assertIsNone(b.converted_field("가격은 (약 100달러)다.", conversion, runner))
        self.assertEqual(runner.extract_foreign_amounts(b.normalize_currency_labels("56억 스웨덴크로나"))[0]["code"], "SEK")

    def test_ledger_compare_and_swap_prevents_second_send_reservation(self):
        class FakeAPI:
            def __init__(self):
                self.doc, self.sha = None, ""
                self.conflict_once = True
            def __call__(self, method, url, token, payload=None):
                if method == "GET":
                    if self.doc is None:
                        return 404, {}
                    return 200, {"sha": self.sha, "content": base64.b64encode(json.dumps(self.doc).encode()).decode()}
                if self.conflict_once:
                    self.conflict_once = False
                    return 409, {}
                if self.doc is not None and payload.get("sha") != self.sha:
                    return 409, {}
                self.doc = json.loads(base64.b64decode(payload["content"]).decode())
                self.sha = str(int(self.sha or 0) + 1)
                return 201, {}
        api = FakeAPI()
        ledger = b.GitHubLedger("owner/repo", "token", api)
        with patch.object(b.time, "sleep"):
            self.assertTrue(ledger.update("2026-11-17:preopen", "1", "reserved"))
            self.assertTrue(ledger.has_slot("2026-11-17:preopen"))
            self.assertFalse(ledger.has_slot("2026-11-17:close"))
            self.assertFalse(ledger.update("2026-11-17:preopen", "2", "reserved"))
            with self.assertRaises(RuntimeError):
                ledger.update("2026-11-17:preopen", "2", "sent", 123)
            self.assertTrue(ledger.update("2026-11-17:preopen", "1", "sent", 123))
            self.assertEqual(api.doc["slots"]["2026-11-17:preopen"]["message_id"], 123)

    def test_refresh_history_checks_exact_commit_blob_and_fails_closed(self):
        data = b'{"seen":{},"updated_at_kst":""}'
        digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self, limit): return data[:limit]
        def api(method, url, token, payload=None):
            if "/commits/main" in url:
                return 200, {"sha": "a" * 40}
            return 200, {"sha": digest, "size": len(data)}
        env = {"BRIEFING_REFRESH_SEEN": "true", "GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "token"}
        telegram = SimpleNamespace(SEEN_PATH=None)
        with tempfile.TemporaryDirectory() as temp, patch.object(b, "OUT", Path(temp)), \
                patch.dict(os.environ, env), patch.object(b, "api_json", side_effect=api), \
                patch.object(b.urllib.request, "urlopen", return_value=Response()):
            b.refresh_sent_history(telegram)
            self.assertEqual(telegram.SEEN_PATH.read_bytes(), data)
            with patch.object(b.hashlib, "sha1") as sha:
                sha.return_value.hexdigest.return_value = "b" * 40
                with self.assertRaisesRegex(RuntimeError, "SHA"):
                    b.refresh_sent_history(telegram)

    @unittest.skipUnless(os.getenv("GAMEJOA_GITHUB_INTEGRATION") == "true", "live GitHub check off by default")
    def test_current_github_history_blob_refresh(self):
        telegram = SimpleNamespace(SEEN_PATH=None)
        with tempfile.TemporaryDirectory() as temp, patch.object(b, "OUT", Path(temp)), \
                patch.dict(os.environ, {"BRIEFING_REFRESH_SEEN": "true"}):
            b.refresh_sent_history(telegram)
            self.assertGreater(telegram.SEEN_PATH.stat().st_size, 1000)

    def test_uncertain_telegram_send_is_not_retried(self):
        class Runner:
            @staticmethod
            def telegram_text_and_entities(text): return text, []
            @staticmethod
            def telegram_utf16_length(text): return len(text)
        with patch.object(b.urllib.request, "urlopen", side_effect=TimeoutError()) as request:
            with self.assertRaisesRegex(RuntimeError, "uncertain"):
                b.send_telegram("test", "token", "chat", Runner())
            self.assertEqual(request.call_count, 1)

    def test_dry_run_builds_full_report_without_reservation_or_send(self):
        stamp = now("2026-11-17T06:31:00+09:00")
        row = {"title": "삼성전자 실적 발표", "source_title": "삼성전자 실적 발표",
               "source_body": "삼성전자가 3분기 매출을 발표했다.", "body_verified": True,
               "publisher": "매체A", "link": "https://news.test/article/1",
               "published": now("2026-11-17T06:00:00+09:00")}
        alert = {**row, "news": row["title"], "telegram_core_fact": "삼성전자가 3분기 매출을 발표했다.",
                 "market_materiality": {"priority": 3, "news_value_rank": 4}}
        runner = SimpleNamespace(
            hydrate_korean_business_details=lambda rows, query_time: ["detail attempted=1 verified=1 failed=0 deferred=0"],
            korean_news_search_url=lambda query: "https://search.test/" + query,
            quality_display_alerts=lambda alerts, limit: alerts,
            market_materiality=materiality,
            collect_fx_snapshot=lambda alerts, query_time: {"rates": {}},
            build_alert_fx_conversion=lambda item, snapshot, query_time: {},
            apply_krw_conversions=lambda text, conversion: text,
            telegram_text_and_entities=lambda text: (text, []),
            telegram_utf16_length=lambda text: len(text),
            core_sentence_is_complete=lambda text: True,
            source_output_aligned=lambda item: True,
            korean_title_core_aligned=lambda title, core: True,
            clean_article_summary_text=lambda value: value.strip(),
            core_has_ui_garbage=lambda value: False,
            extract_foreign_amounts=lambda value: [],
        )
        base = SimpleNamespace(kst_now=lambda: stamp, SOURCES=[])
        strict = SimpleNamespace(
            collect_items=lambda query_time: ([row], runner.hydrate_korean_business_details([row], query_time)),
            classify=lambda source, query_time: alert,
        )
        telegram = SimpleNamespace(normalize_alert=lambda item: item,
                                   filter_previously_seen_alerts=lambda alerts, query_time, lane: (alerts, []),
                                   alert_issuer_keys=lambda item: [])
        pipeline = SimpleNamespace(runner=runner, base=base, telegram=telegram,
                                   contract=SimpleNamespace(strict=strict))
        with tempfile.TemporaryDirectory() as temp, patch.object(b, "OUT", Path(temp)), \
                patch.dict(sys.modules, {"gamejoa_preopen_news_radar_fda_quality_runner": pipeline}), \
                patch.dict(os.environ, {"BRIEFING_SLOT": "preopen", "TELEGRAM_DRY_RUN": "true", "BRIEFING_REFRESH_SEEN": "false"}), \
                patch.object(b, "get_bytes", return_value=b"fixture"), \
                patch.object(b, "parse_krx_list", return_value={"삼성전자": "005930"}), \
                patch.object(b, "parse_daily_quote", return_value={"date": "2026-11-16", "close": "195000", "change_pct": "-6.70"}), \
                patch.object(b, "send_telegram") as send:
            self.assertEqual(b.main(), 0)
            receipt = json.loads((Path(temp) / "gamejoa_issue_briefing.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["delivery_status"], "dry_run")
            self.assertEqual(receipt["selected_topics"], 1)
            self.assertEqual((receipt["social_candidates"], receipt["social_verified"]), (0, 0))
            self.assertTrue(any("AI 커닝 관련주" in item[1] for item in base.SOURCES))
            self.assertIn("삼성전자 195,000원(-6.70%)", (Path(temp) / "gamejoa_issue_briefing.md").read_text(encoding="utf-8"))
            send.assert_not_called()

    def test_live_reservation_prevents_repeat_after_ack_and_after_timeout(self):
        stamp = now("2026-11-17T06:31:00+09:00")
        runner = SimpleNamespace(hydrate_korean_business_details=lambda rows, when: [],
                                 korean_news_search_url=lambda query: "https://search.test/" + query,
                                 quality_display_alerts=lambda alerts, limit: [],
                                 market_materiality=materiality,
                                 collect_fx_snapshot=lambda alerts, when: {"rates": {}},
                                 telegram_text_and_entities=lambda text: (text, []),
                                 telegram_utf16_length=lambda text: len(text))
        base = SimpleNamespace(kst_now=lambda: stamp, SOURCES=[])
        strict = SimpleNamespace(collect_items=lambda when: ([], []), classify=lambda row, when: None)
        telegram = SimpleNamespace(normalize_alert=lambda item: item,
                                   filter_previously_seen_alerts=lambda alerts, when, lane: ([], []))
        pipeline = SimpleNamespace(runner=runner, base=base, telegram=telegram,
                                   contract=SimpleNamespace(strict=strict))
        class Ledger:
            slots = {}
            def __init__(self, repo, token): pass
            def has_slot(self, key): return key in self.slots
            def update(self, key, run_id, status, message_id=None):
                if status == "reserved" and key in self.slots:
                    return False
                self.slots[key] = {"run_id": run_id, "status": status, "message_id": message_id}
                return True
        env = {"BRIEFING_SLOT": "preopen", "TELEGRAM_DRY_RUN": "false", "BRIEFING_REFRESH_SEEN": "false",
               "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "1", "GITHUB_REPOSITORY": "owner/repo",
               "GITHUB_TOKEN": "token", "TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"}
        with tempfile.TemporaryDirectory() as temp, patch.object(b, "OUT", Path(temp)), \
                patch.dict(sys.modules, {"gamejoa_preopen_news_radar_fda_quality_runner": pipeline}), \
                patch.dict(os.environ, env), patch.object(b, "get_bytes", side_effect=TimeoutError()), \
                patch.object(b, "GitHubLedger", Ledger), patch.object(b, "send_telegram", return_value=123) as send:
            self.assertEqual(b.main(), 0)
            receipt = json.loads((Path(temp) / "gamejoa_issue_briefing.json").read_text(encoding="utf-8"))
            self.assertEqual((receipt["delivery_status"], receipt["message_id"]), ("sent", 123))
            self.assertEqual(b.main(), 0)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(json.loads((Path(temp) / "gamejoa_issue_briefing.json").read_text(encoding="utf-8"))["delivery_status"], "skipped_existing_reservation")
            Ledger.slots.clear()
            send.side_effect = RuntimeError("uncertain")
            with self.assertRaisesRegex(RuntimeError, "uncertain"):
                b.main()
            self.assertEqual(Ledger.slots["2026-11-17:preopen"]["status"], "reserved")
            self.assertEqual(b.main(), 0)
            self.assertEqual(send.call_count, 2)

    def test_report_labels_sample_and_never_invents_stock_benefit(self):
        class Runner:
            @staticmethod
            def build_alert_fx_conversion(alert, snapshot, when): return {}
            @staticmethod
            def apply_krw_conversions(value, conversion): return value
        stamp = now("2026-11-17T06:30:00+09:00")
        start, end = b.briefing_window("preopen", stamp)
        groups = [{"title": "삼성전자 실적 발표", "core": "삼성전자가 실적을 발표했다.",
                   "url": "https://example.com/a?x=1&y=2", "alert": {},
                   "stats": {"articles": 3, "publishers": 2, "early": 1, "late": 2},
                   "companies": [("삼성전자", "005930")], "company_source_url": "https://news.test/stock"}]
        quotes = {"005930": {"date": "2026-11-16", "close": "195000", "change_pct": "-6.70"}}
        report = b.render_report("preopen", stamp, start, end, 100, groups, quotes, True, "", {}, Runner())
        self.assertIn("수집 표본: 기사 100건 · 전수 아님", report)
        self.assertIn("기사 직접 언급: 삼성전자 195,000원(-6.70%) | 2026-11-16 종가", report)
        self.assertIn('href="https://example.com/a?x=1&amp;y=2"', report)
        self.assertIn('<a href="https://news.test/stock">종목 근거</a>', report)
        self.assertIn("일부 출처 또는 기사 본문 확인 불가", report)
        self.assertNotIn("수혜", report)

    @unittest.skipUnless(os.getenv("GAMEJOA_INTEGRATION_TEST") == "true", "offline by default")
    def test_current_krx_and_chart_sources(self):
        listed = b.parse_krx_list(b.get_bytes(b.KRX_LIST_URL, 25))
        self.assertEqual(listed.get("삼성전자"), "005930")
        quote = b.parse_daily_quote(b.get_bytes(b.chart_url("005930")), "005930", "삼성전자",
                                    dt.datetime.now(b.KST))
        self.assertGreater(Decimal(quote["close"]), 0)

    @unittest.skipUnless(os.getenv("GAMEJOA_ARTICLE_INTEGRATION") == "true", "live article check off by default")
    def test_actual_ai_cheating_article_body_and_stock_link(self):
        import gamejoa_preopen_news_radar_fda_quality_runner as pipeline
        title = "'AI 커닝', 증시도 흔들었다…AI안경·카메라株 뛰고 보안株는 희비 엇갈려"
        url = "https://www.newsis.com/view/NISX20261116_0003869829"
        source, error = pipeline.base.fetch(url, 20)
        self.assertFalse(error, error)
        detail = pipeline.runner.extract_article_detail(source, title, url)
        self.assertTrue(detail.get("body_verified"), detail)
        row = {"source_title": detail["title"], "source_body": detail["body"],
               "body_verified": True, "link": url, "publisher": "뉴시스"}
        observation = b.ai_cheating_market_observation(row, {"지슨": "446840", "나무가": "190510"})
        self.assertTrue(observation, "Verified article and adjacent listed-stock evidence did not match")
        alert = {**row, "news": row["source_title"], "source_abstract": row["source_body"],
                 "korean_business_news": True, "telegram_core_fact": observation["core"],
                 "policy_plain_summary": observation["core"]}
        self.assertTrue(b.social_observation_verified(alert, observation, pipeline.runner))


if __name__ == "__main__":
    unittest.main()
