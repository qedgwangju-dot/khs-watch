"""Exercise the deployed inline translator without network or real state writes."""
import ast
import contextlib
import html
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from scripts import ai_networking_optics_delivery as delivery

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ai-networking-optics-telegram-watch.yml"
RAW_TITLE = "Lambda Touts First CPO Deployment of Blackwell GPUs - HPCwire"
KOREAN_TITLE = "Lambda, Blackwell GPU 기반 첫 CPO 구축 사례 강조"


def translation_source():
    block = WORKFLOW.read_text(encoding="utf-8").split(
        "      - name: Translate alert to Korean, remove source timestamp, and convert currency to KRW", 1
    )[1].split("      - name: Validate immediate KRW conversion rule", 1)[0]
    return textwrap.dedent(block.split("python - <<'PY'\n", 1)[1].rsplit("\n          PY", 1)[0])


def translation_functions():
    tree = ast.parse(translation_source())
    constants = {"kst", "keep_terms", "DISPLAY_KO", "FX_SYMBOLS", "CURRENCY_NAMES",
                 "fx_cache", "VERIFIED_HEADLINE_TRANSLATIONS"}
    nodes = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))
             or isinstance(node, ast.Assign) and all(isinstance(target, ast.Name) and target.id in constants
                                                    for target in node.targets)]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(WORKFLOW), "exec"), namespace)
    return namespace


def response(value):
    return io.BytesIO(json.dumps([[[value, "original", None, None]], None, "en"]).encode())


class OpticsTranslationTests(unittest.TestCase):
    def setUp(self):
        self.functions = translation_functions()
        self.translate = self.functions["translate_to_korean"]

    def test_observed_hpcwire_title_retains_subject_product_claim_without_api(self):
        with patch.object(urllib.request, "urlopen", side_effect=AssertionError("reviewed title must not need API")) as get:
            self.assertEqual(self.translate(RAW_TITLE), KOREAN_TITLE)
            self.assertEqual(self.translate("  Lambda Touts First CPO Deployment of Blackwell GPUs  "), KOREAN_TITLE)
        get.assert_not_called()
        for term in ("Lambda", "Blackwell", "GPU", "CPO", "첫", "구축", "강조"):
            self.assertIn(term, KOREAN_TITLE)

    def test_reviewed_translation_does_not_rewrite_different_deployment(self):
        title = "Lambda Announces Second CPO Deployment of Blackwell GPUs"
        translated = "Lambda가 Blackwell GPU를 활용한 두 번째 CPO 구축을 발표했습니다."
        with patch.object(urllib.request, "urlopen", return_value=response(translated)) as get:
            self.assertEqual(self.translate(title), translated)
        get.assert_called_once()

    def test_other_company_translation_and_currency_tokens_still_work(self):
        translated = "코히런트가 광학 공장 증설에 $350M 규모로 투자합니다."
        with patch.object(urllib.request, "urlopen", return_value=response(translated)):
            result = self.translate("Coherent invests $350M in an optical factory - Reuters")
        self.assertIn("코히런트", result)
        self.assertIn("35,000만달러", result)

    def test_lost_named_subject_and_corrupted_identifier_remain_blocked(self):
        for raw, translated, reason in (
            ("Coherent expands optical factory", "광학 공장을 확장합니다.", "lost named subject"),
            ("Lambda expands CPO deployment", "Lambda가 ZX KEEP 48 QZ 구축을 확대합니다.", "protected identifier"),
        ):
            with self.subTest(reason=reason), patch.object(urllib.request, "urlopen", return_value=response(translated)):
                with self.assertRaisesRegex(RuntimeError, reason):
                    self.translate(raw)

    def test_exhausted_translation_keeps_provider_error_for_diagnosis(self):
        error = urllib.error.HTTPError("https://translate.google.com/translate_a/single", 429,
                                       "Too Many Requests", None, None)
        log = io.StringIO()
        with patch.object(urllib.request, "urlopen", side_effect=error) as get, patch.object(
            self.functions["time"], "sleep", return_value=None
        ), contextlib.redirect_stdout(log):
            with self.assertRaisesRegex(RuntimeError, "HTTPError: HTTP Error 429"):
                self.translate("Lambda announces a new optical cluster")
        self.assertEqual(get.call_count, 6)
        self.assertIn("translate.googleapis.com", log.getvalue())
        self.assertIn("translate.google.com", log.getvalue())
        self.assertIn("429", log.getvalue())

    @contextlib.contextmanager
    def temporary_run(self, titles):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                Path("out").mkdir()
                Path("data").mkdir()
                text = "<b>검증용 광통신 알림</b>\n" + "".join(
                    "• 원문 제목: " + html.escape(title) + "\n" for title in titles
                ) + "• 출처·시각: 검증용 출처\n• 원문: https://example.test/article\n"
                delivery.ALERT_PATH.write_text(text, encoding="utf-8")
                delivery.atomic_json(delivery.STATE_PATH, {"seen_keys": ["previously-delivered"]})
                delivery.atomic_json(delivery.PENDING_PATH, {"seen_keys": ["unsent", "previously-delivered"]})
                yield text
            finally:
                os.chdir(previous)

    def test_full_translation_stage_produces_complete_title_and_preserves_other_lines(self):
        with self.temporary_run([RAW_TITLE]), patch.object(urllib.request, "urlopen", side_effect=AssertionError("unexpected network")), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(translation_source(), str(WORKFLOW), "exec"), {})
            rendered = delivery.ALERT_PATH.read_text(encoding="utf-8")
            self.assertIn("• 제목: " + KOREAN_TITLE, rendered)
            self.assertNotIn("확인 불가", rendered)
            self.assertNotIn("출처·시각", rendered)
            self.assertIn("• 원문: https://example.test/article", rendered)
            self.assertEqual(delivery.read_json(delivery.STATE_PATH)["seen_keys"], ["previously-delivered"])

    def test_failed_title_leaves_full_payload_pending_and_seen_unchanged(self):
        with self.temporary_run([RAW_TITLE, "Coherent expands optical factory"]) as original, patch.object(
            urllib.request, "urlopen", return_value=response("광학 공장을 확장합니다.")
        ), patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}), contextlib.redirect_stdout(io.StringIO()) as log:
            pending_before = delivery.PENDING_PATH.read_bytes()
            seen_before = delivery.STATE_PATH.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "Korean title incomplete"):
                exec(compile(translation_source(), str(WORKFLOW), "exec"), {})
            self.assertIn("lost named subject", log.getvalue())
            self.assertEqual(delivery.ALERT_PATH.read_text(encoding="utf-8"), original)
            self.assertEqual(delivery.PENDING_PATH.read_bytes(), pending_before)
            # The workflow's always() persistence step must not consume this alert.
            delivery.persist_state()
            self.assertEqual(delivery.STATE_PATH.read_bytes(), seen_before)
            self.assertFalse(delivery.CONFIRMED_PATH.exists())
            self.assertNotIn("제목 번역: 확인 불가", delivery.ALERT_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
