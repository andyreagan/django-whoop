"""HTTP views for OAuth + webhook events.

The OAuth views (``connect`` / ``callback`` / ``disconnect``) cover the
web-callback flow used in admin / dev / testing. Mobile clients should POST
tokens (or an auth code) to a project-local endpoint that calls
:func:`whoop.oauth.ingest_tokens` or :func:`whoop.oauth.exchange_code`.

The ``webhook_receiver`` view validates WHOOP's HMAC signature and emits a
:data:`whoop.signals.event_received` signal for every authenticated event.
Point the webhook URL in the WHOOP developer dashboard at this endpoint.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from . import oauth, webhooks
from .constants import WEBHOOK_SIGNATURE_HEADER, WEBHOOK_TIMESTAMP_HEADER
from .models import WhoopConnection
from .signals import event_received

SESSION_KEY = "whoop_oauth_flow"


def _success_url() -> str:
    return getattr(settings, "WHOOP_CONNECT_SUCCESS_URL", "/admin/")


@login_required
@require_http_methods(["GET"])
def connect(request: HttpRequest) -> HttpResponse:
    auth_url, flow_state = oauth.build_authorization_url()
    request.session[SESSION_KEY] = flow_state.model_dump()
    return redirect(auth_url)


@login_required
@require_http_methods(["GET"])
def callback(request: HttpRequest) -> HttpResponse:
    code = request.GET.get("code")
    received_state = request.GET.get("state")
    error = request.GET.get("error")
    if error:
        return HttpResponseBadRequest(f"OAuth error: {error}")
    if not code:
        return HttpResponseBadRequest("Missing authorization code")

    stashed = request.session.pop(SESSION_KEY, None)
    if not stashed:
        return HttpResponseBadRequest("No OAuth flow in progress")
    flow_state = oauth.OAuthFlowState.model_validate(stashed)

    try:
        tokens = oauth.exchange_code(
            code=code,
            expected_state=flow_state.state,
            received_state=received_state,
        )
    except oauth.StateMismatchError:
        return HttpResponseBadRequest("OAuth state mismatch")

    oauth.ingest_tokens(customer=request.user, tokens=tokens)
    return redirect(_success_url())


@login_required
@require_POST
def disconnect(request: HttpRequest) -> HttpResponse:
    try:
        connection = WhoopConnection.objects.get(customer=request.user)
    except WhoopConnection.DoesNotExist:
        return redirect(_success_url())
    oauth.revoke(connection)
    return redirect(_success_url())


@csrf_exempt
@require_POST
def webhook_receiver(request: HttpRequest) -> HttpResponse:
    """Receive WHOOP webhook POSTs.

    Every delivery is signed with the app's client secret; requests whose
    signature doesn't verify get a 401 and are never processed. Valid events
    emit ``event_received`` and return 204 — any heavy lifting belongs in the
    signal handler (which should hand off to a queue; WHOOP wants its 2xx
    within a second).
    """
    if not webhooks.signature_matches(
        signature=request.headers.get(WEBHOOK_SIGNATURE_HEADER),
        timestamp=request.headers.get(WEBHOOK_TIMESTAMP_HEADER),
        body=request.body,
    ):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("invalid JSON body")
    if not isinstance(payload, dict):
        return HttpResponseBadRequest("expected a JSON object")

    event_received.send(sender=None, payload=payload)
    return HttpResponse(status=204)
