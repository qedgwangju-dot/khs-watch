"""Pure delivery receipt and deduplication rules for the Treasury daily report."""
EXPECTED_BOT_USERNAME = "khs8879887988798879_bot"


def _valid_receipt(record, date_key, expected_date):
    record = record or {}
    return (
        bool(expected_date)
        and record.get(date_key) == expected_date
        and bool(record.get("message_ids"))
        and record.get("bot_username") == EXPECTED_BOT_USERNAME
    )


def source_delivery_complete(state, source_date):
    return _valid_receipt((state or {}).get("last_delivery"), "treasury_date", source_date)


def daily_delivery_complete(state, delivery_date_kst):
    return _valid_receipt(
        (state or {}).get("last_delivery"),
        "daily_delivery_date_kst",
        delivery_date_kst,
    )


def daily_status_notification_complete(state, delivery_date_kst):
    return _valid_receipt(
        (state or {}).get("daily_status_notification"),
        "date_kst",
        delivery_date_kst,
    )


def should_run_delivery(state, source_date, delivery_date_kst, daily_digest, validate_only=False):
    if validate_only:
        return True
    if daily_digest:
        return not daily_delivery_complete(state, delivery_date_kst)
    return not source_delivery_complete(state, source_date)


def should_send_daily_status(state, delivery_date_kst):
    return (
        not daily_delivery_complete(state, delivery_date_kst)
        and not daily_status_notification_complete(state, delivery_date_kst)
    )
