"""WHOOP OAuth 2.0 helpers.

WHOOP's flow is plain OAuth2 (authorization-code, no PKCE) over two endpoints —
no vendor SDK needed, so this module speaks httpx directly. The public API is:

* :func:`build_authorization_url` — produce the consent URL for the web-callback flow.
* :func:`exchange_code` — server-side code → token exchange.
* :func:`ingest_tokens` — persist tokens obtained externally (e.g. a mobile app that
  did the OAuth dance and POSTs the resulting token dict to your backend, mirroring
  the wellrider pattern).
* :func:`refresh_access_token` — refresh a stored connection's tokens (WHOOP
  rotates the refresh token and invalidates the old access token on every refresh).
* :func:`revoke` — delete the user's OAuth access at WHOOP and mark the
  connection revoked.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx
from django.conf import settings

from .constants import (
    ALL_SCOPES,
    API_BASE_URL,
    OAUTH_AUTHORIZATION_URL,
    OAUTH_TOKEN_URL,
    SCOPE_OFFLINE,
)
from .models import ConnectionStatus, WhoopConnection
from .schemas import OAuthFlowState, WhoopTokens

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

log = logging.getLogger(__name__)


class OAuthError(Exception):
    """Base for OAuth-related errors raised by this module."""


class StateMismatchError(OAuthError):
    """Raised when the ``state`` returned from WHOOP doesn't match what we stashed."""


class TokenExchangeError(OAuthError):
    """Raised when the token endpoint returns a non-2xx response."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"token endpoint returned HTTP {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def default_scopes() -> list[str]:
    return list(getattr(settings, "WHOOP_DEFAULT_SCOPES", ALL_SCOPES))


def build_authorization_url(
    *,
    scopes: list[str] | None = None,
    state: str | None = None,
) -> tuple[str, OAuthFlowState]:
    """Build the consent URL and the state to round-trip via the session.

    WHOOP requires ``state`` (minimum eight characters) and grants a refresh
    token only when ``offline`` is among the requested scopes — without it the
    connection can't outlive the first ~1h access token, so the default scope
    set includes it.
    """
    scopes = list(scopes) if scopes is not None else default_scopes()
    flow_state = OAuthFlowState(
        state=state or secrets.token_urlsafe(32),
        scopes=scopes,
    )
    params = {
        "response_type": "code",
        "client_id": settings.WHOOP_CLIENT_ID,
        "redirect_uri": settings.WHOOP_REDIRECT_URI,
        "scope": " ".join(scopes),
        "state": flow_state.state,
    }
    return f"{OAUTH_AUTHORIZATION_URL}?{urlencode(params)}", flow_state


def _token_request(data: dict[str, str]) -> WhoopTokens:
    response = httpx.post(
        OAUTH_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise TokenExchangeError(response.status_code, response.text)
    return WhoopTokens.model_validate(response.json())


def exchange_code(
    *,
    code: str,
    expected_state: str | None = None,
    received_state: str | None = None,
) -> WhoopTokens:
    """Exchange an authorization code for tokens.

    Pass ``expected_state`` and ``received_state`` to enforce CSRF protection at
    this layer; pass neither to skip (e.g. when the upstream view already
    validated).
    """
    if expected_state is not None and received_state != expected_state:
        raise StateMismatchError("OAuth state mismatch")
    return _token_request(
        {
            "grant_type": "authorization_code",
            "client_id": settings.WHOOP_CLIENT_ID,
            "client_secret": settings.WHOOP_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.WHOOP_REDIRECT_URI,
        }
    )


def ingest_tokens(
    *,
    customer: AbstractBaseUser,
    tokens: WhoopTokens | dict[str, Any],
    whoop_user_id: str | None = None,
    now: datetime | None = None,
) -> WhoopConnection:
    """Persist tokens onto a :class:`WhoopConnection` (create or update).

    This is the entry point for the "mobile app already did the OAuth dance
    and is shipping us the token dict" pattern. ``whoop_user_id`` is fetched
    via ``GET /v2/user/profile/basic`` if not provided — best-effort, since it
    is only needed for webhook routing; a transient failure stores an empty
    value rather than failing the connect.
    """
    parsed = (
        tokens
        if isinstance(tokens, WhoopTokens)
        else WhoopTokens.model_validate(tokens)
    )
    if whoop_user_id is None:
        try:
            whoop_user_id = _fetch_whoop_user_id(parsed.access_token)
        except (httpx.HTTPError, OAuthError) as exc:
            log.warning("profile fetch failed (%s) — storing empty whoop_user_id", exc)
            whoop_user_id = ""

    connection, _ = WhoopConnection.objects.update_or_create(
        customer=customer,
        defaults={
            "whoop_user_id": whoop_user_id,
            "access_token": parsed.access_token,
            "refresh_token": parsed.refresh_token or "",
            "token_expires_at": parsed.expires_at(now=now),
            "scopes": parsed.scopes,
            "status": ConnectionStatus.ACTIVE,
        },
    )
    return connection


def refresh_access_token(connection: WhoopConnection) -> WhoopConnection:
    """Refresh the connection's tokens in place using its stored refresh token.

    WHOOP rotates the refresh token on every refresh and invalidates the old
    access token as soon as the new one is minted, so both tokens persist
    together. The refresh grant must re-assert ``scope=offline`` (per WHOOP's
    docs) to keep receiving refresh tokens.
    """
    tokens = _token_request(
        {
            "grant_type": "refresh_token",
            "client_id": settings.WHOOP_CLIENT_ID,
            "client_secret": settings.WHOOP_CLIENT_SECRET,
            "refresh_token": connection.refresh_token,
            "scope": SCOPE_OFFLINE,
        }
    )
    connection.access_token = tokens.access_token
    connection.token_expires_at = tokens.expires_at()
    update_fields = ["access_token", "token_expires_at"]
    if tokens.refresh_token:
        connection.refresh_token = tokens.refresh_token
        update_fields.append("refresh_token")
    connection.save(update_fields=update_fields)
    return connection


def revoke(connection: WhoopConnection) -> None:
    """Delete the user's OAuth access at WHOOP and mark the connection ``REVOKED``.

    ``DELETE /v2/user/access`` is WHOOP's revocation endpoint. Best-effort: a
    non-2xx from WHOOP still flips the local status — the user-facing intent
    (disconnect) shouldn't be blocked by a transient error.
    """
    try:
        httpx.delete(
            f"{API_BASE_URL}/v2/user/access",
            headers={"Authorization": f"Bearer {connection.access_token}"},
            timeout=10.0,
        )
    except httpx.HTTPError:
        pass
    connection.status = ConnectionStatus.REVOKED
    connection.save(update_fields=["status"])


def _fetch_whoop_user_id(access_token: str) -> str:
    """Call ``GET /v2/user/profile/basic`` to resolve the WHOOP user id for a token.

    Requires the ``read:profile`` scope; webhook payloads route by this id.
    """
    response = httpx.get(
        f"{API_BASE_URL}/v2/user/profile/basic",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    if response.status_code >= 400:
        # raise_for_status drops the response body; we want it visible.
        raise OAuthError(
            f"user profile returned HTTP {response.status_code}: {response.text}"
        )
    payload = response.json()
    user_id = payload.get("user_id")
    if not user_id:
        raise OAuthError(f"user profile returned no user id: {payload!r}")
    return str(user_id)
