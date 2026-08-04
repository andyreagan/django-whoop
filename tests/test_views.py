import base64
import hashlib
import hmac
import json
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from django.urls import reverse
from httpx import Response

from whoop.constants import API_BASE_URL, OAUTH_TOKEN_URL
from whoop.models import ConnectionStatus, WhoopConnection
from whoop.signals import event_received
from whoop.views import SESSION_KEY

TOKEN_RESPONSE = {
    "access_token": "cb-access",
    "expires_in": 3600,
    "refresh_token": "cb-refresh",
    "scope": "read:cycles offline",
}


def _sign(body: bytes, timestamp: str, secret: str = "test-client-secret") -> str:
    digest = hmac.new(
        secret.encode(), timestamp.encode() + body, hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()


def _post_event(
    client, payload, *, secret="test-client-secret", timestamp="1700000000000"
):
    body = json.dumps(payload).encode()
    return client.post(
        reverse("whoop:webhooks"),
        data=body,
        content_type="application/json",
        headers={
            "X-WHOOP-Signature": _sign(body, timestamp, secret),
            "X-WHOOP-Signature-Timestamp": timestamp,
        },
    )


@pytest.mark.django_db
class TestConnect:
    def test_requires_login(self, client):
        response = client.get(reverse("whoop:connect"))
        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_redirects_to_whoop_and_stashes_flow(self, client, customer):
        client.force_login(customer)
        response = client.get(reverse("whoop:connect"))

        assert response.status_code == 302
        location = urlparse(response["Location"])
        assert location.hostname == "api.prod.whoop.com"
        params = {k: v[0] for k, v in parse_qs(location.query).items()}

        stashed = client.session[SESSION_KEY]
        assert params["state"] == stashed["state"]
        assert params["scope"].split() == stashed["scopes"]


@pytest.mark.django_db
class TestCallback:
    def _start_flow(self, client, customer):
        client.force_login(customer)
        response = client.get(reverse("whoop:connect"))
        params = {
            k: v[0] for k, v in parse_qs(urlparse(response["Location"]).query).items()
        }
        return params["state"]

    @respx.mock
    def test_happy_path_creates_connection(self, client, customer):
        state = self._start_flow(client, customer)
        respx.post(OAUTH_TOKEN_URL).mock(
            return_value=Response(200, json=TOKEN_RESPONSE)
        )
        respx.get(f"{API_BASE_URL}/v2/user/profile/basic").mock(
            return_value=Response(200, json={"user_id": 10129})
        )

        response = client.get(
            reverse("whoop:callback"), {"code": "auth-code", "state": state}
        )

        assert response.status_code == 302
        connection = WhoopConnection.objects.get(customer=customer)
        assert connection.whoop_user_id == "10129"
        assert connection.access_token == "cb-access"

    def test_state_mismatch_rejected(self, client, customer):
        self._start_flow(client, customer)
        response = client.get(
            reverse("whoop:callback"), {"code": "auth-code", "state": "tampered"}
        )
        assert response.status_code == 400
        assert not WhoopConnection.objects.exists()

    def test_error_param_rejected(self, client, customer):
        client.force_login(customer)
        response = client.get(reverse("whoop:callback"), {"error": "access_denied"})
        assert response.status_code == 400

    def test_missing_code_rejected(self, client, customer):
        client.force_login(customer)
        response = client.get(reverse("whoop:callback"))
        assert response.status_code == 400

    def test_no_flow_in_progress_rejected(self, client, customer):
        client.force_login(customer)
        response = client.get(
            reverse("whoop:callback"), {"code": "auth-code", "state": "s"}
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestDisconnect:
    @respx.mock
    def test_revokes_connection(self, client, connection):
        respx.delete(f"{API_BASE_URL}/v2/user/access").mock(return_value=Response(204))
        client.force_login(connection.customer)
        response = client.post(reverse("whoop:disconnect"))

        assert response.status_code == 302
        connection.refresh_from_db()
        assert connection.status == ConnectionStatus.REVOKED

    def test_no_connection_is_a_noop(self, client, customer):
        client.force_login(customer)
        response = client.post(reverse("whoop:disconnect"))
        assert response.status_code == 302

    def test_get_not_allowed(self, client, connection):
        client.force_login(connection.customer)
        response = client.get(reverse("whoop:disconnect"))
        assert response.status_code == 405


@pytest.mark.django_db
class TestWebhookReceiver:
    EVENT: ClassVar[dict] = {
        "user_id": 10129,
        "id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8",
        "type": "sleep.updated",
        "trace_id": "d3709ee7-104e-4f70-a928-2932964b017b",
    }

    def test_valid_signature_emits_signal_and_returns_204(self, client):
        received = []

        def handler(sender, payload, **kwargs):
            received.append(payload)

        event_received.connect(handler)
        try:
            response = _post_event(client, self.EVENT)
        finally:
            event_received.disconnect(handler)

        assert response.status_code == 204
        assert received == [self.EVENT]

    def test_bad_signature_rejected(self, client):
        response = _post_event(client, self.EVENT, secret="wrong-secret")
        assert response.status_code == 401

    def test_missing_signature_rejected(self, client):
        response = client.post(
            reverse("whoop:webhooks"),
            data=json.dumps(self.EVENT),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_tampered_body_rejected(self, client):
        body = json.dumps(self.EVENT).encode()
        timestamp = "1700000000000"
        response = client.post(
            reverse("whoop:webhooks"),
            data=json.dumps({**self.EVENT, "user_id": 666}),
            content_type="application/json",
            headers={
                "X-WHOOP-Signature": _sign(body, timestamp),
                "X-WHOOP-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 401

    def test_invalid_json_rejected(self, client):
        body = b"not-json{"
        timestamp = "1700000000000"
        response = client.post(
            reverse("whoop:webhooks"),
            data=body,
            content_type="application/json",
            headers={
                "X-WHOOP-Signature": _sign(body, timestamp),
                "X-WHOOP-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 400

    def test_get_not_allowed(self, client):
        response = client.get(reverse("whoop:webhooks"))
        assert response.status_code == 405
