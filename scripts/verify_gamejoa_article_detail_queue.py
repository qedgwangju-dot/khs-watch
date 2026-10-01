#!/usr/bin/env python3
"""Regression checks for fair retrieval, source isolation and same-run reuse."""

from __future__ import annotations

import copy
import datetime as dt
import html
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

import gamejoa_article_detail_queue as queue
import khs_source_fetch as source_fetch
import gamejoa_preopen_news_radar_full_compact_runner as radar
from khs_article_detail import ArticleHTMLParser, extract_article_detail


NOW = dt.datetime(2026, 10, 1, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))


def article(index: int, published=NOW) -> dict:
    return {
        "title": f"기업{index} 신규 공급계약 체결", "link": f"https://www.etnews.com/20261001{index:05d}",
        "source": "전자신문", "publisher": "전자신문", "published": published, "layer": "trusted",
    }


def fixture(title: str, body: str) -> str:
    return f'<meta property="og:title" content="{html.escape(title, quote=True)}"><article itemprop="articleBody">{body}</article>'


class DetailQueueChecks(unittest.TestCase):
    def test_old_http_only_validation_failure_is_rechecked_once(self):
        row = article(0)
        selected, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1)
        queue.record_attempt(state, row, NOW, verified=False, error="title/body mismatch aligned=None body_chars=0")
        entry = state["entries"][queue.article_key(row)]
        entry.pop("response_validation_version")
        selected, state, _ = queue.plan_details([row], state, NOW + dt.timedelta(seconds=1), 1)
        self.assertEqual(selected, [row])
        queue.record_attempt(state, row, NOW + dt.timedelta(seconds=1), verified=False, error="title/body mismatch aligned=None body_chars=0")
        selected, _, stats = queue.plan_details([row], state, NOW + dt.timedelta(seconds=2), 1)
        self.assertFalse(selected)
        self.assertEqual(stats["cooling"], 1)

    def test_fair_progress_despite_continuous_urgent_candidates_and_failures(self):
        original = [article(index) for index in range(200)]
        state = {"entries": {}}
        attempted = set()
        for run in range(20):
            now = NOW + dt.timedelta(minutes=6 * run)
            urgent = [article(1000 + run * 10 + index, now) for index in range(10)]
            selected, state, stats = queue.plan_details(urgent + copy.deepcopy(original), state, now, 20)
            self.assertEqual(stats["fair_slots"], 10)
            for row in selected:
                attempted.add(row["link"])
                queue.record_attempt(state, row, now, verified=False, error="timeout")
        self.assertTrue({row["link"] for row in original} <= attempted)
        self.assertNotIn("source_body", json.dumps(state))
        self.assertNotIn('"seen"', json.dumps(state))

    def test_cooldown_backoff_changed_headline_and_preopen_bypass(self):
        row = article(1)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 12)
        for attempt, minutes in enumerate((5, 15, 60, 120)):
            now = NOW + dt.timedelta(hours=attempt * 3)
            queue.record_attempt(state, row, now, verified=False, error="HTTP 502")
            self.assertEqual(queue.parse_time(state["entries"][queue.article_key(row)]["retry_after_kst"]), now + dt.timedelta(minutes=minutes))
        during = now + dt.timedelta(minutes=1)
        selected, _, stats = queue.plan_details([row], state, during, 12)
        self.assertFalse(selected)
        self.assertEqual(stats["cooling"], 1)
        selected, _, _ = queue.plan_details([row], state, during, 12, respect_cooldown=False)
        self.assertEqual(selected, [row])
        updated = {**row, "title": "기업1 공급계약 금액 확대", "published": during}
        selected, changed, _ = queue.plan_details([updated], state, during, 12)
        self.assertEqual(selected, [updated])
        self.assertEqual(changed["entries"][queue.article_key(updated)]["attempts"], 0)

    def test_merge_keeps_attempt_when_only_discovery_is_newer(self):
        row = article(1)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 12)
        discovered = copy.deepcopy(state)
        queue.record_attempt(state, row, NOW, verified=True)
        discovered["entries"][queue.article_key(row)]["last_discovered_kst"] = (NOW + dt.timedelta(minutes=2)).isoformat()
        merged = queue.merge_state(discovered, state, NOW + dt.timedelta(minutes=2))
        self.assertEqual(merged["entries"][queue.article_key(row)]["attempts"], 1)
        self.assertEqual(merged["entries"][queue.article_key(row)]["verification_status"], "verified")
        self.assertEqual(merged["entries"][queue.article_key(row)]["last_discovered_kst"], discovered["entries"][queue.article_key(row)]["last_discovered_kst"])
        later = copy.deepcopy(merged)
        queue.record_attempt(later, row, NOW + dt.timedelta(minutes=3), verified=False, error="later failure")
        self.assertEqual(queue.merge_state(state, later, NOW)["entries"][queue.article_key(row)]["last_error"], "later failure")

    def test_cache_never_crosses_run_date_fingerprint_or_age(self):
        row = article(1)
        receipt = {"fingerprint": queue.fingerprint(row), "query_time_kst": NOW.isoformat(), "detail": {"body": "current primary text"}, "error": ""}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_RUN_ID": "run-a"}):
            path = Path(folder) / "cache.json"
            queue.save_json(path, {"run_id": "run-a", "receipts": {queue.article_key(row): receipt}})
            cache = queue.load_run_cache(NOW + dt.timedelta(minutes=3), path)
            self.assertIsNotNone(queue.cached_receipt(cache, row))
            self.assertIsNone(queue.cached_receipt(cache, {**row, "title": "changed"}))
            self.assertIsNone(queue.cached_receipt(cache, {**row, "published": NOW + dt.timedelta(seconds=1)}))
            self.assertFalse(queue.load_run_cache(NOW + dt.timedelta(minutes=16), path)["receipts"])
            self.assertFalse(queue.load_run_cache(NOW - dt.timedelta(minutes=1), path)["receipts"])
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "run-b"}):
                self.assertFalse(queue.load_run_cache(NOW, path)["receipts"])
            with patch.dict(os.environ, {"GITHUB_RUN_ID": ""}):
                self.assertFalse(queue.load_run_cache(NOW, path)["receipts"])

    def test_preflight_reuse_and_new_run_rotation_in_real_collector(self):
        rows = [article(index) for index in range(12)]
        body = "<p>회사는 생산시설 확충을 위한 신규 공급계약을 체결했다고 공시했다. 계약 기간은 2027년까지이며 공급 품목은 전력기기다.</p>" * 4
        pages = {row["link"]: '<meta property="og:description" content="unrelated recommendation preview">' + fixture(row["title"], body) for row in rows}
        calls = []

        def fetch(url, timeout, *, response_validator=None):
            calls.append(url)
            self.assertIsNotNone(response_validator)
            self.assertIsNone(response_validator(pages[url]))
            return pages[url], None

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run", "RADAR_RUN_MODE": "live"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar, "KOREAN_BUSINESS_DETAIL_LIMIT", 4), \
                patch.object(radar.telegram, "load_seen_state", return_value={"seen": {}}), \
                patch.object(radar.base, "kst_now", return_value=NOW), patch.object(radar.base, "fetch", side_effect=fetch):
            preflight = copy.deepcopy(rows)
            radar.hydrate_korean_business_details(preflight, NOW)
            first_urls = set(calls)
            self.assertEqual(len(calls), 4)
            send_rows = copy.deepcopy(rows)
            notes = radar.hydrate_korean_business_details(send_rows, NOW + dt.timedelta(minutes=1))
            self.assertEqual(len(calls), 4)
            self.assertIn("cache_hits=4", notes[-1])
            verified = [row for row in send_rows if row.get("body_verified")]
            self.assertTrue(all(row["article_query_time_kst"] == NOW.isoformat(timespec="seconds") for row in verified))
            self.assertTrue(all("unrelated recommendation" not in row["source_abstract"] for row in verified))
            state = queue.load_state(queue.PENDING_PATH)
            self.assertTrue(all(entry["attempts"] == 1 for entry in state["entries"].values() if entry.get("last_attempt_kst")))
            queue.save_json(queue.STATE_PATH, state)
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "next-run"}), patch.object(radar.base, "kst_now", return_value=NOW + dt.timedelta(minutes=6)):
                notes = radar.hydrate_korean_business_details(copy.deepcopy(rows), NOW + dt.timedelta(minutes=6))
            self.assertEqual(len(calls), 8)
            self.assertFalse(first_urls & set(calls[4:]))
            self.assertIn("cache_hits=0", notes[-1])
            diagnostic = radar.telegram.selection_diagnostics([], notes, [], [], [], [], True)
            self.assertEqual(diagnostic["detail_queue"]["source_fetches"], 4)
            self.assertTrue(diagnostic["coverage_incomplete"])

    def test_recently_sent_does_not_hide_updated_article_or_preopen_digest(self):
        original = article(1, NOW - dt.timedelta(minutes=30))
        seen = {"seen": {"a": {"link": original["link"], "title": original["title"], "last_seen_kst": (NOW - dt.timedelta(minutes=5)).isoformat()}}}
        body = "<p>공급계약은 장비 생산 확대와 관련되어 있다. 해당 회사는 신규 공장의 가동을 준비하며 자금 조달을 마쳤다고 설명했다.</p>" * 5
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RADAR_RUN_MODE": "live", "GITHUB_RUN_ID": "recent-test"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar.telegram, "load_seen_state", return_value=seen), \
                patch.object(radar.base, "kst_now", return_value=NOW), \
                patch.object(radar.base, "fetch", return_value=(fixture(original["title"], body), None)) as fetch:
            same = copy.deepcopy(original)
            radar.hydrate_korean_business_details([same], NOW)
            fetch.assert_not_called()
            self.assertEqual(same["_detail_skipped_reason"], "recently_delivered_unchanged_title")
            with patch.dict(os.environ, {"RADAR_RUN_MODE": "preopen"}):
                digest = copy.deepcopy(original)
                radar.hydrate_korean_business_details([digest], NOW)
                self.assertTrue(digest["body_verified"])
            updated = {**original, "published": NOW}
            radar.hydrate_korean_business_details([updated], NOW)
            self.assertTrue(updated["body_verified"])
            self.assertEqual(fetch.call_count, 2)


