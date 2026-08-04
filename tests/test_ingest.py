import itertools
from datetime import datetime, timedelta, timezone

import pytest
import respx
from healthdatamodel.models import Record, Workout, WorkoutMetadataEntry
from httpx import Response

from whoop.client import WhoopClient
from whoop.constants import API_BASE_URL, WHOOP_RECOVERY_SCORE_TYPE, WHOOP_STRAIN_TYPE
from whoop.ingest import (
    map_body_measurement,
    map_cycle,
    map_recovery,
    map_sleep,
    map_workout,
    sync_user,
)

CYCLE = {
    "id": 93845,
    "user_id": 10129,
    "created_at": "2022-04-24T11:25:44.774Z",
    "updated_at": "2022-04-24T14:25:44.774Z",
    "start": "2022-04-24T02:25:44.774Z",
    "end": "2022-04-24T10:25:44.774Z",
    "timezone_offset": "-05:00",
    "score_state": "SCORED",
    "score": {
        "strain": 5.2951527,
        "kilojoule": 8288.297,
        "average_heart_rate": 68,
        "max_heart_rate": 141,
    },
}

SLEEP = {
    "id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8",
    "cycle_id": 93845,
    "user_id": 10129,
    "created_at": "2022-04-24T11:25:44.774Z",
    "updated_at": "2022-04-24T14:25:44.774Z",
    "start": "2022-04-24T02:25:44.774Z",
    "end": "2022-04-24T10:25:44.774Z",
    "timezone_offset": "-05:00",
    "nap": False,
    "score_state": "SCORED",
    "score": {
        "stage_summary": {
            "total_in_bed_time_milli": 30272735,
            "total_awake_time_milli": 1403507,
            "total_no_data_time_milli": 0,
            "total_light_sleep_time_milli": 14905851,
            "total_slow_wave_sleep_time_milli": 6630370,
            "total_rem_sleep_time_milli": 5879573,
            "sleep_cycle_count": 3,
            "disturbance_count": 12,
        },
        "sleep_needed": {
            "baseline_milli": 27395716,
            "need_from_sleep_debt_milli": 352230,
            "need_from_recent_strain_milli": 208595,
            "need_from_recent_nap_milli": -12312,
        },
        "respiratory_rate": 16.11328125,
        "sleep_performance_percentage": 98,
        "sleep_consistency_percentage": 90,
        "sleep_efficiency_percentage": 91.69533848,
    },
}

RECOVERY = {
    "cycle_id": 93845,
    "sleep_id": "123e4567-e89b-12d3-a456-426614174000",
    "user_id": 10129,
    "created_at": "2022-04-24T11:25:44.774Z",
    "updated_at": "2022-04-24T14:25:44.774Z",
    "score_state": "SCORED",
    "score": {
        "user_calibrating": False,
        "recovery_score": 44,
        "resting_heart_rate": 64,
        "hrv_rmssd_milli": 31.813562,
        "spo2_percentage": 95.6875,
        "skin_temp_celsius": 33.7,
    },
}

WORKOUT = {
    "id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8",
    "user_id": 9012,
    "created_at": "2022-04-24T11:25:44.774Z",
    "updated_at": "2022-04-24T14:25:44.774Z",
    "start": "2022-04-24T02:25:44.774Z",
    "end": "2022-04-24T03:25:44.774Z",
    "timezone_offset": "-05:00",
    "sport_name": "running",
    "score_state": "SCORED",
    "score": {
        "strain": 8.2463,
        "average_heart_rate": 123,
        "max_heart_rate": 146,
        "kilojoule": 1569.34,
        "percent_recorded": 100.0,
        "distance_meter": 1772.77,
        "altitude_gain_meter": 46.64,
        "altitude_change_meter": -0.78,
        "zone_durations": {
            "zone_zero_milli": 300000,
            "zone_one_milli": 600000,
            "zone_two_milli": 900000,
            "zone_three_milli": 900000,
            "zone_four_milli": 600000,
            "zone_five_milli": 300000,
        },
    },
}

BODY = {"height_meter": 1.8288, "weight_kilogram": 90.7185, "max_heart_rate": 200}


