from datetime import datetime, timedelta, timezone

import pytest

from whoop.models import ConnectionStatus, WhoopConnection


@pytest.mark.django_db
class TestWhoopConnection:
    def test_str(self, connection):
        assert str(connection.customer_id) in str(connection)
        assert "active" in str(connection)

    def test_defaults(self, connection):
        assert connection.status == ConnectionStatus.ACTIVE
        assert connection.last_sync_at is None
        assert connection.connected_at is not None

    def test_one_connection_per_customer(self, connection):
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            WhoopConnection.objects.create(
                customer=connection.customer,
                whoop_user_id="other",
                access_token="x",
                refresh_token="y",
                token_expires_at=datetime.now(timezone.utc),
            )


class TestIsTokenExpired:
    def _connection(self, expires_at):
        return WhoopConnection(token_expires_at=expires_at)

    def test_future_expiry_is_fresh(self):
        conn = self._connection(datetime.now(timezone.utc) + timedelta(hours=1))
        assert conn.is_token_expired() is False

    def test_past_expiry_is_expired(self):
        conn = self._connection(datetime.now(timezone.utc) - timedelta(minutes=1))
        assert conn.is_token_expired() is True

    def test_leeway_window_counts_as_expired(self):
        conn = self._connection(datetime.now(timezone.utc) + timedelta(seconds=30))
        assert conn.is_token_expired(leeway_seconds=60) is True

    def test_explicit_now(self):
        expires = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
        conn = self._connection(expires)
        before = datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc)
        after = datetime(2026, 7, 7, 13, 0, tzinfo=timezone.utc)
        assert conn.is_token_expired(now=before) is False
        assert conn.is_token_expired(now=after) is True
