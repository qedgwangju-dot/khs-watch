"""Confirmed-part receipts for retryable, lossless Telegram policy bundles."""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Callable


def deliver_policy_parts(
    parts: list[str], *, digest: str, route: str, title: str,
    sent_state: dict, now_utc: dt.datetime, dedupe_hours: int,
    send: Callable[[str], int], checkpoint: Callable[[dict], None],
    force: bool = False,
) -> dict:
    confirmed_ids: list[int] = []
    new_ids: list[int] = []
    stamp = now_utc.isoformat().replace("+00:00", "Z")
    for index, text in enumerate(parts, 1):
        part_key = "part-" + hashlib.sha256(f"{route}|{digest}|{index}|{text}".encode()).hexdigest()[:24]
        receipt = sent_state.get(part_key, {})
        try:
            sent_at = dt.datetime.fromisoformat(str(receipt.get("sent_at_utc", "")).replace("Z", "+00:00"))
            recent = dt.timedelta(0) <= now_utc - sent_at < dt.timedelta(hours=dedupe_hours)
        except (TypeError, ValueError):
            recent = False
        if not force and recent and receipt.get("message_id") is not None:
            confirmed_ids.append(int(receipt["message_id"]))
            continue
        message_id = send(text)
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
            raise RuntimeError("Telegram part has no valid confirmed message_id")
        confirmed_ids.append(message_id)
        new_ids.append(message_id)
        sent_state[part_key] = {
            "sent_at_utc": stamp, "route": route, "title": title,
            "parent_digest": digest, "part_index": index, "part_count": len(parts),
            "message_id": message_id,
        }
        # Persist the acknowledgment before sending the next part.
        checkpoint({"status": "partial", "route": route, "digest": digest,
                    "confirmed_message_ids": list(confirmed_ids), "new_message_ids": list(new_ids)})
    if confirmed_ids:
        sent_state[digest] = {
            "sent_at_utc": stamp, "title": title, "route": route,
            "message_id": confirmed_ids[-1], "message_ids": confirmed_ids,
        }
        checkpoint({"status": "complete", "route": route, "digest": digest,
                    "confirmed_message_ids": list(confirmed_ids), "new_message_ids": list(new_ids)})
    return {"confirmed_message_ids": confirmed_ids, "new_message_ids": new_ids}
