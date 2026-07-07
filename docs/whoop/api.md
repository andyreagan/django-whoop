# WHOOP API v2 — endpoints and payload shapes

Ground truth is the OpenAPI document at
`https://api.prod.whoop.com/developer/doc/openapi.json` (fetched 2026-07-07).
Base URL: `https://api.prod.whoop.com/developer`. v1 was removed 2025-10-01.

## Endpoints (user data)

| Method | Path | Scope |
|---|---|---|
| GET | `/v2/cycle` | `read:cycles` |
| GET | `/v2/cycle/{cycleId}` | `read:cycles` |
| GET | `/v2/cycle/{cycleId}/sleep` | `read:sleep` |
| GET | `/v2/cycle/{cycleId}/recovery` | `read:recovery` |
| GET | `/v2/recovery` | `read:recovery` |
| GET | `/v2/activity/sleep` | `read:sleep` |
| GET | `/v2/activity/sleep/{sleepId}` | `read:sleep` |
| GET | `/v2/activity/workout` | `read:workout` |
| GET | `/v2/activity/workout/{workoutId}` | `read:workout` |
| GET | `/v2/user/profile/basic` | `read:profile` |
| GET | `/v2/user/measurement/body` | `read:body_measurement` |
| DELETE | `/v2/user/access` | (any valid token) |
| GET | `/v1/activity-mapping/{activityV1Id}` | v1→v2 id mapping helper |

## Pagination (all four collections)

Query params: `limit` (default 10, **max 25** — larger values are rejected),
`start` (inclusive RFC3339), `end` (records intersecting it included;
defaults to now), `nextToken`.

Response envelope:

```json
{"records": [...], "next_token": "MTIzOjEyMzEyMw"}
```

Absent `next_token` means last page. The collections filter by the record's
own time range (unlike Garmin's upload-time semantics) — historic data is
fetched the same way as recent data.

## Resource shapes

Common fields: `user_id` (int64), `created_at`/`updated_at`/`start`/`end`
(RFC3339), `timezone_offset` (TZD, e.g. `-05:00`), `score_state`
(`SCORED` | `PENDING_SCORE` | `UNSCORABLE`), `score` (object, only when
`SCORED`). An open cycle (the one in progress) has no `end`.

### Cycle — `id` int64

`score`: `strain` (float, 0–21), `kilojoule` (float, TOTAL cycle energy),
`average_heart_rate` (int), `max_heart_rate` (int).

### Sleep — `id` UUID (v2), `cycle_id` int64, `nap` bool

`score.stage_summary` (all int milliseconds unless noted):
`total_in_bed_time_milli`, `total_awake_time_milli`,
`total_no_data_time_milli`, `total_light_sleep_time_milli`,
`total_slow_wave_sleep_time_milli`, `total_rem_sleep_time_milli`,
`sleep_cycle_count`, `disturbance_count`.

`score.sleep_needed`: `baseline_milli`, `need_from_sleep_debt_milli`,
`need_from_recent_strain_milli`, `need_from_recent_nap_milli` (≤ 0).

`score` scalars: `respiratory_rate`, `sleep_performance_percentage`,
`sleep_consistency_percentage`, `sleep_efficiency_percentage` (floats;
the percentages may be absent for new users).

Note: v2 exposes stage **totals only** — no per-stage intervals.

### Recovery — keyed by `cycle_id` int64, carries `sleep_id` UUID

`score`: `user_calibrating` (bool), `recovery_score` (float 0–100),
`resting_heart_rate` (float), `hrv_rmssd_milli` (float, RMSSD in ms),
`spo2_percentage` (float, 4.0+ hardware only), `skin_temp_celsius` (float,
4.0+ hardware only).

### Workout — `id` UUID (v2), `sport_name` string (replaces v1 `sport_id`)

`score`: `strain`, `average_heart_rate`, `max_heart_rate`, `kilojoule`,
`percent_recorded`, `distance_meter`*, `altitude_gain_meter`*,
`altitude_change_meter`*, `zone_durations` (`zone_zero_milli` …
`zone_five_milli`, int ms). *Only present when the data was recorded.

### UserBasicProfile

`user_id` (int64), `email`, `first_name`, `last_name`.

### UserBodyMeasurement (current values, no history)

`height_meter`, `weight_kilogram`, `max_heart_rate`.
