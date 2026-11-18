"""Run the actual rendering chain without network, sending, or state mutation."""
import contextlib
import datetime as dt
import html
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import physical_ai_watch_airan_guard as entry
import robot_watch_nov18_verified_events as events
from robot_watch_delivery import build_chunks


def run():
    base = entry.base
    original_state_bytes = base.STATE_PATH.read_bytes()
    original_state = json.loads(original_state_bytes)
    original_seen = set(original_state["seen"])
    expected = {events.event_key(name) for name in events.EVENTS} - original_seen
    delivered = set()
    counts = []
    with tempfile.TemporaryDirectory(prefix="robot-full-render-") as temporary:
        root = Path(temporary)
        with patch.object(base, "NOW", dt.datetime(2026, 11, 18, 6, tzinfo=dt.timezone.utc)), \
             patch.object(base, "FORCE", False), \
             patch.object(base, "QUERIES", [events.BACKFILL]), \
             patch.object(base, "query_news", side_effect=lambda q: events.rows(base.NOW)), \
             patch.object(base, "STATE_PATH", root / "state.json"), \
             patch.object(base, "PENDING_PATH", root / "pending.json"), \
             patch.object(base, "ALERT_PATH", root / "alert.txt"), \
             patch.object(base, "STATUS_PATH", root / "status.md"), \
             patch.object(base, "OUT_DIR", root), \
             patch.object(entry.qty.current, "_usdkrw", return_value=(1330.2, True)), \
             patch.object(entry.qty, "_official_prices", return_value=({}, {})), \
             patch("socket.create_connection", side_effect=AssertionError("offline test attempted network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("offline test attempted HTTP")):
            base.STATE_PATH.write_bytes(original_state_bytes)
            for attempt in range(3):
                before = base.load_state()
                with contextlib.redirect_stdout(io.StringIO()):
                    base.main()
                    entry.qty.current.opt.current.fig.legacy.repair_pending_seen(before)
                    entry.qty.current.opt._finalize_alert_text()
                    entry.qty.current._append_value_estimate()
                    entry.qty.enrich_quantity_values()
                    entry._finalize_airan_criteria()
                    base.reconcile_pending_with_rendered(before)
                pending = json.loads(base.PENDING_PATH.read_text(encoding="utf-8"))
                rendered = base.ALERT_PATH.read_text(encoding="utf-8")
                selected = set(pending["last_selected"])
                chunks = build_chunks(rendered, pending)
                assert {key for chunk in chunks for key in chunk["event_keys"]} == selected
                assert original_seen <= set(pending["seen"]), "Historical delivery keys changed"
                assert not selected & delivered, "A delivered event repeated"
                assert len(selected) <= base.MAX_ALERTS, "Existing cap changed"
                assert events.event_key("lg_safety") not in selected, "Previously delivered LG MOU replayed"
                assert "11/18 00:00" not in rendered, "An unknown publication minute was invented"
                for record in pending["last_selected_events"]:
                    assert record["key"] in selected
                    assert html.escape(record["link"], quote=True) in rendered, ("Selected original link disappeared", record["title"])
                delivered |= selected
                counts.append(len(selected))
                # Simulate only successful persistence; this test never sends.
                base.STATE_PATH.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")
                if attempt == 2:
                    assert not rendered.strip(), "Third identical scan should remain silent"
            assert delivered == expected, ("Missing or extra reviewed events", expected - delivered, delivered - expected)
    assert base.STATE_PATH.read_bytes() == original_state_bytes, "Test modified production state"
    print(f"Actual rendering chain / retained state / overflow / repeat silence: PASS {counts}")


if __name__ == "__main__":
    run()
