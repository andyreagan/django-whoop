# WHOOP webhooks (v2)

Summarized from <https://developer.whoop.com/docs/developing/webhooks>
(verified 2026-07-07). Configure the webhook URL per app in the developer
dashboard.

## Delivery

One event per POST; the payload names the resource but carries no data —
fetch it back through the API with the matching user's credentials:

```json
{
  "user_id": 10129,
  "id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8",
  "type": "sleep.updated",
  "trace_id": "d3709ee7-104e-4f70-a928-2932964b017b"
}
```

- `user_id` — int64 WHOOP user (matches `WhoopConnection.whoop_user_id`)
- `id` — UUID of the resource (v2); for `recovery.*` it is the **sleep**
  UUID associated with the recovery, not a recovery id
- `trace_id` — unique per event, for deduplication

## Event types

`workout.updated`, `workout.deleted`, `sleep.updated`, `sleep.deleted`,
`recovery.updated`, `recovery.deleted`. `*.updated` fires for creates AND
updates.

## Signature validation

Headers:

- `X-WHOOP-Signature` — `base64(HMAC_SHA256(timestamp + raw_body, client_secret))`
- `X-WHOOP-Signature-Timestamp` — unix milliseconds

Validate by prepending the timestamp header to the **raw** request body,
HMAC-SHA256 with the app's client secret, base64-encode, compare.

## Response expectations

Any 2xx within ~1 second counts as delivered; anything else (or a timeout) is
retried five times over roughly an hour. Do heavy processing async.
