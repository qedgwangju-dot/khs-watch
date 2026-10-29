import hashlib
import ast
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import us_positioning_presentation as presentation


def snapshot():
    return json.loads((ROOT / "tests/fixtures/us_positioning_20261014_saved.json").read_text(encoding="utf-8"))["values"]


def render(values=None, **kwargs):
    values = values if values is not None else snapshot()
    ordered = [values[key] for key in ("CFTC|cot", "Cboe|options", "Nasdaq SOX|sox") if key in values]
    return presentation.render_detail_alert(
        values.get("CFTC|cot"), values.get("Cboe|options"), values.get("Nasdaq SOX|sox"),
        ordered, ordered, **kwargs,
    )


class TagBalance(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in ("b", "a"):
            raise AssertionError(f"Unexpected Telegram tag: {tag}")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise AssertionError(f"Unbalanced Telegram tag: {tag}")


class PriceDirectionTests(unittest.TestCase):
    def direction(self, d1, d3, d5, confirmed=True):
        return presentation.price_direction({"metrics": {
            "d1_pct": d1, "d3_pct": d3, "d5_pct": d5, "final_close_confirmed": confirmed,
        }})

    def test_all_negative_is_semiconductor_down_not_whole_us_market(self):
        icon, title, _ = self.direction(-4.30, -7.06, -10.58)
        self.assertEqual((icon, title), ("🔴", "반도체 하락 우세"))
        self.assertNotIn("미국 증시 하락", title)

    def test_all_positive_is_up(self):
        self.assertEqual(self.direction(1, 2, 3)[1], "반도체 상승 우세")

    def test_one_day_rebound_is_not_uptrend(self):
        title = self.direction(1, -2, -3)[1]
        self.assertIn("당일 반등", title)
        self.assertNotIn("상승 우세", title)

    def test_one_day_drop_does_not_erase_positive_multiday_returns(self):
        self.assertIn("당일 하락 · 추세 혼재", self.direction(-1, 2, 3)[1])

    def test_other_mixed_periods(self):
        for values in ((1, -2, 3), (-1, 2, -3), (0, 1, -2)):
            with self.subTest(values=values):
                self.assertIn("방향 혼재", self.direction(*values)[1])

    def test_zero_returns_are_flat_not_bearish(self):
        self.assertEqual(self.direction(0, 0, 0)[1], "반도체 보합")

    def test_missing_nonfinite_or_unverified_prices_do_not_get_a_direction(self):
        for values in ((None, -2, -3), (float("nan"), -2, -3)):
            self.assertIn("확인 대기", self.direction(*values)[1])
        self.assertIn("확인 대기", self.direction(-1, -2, -3, False)[1])
        self.assertIn("추세 확인 대기", self.direction(-1, None, -3)[1])


class PositionTests(unittest.TestCase):
    def test_level_and_change_combinations_and_sign_crossings(self):
        cases = [
            (74856, 4055, "순롱 확대"), (-26738, 7044, "순숏 축소"),
            (200, -50, "순롱 축소"), (-200, -50, "순숏 확대"),
            (10, 30, "순숏 → 순롱 전환"), (-10, -30, "순롱 → 순숏 전환"),
            (0, 20, "순숏 해소·롱숏 균형"), (0, -20, "순롱 해소·롱숏 균형"),
            (10, 10, "순롱 형성"), (-10, -10, "순숏 형성"),
            (-20, 0, "주간 변화 없음"), (20, 0, "주간 변화 없음"),
        ]
        for net, change, expected in cases:
            with self.subTest(net=net, change=change):
                self.assertEqual(presentation.position_change(net, change), expected)

    def test_missing_positions_never_become_zero(self):
        self.assertEqual(presentation.position_level(None), "순포지션 미확인")
        self.assertIn("미확인", presentation.position_change(20, None))
        self.assertNotIn("0계약", presentation.position_line("기관", None, None))

    def test_eight_day_lag_is_prominent_and_unchanged_short_stays_short(self):
        message = render()
        self.assertIn("순숏 26,738계약", message)
        self.assertIn("주간 순포지션 변화 +7,044계약 (순숏 7,044계약 축소)", message)
        self.assertIn("여전히 순숏", message)
        self.assertIn("<b>8일 이전</b>", message)
        self.assertIn("2026-10-06 주간", message)
        self.assertIn("2026-10-14 마감", message)

    def test_nasdaq_consolidated_and_nq_mini_are_labelled_separately(self):
        message = render()
        self.assertIn("나스닥100 통합 · 선물만", message)
        self.assertIn("NQ E-mini 선물만", message)
        self.assertIn("순숏 19,212계약", message)
        self.assertIn("집계 범위가 달라 합산하지 않음", message)

    def test_unknown_date_gap_is_not_assumed_to_be_zero(self):
        values = snapshot()
        values["CFTC|cot"]["period"] = "unavailable"
        self.assertIn("기준일 차이 미확인", render(values))


class PositionClarityTests(unittest.TestCase):
    def test_actual_three_periods_describe_short_size_and_never_imply_a_long_holding(self):
        for change, expected in ((5511,"순숏 5,511계약 축소"),(-5120,"순숏 5,120계약 확대"),(49405,"순숏 49,405계약 축소")):
            with self.subTest(change=change):
                self.assertEqual(presentation.position_movement(-19212,change),expected)

    def test_long_holdings_expand_and_shrink_with_the_correct_quantity(self):
        for net, change, expected in ((74856,4055,"순롱 4,055계약 확대"),(100,-50,"순롱 50계약 축소"),(-100,-50,"순숏 50계약 확대"),(-100,50,"순숏 50계약 축소")):
            with self.subTest(net=net,change=change):
                self.assertEqual(presentation.position_movement(net,change),expected)

    def test_crossings_show_both_observed_levels_instead_of_only_a_size_change(self):
        for net, change, expected in ((10,30,"순숏 20계약 → 순롱 10계약 전환"),(-10,-30,"순롱 20계약 → 순숏 10계약 전환")):
            with self.subTest(net=net):
                self.assertEqual(presentation.position_movement(net,change),expected)

    def test_zero_levels_balanced_holdings_and_formation_remain_distinct(self):
        cases=[(0,20,"순숏 20계약 해소 · 롱·숏 균형"),(0,-20,"순롱 20계약 해소 · 롱·숏 균형"),
               (20,20,"순롱 20계약 형성"),(-20,-20,"순숏 20계약 형성"),
               (0,0,"롱·숏 균형 유지"),(20,0,"순롱 규모 변화 없음"),(-20,0,"순숏 규모 변화 없음")]
        for net,change,expected in cases:
            with self.subTest(net=net,change=change):
                self.assertEqual(presentation.position_movement(net,change),expected)

    def test_missing_nonfinite_or_fractional_contracts_are_not_rounded_into_a_claim(self):
        for net, change in ((None,20),(-20,None),(float("nan"),20),(20,float("inf")),(10.5,2),(10,2.5),(True,2)):
            with self.subTest(net=net,change=change):
                self.assertEqual(presentation.position_movement(net,change),"순포지션 변화 확인 대기")
        self.assertNotIn("미확인계약",presentation.position_line("기관",None,None))

    def test_gross_components_use_increase_decrease_words_and_do_not_claim_orders(self):
        self.assertEqual(presentation.holding_change("롱",3199),"롱 3,199 증가")
        self.assertEqual(presentation.holding_change("숏",-2312),"숏 2,312 감소")
        self.assertEqual(presentation.holding_change("롱",0),"롱 보유 변화 없음")
        self.assertEqual(presentation.holding_change("숏",None),"숏 보유 변화 미확인")


class OptionsTests(unittest.TestCase):
    def test_actual_volumes_are_observations_not_bullish_bearish_orders(self):
        message = render()
        self.assertIn("콜 거래량이 풋의 1.63배", message)
        self.assertIn("콜·풋 거래량 비슷", message)
        self.assertIn("매수·매도는 구분되지 않아", message)
        for misleading in ("시장 전체 위험선호는 중립", "지수 전체 방향성·헤지는 중립권", "상방 수요", "헤지 수요", "콜 매수 우위"):
            self.assertNotIn(misleading, message)

    def test_all_nine_volume_combinations_never_claim_market_direction(self):
        for equity in (0.6, 1.0, 1.4):
            for index in (0.6, 1.0, 1.4):
                values = snapshot()
                for prefix, ratio in (("equity", equity), ("index", index)):
                    m = values["Cboe|options"]["metrics"]
                    m[prefix + "_calls"] = 100
                    m[prefix + "_puts"] = round(ratio * 100)
                    m[prefix + "_pc_ratio"] = ratio
                message = render(values)
                self.assertIn("단기 판정: 하락 우세", message)
                self.assertNotIn("시장 전체 상방", message)
                self.assertNotIn("지수 하락 방어", message)

    def test_missing_volume_zero_volume_and_missing_ratio_are_distinct(self):
        self.assertEqual(presentation.volume_description(None, None, None), "거래량·비율 미확인")
        self.assertIn("공표 비율 기준", presentation.volume_description(None, None, 0.6))
        self.assertIn("비율 계산 불가", presentation.volume_description(0, 0, None))
        self.assertEqual(presentation.volume_description(0, 20, None), "콜 0 · 풋만 거래됨")
        self.assertEqual(presentation.volume_description(20, 0, 0), "풋 0 · 콜만 거래됨")


class RenderingTests(unittest.TestCase):
    def test_saved_numeric_detail_and_source_links_are_preserved(self):
        message = render()
        for value in ("11,684.38", "12,208.79", "-4.30%", "-7.06%", "-10.58%", "112,821", "37,965", "48,139", "74,877", "51,349", "70,561", "+5,511", "+13,032", "24.9%"):
            self.assertIn(value, message)
        for value in ("순숏 27 / 총숏 20 / 숏÷OI 17", "순숏 45 / 총숏 38 / 숏÷OI 21", "78.4%", "47.9%", "-2,312", "-8,985", "+25,649", "2026-09-22", "2,931,155", "1,799,662", "4,150,856", "4,181,999", "9,084,651", "7,998,416", "62.0%", "49.8%", "53.2%"):
            self.assertIn(value, message)
        for source in snapshot().values():
            self.assertIn(source["url"], message)

    def test_rendering_is_pure_and_has_no_input_mutation(self):
        values = snapshot()
        original = copy.deepcopy(values)
        self.assertEqual(render(values), render(values))
        self.assertEqual(values, original)

    def test_missing_history_is_visible_and_never_fabricates_zero_percentiles(self):
        values = snapshot()
        values["CFTC|cot"]["history_3y"] = {"error": "unavailable"}
        message = render(values)
        self.assertIn("3년 백분위: 공식 자료 확인 대기", message)
        self.assertIn("10년 백분위·최대 기록: 공식 자료 확인 대기", message)
        self.assertNotIn("순숏 0 /", message)

    def test_escaped_source_and_event_text_cannot_inject_html(self):
        values = snapshot()
        values["CFTC|cot"]["source"] = '<script>x</script>'
        message = render(values, event_label='<fake>')
        self.assertNotIn('<script>', message)
        self.assertIn('&lt;script&gt;', message)
        self.assertIn('&lt;fake&gt;', message)

    def test_current_snapshot_fits_one_existing_telegram_chunk_and_each_line_is_balanced(self):
        message = render()
        self.assertLessEqual(len(message.strip()), 3800)
        for line in message.splitlines():
            parser = TagBalance()
            parser.feed(line)
            self.assertFalse(parser.stack, line)
        self.assertLess(message.index("기간 종합"), message.index("원수치"))


class OperatingIntegrationTests(unittest.TestCase):
    """Execute the real collector tail with frozen, in-memory source snapshots.

    No network collectors are called; no live repository state or sender is used.
    The actual production freshness/math gates, dedupe and render call execute.
    """

    def run_operating_tail(self, values, prior_state=None, context=None):
        source = (ROOT / "scripts/us_positioning_watch.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        start = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "state" for target in node.targets))
        tail = ast.Module(body=tree.body[start:], type_ignores=[])

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 15, 7, 30, tzinfo=timezone.utc).astimezone(tz)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                "load_state": lambda: copy.deepcopy(prior_state or {"seen": {}, "values": {}}),
                "parse_cftc": lambda: copy.deepcopy(values["CFTC|cot"]),
                "parse_cboe": lambda: copy.deepcopy(values["Cboe|options"]),
                "parse_sox": lambda: copy.deepcopy(values["Nasdaq SOX|sox"]),
                "render_alert": presentation.render_alert,
                "render_detail_document": presentation.render_detail_document,
                "PRESENTATION_VERSION": presentation.PRESENTATION_VERSION,
                # The extracted tail normally runs after this module-level flag
                # has been set; these cases exercise the non-digest route.
                "DAILY_DIGEST": False,
                "STATUS": root / "status.md", "ALERT": root / "alert.html", "DETAIL": root / "detail.html", "PENDING": root / "pending.json",
                "os": os, "json": json, "datetime": FrozenDatetime, "OUT": root,
                "fp": lambda v: hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                "timezone": timezone, "timedelta": timedelta, "NQ_CFTC_CODE": "209742",
            }
            with patch.dict(os.environ, {"FORCE_SEND": "false", "GITHUB_RUN_ID": "", "GITHUB_REPOSITORY": ""}), patch("us_positioning_context.collect_context", return_value=copy.deepcopy(context or {})), redirect_stdout(io.StringIO()):
                exec(compile(tail, str(ROOT / "scripts/us_positioning_watch.py"), "exec"), env)
            return {
                "gate": env["quality_gate_ok"], "updates": len(env["updates"]), "sources": env["results"],
                "status": env["STATUS"].read_text(encoding="utf-8"),
                "alert": env["ALERT"].read_text(encoding="utf-8") if env["ALERT"].exists() else None,
                "detail": env["DETAIL"].read_text(encoding="utf-8") if env["DETAIL"].exists() else None,
                "pending": json.loads(env["PENDING"].read_text(encoding="utf-8")) if env["PENDING"].exists() else None,
            }

    def test_actual_saved_input_passes_original_math_gates_and_renders_new_layout(self):
        result = self.run_operating_tail(snapshot())
        self.assertTrue(result["gate"])
        self.assertEqual(result["updates"], 4)
        self.assertEqual(result["alert"], presentation.render_alert(snapshot()["CFTC|cot"], snapshot()["Cboe|options"], snapshot()["Nasdaq SOX|sox"], result["sources"], result["sources"]))
        self.assertEqual({k:result["pending"]["values"][k] for k in snapshot()}, snapshot())
        self.assertIn("미국 주요지수·시장 확산·옵션 과거 비교|context", result["pending"]["values"])
        self.assertEqual(result["pending"]["presentation_version"], presentation.PRESENTATION_VERSION)
        self.assertEqual(result["detail"], presentation.render_detail_document(snapshot()["CFTC|cot"], snapshot()["Cboe|options"], snapshot()["Nasdaq SOX|sox"], result["sources"], result["sources"]))

    def test_unchanged_snapshot_creates_no_message_or_pending_state(self):
        values = snapshot()
        first = self.run_operating_tail(values)
        second = self.run_operating_tail(values, first["pending"])
        self.assertTrue(second["gate"])
        self.assertEqual(second["updates"], 0)
        self.assertIsNone(second["alert"])
        self.assertIsNone(second["detail"])
        self.assertIsNone(second["pending"])

    def test_bad_math_never_reaches_the_new_message(self):
        values = snapshot()
        values["CFTC|cot"]["metrics"]["lev_net"] += 1
        result = self.run_operating_tail(values)
        self.assertFalse(result["gate"])
        self.assertIsNone(result["alert"])
        self.assertNotIn("CFTC|cot", result["pending"].get("seen", {}))
        self.assertNotIn("presentation_version", result["pending"])

    def test_new_presentation_sends_once_without_source_changes_and_preserves_saved_values(self):
        values = snapshot()
        prior = self.run_operating_tail(values)["pending"]
        prior.pop("presentation_version")
        unchanged = copy.deepcopy(prior)
        first = self.run_operating_tail(values, prior)
        self.assertEqual(first["updates"], 0)
        self.assertIn("요약형 전환", first["alert"])
        self.assertEqual(first["pending"]["seen"], prior["seen"])
        self.assertEqual(first["pending"]["values"], prior["values"])
        self.assertEqual(prior, unchanged)
        second = self.run_operating_tail(values, first["pending"])
        self.assertIsNone(second["alert"])
        self.assertIsNone(second["pending"])

    def test_presentation_version_does_not_bypass_the_source_gate(self):
        values = snapshot()
        prior = self.run_operating_tail(values)["pending"]
        prior["presentation_version"] = "old-layout"
        values["CFTC|cot"]["metrics"]["lev_net"] += 1
        first = self.run_operating_tail(values, prior)
        self.assertFalse(first["gate"])
        self.assertIsNone(first["alert"])
        self.assertIsNone(first["detail"])
        self.assertIsNone(first["pending"])

    def test_stale_source_keeps_original_collection_gate_closed(self):
        values = snapshot()
        values["CFTC|cot"]["period"] = "September 1, 2026"
        result = self.run_operating_tail(values)
        self.assertFalse(result["gate"])
        self.assertIsNone(result["alert"])


if __name__ == "__main__":
    unittest.main()
