# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-07

Ground-up rewrite onto the official WHOOP API (v2) and
[django-healthdatamodel](https://github.com/django-health/django-healthdatamodel).
**Breaking: no migration path from ≤ 0.1.3**, which spoke the now-dead
unofficial password-grant API (`api-7.whoop.com`) and stored data in its own
tables.

### Added
- `whoop` package (replaces `django_whoop`): OAuth 2.0 authorization-code
  flow with token refresh/rotation and revocation (`whoop.oauth`), REST
  client with pagination, retries, and proactive token refresh
  (`whoop.client`), mappers + sync orchestrator persisting through
  healthdatamodel (`whoop.ingest`)
- `WhoopConnection` model — the only table this app owns now
- Signed webhook receiver (HMAC validation), `event_received` signal, and
  `process_event` fetch-back processing for v2 webhook events
- `sync_whoop` management command (all/one user, window flags, collection
  filter)
- Runnable demo project (`demo/`) with login → connect → sync flow
- Vendored WHOOP API docs (`docs/whoop/`), test suite (pytest + respx), CI
  parity with sibling repos

### Removed
- Everything from the unofficial-API era: `WhoopUser`, `Daily`, `Recovery`,
  `Sleep`, `SleepDetail`, `Strain`, `Workout`, `HR`, `JournalEntry` models,
  their views/templates/migrations, and the password-based login flow

## [0.1.3 and earlier] - 2021–2025

Unofficial-API era (`api-7.whoop.com`, password grant): own data models,
dashboard/data views, token refresh, `sync_whoop` command, bulk loading
script. See git history for details.
