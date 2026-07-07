"""Map WHOOP API (v2) resources onto django-healthdatamodel records.

Mappers cover the four user-data collections:

  cycles      → list[:class:`RecordInput`] (strain score, cycle energy)
  sleeps      → list[:class:`RecordInput`] (sleep stages, respiratory rate)
  recoveries  → list[:class:`RecordInput`] (recovery score, resting HR, HRV,
                SpO2, skin temperature)
  workouts    → :class:`WorkoutInput`

plus a point-in-time ``body`` snapshot (height, weight) from
``GET /v2/user/measurement/body``.

Mapping notes (see ``docs/whoop/data-model.md`` for payload shapes):

* WHOOP v2 exposes sleep **stage totals** (milliseconds), not per-stage
  intervals. Each total becomes one synthetic Record laid out sequentially
  from the sleep's start (light → SWS → REM → awake), so per-day duration
  sums are exact even though intra-night stage timing is not real.
* WHOOP's HRV is RMSSD; Apple HealthKit's only HRV identifier is SDNN. The
  RMSSD value is stored under the HK identifier — a documented approximation,
  same trade-off every WHOOP→HealthKit bridge makes.
* Cycle ``kilojoule`` is WHOOP's *total* energy for the (wake-to-wake) cycle,
  resting burn included; healthdatamodel has no TOTAL_CALORIES metric, so it
  lands in ACTIVE_CALORIES. Don't also ingest a basal estimate on top.
* Strain and recovery scores have no HK equivalent and are stored under the
  package-specific types ``WHOOPStrain`` / ``WHOOPRecoveryScore``.
* Un-scored resources (``score_state`` != ``SCORED``) contribute whatever
  fields exist without a score; a pending sleep still records its interval.

The high-level orchestrator is :func:`sync_user`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import dateutil.parser
from healthdatamodel.constants import DataSource
from healthdatamodel.ingest import ingest_records, ingest_workouts
from healthdatamodel.query import SLEEP_TYPE, ActivityMetric, SleepValue
from healthdatamodel.schemas import MetadataEntry, RecordInput, WorkoutInput

from .client import WhoopClient
from .constants import (
    COLLECTION_BODY,
    COLLECTION_CYCLES,
    COLLECTION_RECOVERIES,
    COLLECTION_SLEEPS,
    COLLECTION_WORKOUTS,
    SOURCE_NAME,
    WHOOP_RECOVERY_SCORE_TYPE,
    WHOOP_STRAIN_TYPE,
)

if TYPE_CHECKING:
    from .models import WhoopConnection

# Apple HealthKit identifiers not exported as enum members in healthdatamodel.
HK_RESTING_HEART_RATE = "HKQuantityTypeIdentifierRestingHeartRate"
HK_HEART_RATE_VARIABILITY = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
HK_OXYGEN_SATURATION = "HKQuantityTypeIdentifierOxygenSaturation"
HK_WRIST_TEMPERATURE = "HKQuantityTypeIdentifierAppleSleepingWristTemperature"
HK_RESPIRATORY_RATE = "HKQuantityTypeIdentifierRespiratoryRate"
HK_BODY_MASS = "HKQuantityTypeIdentifierBodyMass"
HK_HEIGHT = "HKQuantityTypeIdentifierHeight"

KCAL_PER_KILOJOULE = 1 / 4.184

# Sleep stage totals (SleepStageSummary keys) → healthdatamodel SleepValue, in
# the synthetic layout order. WHOOP's "light" maps to HealthKit's "core" (both
# mean non-REM stages 1-2); awake goes last so the asleep block is contiguous.
_STAGE_LAYOUT: tuple[tuple[str, str], ...] = (
    ("total_light_sleep_time_milli", SleepValue.ASLEEP_CORE),
    ("total_slow_wave_sleep_time_milli", SleepValue.ASLEEP_DEEP),
    ("total_rem_sleep_time_milli", SleepValue.ASLEEP_REM),
    ("total_awake_time_milli", SleepValue.AWAKE),
)


@dataclass
class SyncResult:
    """Per-collection counts returned by :func:`sync_user`."""

    counts: dict[str, int] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _parse(raw: str) -> datetime:
    """Parse WHOOP's RFC3339 timestamps to aware UTC datetimes."""
    return dateutil.parser.isoparse(raw).astimezone(timezone.utc)


def _record(
    *,
    record_id: str | None,
    start: datetime,
    end: datetime,
    type: str,
    value: Any,
    unit: str | None,
) -> RecordInput:
    """Build a RecordInput keyed off the WHOOP resource id.

    One WHOOP resource fans out into several Records, so a per-metric suffix
    keeps recordIds unique. WHOOP re-sends a resource with the same id when it
    is updated (webhooks fire ``*.updated`` for creates and updates alike), so
    the stable recordId identifies the logical datum across re-ingests.
    """
    return RecordInput(
        recordId=record_id,
        startDate=start,
        endDate=end,
        creationDate=start,
        sourceName=SOURCE_NAME,
        type=type,
        value=str(value),
        unit=unit,
    )


