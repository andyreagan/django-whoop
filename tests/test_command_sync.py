from datetime import datetime, timedelta, timezone
from io import StringIO

import pytest
import respx
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from httpx import Response

from whoop.constants import API_BASE_URL
from whoop.models import ConnectionStatus, WhoopConnection

from .test_ingest import BODY, CYCLE

COLLECTION_ROUTES = {
    "cycles": f"{API_BASE_URL}/v2/cycle",
    "sleeps": f"{API_BASE_URL}/v2/activity/sleep",
    "recoveries": f"{API_BASE_URL}/v2/recovery",
    "workouts": f"{API_BASE_URL}/v2/activity/workout",
}


def _mock_all_empty():
    for url in COLLECTION_ROUTES.values():
        respx.get(url).mock(return_value=Response(200, json={"records": []}))
    respx.get(f"{API_BASE_URL}/v2/user/measurement/body").mock(
        return_value=Response(200, json=BODY)
    )


@pytest.mark.django_db
class TestSyncWhoopCommand:
    @respx.mock
    def test_syncs_all_active_connections(self, connection):
        _mock_all_empty()
        out = StringIO()
        call_command("sync_whoop", stdout=out)
        assert "✓" in out.getvalue()
        connection.refresh_from_db()
        assert connection.last_sync_at is not None

    @respx.mock
    def test_user_filter(self, connection):
        _mock_all_empty()
        User = get_user_model()
        other = User.objects.create_user(username="other")
        WhoopConnection.objects.create(
            customer=other,
            whoop_user_id="other-id",
            access_token="a",
            refresh_token="r",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        out = StringIO()
        call_command("sync_whoop", "--user", "test-customer", stdout=out)
        assert "Syncing 1 connection(s)" in out.getvalue()

    def test_unknown_user_errors(self, db):
        with pytest.raises(CommandError, match="No user with"):
            call_command("sync_whoop", "--user", "ghost")

    def test_user_and_user_id_mutually_exclusive(self, connection):
        with pytest.raises(CommandError, match="not both"):
            call_command(
                "sync_whoop",
                "--user",
                "test-customer",
                "--user-id",
                str(connection.customer_id),
            )

    def test_start_requires_end(self, db):
        with pytest.raises(CommandError, match="together"):
            call_command("sync_whoop", "--start", "2026-07-01T00:00:00Z")

    def test_invalid_start_end(self, db):
        with pytest.raises(CommandError, match="ISO-8601"):
            call_command("sync_whoop", "--start", "not-a-date", "--end", "also-not")

    def test_no_connections_warns(self, db):
        out = StringIO()
        call_command("sync_whoop", stdout=out)
        assert "No matching active connections" in out.getvalue()

    def test_inactive_connections_skipped(self, connection):
        connection.status = ConnectionStatus.REVOKED
        connection.save()
        out = StringIO()
        call_command("sync_whoop", stdout=out)
        assert "No matching active connections" in out.getvalue()

    @respx.mock
    def test_collection_filter(self, connection):
        route = respx.get(COLLECTION_ROUTES["cycles"]).mock(
            return_value=Response(200, json={"records": [CYCLE]})
        )
        out = StringIO()
        call_command("sync_whoop", "--collection", "cycles", stdout=out)
        assert route.called
        assert "cycles=2" in out.getvalue()

    @respx.mock
    def test_failed_user_does_not_stop_others(self, connection):
        User = get_user_model()
        other = User.objects.create_user(username="zz-other")
        WhoopConnection.objects.create(
            customer=other,
            whoop_user_id="other-id",
            access_token="a",
            refresh_token="r",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        # First connection's fetch blows up; second succeeds.
        respx.get(COLLECTION_ROUTES["cycles"]).mock(
            side_effect=[
                Response(400, json={"message": "boom"}),
                Response(200, json={"records": []}),
            ]
        )
        out, err = StringIO(), StringIO()
        with pytest.raises(CommandError, match="1 connection"):
            call_command("sync_whoop", "--collection", "cycles", stdout=out, stderr=err)
        assert "✗" in err.getvalue()
        assert "✓" in out.getvalue()
