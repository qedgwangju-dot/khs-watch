from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import us_positioning_etf_short_interest as etf


def _chart(current, previous):
    return f"""<table><tr><th>Settlement Date</th><th>Short Interest %</th><th>Short Position</th><th>Days To Cover</th><th>Short Change</th><th>Change %</th></tr>
    <tr><td>2026-10-15</td><td>12.26</td><td>{current:,}</td><td>2.41</td><td>+10,000,000</td><td>16.38</td></tr>
    <tr><td>2026-09-30</td><td>10.50</td><td>{previous:,}</td><td>1.95</td><td>+4,000,000</td><td>7.19</td></tr>
    </table>"""


def _benz(current, previous):
    return f"""<table><tr><th>Settlement Date</th><th>Dissemination Date</th><th>% Float</th><th>Float</th><th>Short Interest</th><th>Volume</th><th>Days to Cover</th></tr>
    <tr><td>Oct 15, 2026</td><td>Oct 26, 2026</td><td>—</td><td>—</td><td>{current:,}</td><td>33,969,720</td><td>2.41</td></tr>
    <tr><td>Sep 30, 2026</td><td>Oct 9, 2026</td><td>—</td><td>—</td><td>{previous:,}</td><td>36,049,629</td><td>1.95</td></tr>
    </table>"""


def _finshort(current, previous):
    return f"""<table><tr><th>Settlement date</th><th>Short interest</th><th>Change</th></tr>
    <tr><td>Oct 15, 2026</td><td>{current:,}</td><td>+16.38%</td></tr>
    <tr><td>Sep 30, 2026</td><td>{previous:,}</td><td>+7.19%</td></tr>
    </table>"""


CALENDAR = """<table><tr><th>Settlement Date</th><th>Due Date</th><th>Publication Date</th></tr>
<tr><td>October 15 (Thursday)</td><td>October 19 – 6:00 p.m. (Monday)</td><td>October 26 (Monday)</td></tr>
<tr><td>October 30 (Friday)</td><td>November 3 – 6:00 p.m. (Tuesday)</td><td>November 10 (Tuesday)</td></tr>
</table>"""


def _getter(*, spy=None, qqq=None, corrupt=False):
    amounts = {
        "QQQ": qqq or (82_001_618, 70_458_005),
        "SPY": spy or (92_995_326, 98_476_070),
    }

    def get(url):
        if "finra.org" in url:
            return CALENDAR
        ticker = "QQQ" if "QQQ" in url or "qqq/" in url else "SPY"
        current, previous = amounts[ticker]
        if "chartexchange" in url:
            return _chart(current + (11 if corrupt else 0), previous)
        if "benzinga" in url:
            return _benz(current, previous)
        if "finshort" in url:
            return _finshort(current, previous)
        raise AssertionError("Unexpected endpoint")
    return get


def test_finra_calendar_matches_verifiable_2026_dates():
    actual = etf.read_calendar(CALENDAR, 2026)
    assert actual["2026-10-15"] == "2026-10-26"
    assert actual["2026-10-30"] == "2026-11-10"


@pytest.mark.parametrize("provider,html", [
    ("chartexchange", _chart(82_001_618, 70_458_005)),
    ("benzinga", _benz(82_001_618, 70_458_005)),
    ("finshort", _finshort(82_001_618, 70_458_005)),
])
def test_short_interest_parse_is_twice_monthly_position_not_daily_volume(provider, html):
    rows = etf.parse_provider(provider, html)
    assert rows[0] == {"settlement": "2026-10-15", "shares": 82_001_618}
    assert rows[1] == {"settlement": "2026-09-30", "shares": 70_458_005}


def test_qqq_spy_oct_15_opposite_short_interest_shifts_verified():
    data = etf.collect(now=dt.date(2026, 11, 1), getter=_getter())
    assert data["QQQ"]["shares"] == 82_001_618
    assert data["QQQ"]["change_shares"] == 11_543_613
    assert data["SPY"]["shares"] == 92_995_326
    assert data["SPY"]["change_shares"] == -5_480_744
    assert round(data["QQQ"]["change_pct"], 2) == 16.38
    assert round(data["SPY"]["change_pct"], 2) == -5.57
    assert round(data["divergence_pp"], 2) == 21.95
    assert data["signal"] is True
    assert data["published"] == "2026-10-26"
    assert all(data[t]["publisher_count"] >= 2 for t in ("QQQ", "SPY"))
    title, body = etf.render(data)
    assert "2026-10-15" in body and "2026-10-26" in body
    assert "QQQ" in body and "SPY" in body
    assert "공매도" in title and len(title) + len(body) < 3900


def test_one_conflicting_publisher_is_not_used_for_consensus():
    data = etf.collect(now=dt.date(2026, 11, 1), getter=_getter(corrupt=True))
    assert data["QQQ"]["shares"] == 82_001_618
    assert "chartexchange" not in data["QQQ"]["sources"]


def test_not_publishable_before_finra_release_or_after_recency_limit():
    with pytest.raises(RuntimeError, match="not current"):
        etf.collect(now=dt.date(2026, 10, 25), getter=_getter())
    with pytest.raises(RuntimeError, match="not current"):
        etf.collect(now=dt.date(2026, 11, 12), getter=_getter())


def test_qqq_spy_divergence_not_automatic_crash_or_daily_short_volume():
    flat = etf.collect(now=dt.date(2026, 11, 1),
                       getter=_getter(qqq=(71_000_000, 70_458_005),
                                      spy=(99_000_000, 98_476_070)))
    assert not flat["signal"]
    assert "ETF 헤지" in etf.render(flat)[1]


def test_first_alert_validate_mode_cannot_send_or_advance_state(monkeypatch, tmp_path):
    path = tmp_path / "state.json"
    monkeypatch.setattr(etf, "send_message", lambda *args, **kwargs: pytest.fail("validate mode sent Telegram"))
    observed = etf.run(validate_only=True, now=dt.date(2026, 11, 1),
                       getter=_getter(), state_path=path)
    assert observed["status"] == "alert_due"
    assert observed["telegram_sent"] is False
    assert not path.exists()


def test_sent_event_deduplicates_and_records_verified_receipt(monkeypatch, tmp_path):
    path = tmp_path / "state.json"
    messages = []
    def fake_send(title, body):
        messages.append(body)
        return {"message_id": 102, "chat_id_returned": True,
                "chat_id_match": True, "bot_username": etf.EXPECTED_BOT}
    monkeypatch.setattr(etf, "send_message", fake_send)
    first = etf.run(validate_only=False, now=dt.date(2026, 11, 1),
                    getter=_getter(), state_path=path)
    assert first["telegram_sent"]
    assert json.loads(path.read_text())["last_alert"]["message_id"] == 102
    second = etf.run(validate_only=False, now=dt.date(2026, 11, 1),
                     getter=_getter(), state_path=path)
    assert second["status"] == "duplicate_suppressed"
    assert len(messages) == 1


def test_corrupt_existing_state_fails_closed(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{NOT JSON")
    with pytest.raises(RuntimeError, match="refuse to reset|unreadable"):
        etf.load_state(path)


def test_qqq_spy_requires_exact_compatible_periods():
    fake = _benz(82_001_618, 70_458_005).replace("Oct 15, 2026", "Oct 13, 2026")
    assert etf.parse_provider("benzinga", fake)[0]["settlement"] == "2026-10-13"


def test_finra_daily_short_sale_volume_not_a_valid_position_record():
    html = "<p>QQQ daily short volume 20,683,025 on October 30 2026</p>"
    with pytest.raises(ValueError):
        etf.parse_provider("finshort", html)
