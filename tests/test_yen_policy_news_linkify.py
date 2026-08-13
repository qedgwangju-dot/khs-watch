from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_policy_news_alert as news  # noqa: E402
import yen_policy_news_linkify as linkify  # noqa: E402


class YenPolicyNewsLinkifyTests(unittest.TestCase):
    def test_single_source_renders_clickable_original_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            alert_json = root / "alert.json"
            body = root / "alert.md"
            alert_json.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "topic": "BOJ 조기·가속 인상 기대·신호",
                                "source_group": "Bloomberg",
                                "corroborating_groups": ["Bloomberg"],
                                "link": "https://news.google.com/rss/articles/bloomberg-test",
                                "published_at_kst": "2026-08-13T14:04:00+09:00",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            body.write_text(
                "헤드라인: 일본 정부는 BOJ의 더 빠른 금리 인상을 지지\n"
                "교차확인: Bloomberg\n",
                encoding="utf-8",
            )
            with mock.patch.object(news, "collect_items", return_value=([], [])):
                self.assertTrue(
                    linkify.linkify(
                        alert_json,
                        body,
                        dt.datetime(2026, 8, 13, 7, 36, tzinfo=dt.timezone.utc),
                    )
                )
            rendered = body.read_text(encoding="utf-8")
            self.assertIn(
                '확인 출처: Bloomberg · <a href="https://news.google.com/rss/articles/bloomberg-test">원문</a>',
                rendered,
            )
            self.assertNotIn("교차확인: Bloomberg", rendered)
            payload = json.loads(alert_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["telegram_parse_mode"], "HTML")
            self.assertEqual(
                payload["items"][0]["corroborating_sources"][0]["source_group"],
                "Bloomberg",
            )

    def test_multiple_sources_each_get_their_own_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            alert_json = root / "alert.json"
            body = root / "alert.md"
            alert_json.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "topic": "미·일 공동개입/미국 참여",
                                "source_group": "Reuters",
                                "corroborating_groups": ["Bloomberg", "Reuters"],
                                "link": "https://example.com/reuters",
                                "published_at_kst": "2026-08-13T14:04:00+09:00",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            body.write_text("교차확인: Bloomberg, Reuters\n", encoding="utf-8")

            bloomberg_item = news.NewsItem(
                title="Japan and U.S. conduct joint yen intervention",
                link="https://example.com/bloomberg",
                source="Bloomberg",
                description="",
                published=dt.datetime(2026, 8, 13, 5, 30, tzinfo=dt.timezone.utc),
            )
            bloomberg_classified = news.ClassifiedItem(
                item=bloomberg_item,
                topic="미·일 공동개입/미국 참여",
                material_score=5,
                source_level=1,
                source_group="Bloomberg",
            )
            with (
                mock.patch.object(news, "collect_items", return_value=([bloomberg_item], [])),
                mock.patch.object(news, "classify", return_value=bloomberg_classified),
            ):
                linkify.linkify(
                    alert_json,
                    body,
                    dt.datetime(2026, 8, 13, 7, 36, tzinfo=dt.timezone.utc),
                )

            rendered = body.read_text(encoding="utf-8")
            self.assertIn("교차확인: ", rendered)
            self.assertIn(
                'Bloomberg · <a href="https://example.com/bloomberg">원문</a>',
                rendered,
            )
            self.assertIn(
                'Reuters · <a href="https://example.com/reuters">원문</a>',
                rendered,
            )

    def test_non_link_lines_are_html_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            alert_json = root / "alert.json"
            body = root / "alert.md"
            alert_json.write_text(
                json.dumps({"items": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            body.write_text("헤드라인: A & B < C\n", encoding="utf-8")
            linkify.linkify(
                alert_json,
                body,
                dt.datetime(2026, 8, 13, 7, 36, tzinfo=dt.timezone.utc),
            )
            self.assertEqual(
                body.read_text(encoding="utf-8"),
                "헤드라인: A &amp; B &lt; C\n",
            )


if __name__ == "__main__":
    unittest.main()
