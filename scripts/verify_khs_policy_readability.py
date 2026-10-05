#!/usr/bin/env python3
"""Replay the six clipped policy alerts without sending or changing seen state."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import contextlib
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import khs_policy_telegram_formatter as formatter
from khs_policy_telegram_delivery import deliver_policy_parts
import khs_telegram_delivery_guard as guard
import khs_trusted_policy_news_watch as watch


NOW = dt.datetime(2026, 10, 4, 12, 0, tzinfo=watch.KST)
RULES = {rule.key: rule for rule in watch.STORY_RULES}
FCC_ROOT = "https://docs.fcc.gov/public/attachments/"
ARMY_ROOT = "https://www.army.mil/article/"
CASES = [
    ("nepa", "us_fcc_space_nepa_reform", {
        "title": RULES["us_fcc_space_nepa_reform"].title,
        "description": "FCC adopts NEPA reform for space-based operations and satellite deployment.",
        "source": "Federal Communications Commission", "link": FCC_ROOT + "FCC-26-64A1.pdf",
        "published_kst": "2026-10-01T00:00:00+09:00",
    }, ["주요 연방행위", "안테나 구조물", "FAA", "최종 명령", "2026년 9월 30일"]),
    ("spectrum", "us_fcc_satellite_spectrum_abundance", {
        "title": RULES["us_fcc_satellite_spectrum_abundance"].title,
        "description": "FCC adopts Satellite Spectrum Abundance opening 1,050 megahertz in 12.7-13.25 GHz and 42-42.5 GHz.",
        "source": "Federal Communications Commission", "link": FCC_ROOT + "FCC-26-65A1.pdf",
        "published_kst": "2026-10-01T00:00:00+09:00",
    }, ["1,050MHz", "550MHz", "500MHz", "12.7~12.75GHz", "동결은 유지", "개별 허가"]),
    ("followon", "us_fcc_satellite_spectrum_followon_fnprm", {
        "title": RULES["us_fcc_satellite_spectrum_followon_fnprm"].title,
        "description": "FCC seeks comment on satellite communications with 1,450 megahertz and 138.25 gigahertz in the Spectrum Abundance FNPRM.",
        "source": "Federal Communications Commission", "link": FCC_ROOT + "FCC-26-65A1.pdf",
        "published_kst": "2026-10-01T00:00:00+09:00",
    }, ["1,450MHz", "138.25GHz", "총 대역폭", "최종 개방·할당은 미확정", "합산하지"]),
    ("fascom", "us_dow_autonomous_warfare_execution", {
        "title": "Army announces Futures and Autonomous Systems Command",
        "description": "Army establishes FASCOM and a Portfolio Acquisition Executive for Autonomy. Acquisition and fielding are prioritized across at least six areas by FY2028.",
        "source": "U.S. Army", "link": ARMY_ROOT + "295913/army_announces_futures_and_autonomous_systems_command",
        "published_kst": "2026-10-03T07:23:00+09:00",
    }, ["FASCOM", "2028회계연도", "15X", "390A", "6개", "획득", "2026년 10월 1일", "2026년 10월 2일"]),
    ("meridian", "us_dow_project_meridian_future_warfare", {
        "title": "Project Meridian",
        "description": "MITRE leads independent Project Meridian to study future warfare. Elon Musk, Palmer Luckey and Newt Gingrich are co-directors.",
        "source": "MITRE", "link": "https://www.mitre.org/news-insights/publication/project-meridian",
        "published_kst": "2026-10-02T00:00:00+09:00",
    }, ["MITRE", "제출 일정은 의뢰서 원문 재확인 필요", "연구", "계약", "머스크"]),
    ("autowarcom", "us_dow_autonomous_warfare_execution", {
        "title": "Hegseth delivers State of the Force address, outlines series of new initiatives",
        "description": "Announced creation of four-star Autonomous Warfare Command AUTOWARCOM and Project Agincourt to expand autonomous and robotic systems across the joint force.",
        "source": "U.S. Army", "link": ARMY_ROOT + "295897/hegseth_delivers_state_of_the_force_address_outlines_series_of_new_initiatives",
        "published_kst": "2026-10-02T22:50:00+09:00",
    }, ["4성급", "Agincourt", "창설 발표", "이미 가동", "2026년 9월 30일"]),
]
for case in CASES[:3]:
    case[2]["published_precision"] = "date"


def render_cases(cases: list, title: str = "정책 워치 검증 표본") -> tuple[str, str]:
    lines = [f"{NOW:%Y년 %m월 %d일 %H:%M KST}", f"공식 확인 정책 뉴스 {len(cases)}건 확인", ""]
    for index, (_, key, item, _) in enumerate(cases, 1):
        lines.extend(watch.render_alert_section(RULES[key], [item], NOW, index))
    return formatter.format_policy_message(title, "\n".join(lines), rates={}, now=NOW)


class TelegramHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.urls: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in {"a", "b"}:
            raise AssertionError(f"unexpected Telegram tag: {tag}")
        self.stack.append(tag)
        if tag == "a":
            url = dict(attrs).get("href", "")
            if not url.startswith("https://"):
                raise AssertionError(f"invalid source link: {url}")
            self.urls.append(url)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack.pop() != tag:
            raise AssertionError("unbalanced Telegram HTML")

    def handle_data(self, data: str) -> None:
        self.text.append(data)


class ReadabilityTests(unittest.TestCase):
    def test_six_complete_source_specific_cases(self) -> None:
        self.assertTrue(Path(watch.__file__).resolve().is_relative_to(ROOT))
        for case in CASES:
            with self.subTest(case=case[0]):
                title, body = render_cases([case])
                self.assertEqual(formatter.validate_final_policy_message(title, body), [])
                core = re.search(r"(?m)^- 핵심: (.+)$", body).group(1)
                self.assertRegex(core, r"(?:했습니다|합니다|됐습니다|시켰습니다|있습니다)\.$")
                self.assertNotRegex(core, r"(?:Systems|Elon Musk|MHz와|FSS\) 상)입니다")
                for marker in case[3]:
                    self.assertIn(marker, body)
                for forbidden in ("🔎 핵심 변화", "🇰🇷 기업·매출 연결", "⚠️ 병목·실패모드", "- 투자 관점:", "- 한국장 영향:"):
                    self.assertNotIn(forbidden, body)
                self.assertLess(body.index("- 핵심:"), body.index("- 실제 내용:"))
                self.assertLess(body.index("- 실제 내용:"), body.index("- 현재 단계:"))
                self.assertLess(body.index("- 현재 단계:"), body.index("- 타임라인:"))
                self.assertLess(body.index("- 타임라인:"), body.index("- 출처:"))

    def test_formatting_is_idempotent(self) -> None:
        title, body = render_cases(CASES)
        self.assertEqual(formatter.format_policy_message(title, body, rates={}, now=NOW), (title, body))

    def test_html_headings_dates_and_clickable_links(self) -> None:
        title, body = render_cases(CASES[:3])
        message = formatter.prepare_telegram_html(title, body)
        parser = TelegramHTML()
        parser.feed(message)
        self.assertEqual(parser.stack, [])
        self.assertEqual(parser.urls, [case[2]["link"] for case in CASES[:3]])
        self.assertIn("<b>- 핵심:</b>", message)
        self.assertIn("<b>2026년 9월 30일</b>", message)
        self.assertIn('<a href="https://docs.fcc.gov/', message)
        self.assertNotIn("&lt;a href", message)

    def test_long_prose_survives_real_delivery_guard(self) -> None:
        for case in CASES:
            with self.subTest(case=case[0]), tempfile.TemporaryDirectory() as tmp:
                title, body = render_cases([case])
                lane = guard.Lane("trusted_policy_news", Path(tmp) / "title.txt", Path(tmp) / "body.md")
                lane.title.write_text(title, encoding="utf-8")
                lane.body.write_text(body, encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    guard.guard_lane(lane)
                self.assertTrue(lane.body.exists(), case[0])
                self.assertEqual(lane.body.read_text(encoding="utf-8"), body)

    def test_all_facts_survive_message_splitting(self) -> None:
        title, body = render_cases(CASES)
        self.assertGreater(len(formatter.prepare_telegram_html(title, body)), 4096)
        messages = formatter.prepare_telegram_messages(title, body)
        self.assertGreater(len(messages), 1)
        parsers = []
        for message in messages:
            self.assertLessEqual(len(message), 4096)
            parser = TelegramHTML()
            parser.feed(message)
            self.assertEqual(parser.stack, [])
            parsers.append(parser)
        plain = "\n".join("".join(parser.text) for parser in parsers)
        expected_lines = Counter(line for line in body.splitlines() if line.strip() and not line.startswith("- 출처:"))
        actual_lines = Counter(plain.splitlines())
        for line, count in expected_lines.items():
            self.assertEqual(actual_lines[html.unescape(line)], count, line)
        self.assertEqual([url for parser in parsers for url in parser.urls], [case[2]["link"] for case in CASES])

    def test_oversized_article_splits_fields_not_text(self) -> None:
        title, body = render_cases(CASES[:1])
        details = [f"- 대상: 검증번호 {index:03d}의 적용 대상과 허가 조건을 원문에 따라 확인했습니다." for index in range(120)]
        body = body.replace("- 다음 확인:", "\n".join(details) + "\n- 다음 확인:")
        messages = formatter.prepare_telegram_messages(title, body)
        plain = html.unescape(re.sub(r"<[^>]+>", "", "\n".join(messages)))
        self.assertGreater(len(messages), 1)
        for detail in details:
            self.assertEqual(plain.count(detail), 1)

    def test_extreme_single_field_is_not_silently_cropped(self) -> None:
        with self.assertRaisesRegex(ValueError, "preserve source text"):
            formatter.prepare_telegram_messages("정책 워치", "- 실제 내용: " + "원문 사실 " * 2000)

    def test_fx_preserves_amount_roles_and_complete_action(self) -> None:
        title, body = formatter.format_policy_message("정책 워치", "\n".join([
            "1. [상·공식 확인] 미국, 에너지 투자와 추가 계획 발표",
            "- 핵심: 투자액 9500억달러와 추가 계획 1조7000억달러가 발표됐습니다.",
            '- 출처: <a href="https://example.com/source?a=1&amp;b=2">원문</a>',
        ]), rates={"USD": 1462}, now=NOW)
        self.assertIn("9500억달러(약 1,389조원)", body)
        self.assertIn("1조7000억달러(약 2,485조원)", body)
        self.assertIn("투자액", body)
        self.assertIn("추가 계획", body)
        self.assertIn("발표됐습니다.", body)
        self.assertEqual(formatter.validate_final_policy_message(title, body), [])
        parser = TelegramHTML()
        parser.feed(formatter.prepare_telegram_html(title, body))
        self.assertEqual(parser.urls, ["https://example.com/source?a=1&b=2"])

    def test_old_nominal_fragments_fail_validation(self) -> None:
        for core in ("FCC는 FSS) 상입니다.", "FCC는 1,450MHz와입니다.", "미 육군이 Futures and Autonomous Systems입니다."):
            self.assertIn("policy_core_nominal_fragment", formatter.validate_final_policy_message("정책 워치", f"- 핵심: {core}"))

    def test_date_only_release_is_not_invented_midnight(self) -> None:
        _, body = render_cases(CASES[:3])
        self.assertNotIn("00:00 KST", body)
        self.assertEqual(body.count("시각 미공개"), 3)
        self.assertIn("- 채택일: 2026년 9월 30일", body)
        self.assertIn("- 공개일: 2026년 10월 1일", body)

    def test_fcc_snapshot_is_not_attached_to_a_different_order(self) -> None:
        item = dict(CASES[0][2], link=FCC_ROOT + "FCC-26-99A1.pdf")
        self.assertIsNone(watch.item_story_profile(RULES[CASES[0][1]], [item]))

    def test_inline_workflow_python_compiles(self) -> None:
        for filename in ("khs-policy-watch.yml",):
            lines = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8").splitlines()
            snippets = []
            current = None
            for line in lines:
                if "<<'PY'" in line:
                    current = []
                elif current is not None and line.strip() == "PY":
                    snippets.append(textwrap.dedent("\n".join(current)))
                    current = None
                elif current is not None:
                    current.append(line)
            self.assertTrue(snippets, filename)
            for snippet in snippets:
                ast.parse(snippet, filename=filename)

    def test_workflow_uses_same_lossless_splitter_and_keeps_pause(self) -> None:
        workflow = (ROOT / ".github/workflows/khs-policy-watch.yml").read_text(encoding="utf-8")
        self.assertIn("prepare_telegram_messages", workflow)
        self.assertIn("deliver_policy_parts", workflow)
        self.assertIn("out/khs_telegram_delivery_partial.json", workflow)
        self.assertIn("state_paths=(data/khs_telegram_delivery_seen.json)", workflow)
        self.assertNotRegex(workflow, r"gh api.*?/enable")
        self.assertNotRegex(workflow, r"gh workflow run.*telegram_dry_run=false")
        self.assertIn("verify_khs_policy_readability.py --write-previews", workflow)
        radar = (ROOT / ".github/workflows/gamejoa-preopen-news-radar.yml").read_text(encoding="utf-8")
        self.assertIn("verify_khs_policy_readability.py --write-previews", radar)

    def test_partial_send_retry_skips_acknowledged_parts(self) -> None:
        state, checkpoints = {}, []
        calls = []
        def interrupted(text):
            calls.append(text)
            if text == "second":
                raise RuntimeError("synthetic transport failure")
            return 101
        kwargs = dict(digest="fixture", route="policy", title="정책 워치", sent_state=state,
                      now_utc=NOW.astimezone(dt.timezone.utc), dedupe_hours=24,
                      checkpoint=lambda value: checkpoints.append(value))
        with self.assertRaisesRegex(RuntimeError, "synthetic transport failure"):
            deliver_policy_parts(["first", "second", "third"], send=interrupted, **kwargs)
        self.assertNotIn("fixture", state)
        self.assertEqual(checkpoints[-1]["status"], "partial")
        retries = []
        def resumed(text):
            retries.append(text)
            return 201 + len(retries)
        receipt = deliver_policy_parts(["first", "second", "third"], send=resumed, **kwargs)
        self.assertEqual(retries, ["second", "third"])
        self.assertEqual(receipt["confirmed_message_ids"], [101, 202, 203])
        self.assertEqual(receipt["new_message_ids"], [202, 203])
        self.assertEqual(checkpoints[-1]["status"], "complete")
        self.assertEqual(state["fixture"]["message_ids"], [101, 202, 203])

    def test_partial_receipt_never_accepts_missing_message_id(self) -> None:
        state = {}
        with self.assertRaisesRegex(RuntimeError, "confirmed message_id"):
            deliver_policy_parts(["first"], digest="fixture", route="policy", title="정책 워치",
                                 sent_state=state, now_utc=NOW.astimezone(dt.timezone.utc), dedupe_hours=24,
                                 send=lambda text: None, checkpoint=lambda receipt: None)
        self.assertEqual(state, {})


def check_official_sources() -> dict:
    receipts = []
    for document, rule_keys in (
        ("FCC-26-64A1", ["us_fcc_space_nepa_reform"]),
        ("FCC-26-65A1", ["us_fcc_satellite_spectrum_abundance", "us_fcc_satellite_spectrum_followon_fnprm"]),
    ):
        url = FCC_ROOT + document + ".txt"
        raw = watch.fetch_text(url, timeout=40)
        plain = watch.clean_text(raw)
        expected = {
            "us_fcc_space_nepa_reform": "us-fcc-space-nepa-adopted",
            "us_fcc_satellite_spectrum_abundance": "us-fcc-satellite-spectrum-abundance-adopted",
            "us_fcc_satellite_spectrum_followon_fnprm": "us-fcc-satellite-spectrum-followon-proposal",
        }
        for key in rule_keys:
            item = {"title": RULES[key].title, "description": plain[:50000], "link": url, "source": "Federal Communications Commission"}
            actual = watch.semantic_policy_event_key(item)
            if actual != expected[key]:
                raise AssertionError(f"production official text assigned to wrong event: {key} {actual}")
        receipts.append({"url": url, "status": "read", "characters": len(raw), "sha256": hashlib.sha256(raw.encode()).hexdigest(), "checked_at_kst": dt.datetime.now(watch.KST).isoformat(timespec="seconds")})
    return {"receipts": receipts, "status": "passed"}


def write_previews(result: unittest.TestResult, sources: dict | None) -> None:
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    files = []
    for label, cases in (("fcc", CASES[:3]), ("army", CASES[3:])):
        title, body = render_cases(cases)
        md = out / f"khs_policy_readability_{label}.md"
        md.write_text("검증 표본: 기존 6건의 형식 재현이며 새 뉴스 송출이 아닙니다.\n\n" + body, encoding="utf-8")
        messages = formatter.prepare_telegram_messages(title, body)
        rendered = "\n<hr>\n".join(f'<section style="white-space:pre-wrap">{message}</section>' for message in messages)
        page = out / f"khs_policy_readability_{label}.html"
        page.write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>정책워치 형식 검증</title><style>body{max-width:760px;margin:24px auto;padding:0 20px;font:16px/1.65 sans-serif;color:#222}a{color:#087fa4}hr{margin:24px 0;border:0;border-top:1px solid #ddd}</style><p>기존 기사의 형식 검증 표본. 실제 재송출하지 않았습니다.</p>' + rendered + "</html>", encoding="utf-8")
        files.extend([str(md.relative_to(ROOT)), str(page.relative_to(ROOT))])
    audit = {"status": "passed" if result.wasSuccessful() else "failed", "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "generated_at_kst": dt.datetime.now(watch.KST).isoformat(timespec="seconds"), "fixture_article_count": len(CASES), "external_delivery": False, "seen_state_changed": False, "sources": sources or {"status": "fixture_only_not_live_source_verification"}, "files": files}
    (out / "khs_policy_readability_verification.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-previews", action="store_true")
    parser.add_argument("--check-live-sources", action="store_true")
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReadabilityTests))
    if not result.wasSuccessful():
        return 1
    sources = check_official_sources() if args.check_live_sources else None
    if args.write_previews:
        write_previews(result, sources)
    print(f"khs_policy_readability=passed tests={result.testsRun} cases={len(CASES)} external_delivery=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
