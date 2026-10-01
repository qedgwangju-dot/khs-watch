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

import gamejoa_article_detail_queue as queue
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
        pages = {row["link"]: fixture(row["title"], body) for row in rows}
        calls = []

        def fetch(url, timeout):
            calls.append(url)
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

    def test_workflow_persists_attempts_separately_from_delivery(self):
        workflow = (queue.ROOT / ".github/workflows/gamejoa-preopen-news-radar.yml").read_text(encoding="utf-8")
        self.assertIn('GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT: "160"', workflow)
        self.assertIn('GAMEJOA_KOREAN_BUSINESS_DETAIL_WORKERS: "12"', workflow)
        self.assertIn("python scripts/verify_gamejoa_article_detail_queue.py", workflow)
        self.assertIn("Commit GAMEJOA article retrieval queue", workflow)
        self.assertIn("always() && github.event.inputs.telegram_dry_run != 'true'", workflow)
        self.assertIn("out/gamejoa_article_detail_queue_pending.json", workflow)
        self.assertIn("data/gamejoa_article_detail_queue.json", workflow)


def verify_live_source_boundaries() -> None:
    cases = (
        ("https://biz.heraldcorp.com/article/10891069", "sports", ("강진모",)),
        ("https://core.asiae.co.kr/article/2026100112163454437", "intraday", ("코스피", "코스닥")),
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
        else:
            assert "주요종목시세" not in detail["body"] and "출처: 한국거래소" not in detail["body"], "Hidden quote-popup data leaked into body"
        results.append({
            "url": url, "source_title": detail["title"], "body_chars": len(detail["body"]),
            "explicit_regions": len(parser.target_bodies), "body_verified": detail["body_verified"],
            "nonmarket_event": radar.is_nonmarket_business_event({"title": detail["title"]}),
            "query_time_kst": dt.datetime.now(NOW.tzinfo).isoformat(timespec="seconds"),
        })
    queue.save_json(queue.ROOT / "out/gamejoa_live_source_boundary_audit.json", {"status": "passed", "sources": results})
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    if "--live-sources" in sys.argv:
        verify_live_source_boundaries()
    else:
        unittest.main()