class TestMapCycle:
    def test_strain_and_energy(self):
        records = map_cycle(CYCLE)
        by_type = {r.type: r for r in records}

        strain = by_type[WHOOP_STRAIN_TYPE]
        assert strain.value == "5.2951527"
        assert strain.recordId == "93845-strain"
        assert strain.startDate == datetime(
            2022, 4, 24, 2, 25, 44, 774000, tzinfo=timezone.utc
        )

        energy = by_type["HKQuantityTypeIdentifierActiveEnergyBurned"]
        assert energy.unit == "kcal"
        assert float(energy.value) == pytest.approx(8288.297 / 4.184)

    def test_unscored_cycle_yields_nothing(self):
        pending = {**CYCLE, "score_state": "PENDING_SCORE", "score": None}
        assert map_cycle(pending) == []

    def test_open_cycle_uses_updated_at(self):
        open_cycle = {**CYCLE}
        del open_cycle["end"]
        records = map_cycle(open_cycle)
        assert all(
            r.endDate == datetime(2022, 4, 24, 14, 25, 44, 774000, tzinfo=timezone.utc)
            for r in records
        )


class TestMapSleep:
    def test_stages_are_sequential_and_sum_exactly(self):
        records = map_sleep(SLEEP)
        stages = [
            r for r in records if r.type == "HKCategoryTypeIdentifierSleepAnalysis"
        ]
        assert len(stages) == 4  # light, SWS, REM, awake

        start = datetime(2022, 4, 24, 2, 25, 44, 774000, tzinfo=timezone.utc)
        assert stages[0].startDate == start
        for prev, nxt in itertools.pairwise(stages):
            assert prev.endDate == nxt.startDate

        summary = SLEEP["score"]["stage_summary"]
        asleep_milli = (
            summary["total_light_sleep_time_milli"]
            + summary["total_slow_wave_sleep_time_milli"]
            + summary["total_rem_sleep_time_milli"]
        )
        asleep = [s for s in stages if "Asleep" in s.value]
        total = sum((s.endDate - s.startDate).total_seconds() for s in asleep)
        assert total == pytest.approx(asleep_milli / 1000)

    def test_stage_values(self):
        records = map_sleep(SLEEP)
        values = {r.recordId: r.value for r in records}
        assert (
            values[f"{SLEEP['id']}-total_light_sleep_time_milli"]
            == "HKCategoryValueSleepAnalysisAsleepCore"
        )
        assert (
            values[f"{SLEEP['id']}-total_slow_wave_sleep_time_milli"]
            == "HKCategoryValueSleepAnalysisAsleepDeep"
        )
        assert (
            values[f"{SLEEP['id']}-total_rem_sleep_time_milli"]
            == "HKCategoryValueSleepAnalysisAsleepREM"
        )
        assert (
            values[f"{SLEEP['id']}-total_awake_time_milli"]
            == "HKCategoryValueSleepAnalysisAwake"
        )

    def test_respiratory_rate_record(self):
        records = map_sleep(SLEEP)
        resp = [
            r for r in records if r.type == "HKQuantityTypeIdentifierRespiratoryRate"
        ]
        assert len(resp) == 1
        assert resp[0].unit == "count/min"
        assert float(resp[0].value) == pytest.approx(16.11328125)

    def test_unscored_sleep_falls_back_to_session_record(self):
        pending = {**SLEEP, "score_state": "PENDING_SCORE", "score": None}
        records = map_sleep(pending)
        assert len(records) == 1
        assert records[0].value == "HKCategoryValueSleepAnalysisAsleepUnspecified"
        assert records[0].startDate < records[0].endDate


class TestMapRecovery:
    def test_all_metrics(self):
        records = map_recovery(RECOVERY)
        by_type = {r.type: r for r in records}

        assert by_type[WHOOP_RECOVERY_SCORE_TYPE].value == "44"
        assert by_type["HKQuantityTypeIdentifierRestingHeartRate"].value == "64"
        assert float(
            by_type["HKQuantityTypeIdentifierHeartRateVariabilitySDNN"].value
        ) == pytest.approx(31.813562)
        assert float(
            by_type["HKQuantityTypeIdentifierOxygenSaturation"].value
        ) == pytest.approx(95.6875)
        assert float(
            by_type["HKQuantityTypeIdentifierAppleSleepingWristTemperature"].value
        ) == pytest.approx(33.7)

        instant = datetime(2022, 4, 24, 11, 25, 44, 774000, tzinfo=timezone.utc)
        assert all(r.startDate == r.endDate == instant for r in records)

    def test_missing_optional_fields_skipped(self):
        older_device = {
            **RECOVERY,
            "score": {
                "user_calibrating": False,
                "recovery_score": 44,
                "resting_heart_rate": 64,
                "hrv_rmssd_milli": 31.8,
            },
        }
        records = map_recovery(older_device)
        types = {r.type for r in records}
        assert "HKQuantityTypeIdentifierOxygenSaturation" not in types
        assert "HKQuantityTypeIdentifierAppleSleepingWristTemperature" not in types

    def test_unscored_recovery_yields_nothing(self):
        pending = {**RECOVERY, "score_state": "PENDING_SCORE", "score": None}
        assert map_recovery(pending) == []


