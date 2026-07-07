# WHOOP OAuth 2.0

Summarized from <https://developer.whoop.com/docs/developing/oauth> (verified
2026-07-07). Plain authorization-code flow — no PKCE.

## Endpoints

| | |
|---|---|
| Authorization (GET, user-facing consent) | `https://api.prod.whoop.com/oauth/oauth2/auth` |
| Token (POST, form-encoded) | `https://api.prod.whoop.com/oauth/oauth2/token` |
| Revocation | `DELETE https://api.prod.whoop.com/developer/v2/user/access` (bearer auth) |

Client id/secret and redirect URLs are configured in the
[WHOOP developer dashboard](https://developer-dashboard.whoop.com/). The
redirect URI must match a registered URL byte-for-byte.

## Authorization request parameters

- `response_type=code`
- `client_id`
- `redirect_uri`
- `scope` — space-separated (see below)
- `state` — **required**, minimum eight characters; echoed back on the
  callback for CSRF protection

## Scopes

| Scope | Grants |
|---|---|
| `read:recovery` | `GET /v2/recovery`, `GET /v2/cycle/{id}/recovery` |
| `read:cycles` | `GET /v2/cycle`, `GET /v2/cycle/{id}` |
| `read:sleep` | `GET /v2/activity/sleep`, `GET /v2/activity/sleep/{id}` |
| `read:workout` | `GET /v2/activity/workout`, `GET /v2/activity/workout/{id}` |
| `read:profile` | `GET /v2/user/profile/basic` |
| `read:body_measurement` | `GET /v2/user/measurement/body` |
| `offline` | A refresh token in the token response |

Without `offline` there is **no refresh token** and the connection dies when
the first access token expires (`expires_in` is roughly an hour).

## Token behavior

- Expired access tokens get `401 Unauthorized` from the API.
- Refresh grant (form-encoded): `grant_type=refresh_token`, `refresh_token`,
  `client_id`, `client_secret`, and `scope=offline` (WHOOP's documented
  refresh payload re-asserts the offline scope).
- **Rotation:** each refresh returns a new refresh token, and the existing
  access token is invalidated as soon as the refresh happens. Persist both
  tokens from every refresh response.

## Revocation

`DELETE /v2/user/access` with the user's bearer token removes the app's
access. WHOOP asks integrations that offer a "disconnect" affordance to call
this.
