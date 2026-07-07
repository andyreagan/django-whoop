"""Incoming webhook processing.

WHOOP delivers one event per POST — a small JSON object naming the user, the
resource, and what happened::

    {"user_id": 10129, "id": "ecfc6a15-...", "type": "sleep.updated", "trace_id": "..."}

``*.updated`` fires for creates and updates alike; the payload carries no
resource data, so processing means fetching the resource with the matching
user's credentials and re-ingesting it. Events route to users via
``user_id``, so a connection whose ``whoop_user_id`` is unknown is skipped
with a warning.

Signature validation: WHOOP signs every delivery with the app's client
secret — ``base64(HMAC_SHA256(timestamp + raw_body, client_secret))`` in the
``X-WHOOP-Signature`` header, timestamp (unix milliseconds) in
``X-WHOOP-Signature-Timestamp``. :func:`signature_matches` implements the
check; the receiver view enforces it whenever ``WHOOP_CLIENT_SECRET`` is set.

``*.deleted`` events are acknowledged but not processed — healthdatamodel has
no deletion API yet; they're logged so the gap is visible.

:func:`process_event` is safe to call from a queue worker — the receiver view
only emits the :data:`whoop.signals.event_received` signal, and your handler
decides whether to process inline or hand off. WHOOP retries non-2xx
deliveries five times over ~an hour and expects a response within a second.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

from .client import WhoopClient
from .constants import (
    COLLECTION_RECOVERIES,
    COLLECTION_SLEEPS,
    COLLECTION_WORKOUTS,
    EVENT_RECOVERY_UPDATED,
    EVENT_SLEEP_UPDATED,
    EVENT_WORKOUT_UPDATED,
)
from .ingest import ingest_resources
from .models import WhoopConnection

log = logging.getLogger(__name__)


def signature_matches(
    *,
    signature: str | None,
    timestamp: str | None,
    body: bytes,
    secret: str | None = None,
) -> bool:
    """Validate ``X-WHOOP-Signature`` for a raw request body.

    Constant-time comparison; missing header or secret fails closed.
    """
    if secret is None:
        secret = getattr(settings, "WHOOP_CLIENT_SECRET", "")
    if not signature or timestamp is None or not secret:
        return False
    digest = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def process_event(payload: dict[str, Any]) -> int:
    """Fetch + ingest the resource named by one webhook event.

    Returns the number of records/workouts written (0 for deletes, unknown
    event types, and unroutable users — logged, never raised, so a webhook
    delivery is always acknowledged).
    """
    event_type = str(payload.get("type") or "")
    resource_id = payload.get("id")
    user_id = str(payload.get("user_id") or "")

    if not user_id or resource_id is None:
        log.warning("Skipping webhook event without user_id/id: %r", payload)
        return 0

    if event_type.endswith(".deleted"):
        # healthdatamodel has no deletion API; surface the gap in logs.
        log.info(
            "Ignoring %s for whoop user %s (id=%s)", event_type, user_id, resource_id
        )
        return 0

    try:
        connection = WhoopConnection.objects.get(whoop_user_id=user_id)
    except WhoopConnection.DoesNotExist:
        log.warning("Webhook event for unknown whoop user_id=%s", user_id)
        return 0

    with WhoopClient(connection) as client:
        if event_type == EVENT_WORKOUT_UPDATED:
            resources = [client.get_workout(str(resource_id))]
            collection = COLLECTION_WORKOUTS
        elif event_type == EVENT_SLEEP_UPDATED:
            resources = [client.get_sleep(str(resource_id))]
            collection = COLLECTION_SLEEPS
        elif event_type == EVENT_RECOVERY_UPDATED:
            # The event's id is the associated *sleep* UUID; recovery itself
            # is addressed by cycle. Resolve sleep → cycle_id → recovery.
            sleep = client.get_sleep(str(resource_id))
            cycle_id = sleep.get("cycle_id")
            if cycle_id is None:
                log.warning(
                    "recovery.updated: sleep %s has no cycle_id; skipping", resource_id
                )
                return 0
            resources = [client.get_cycle_recovery(cycle_id)]
            collection = COLLECTION_RECOVERIES
        else:
            log.info("Ignoring unknown webhook event type %r", event_type)
            return 0

        count = ingest_resources(connection, collection, resources)

    connection.last_sync_at = datetime.now(timezone.utc)
    connection.save(update_fields=["last_sync_at"])
    return count
