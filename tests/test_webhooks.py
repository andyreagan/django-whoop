import base64
import hashlib
import hmac

import pytest
import respx
from healthdatamodel.models import Record, Workout
from httpx import Response

from whoop import webhooks
from whoop.constants import API_BASE_URL

from .test_ingest import RECOVERY, SLEEP, WORKOUT


class TestSignatureMatches:
    BODY = b'{"user_id": 10129}'
    TIMESTAMP = "1700000000000"
    SECRET = "test-client-secret"

    def _signature(self, body=BODY, timestamp=TIMESTAMP, secret=SECRET):
        digest = hmac.new(
            secret.encode(), timestamp.encode() + body, hashlib.sha256
        ).digest()
        return base64.b64encode(digest).decode()

    def test_valid_signature(self):
        assert webhooks.signature_matches(
            signature=self._signature(),
            timestamp=self.TIMESTAMP,
            body=self.BODY,
        )

    def test_wrong_secret_fails(self):
        assert not webhooks.signature_matches(
            signature=self._signature(secret="other"),
            timestamp=self.TIMESTAMP,
            body=self.BODY,
        )

    def test_tampered_body_fails(self):
        assert not webhooks.signature_matches(
            signature=self._signature(),
            timestamp=self.TIMESTAMP,
            body=b'{"user_id": 666}',
        )

    def test_tampered_timestamp_fails(self):
        assert not webhooks.signature_matches(
            signature=self._signature(),
            timestamp="1700000099999",
            body=self.BODY,
        )

    def test_missing_pieces_fail_closed(self):
        assert not webhooks.signature_matches(
            signature=None, timestamp=self.TIMESTAMP, body=self.BODY
        )
        assert not webhooks.signature_matches(
            signature=self._signature(), timestamp=None, body=self.BODY
        )
        assert not webhooks.signature_matches(
            signature=self._signature(),
            timestamp=self.TIMESTAMP,
            body=self.BODY,
            secret="",
        )


@pytest.mark.django_db
class TestProcessEvent:
    @respx.mock
    def test_sleep_updated_fetches_and_ingests(self, connection):
        respx.get(f"{API_BASE_URL}/v2/activity/sleep/{SLEEP['id']}").mock(
            return_value=Response(200, json=SLEEP)
        )
        count = webhooks.process_event(
            {"user_id": 10129, "id": SLEEP["id"], "type": "sleep.updated"}
        )
        assert count == 5
        assert Record.objects.filter(customer=connection.customer).count() == 5
        connection.refresh_from_db()
        assert connection.last_sync_at is not None

    @respx.mock
    def test_workout_updated_fetches_and_ingests(self, connection):
        respx.get(f"{API_BASE_URL}/v2/activity/workout/{WORKOUT['id']}").mock(
            return_value=Response(200, json=WORKOUT)
        )
        count = webhooks.process_event(
            {"user_id": 10129, "id": WORKOUT["id"], "type": "workout.updated"}
        )
        assert count == 1
        assert Workout.objects.filter(customer=connection.customer).count() == 1

    @respx.mock
    def test_recovery_updated_resolves_sleep_then_cycle(self, connection):
        respx.get(f"{API_BASE_URL}/v2/activity/sleep/{RECOVERY['sleep_id']}").mock(
            return_value=Response(200, json={**SLEEP, "id": RECOVERY["sleep_id"]})
        )
        respx.get(f"{API_BASE_URL}/v2/cycle/{SLEEP['cycle_id']}/recovery").mock(
            return_value=Response(200, json=RECOVERY)
        )
        count = webhooks.process_event(
            {"user_id": 10129, "id": RECOVERY["sleep_id"], "type": "recovery.updated"}
        )
        assert count == 5

    def test_deleted_events_acknowledged_but_skipped(self, connection):
        count = webhooks.process_event(
            {"user_id": 10129, "id": SLEEP["id"], "type": "sleep.deleted"}
        )
        assert count == 0

    def test_unknown_user_skipped(self, db):
        count = webhooks.process_event(
            {"user_id": 424242, "id": SLEEP["id"], "type": "sleep.updated"}
        )
        assert count == 0

    def test_unknown_event_type_skipped(self, connection):
        count = webhooks.process_event(
            {"user_id": 10129, "id": "x", "type": "something.new"}
        )
        assert count == 0

    def test_malformed_payload_skipped(self, db):
        assert webhooks.process_event({}) == 0
        assert webhooks.process_event({"type": "sleep.updated"}) == 0