class SourceIsolationChecks(unittest.TestCase):
    def test_article_validation_requests_html_not_feed_content(self):
        validator = lambda text: None
        with patch.object(radar.base, "fetch_text", return_value=("body", None)) as fetch:
            radar.base.fetch("https://www.hankyung.com/article/fixture", response_validator=validator)
            self.assertEqual(fetch.call_args.kwargs["accept"], "text/html,application/xhtml+xml,*/*")
            self.assertIs(fetch.call_args.kwargs["response_validator"], validator)
            radar.base.fetch("https://source.example/rss")
            self.assertIn("application/rss+xml", fetch.call_args.kwargs["accept"])
            self.assertIsNone(fetch.call_args.kwargs["response_validator"])

    def test_fast_invalid_proxy_does_not_hide_valid_direct_article(self):
        import time
        title = "한국 수출 증가 발표"
        body = "한국 수출이 전년 대비 증가했다. 정부는 수출액과 주요 산업별 실적을 발표했으며 반도체와 자동차 수출이 늘었다. " * 6
        good = fixture(title, body)
        bad = '<meta property="og:title" content="한국 수출 증가 발표"><div>본문 없는 동의 화면</div>'

        def direct(*args):
            time.sleep(0.03)
            return good, None

        def validate(text):
            return None if extract_article_detail(text, title)["body_verified"] else "unverified article"

        with patch.object(source_fetch, "_fetch_proxy", return_value=(bad, None)), \
                patch.object(source_fetch, "_fetch_direct", side_effect=direct), \
                patch.dict(os.environ, {"KHS_SOURCE_PROXY_URL": "https://proxy.example/fetch", "KHS_SOURCE_PROXY_FIRST": "true"}):
            text, error = radar.base.fetch("https://www.hankyung.com/article/fixture", 1, response_validator=validate)
            self.assertIsNone(error)
            self.assertEqual(text, good)
            legacy, legacy_error = radar.base.fetch("https://www.hankyung.com/article/fixture", 1)
            self.assertIsNone(legacy_error)
            self.assertEqual(legacy, bad)

    def test_both_invalid_routes_stay_failed_with_both_reasons(self):
        with patch.object(source_fetch, "_fetch_proxy", return_value=("wrong title", None)), \
                patch.object(source_fetch, "_fetch_direct", return_value=("empty body", None)), \
                patch.dict(os.environ, {"KHS_SOURCE_PROXY_URL": "https://proxy.example/fetch", "KHS_SOURCE_PROXY_FIRST": "true"}):
            text, error = source_fetch.fetch_text(
                "https://www.hankyung.com/article/fixture", "test", timeout=1, attempts=1,
                response_validator=lambda text: text,
            )
            self.assertIsNone(text)
            self.assertIn("proxy race", error)
            self.assertIn("wrong title", error)
            self.assertIn("direct race", error)
            self.assertIn("empty body", error)

    def test_sequential_validation_uses_fallback_without_changing_defaults(self):
        with patch.object(source_fetch, "_fetch_direct", return_value=("empty body", None)), \
                patch.object(source_fetch, "_fetch_proxy", return_value=("verified body", None)), \
                patch.dict(os.environ, {"KHS_SOURCE_PROXY_URL": "https://proxy.example/fetch", "KHS_SOURCE_PROXY_FIRST": "false"}):
            text, error = source_fetch.fetch_text(
                "https://source.example/article", "test", timeout=1, attempts=1,
                response_validator=lambda text: None if text == "verified body" else "missing body",
            )
            self.assertIsNone(error)
            self.assertEqual(text, "verified body")
            text, error = source_fetch.fetch_text("https://source.example/article", "test", timeout=1, attempts=1)
            self.assertEqual(text, "empty body")
            self.assertIsNone(error)

    def test_explicit_body_beats_all_other_article_nodes(self):
        title = "기업 신규 공장 투자계획 발표"
        body = "<p>기업이 신규 공장 투자계획을 발표했다. 생산시설 확충을 통해 공급 능력을 늘리기로 했으며 공장 가동 일정은 내년이다.</p>" * 5
        page = '<article class="editor">편집자 소개</article>' + fixture(title, body)
        page += '<article class="thistime_news">엉뚱한 추천 뉴스와 스포츠 선거 소식</article>' * 30
        detail = extract_article_detail(page, title)
        self.assertTrue(detail["body_verified"])
        self.assertIn("공장 가동 일정", detail["body"])
        self.assertNotIn("추천 뉴스", detail["body"])
        self.assertNotIn("편집자 소개", detail["body"])

    def test_hidden_stock_popup_and_sidebar_are_not_source_facts(self):
        title = "코스피 장중 상승 전환"
        paragraph = '<p>코스피는 오후 12시 현재 상승했다. <a>삼성전자<span class="lay_feature" style="display:none;"><span>주가 팝업 관련뉴스: 중국 기업 인수</span></span></a>와 다른 종목도 올랐다.</p>'
        page = fixture(title, paragraph * 6 + '<aside><p>사이드바에서 추천하는 반도체 매각 소식</p></aside>')
        detail = extract_article_detail(page, title)
        self.assertTrue(detail["body_verified"])
        self.assertIn("삼성전자", detail["body"])
        for contaminant in ("중국 기업 인수", "매각 소식", "주가 팝업"):
            self.assertNotIn(contaminant, detail["body"])

    def test_json_ld_is_joined_per_script_and_selected_by_identity(self):
        title = "기업 신규 공급계약 체결"
        wrong = {"@type": "NewsArticle", "headline": "스포츠 선거 당선", "articleBody": "다른 기사 내용 " * 100}
        right = {"@type": "NewsArticle", "headline": title, "articleBody": "실제 공급계약과 생산계획이 공시됐다. " * 20}
        source = f'<meta property="og:title" content="{title}"><script type="application/ld+json">{json.dumps(wrong)}</script><script type="application/ld+json">{json.dumps(right)}</script>'
        parser = ArticleHTMLParser()
        for start in range(0, len(source), 7):
            parser.feed(source[start:start + 7])
        parser.close()
        self.assertEqual(len(parser.json_ld_parts), 2)
        detail = extract_article_detail(source, title)
        self.assertTrue(detail["body_verified"])
        self.assertIn("실제 공급계약", detail["body"])
        self.assertNotIn("다른 기사", detail["body"])

    def test_sports_election_and_ceremonial_photo_not_corporate_events(self):
        for title in ("제4대 대한당구연맹 회장 선거, 강진모 후보 당선", "이더커넥트2026, 폐회사 하는 이종재 이투데이 대표 [포토]"):
            self.assertTrue(radar.is_nonmarket_business_event({"title": title}))
        for title in (
            "최태원 회장, SK하이닉스 주식 3620주 매수", "회장, 자사주 매수 발표 [포토]",
            "기업 투자협약 기념촬영 [포토]", "기업 CEO 신규 공급계약 체결",
            "폭염에 변압기 과부하로 서울 아파트 정전", "美 관세 정책 발표",
        ):
            self.assertFalse(radar.is_nonmarket_business_event({"title": title}))

    def test_intraday_snapshot_is_not_presented_as_after_close_update(self):
        snapshot = {"source_title": "코스피, 모든 주체 매도세에도 소폭 상승세 전환", "published": (NOW.replace(hour=12)).isoformat(), "source_abstract": "오후 12시 현재 코스피는 상승했다."}
        with patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            self.assertTrue(radar.is_stale_intraday_market_report(snapshot, NOW))
            self.assertFalse(radar.is_stale_intraday_market_report(snapshot, NOW.replace(hour=13)))
            self.assertFalse(radar.is_stale_intraday_market_report({**snapshot, "source_title": "코스피 상승 마감"}, NOW))
            self.assertFalse(radar.is_stale_intraday_market_report({**snapshot, "source_title": "코스피, 정책 수혜에 내일 반등 기대"}, NOW))
        with patch.dict(os.environ, {"RADAR_RUN_MODE": "preopen"}):
            self.assertFalse(radar.is_stale_intraday_market_report(snapshot, NOW))

    def test_generated_sector_is_not_a_source_market_event(self):
        cases = (
            ("오아시스, 90년대 미공개 녹음본 28억 경매에 법적 대응…출품 취소",
             "영국 밴드 오아시스는 미공개 녹음 테이프 경매에 법적 대응했다. 음원 지식재산권(IP)은 밴드가 보유하고 있다."),
            ('프락시스 CEO "서울 모처에 디지털국가 대사관 짓겠다"',
             "프락시스 CEO는 서울에 공동체 공간을 만들겠다고 말했다. 과거 펀드로부터 투자를 받았으며 정부와의 협약은 없는 단계다."),
        )
        for title, body in cases:
            alert = {
                "source_title": title, "source_abstract": body, "source_body": body,
                "korean_business_news": True, "body_verified": True,
                "sectors": ["AI/데이터센터"], "policy_plain_summary": "반도체 실적과 수급을 바꿉니다.",
            }
            self.assertFalse(radar.stock_market_channels(alert))
            self.assertFalse(radar.has_stock_market_link(alert), title)
            self.assertFalse(radar.quality_display_alerts([alert], 1), title)

    def test_source_market_event_keeps_broad_industries_and_private_investment(self):
        cases = (
            ("스타트업, 800억원 투자 유치", "국내 바이오 스타트업이 연구개발을 위해 800억원 투자를 유치했다고 밝혔다."),
            ("지자체, 앵커기업 투자보조금 조례 제정", "시는 기업의 생산시설 투자를 유치하기 위한 조례를 제정했다."),
            ("자동차 부품사, 해외 공장 법인 설립", "자동차 부품사는 현지 생산과 고객 지원을 위한 신규 법인을 설립했다."),
            ("양식장 폭염에 물고기 집단 폐사", "고수온으로 양식장의 생산 피해가 늘며 수산물 공급 차질이 우려된다."),
            ("제약사, 신약 임상 3상 승인", "제약사는 임상 3상 시험을 승인받았으며 의약품 상용화를 추진한다."),
            ("최태원 회장, SK하이닉스 주식 3620주 매수", "최태원 회장은 SK하이닉스 주식을 장내 매수했다고 공시했다."),
            ("해운사 파업에 항만 공급 차질", "해운사 노동자 파업으로 항만 운송과 공급 차질이 확대됐다."),
            ("전력장비 업체, AI 냉각 신제품 출시", "전력장비 업체는 데이터센터 고객에게 공급할 냉각 제품을 출시했다."),
        )
        for title, body in cases:
            alert = {"source_title": title, "source_body": body, "korean_business_news": True, "body_verified": True}
            self.assertTrue(radar.has_stock_market_link(alert), title)

    def test_photo_credit_and_obfuscated_email_are_not_core_facts(self):
        title = "기업, 신규 공장 투자계획 발표"
        body = (
            "[서울=뉴시스] 기업 공장. (사진 = 기업 제공) [email protected] *재판매 및 DB 금지 "
            "[촬영 박수현] (서울=연합뉴스) 박수현 기자 = "
            "2026.10.1 willow@yna.co.kr 기업은 신규 공장에 1000억원을 투자한다고 발표했다."
        )
        core = radar.detailed_article_core(title, body)
        self.assertIn("1000억원", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        for garbage in ("email protected", "촬영", "DB 금지", "@", "2026.10.1"):
            self.assertNotIn(garbage, core)
        self.assertTrue(radar.core_has_ui_garbage("[email protected] 기업이 투자한다고 밝혔다."))
        self.assertTrue(radar.core_has_ui_garbage("[촬영 박수현] 기업이 투자한다고 밝혔다."))
        self.assertTrue(radar.core_has_ui_garbage("willow@yna.co.kr 기업이 투자한다고 밝혔다."))

    def test_workflow_persists_attempts_separately_from_delivery(self):
        workflow = (queue.ROOT / ".github/workflows/gamejoa-preopen-news-radar.yml").read_text(encoding="utf-8")
        self.assertIn('GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT: "160"', workflow)
        self.assertIn('GAMEJOA_KOREAN_BUSINESS_DETAIL_WORKERS: "12"', workflow)
        self.assertIn("python scripts/verify_gamejoa_article_detail_queue.py", workflow)
        self.assertIn("Commit GAMEJOA article retrieval queue", workflow)
        self.assertIn("always() && github.event.inputs.telegram_dry_run != 'true'", workflow)
        self.assertIn("out/gamejoa_article_detail_queue_pending.json", workflow)
        self.assertIn("data/gamejoa_article_detail_queue.json", workflow)

    def test_probability_core_preserves_actual_market_action(self):
        title = "美 10월 금리동결 확률 상승, 예상 밑돈 물가"
        body = (
            "8월 PCE 물가가 전년 동월 대비 3.4% 올랐다. 다우존스의 전문가 예상치 3.7%를 밑돈 수치다. "
            "CME 페드워치에 따르면 시장은 연준이 오는 10월 기준금리를 동결할 가능성을 전날 49.1%에서 이날 65.1%로 올려 반영했다."
        )
        core = radar.detailed_article_core(title, body)
        for fact in ("10월 금리동결", "49.1%", "65.1%", "CME 페드워치"):
            self.assertIn(fact, core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertFalse(radar.policy_probability_article_fact(title, body.replace("페드워치", "일반 전망")))

    def test_company_statement_wins_over_context_only_background(self):
        title = "SK하이닉스, 솔리다임 자금조달 방식 미정"
        body = (
            "SK하이닉스가 솔리다임의 경쟁력을 강화할 여러 전략을 검토 중이라고 공식화했다. "
            "이 과정에서 솔리다임이 별도 상장될 경우 SK하이닉스 주주가치가 훼손될 수 있다는 우려가 나왔다. "
            "솔리다임의 자금조달 방식은 아직 결정되지 않았다."
        )
        core = radar.detailed_article_core(title, body)
        self.assertFalse(core.startswith("이 과정"))
        self.assertIn("솔리다임", core)
        self.assertTrue("검토" in core or "결정되지" in core)

    def test_image_credit_not_part_of_financial_fact(self):
        core = radar.detailed_article_core(
            "3분기 스타트업 누적 투자액 10조원 돌파",
            "(AI 이미지 생성)\n3분기 국내 스타트업의 누적 투자액이 10조원을 돌파했다. 투자 회복세는 4년 만이다.",
        )
        self.assertIn("10조원", core)
        self.assertNotIn("이미지 생성", core)
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_corporate_denial_not_replaced_with_market_speculation(self):
        title = "SK하이닉스, 솔리다임 자금조달 방식 미정"
        statement = "SK하이닉스는 솔리다임 관련 보도에 대해 확정된 사항은 없다고 설명했다."
        rumour = "시장은 SK하이닉스가 솔리다임 투자 재원 마련을 위해 외부자본을 유치할 수 있다는 관측을 제기했다."
        core = radar.detailed_article_core(title, statement + " " + rumour)
        self.assertIn("확정된 사항은 없", core)
        self.assertIn("자금조달 방식", core)
        self.assertNotIn("관측", core)
        self.assertFalse(radar.unconfirmed_company_action_fact(title, rumour))

    def test_decimal_values_are_not_treated_as_sentence_boundaries(self):
        source = "출처 안내문이 길게 붙었다 " * 30 + ". 미국 8월 PCE 물가는 전년 동월 대비 3.4% 상승했다."
        core = radar.complete_prose_text(source, limit=100)
        self.assertEqual(core, "미국 8월 PCE 물가는 전년 동월 대비 3.4% 상승했다.")

    def test_forecast_comparison_and_anaphora_need_the_actual_fact(self):
        for orphan in (
            "다우존스가 집계한 전문가 예상치 3.7%를 밑돈 수치다.",
            "이 과정에서 솔리다임이 상장되면 주주가치가 훼손될 수 있다는 우려가 나왔다.",
        ):
            self.assertFalse(radar.core_sentence_is_complete(orphan))
        self.assertTrue(radar.core_sentence_is_complete("KB증권은 내년 기업 매출이 23% 늘어날 것으로 예상했다."))


def verify_live_source_boundaries() -> None:
    cases = (
        ("https://biz.heraldcorp.com/article/10891069", "sports", ("강진모",)),
        ("https://core.asiae.co.kr/article/2026100112163454437", "intraday", ("코스피", "코스닥")),
        ("https://www.etoday.co.kr/news/view/2631400", "company", ("솔리다임", "확정된")),
    )
    results = []
    for url, kind, anchors in cases:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=25) as response:
            source = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        parser = ArticleHTMLParser()
        parser.feed(source)
        parser.close()
        detail = extract_article_detail(source)
        assert detail["body_verified"] and parser.target_bodies, f"Unverified explicit source body: {url}"
        assert all(anchor in detail["body"] for anchor in anchors), f"Missing article facts: {url}"
        if kind == "sports":
            assert radar.is_nonmarket_business_event({"title": detail["title"]}), "Sports election must not become a market alert"
            assert not any(marker in detail["body"] for marker in ("'속보' 확인", "프리미엄콘텐츠", "기사를 더 봅니다"))
        elif kind == "intraday":
            assert "주요종목시세" not in detail["body"] and "출처: 한국거래소" not in detail["body"], "Hidden quote-popup data leaked into body"
        else:
            core = radar.detailed_article_core(detail["title"], detail["body"])
            assert radar.core_sentence_is_complete(core) and "확정된 사항은 없" in core and "자금조달 방식" in core, f"Primary company statement was replaced: {core!r}"
        results.append({
            "url": url, "source_title": detail["title"], "body_chars": len(detail["body"]),
            "explicit_regions": len(parser.target_bodies), "body_verified": detail["body_verified"],
            "nonmarket_event": radar.is_nonmarket_business_event({"title": detail["title"]}),
            "query_time_kst": dt.datetime.now(NOW.tzinfo).isoformat(timespec="seconds"),
        })
    queue.save_json(queue.ROOT / "out/gamejoa_live_source_boundary_audit.json", {"status": "passed", "sources": results})
    print(json.dumps(results, ensure_ascii=False))


def audit_saved_report(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist() if name.endswith("gamejoa_preopen_news_radar.json"))
        report = json.loads(archive.read(name))
    audited = []
    for alert in report["alerts"]:
        if not alert.get("korean_business_news"):
            continue
        title = alert.get("source_title") or alert["news"]
        draft = radar.detailed_article_core(title, alert.get("source_body") or alert.get("source_abstract") or "")
        revised = radar.verified_alert_core({**alert, "telegram_core_fact": draft}, title)
        assert radar.core_sentence_is_complete(revised), f"No complete recovered fact: {title}"
        assert radar.compact_title_summary_aligned(title, revised), f"Recovered title/core mismatch: {title}"
        assert not radar.core_has_ui_garbage(revised) and "이미지 생성" not in revised, f"Publisher credit leaked into core: {title}"
        audited.append({
            "title": title, "previous_core": alert.get("telegram_core_fact"), "recovered_core": revised,
            "source_market_event": radar.has_stock_market_link(alert),
        })
    queue.save_json(queue.ROOT / "out/gamejoa_saved_report_core_audit.json", {"status": "passed", "artifact_zip": str(path), "audited": audited})
    print(json.dumps(audited, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    if "--live-sources" in sys.argv:
        verify_live_source_boundaries()
    elif "--audit-report" in sys.argv:
        audit_saved_report(Path(sys.argv[sys.argv.index("--audit-report") + 1]))
    else:
        unittest.main()