# Mappers ---------------------------------------------------------------------


def map_cycle(cycle: dict[str, Any]) -> list[RecordInput]:
    """Strain score + total energy for one physiological cycle.

    An open cycle (the one the user is currently in) has no ``end``; its
    records span up to ``updated_at`` and will be re-sent once it closes.
    """
    start = _parse(cycle["start"])
    end = _parse(cycle["end"] if cycle.get("end") else cycle["updated_at"])
    score = cycle.get("score") or {}
    cycle_id = cycle.get("id")
    records: list[RecordInput] = []

    if score.get("strain") is not None:
        records.append(
            _record(
                record_id=f"{cycle_id}-strain" if cycle_id else None,
                start=start,
                end=end,
                type=WHOOP_STRAIN_TYPE,
                value=score["strain"],
                unit="count",
            )
        )
    if score.get("kilojoule") is not None:
        records.append(
            _record(
                record_id=f"{cycle_id}-energy" if cycle_id else None,
                start=start,
                end=end,
                type=str(ActivityMetric.ACTIVE_CALORIES),
                value=float(score["kilojoule"]) * KCAL_PER_KILOJOULE,
                unit="kcal",
            )
        )
    return records


def map_sleep(sleep: dict[str, Any]) -> list[RecordInput]:
    """Decompose a sleep activity into synthetic per-stage Records.

    v2 reports stage *totals*, not intervals, so stages are laid out
    back-to-back from the sleep's start (see module docstring). Sessions
    without a score fall back to a single ASLEEP_UNSPECIFIED record over
    the whole session.
    """
    start = _parse(sleep["start"])
    end = _parse(sleep["end"])
    sleep_id = sleep.get("id")
    stage_summary = (sleep.get("score") or {}).get("stage_summary") or {}
    records: list[RecordInput] = []

    cursor = start
    for key, sleep_value in _STAGE_LAYOUT:
        milli = stage_summary.get(key)
        if not milli:
            continue
        stage_end = cursor + timedelta(milliseconds=int(milli))
        records.append(
            _record(
                record_id=f"{sleep_id}-{key}" if sleep_id else None,
                start=cursor,
                end=stage_end,
                type=SLEEP_TYPE,
                value=sleep_value,
                unit=None,
            )
        )
        cursor = stage_end

    if not records:
        records.append(
            _record(
                record_id=f"{sleep_id}-session" if sleep_id else None,
                start=start,
                end=end,
                type=SLEEP_TYPE,
                value=SleepValue.ASLEEP_UNSPECIFIED,
                unit=None,
            )
        )

    respiratory_rate = (sleep.get("score") or {}).get("respiratory_rate")
    if respiratory_rate is not None:
        records.append(
            _record(
                record_id=f"{sleep_id}-respiratory-rate" if sleep_id else None,
                start=start,
                end=end,
                type=HK_RESPIRATORY_RATE,
                value=respiratory_rate,
                unit="count/min",
            )
        )
    return records


def map_recovery(recovery: dict[str, Any]) -> list[RecordInput]:
    """Point-in-time recovery metrics, stamped at the recovery's created_at."""
    instant = _parse(recovery["created_at"])
    score = recovery.get("score") or {}
    cycle_id = recovery.get("cycle_id")
    records: list[RecordInput] = []

    def add(suffix: str, type: str, unit: str | None, value: Any) -> None:
        if value is None:
            return
        records.append(
            _record(
                record_id=f"{cycle_id}-{suffix}" if cycle_id else None,
                start=instant,
                end=instant,
                type=type,
                value=value,
                unit=unit,
            )
        )

    add("recovery-score", WHOOP_RECOVERY_SCORE_TYPE, "%", score.get("recovery_score"))
    add(
        "resting-hr",
        HK_RESTING_HEART_RATE,
        "count/min",
        score.get("resting_heart_rate"),
    )
    # WHOOP reports RMSSD in milliseconds; HK's identifier says SDNN. See
    # module docstring.
    add("hrv-rmssd", HK_HEART_RATE_VARIABILITY, "ms", score.get("hrv_rmssd_milli"))
    add("spo2", HK_OXYGEN_SATURATION, "%", score.get("spo2_percentage"))
    add("skin-temp", HK_WRIST_TEMPERATURE, "degC", score.get("skin_temp_celsius"))
    return records


def map_body_measurement(
    body: dict[str, Any], *, at: datetime | None = None
) -> list[RecordInput]:
    """Height/weight snapshot. WHOOP reports current values with no history,
    so records are stamped at fetch time (``at``) and carry no recordId —
    each sync appends a fresh observation."""
    instant = at or datetime.now(timezone.utc)
    records: list[RecordInput] = []
    if body.get("weight_kilogram") is not None:
        records.append(
            _record(
                record_id=None,
                start=instant,
                end=instant,
                type=HK_BODY_MASS,
                value=body["weight_kilogram"],
                unit="kg",
            )
        )
    if body.get("height_meter") is not None:
        records.append(
            _record(
                record_id=None,
                start=instant,
                end=instant,
                type=HK_HEIGHT,
                value=body["height_meter"],
                unit="m",
            )
        )
    return records


