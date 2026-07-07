# Notes for Claude (and human contributors)

This project is a reusable Django library — small, focused, with a real
shipping cadence to PyPI. Slice-sized changes; commit messages with the
"why"; tests for every behavior; live calibration over docs guessing.

It is a sibling of `django-health/django-garmin` and
`django-health/django-google-health` and deliberately mirrors their layout,
pyproject/CI/pre-commit setup, and OAuth/client/ingest module boundaries.
When in doubt about a pattern, check what those repos do.

## WHOOP API ground truth

The OpenAPI document at
`https://api.prod.whoop.com/developer/doc/openapi.json` is ground truth for
endpoint paths, scopes, and payload schemas — grep it before trusting the
human-facing docs. Local summaries live in `docs/whoop/`. The mappers in
`whoop/ingest.py` were written against the OpenAPI examples and have NOT yet
been calibrated against a live account — when live credentials are available,
verify against real payloads and promote findings into code comments + tests.

Live-calibration entry point: run the demo (`README.md` → "Try it on your own
data"), then pull the access token from `db.sqlite3` and hit
`https://api.prod.whoop.com/developer/v2/...` directly with `httpx` before
guessing at code fixes.

Things WHOOP does differently from the siblings (don't "fix" them):

- No PKCE; plain authorization-code flow. `state` is required (min 8 chars).
- Refresh tokens only exist if the `offline` scope was granted, refresh
  requests re-assert `scope=offline`, and BOTH tokens rotate on every
  refresh (the old access token is invalidated immediately).
- Collections filter by the record's own time range (not upload time — no
  Garmin-style 24h windowing) and page via `nextToken`, max 25 per page.
- Sleep/workout ids are UUIDs in v2; cycles are int64. A recovery is keyed
  by cycle but its webhook event carries the associated *sleep* UUID —
  processing resolves sleep → cycle_id → recovery.
- Webhooks carry no resource data (fetch-back model) and are HMAC-signed
  with the client secret (`docs/whoop/webhooks.md`).
- Sleep stages come as TOTALS only; ingest lays them out as synthetic
  sequential intervals so per-day sums are right (see `whoop/ingest.py`).

## Upstream contributions to django-healthdatamodel

The sister repo `django-health/django-healthdatamodel` is where the storage
layer lives. When a change there unblocks this project, you have end-to-end
release autonomy as long as CI is green:

1. Open the PR.
2. Wait for CI green.
3. Bump version in `pyproject.toml` (minor for additive, patch for fix).
4. Squash-merge.
5. Tag `v<X>` on `main`, push the tag — triggers PyPI publish via OIDC.
6. Bump the floor in this repo's `pyproject.toml`, swap any local stopgaps
   for the upstream API, commit + push.

Both repos publish to PyPI via trusted publishing — no manual upload.

## Out of scope for this project

- **Token encryption at rest.** Production deployment uses Postgres with
  encryption-at-rest at the storage layer. Don't add Fernet /
  django-cryptography fields to `WhoopConnection`.
- **Signup view in the demo.** `createsuperuser` is the way. The demo exists
  so the maintainer can test against their own WHOOP account; it isn't a
  hosted SaaS shell.
- **The legacy unofficial API.** Versions ≤ 0.1.3 spoke password-grant
  `api-7.whoop.com`; that API is dead and the old models are gone. Don't
  resurrect compatibility shims for them.
