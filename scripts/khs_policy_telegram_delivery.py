"""Confirmed-part receipts for retryable, lossless Telegram policy bundles."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Callable


def _semantic_delivery_digest(parts: list[str], *, digest: str, route: str, title: str) -> str:
    """Collapse known policy event families across parallel alert lanes."""
    text = re.sub(r"\s+", " ", f"{title} {' '.join(parts)}").lower()
    dpa = "defense production act" in text or re.search(r"\bdpa\b", text) is not None
    alaska = any(term in text for term in ("beluga-healy", "beluga healy", "alaska railbelt"))
    grid = any(term in text for term in (
        "전력망", "송전", "변압기", "grid", "transmission", "transformer", "substation"
    ))
    if dpa and alaska and grid:
        return hashlib.sha256(
            f"{route}|semantic|us-grid-dpa-beluga-healy-funding-2026-10-05".encode()
        ).hexdigest()[:20]
    section303 = "제303조" in text or "section 303" in text
    equipment = sum(
        term in text
        for term in (
            "변압기", "송전선", "도체", "변전소", "고압차단기", "보호계전",
            "커패시터뱅크", "전기강판", "transformer", "transmission line",
            "conductor", "substation", "circuit breaker", "capacitor bank",
            "electrical core steel",
        )
    )
    if dpa and section303 and equipment >= 2:
        return hashlib.sha256(
            f"{route}|semantic|us-grid-dpa-section303-base-2026-04-20".encode()
        ).hexdigest()[:20]
    return digest


def deliver_policy_parts(
    parts: list[str], *, digest: str, route: str, title: str,
    sent_state: dict, now_utc: dt.datetime, dedupe_hours: int,
    send: Callable[[str], int], checkpoint: Callable[[dict], None],
    force: bool = False,
) -> dict:
    effective_digest = _semantic_delivery_digest(
        parts, digest=digest, route=route, title=title
    )
    confirmed_ids: list[int] = []
    new_ids: list[int] = []
    stamp = now_utc.isoformat().replace("+00:00", "Z")
    for index, text in enumerate(parts, 1):
        part_key = "part-" + hashlib.sha256(
            f"{route}|{effective_digest}|{index}|{text}".encode()
        ).hexdigest()[:24]
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
        checkpoint({"status": "partial", "route": route, "digest": effective_digest,
                    "confirmed_message_ids": list(confirmed_ids), "new_message_ids": list(new_ids)})
    if confirmed_ids:
        sent_state[effective_digest] = {
            "sent_at_utc": stamp, "title": title, "route": route,
            "message_id": confirmed_ids[-1], "message_ids": confirmed_ids,
        }
        checkpoint({"status": "complete", "route": route, "digest": effective_digest,
                    "confirmed_message_ids": list(confirmed_ids), "new_message_ids": list(new_ids)})
    return {"confirmed_message_ids": confirmed_ids, "new_message_ids": new_ids}