def map_workout(workout: dict[str, Any]) -> WorkoutInput:
    start = _parse(workout["start"])
    end = _parse(workout["end"])
    score = workout.get("score") or {}
    distance_m = score.get("distance_meter")

    extra_metadata: list[MetadataEntry] = []

    def meta(key: str, value: Any) -> None:
        if value is not None:
            extra_metadata.append(MetadataEntry(key=key, value=str(value)))

    meta("strain", score.get("strain"))
    meta("average_heart_rate_bpm", score.get("average_heart_rate"))
    meta("max_heart_rate_bpm", score.get("max_heart_rate"))
    meta("percent_recorded", score.get("percent_recorded"))
    meta("altitude_gain_meter", score.get("altitude_gain_meter"))
    meta("altitude_change_meter", score.get("altitude_change_meter"))
    for zone_key, zone_milli in (score.get("zone_durations") or {}).items():
        meta(zone_key, zone_milli)

    kilojoule = score.get("kilojoule")
    return WorkoutInput(
        recordId=str(workout["id"]) if workout.get("id") else None,
        startDate=start,
        endDate=end,
        creationDate=_parse(workout["created_at"])
        if workout.get("created_at")
        else start,
        sourceName=SOURCE_NAME,
        durationUnit="s",
        duration=(end - start).total_seconds(),
        workoutActivityType=str(workout.get("sport_name", "unknown")),
        caloriesBurned=float(kilojoule) * KCAL_PER_KILOJOULE
        if kilojoule is not None
        else None,
        caloriesUnit="kcal" if kilojoule is not None else None,
        distance=float(distance_m) / 1000.0 if distance_m is not None else None,
        distanceUnit="km" if distance_m is not None else None,
        metadataEntry=extra_metadata or None,
    )


# Orchestrator ----------------------------------------------------------------


DEFAULT_COLLECTIONS: tuple[str, ...] = (
    COLLECTION_CYCLES,
    COLLECTION_SLEEPS,
    COLLECTION_RECOVERIES,
    COLLECTION_WORKOUTS,
    COLLECTION_BODY,
)

RECORD_MAPPERS = {
    COLLECTION_CYCLES: map_cycle,
    COLLECTION_SLEEPS: map_sleep,
    COLLECTION_RECOVERIES: map_recovery,
}


def ingest_resources(
    connection: WhoopConnection,
    collection: str,
    resources: list[dict[str, Any]],
) -> int:
    """Persist already-fetched WHOOP resources (e.g. from a webhook).

    Returns the number of records/workouts written. Unknown collections are
    skipped with a zero count so webhook processing stays forward-compatible.
    """
    if collection == COLLECTION_WORKOUTS:
        workouts = [map_workout(w) for w in resources]
        ingest_workouts(connection.customer, workouts, source=DataSource.WHOOP)
        return len(workouts)

    if collection == COLLECTION_BODY:
        records = []
        for body in resources:
            records.extend(map_body_measurement(body))
        ingest_records(connection.customer, records, source=DataSource.WHOOP)
        return len(records)

    mapper = RECORD_MAPPERS.get(collection)
    if mapper is None:
        return 0
    records = []
    for resource in resources:
        records.extend(mapper(resource))
    ingest_records(connection.customer, records, source=DataSource.WHOOP)
    return len(records)


def sync_user(
    connection: WhoopConnection,
    *,
    start: datetime,
    end: datetime,
    collections: list[str] | None = None,
    client: WhoopClient | None = None,
) -> SyncResult:
    """Fetch + ingest all configured collections for ``connection`` over [start, end].

    The window filters by the records' own time bounds (WHOOP semantics:
    ``start`` inclusive, records intersecting ``end`` included). The ``body``
    collection is a current-values snapshot and ignores the window.

    Pass a pre-built ``client`` to override the default (useful in tests).
    """
    result = SyncResult()
    owns_client = client is None
    if client is None:
        client = WhoopClient(connection)

    fetchers = {
        COLLECTION_CYCLES: lambda: list(client.iter_cycles(start=start, end=end)),
        COLLECTION_SLEEPS: lambda: list(client.iter_sleeps(start=start, end=end)),
        COLLECTION_RECOVERIES: lambda: list(
            client.iter_recoveries(start=start, end=end)
        ),
        COLLECTION_WORKOUTS: lambda: list(client.iter_workouts(start=start, end=end)),
        COLLECTION_BODY: lambda: [client.get_body_measurement()],
    }

    try:
        for collection in collections or DEFAULT_COLLECTIONS:
            fetcher = fetchers.get(collection)
            if fetcher is None:
                result.counts[collection] = 0
                continue
            result.counts[collection] = ingest_resources(
                connection, collection, fetcher()
            )
    finally:
        if owns_client:
            client.close()

    connection.last_sync_at = datetime.now(timezone.utc)
    connection.save(update_fields=["last_sync_at"])
    result.finished_at = datetime.now(timezone.utc)
    return result
