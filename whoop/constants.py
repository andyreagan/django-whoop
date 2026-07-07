"""Service URLs, scopes, and identifiers for the WHOOP API (v2).

Ground truth is WHOOP's OpenAPI document at
``https://api.prod.whoop.com/developer/doc/openapi.json``; the endpoint and
payload shapes are summarized in ``docs/whoop/``.
"""

# User-facing consent page (GET).
OAUTH_AUTHORIZATION_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
# Token endpoint (POST, form-encoded) for both authorization_code and
# refresh_token grants.
OAUTH_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"

API_BASE_URL = "https://api.prod.whoop.com/developer"

# OAuth scopes. ``offline`` is what makes WHOOP return a refresh token — leave
# it out and the connection dies when the first access token expires (~1h).
SCOPE_READ_RECOVERY = "read:recovery"
SCOPE_READ_CYCLES = "read:cycles"
SCOPE_READ_SLEEP = "read:sleep"
SCOPE_READ_WORKOUT = "read:workout"
SCOPE_READ_PROFILE = "read:profile"
SCOPE_READ_BODY_MEASUREMENT = "read:body_measurement"
SCOPE_OFFLINE = "offline"

ALL_SCOPES = (
    SCOPE_READ_RECOVERY,
    SCOPE_READ_CYCLES,
    SCOPE_READ_SLEEP,
    SCOPE_READ_WORKOUT,
    SCOPE_READ_PROFILE,
    SCOPE_READ_BODY_MEASUREMENT,
    SCOPE_OFFLINE,
)

# Collection identifiers, used as REST paths and as the keys of
# SyncResult.counts. "recoveries"/"cycles" are ours; the REST paths differ.
COLLECTION_CYCLES = "cycles"
COLLECTION_SLEEPS = "sleeps"
COLLECTION_RECOVERIES = "recoveries"
COLLECTION_WORKOUTS = "workouts"
COLLECTION_BODY = "body"

# Collection endpoints return at most 25 records per page (OpenAPI maximum);
# larger ``limit`` values are rejected, not clamped.
MAX_PAGE_SIZE = 25

# Webhook signature headers. The signature is
# base64(HMAC_SHA256(timestamp + raw_body, client_secret)).
WEBHOOK_SIGNATURE_HEADER = "X-WHOOP-Signature"
WEBHOOK_TIMESTAMP_HEADER = "X-WHOOP-Signature-Timestamp"

# v2 webhook event types.
EVENT_WORKOUT_UPDATED = "workout.updated"
EVENT_WORKOUT_DELETED = "workout.deleted"
EVENT_SLEEP_UPDATED = "sleep.updated"
EVENT_SLEEP_DELETED = "sleep.deleted"
EVENT_RECOVERY_UPDATED = "recovery.updated"
EVENT_RECOVERY_DELETED = "recovery.deleted"

# Human-readable, stored in Record.sourceName. The machine identifier is
# ``healthdatamodel.constants.DataSource.WHOOP`` (added in 0.8.0).
SOURCE_NAME = "WHOOP"

# WHOOP's headline scores have no Apple HealthKit equivalent, so they're
# stored under these package-specific Record.type strings.
WHOOP_STRAIN_TYPE = "WHOOPStrain"
WHOOP_RECOVERY_SCORE_TYPE = "WHOOPRecoveryScore"
