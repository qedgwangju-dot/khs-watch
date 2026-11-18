"""No-send checks for RSS provenance and final-render dedup reconciliation."""
import datetime as dt
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import robotis_physical_ai_watch as base


def run():
    rss = b'''<rss><channel><item><title>Confirmed robot milestone</title>
    <link>https://news.google.com/rss/articles/opaque</link><description>Example</description>
    <pubDate>Wed, 18 Nov 2026 01:00:00 GMT</pubDate>
    <source url="https://bostondynamics.com">Boston Dynamics</source>
    </item></channel></rss>'''
    with patch.object(base, "fetch", return_value=rss):
        row = base.query_news("fixture")[0]
    assert row["source_url"] == "https://bostondynamics.com"
    assert row["link"].startswith("https://news.google.com/")
    assert not row.get("original_body_verified"), "RSS provenance is not body verification"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        with patch.object(base, "PENDING_PATH", path / "pending.json"), \
             patch.object(base, "ALERT_PATH", path / "alert.txt"):
            pre = {"seeded": True, "seen": ["historic", "already-delivered"]}
            pending = {"seen": ["historic", "retained", "filtered", "already-delivered"],
                       "last_selected": ["retained", "filtered", "already-delivered"],
                       "last_selected_events": [
                           {"key": "retained", "link": "https://example.com/a?x=1&y=2"},
                           {"key": "filtered", "link": "https://example.com/stock-noise"},
                           {"key": "already-delivered", "link": "https://example.com/old"}]}
            base.PENDING_PATH.write_text(json.dumps(pending))
            base.ALERT_PATH.write_text('<a href="https://example.com/a?x=1&amp;y=2">원문</a>')
            base.reconcile_pending_with_rendered(pre)
            result = json.loads(base.PENDING_PATH.read_text())
            assert result["last_selected"] == ["retained"]
            assert result["seen"] == ["historic", "already-delivered", "retained"]
            assert len(result["last_selected_events"]) == 1
            assert "filtered" not in result["seen"], "Unsent filtered event must remain eligible"
            # An entirely suppressed message also consumes no new key.
            base.ALERT_PATH.write_text("")
            base.reconcile_pending_with_rendered(pre)
            result = json.loads(base.PENDING_PATH.read_text())
            assert result["last_selected"] == []
            assert result["seen"] == pre["seen"]
            # Preserve initial no-alert seeding, including its established keys.
            seeded = {"seen": ["baseline"], "last_selected": [], "last_selected_events": []}
            base.PENDING_PATH.write_text(json.dumps(seeded))
            before = base.PENDING_PATH.read_bytes()
            base.reconcile_pending_with_rendered({"seeded": False, "seen": []})
            assert base.PENDING_PATH.read_bytes() == before
    print("RSS provenance / final-render selected-key reconciliation: PASS")

    # A successful HTTP fetch with malformed data is not a successful query.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sample = {"title": "fixture", "description": "", "source": "fixture",
                  "link": "https://example.com/valid", "published": base.NOW.isoformat()}
        with patch.object(base, "STATE_PATH", root / "state.json"), \
             patch.object(base, "PENDING_PATH", root / "pending.json"), \
             patch.object(base, "ALERT_PATH", root / "alert.txt"), \
             patch.object(base, "STATUS_PATH", root / "status.md"), \
             patch.object(base, "OUT_DIR", root), \
             patch.object(base, "FORCE", False), \
             patch.object(base, "QUERIES", ["valid", "malformed"]), \
             patch.object(base, "query_news", side_effect=lambda q: [dict(sample)] if q == "valid" else [{}]), \
             patch.object(base, "topic_group", return_value="robotis"), \
             patch.object(base, "key", return_value="fixture-key"), \
             patch.object(base, "score", return_value=20), \
             contextlib.redirect_stdout(io.StringIO()):
            base.main()
            status = base.STATUS_PATH.read_text()
            assert "queries_ok: 1/2" in status
            assert "malformed: KeyError" in status
    print("Malformed fetched source is reported as a processing failure: PASS")


if __name__ == "__main__":
    run()