class TestMapBodyMeasurement:
    def test_height_and_weight(self):
        at = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
        records = map_body_measurement(BODY, at=at)
        by_type = {r.type: r for r in records}
        assert float(by_type["HKQuantityTypeIdentifierBodyMass"].value) == 90.7185
        assert by_type["HKQuantityTypeIdentifierBodyMass"].unit == "kg"
        assert float(by_type["HKQuantityTypeIdentifierHeight"].value) == 1.8288
        assert all(r.startDate == at for r in records)


class TestMapWorkout:
    def test_core_fields(self):
        workout = map_workout(WORKOUT)
        assert workout.recordId == WORKOUT["id"]
        assert workout.workoutActivityType == "running"
        assert workout.duration == 3600.0
        assert workout.durationUnit == "s"
        assert workout.caloriesBurned == pytest.approx(1569.34 / 4.184)
        assert workout.caloriesUnit == "kcal"
        assert workout.distance == pytest.approx(1.77277)
        assert workout.distanceUnit == "km"

    def test_metadata(self):
        workout = map_workout(WORKOUT)
        meta = {e.key: e.value for e in workout.metadataEntry}
        assert meta["strain"] == "8.2463"
        assert meta["average_heart_rate_bpm"] == "123"
        assert meta["max_heart_rate_bpm"] == "146"
        assert meta["zone_two_milli"] == "900000"

    def test_unscored_workout(self):
        pending = {**WORKOUT, "score_state": "PENDING_SCORE", "score": None}
        workout = map_workout(pending)
        assert workout.caloriesBurned is None
        assert workout.distance is None
        assert workout.metadataEntry is None


@pytest.mark.django_db
class TestSyncUser:
    @respx.mock
    def test_full_sync_persists_records_and_workouts(self, connection):
        respx.get(f"{API_BASE_URL}/v2/cycle").mock(
            return_value=Response(200, json={"records": [CYCLE]})
        )
        respx.get(f"{API_BASE_URL}/v2/activity/sleep").mock(
            return_value=Response(200, json={"records": [SLEEP]})
        )
        respx.get(f"{API_BASE_URL}/v2/recovery").mock(
            return_value=Response(200, json={"records": [RECOVERY]})
        )
        respx.get(f"{API_BASE_URL}/v2/activity/workout").mock(
            return_value=Response(200, json={"records": [WORKOUT]})
        )
        respx.get(f"{API_BASE_URL}/v2/user/measurement/body").mock(
            return_value=Response(200, json=BODY)
        )

        end = datetime.now(timezone.utc)
        result = sync_user(connection, start=end - timedelta(days=7), end=end)

        assert result.counts == {
            "cycles": 2,  # strain + energy
            "sleeps": 5,  # 4 stages + respiratory rate
            "recoveries": 5,
            "workouts": 1,
            "body": 2,
        }
        assert result.total == 15

        assert Record.objects.filter(customer=connection.customer).count() == 14
        assert Record.objects.filter(source="whoop").count() == 14
        workout = Workout.objects.get(customer=connection.customer)
        assert workout.source == "whoop"
        assert workout.workoutActivityType == "running"
        assert WorkoutMetadataEntry.objects.filter(workout=workout).count() > 0

        connection.refresh_from_db()
        assert connection.last_sync_at is not None

    @respx.mock
    def test_collection_subset(self, connection):
        route = respx.get(f"{API_BASE_URL}/v2/activity/sleep").mock(
            return_value=Response(200, json={"records": [SLEEP]})
        )
        end = datetime.now(timezone.utc)
        result = sync_user(
            connection,
            start=end - timedelta(days=1),
            end=end,
            collections=["sleeps"],
        )
        assert route.called
        assert set(result.counts) == {"sleeps"}

    @respx.mock
    def test_injected_client_is_not_closed(self, connection):
        respx.get(f"{API_BASE_URL}/v2/cycle").mock(
            return_value=Response(200, json={"records": []})
        )
        client = WhoopClient(connection)
        end = datetime.now(timezone.utc)
        sync_user(
            connection,
            start=end - timedelta(days=1),
            end=end,
            collections=["cycles"],
            client=client,
        )
        # A closed httpx client raises on reuse; this should not.
        respx.get(f"{API_BASE_URL}/v2/user/measurement/body").mock(
            return_value=Response(200, json=BODY)
        )
        client.get_body_measurement()
        client.close()
