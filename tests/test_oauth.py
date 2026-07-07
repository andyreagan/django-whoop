from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from httpx import Response

from whoop import oauth
from whoop.constants import API_BASE_URL, OAUTH_AUTHORIZATION_URL, OAUTH_TOKEN_URL
from whoop.models import ConnectionStatus, WhoopConnection

TOKEN_RESPONSE = {
    "access_token": "new-access-token",
    "expires_in": 3600,
    "token_type": "bearer",
    "refresh_token": "new-refresh-token",
    "scope": "read:cycles read:sleep offline",
}

PROFILE_URL = f"{API_BASE_URL}/v2/user/profile/basic"


class TestBuildAuthorizationUrl:
    def test_url_and_params(self):
        url, flow_state = oauth.build_authorization_url()
        parsed = urlparse(url)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        assert url.startswith(OAUTH_AUTHORIZATION_URL)
        assert params["response_type"] == "code"
        assert params["client_id"] == "test-client-id"
        assert params["redirect_uri"] == "http://testserver/whoop/callback/"
        assert params["state"] == flow_state.state
        # WHOOP requires state to be at least eight characters.
        assert len(flow_state.state) >= 8

    def test_default_scopes_include_offline(self):
        url, flow_state = oauth.build_authorization_url()
        params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert "offline" in params["scope"].split()
        assert flow_state.scopes == params["scope"].split()

    def test_explicit_scopes_and_state(self):
        url, flow_state = oauth.build_authorization_url(
            scopes=["read:sleep"], state="fixed-state"
        )
        assert flow_state.state == "fixed-state"
        assert flow_state.scopes == ["read:sleep"]
        assert "state=fixed-state" in url

    def test_state_is_unique_per_call(self):
        _, first = oauth.build_authorization_url()
        _, second = oauth.build_authorization_url()
        assert first.state != second.state


class TestExchangeCode:
    @respx.mock
    def test_posts_grant_and_returns_tokens(self):
        route = respx.post(OAUTH_TOKEN_URL).mock(
            return_value=Response(200, json=TOKEN_RESPONSE)
        )
        tokens = oauth.exchange_code(code="auth-code")

        assert tokens.access_token == "new-access-token"
        assert tokens.refresh_token == "new-refresh-token"
        assert tokens.scopes == ["read:cycles", "read:sleep", "offline"]

        sent = dict(
            pair.split("=", 1)
            for pair in route.calls.last.request.content.decode().split("&")
        )
        assert sent["grant_type"] == "authorization_code"
        assert sent["code"] == "auth-code"
        assert sent["client_id"] == "test-client-id"
        assert sent["client_secret"] == "test-client-secret"

    def test_state_mismatch_raises(self):
        with pytest.raises(oauth.StateMismatchError):
            oauth.exchange_code(
                code="auth-code",
                expected_state="expected",
                received_state="tampered",
            )

    @respx.mock
    def test_non_2xx_raises_token_exchange_error(self):
        respx.post(OAUTH_TOKEN_URL).mock(
            return_value=Response(400, json={"error": "invalid_grant"})
        )
        with pytest.raises(oauth.TokenExchangeError) as excinfo:
            oauth.exchange_code(code="bad")
        assert excinfo.value.status_code == 400


@pytest.mark.django_db
class TestIngestTokens:
    @respx.mock
    def test_creates_connection_and_fetches_user_id(self, customer):
        respx.get(PROFILE_URL).mock(
            return_value=Response(
                200,
                json={
                    "user_id": 10129,
                    "email": "j@example.com",
                    "first_name": "J",
                    "last_name": "S",
                },
            )
        )
        now = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)

        connection = oauth.ingest_tokens(
            customer=customer, tokens=TOKEN_RESPONSE, now=now
        )

        assert connection.whoop_user_id == "10129"
        assert connection.access_token == "new-access-token"
        assert connection.refresh_token == "new-refresh-token"
        assert connection.token_expires_at == datetime(
            2026, 7, 6, 13, 0, tzinfo=timezone.utc
        )
        assert connection.scopes == ["read:cycles", "read:sleep", "offline"]
        assert connection.status == ConnectionStatus.ACTIVE

    @respx.mock
    def test_profile_failure_stores_empty_user_id(self, customer):
        respx.get(PROFILE_URL).mock(return_value=Response(500, text="boom"))
        connection = oauth.ingest_tokens(customer=customer, tokens=TOKEN_RESPONSE)
        assert connection.whoop_user_id == ""

    def test_explicit_id_skips_http(self, customer):
        connection = oauth.ingest_tokens(
            customer=customer,
            tokens=TOKEN_RESPONSE,
            whoop_user_id="explicit-id",
        )
        assert connection.whoop_user_id == "explicit-id"

    def test_reconnect_updates_existing_row(self, connection):
        updated = oauth.ingest_tokens(
            customer=connection.customer,
            tokens=TOKEN_RESPONSE,
            whoop_user_id="same-user",
        )
        assert updated.pk == connection.pk
        assert WhoopConnection.objects.count() == 1
        assert updated.access_token == "new-access-token"


@pytest.mark.django_db
class TestRefreshAccessToken:
    @respx.mock
    def test_rotates_both_tokens(self, connection):
        route = respx.post(OAUTH_TOKEN_URL).mock(
            return_value=Response(200, json=TOKEN_RESPONSE)
        )
        oauth.refresh_access_token(connection)

        connection.refresh_from_db()
        assert connection.access_token == "new-access-token"
        # WHOOP rotates the refresh token on every refresh.
        assert connection.refresh_token == "new-refresh-token"

        sent = dict(
            pair.split("=", 1)
            for pair in route.calls.last.request.content.decode().split("&")
        )
        assert sent["grant_type"] == "refresh_token"
        assert sent["refresh_token"] == "whoop-initial-refresh"
        # WHOOP's docs require re-asserting the offline scope on refresh.
        assert sent["scope"] == "offline"

    @respx.mock
    def test_refresh_without_new_refresh_token_keeps_old(self, connection):
        respx.post(OAUTH_TOKEN_URL).mock(
            return_value=Response(
                200, json={"access_token": "fresh", "expires_in": 3600}
            )
        )
        oauth.refresh_access_token(connection)
        connection.refresh_from_db()
        assert connection.access_token == "fresh"
        assert connection.refresh_token == "whoop-initial-refresh"


@pytest.mark.django_db
class TestRevoke:
    @respx.mock
    def test_deletes_access_and_marks_revoked(self, connection):
        route = respx.delete(f"{API_BASE_URL}/v2/user/access").mock(
            return_value=Response(204)
        )
        oauth.revoke(connection)

        assert route.called
        auth = route.calls.last.request.headers["Authorization"]
        assert auth == "Bearer whoop-initial-access"
        connection.refresh_from_db()
        assert connection.status == ConnectionStatus.REVOKED

    @respx.mock
    def test_whoop_error_still_revokes_locally(self, connection):
        respx.delete(f"{API_BASE_URL}/v2/user/access").mock(return_value=Response(500))
        oauth.revoke(connection)
        connection.refresh_from_db()
        assert connection.status == ConnectionStatus.REVOKED
