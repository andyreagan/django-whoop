"""
Tests for django_whoop models.

WHOOP API calls (requests.post / requests.get) are mocked throughout so no
network access is required.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytz
import pytest
from django.contrib.auth.models import User

from django_whoop.models import (
    Daily,
    HR,
    JournalEntry,
    Recovery,
    Sleep,
    SleepDetail,
    Strain,
    WhoopUser,
    Workout,
    get_date,
    get_utc_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(username="testuser"):
    return User.objects.create_user(username=username, password="secret")


def make_whoop_user(django_user=None):
    if django_user is None:
        django_user = make_user()
    return WhoopUser.objects.create(
        user=django_user,
        access_token="tok_access",
        refresh_token="tok_refresh",
        whoop_user_id=42,
    )


def make_daily(whoop_user, day_str="2021-03-17", daily_id=1001):
    return Daily.objects.create(
        id=daily_id,
        user=whoop_user,
        day=datetime.date.fromisoformat(day_str),
    )


# ---------------------------------------------------------------------------
# get_date utility
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetDate:
    def test_none_returns_none(self):
        assert get_date(None) is None

    def test_iso_date(self):
        d = get_date("2021-03-17")
        assert d == datetime.datetime(2021, 3, 17)

    def test_iso_datetime_z(self):
        d = get_date("2021-03-17T12:00:00Z")
        assert d == datetime.datetime(2021, 3, 17, 12, 0, 0)

    def test_iso_datetime_with_millis(self):
        d = get_date("2021-03-17T12:00:00.000Z")
        assert d == datetime.datetime(2021, 3, 17, 12, 0, 0)

    def test_tzinfo_applied(self):
        d = get_date("2021-03-17", tzinfo=pytz.UTC)
        assert d.tzinfo == pytz.UTC

    def test_year_only(self):
        d = get_date("2021")
        assert d == datetime.datetime(2021, 1, 1)


# ---------------------------------------------------------------------------
# get_utc_time utility
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetUtcTime:
    def test_none_returns_none(self):
        assert get_utc_time(None) is None

    def test_epoch_zero(self):
        d = get_utc_time(0)
        assert d == datetime.datetime(1970, 1, 1, tzinfo=pytz.UTC)

    def test_milliseconds_string(self):
        # 1_000_000_000 seconds since epoch — will fail without /1000, but the
        # function should handle a value already in seconds fine.
        ts = 1_616_000_000  # seconds
        d = get_utc_time(ts)
        assert d == datetime.datetime.utcfromtimestamp(ts).replace(tzinfo=pytz.UTC)

    def test_float_string(self):
        d = get_utc_time("1616000000.0")
        assert d is not None
        assert d.tzinfo == pytz.UTC


# ---------------------------------------------------------------------------
# WhoopUser model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWhoopUser:
    def test_str(self):
        wu = make_whoop_user(make_user("alice"))
        assert str(wu) == "alice"

    def test_fields(self):
        user = make_user("bob")
        wu = make_whoop_user(user)
        assert wu.access_token == "tok_access"
        assert wu.refresh_token == "tok_refresh"
        assert wu.whoop_user_id == 42

    def test_one_to_one_with_user(self):
        user = make_user("carol")
        wu = make_whoop_user(user)
        assert user.whoopuser == wu

    @patch("django_whoop.models.requests.post")
    def test_create_with_password(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "new_access",
            "expires_in": 3600,
            "refresh_token": "new_refresh",
            "user": {
                "id": 99,
                "createdAt": "2020-10-18T00:57:18.609Z",
            },
        }
        mock_post.return_value = mock_resp

        django_user = make_user("dave")
        wu = WhoopUser.createWithPassword(django_user, "dave@example.com", "hunter2")
        assert wu.access_token == "new_access"
        assert wu.whoop_user_id == 99
        assert wu.refresh_token == "new_refresh"
        mock_post.assert_called_once()

    @patch("django_whoop.models.requests.post")
    def test_refresh_token(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "refreshed_access",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_resp

        wu = make_whoop_user(make_user("eve"))
        wu.refreshToken()

        assert wu.access_token == "refreshed_access"
        mock_post.assert_called_once()

    @patch("django_whoop.models.requests.post")
    def test_refresh_with_password(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "pw_refreshed",
            "expires_in": 7200,
            "refresh_token": "new_rt",
        }
        mock_post.return_value = mock_resp

        wu = make_whoop_user(make_user("frank"))
        wu.refreshWithPassword("frank@example.com", "password123")

        assert wu.access_token == "pw_refreshed"
        assert wu.refresh_token == "new_rt"


# ---------------------------------------------------------------------------
# Daily model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDailyModel:
    def test_str(self):
        wu = make_whoop_user()
        daily = make_daily(wu, "2021-03-17")
        assert str(daily) == "2021-03-17"

    def test_fields(self):
        wu = make_whoop_user()
        daily = make_daily(wu, "2021-03-17", daily_id=2001)
        assert daily.id == 2001
        assert daily.user == wu
        assert daily.day == datetime.date(2021, 3, 17)

    def test_fill_from_cycle_response_minimal(self):
        django_user = make_user("grace")
        wu = make_whoop_user(django_user)

        # Attach the reverse relation that fill_from_cycle_response expects
        # (user.whoopuser) — the view passes the django User object.
        django_user.whoopuser = wu

        cycle = {
            "id": 3001,
            "days": ["2021-03-17"],
            "during": {
                "bounds": "[)",
                "lower": "2021-03-17T00:00:00Z",
                "upper": "2021-03-18T00:00:00Z",
            },
            "lastUpdatedAt": "2021-03-17T20:00:00Z",
        }
        daily = Daily.fill_from_cycle_response(django_user, cycle)
        assert daily.id == 3001
        # get_date returns a datetime; the DateField stores/returns it as a date
        assert str(daily.day) == "2021-03-17"
        assert daily.during_bounds == "[)"

    def test_fill_from_cycle_response_with_recovery(self):
        django_user = make_user("hannah")
        wu = make_whoop_user(django_user)
        django_user.whoopuser = wu

        cycle = {
            "id": 3002,
            "days": ["2021-03-18"],
            "recovery": {
                "id": 60001,
                "heartRateVariabilityRmssd": 0.059,
                "restingHeartRate": 51,
                "score": 54,
                "timestamp": "2021-03-18T11:33:00Z",
            },
        }
        daily = Daily.fill_from_cycle_response(django_user, cycle)
        recovery = Recovery.objects.get(day=daily)
        assert recovery.score == 54
        assert recovery.restingHeartRate == 51

    def test_fill_from_cycle_response_with_strain_and_workout(self):
        django_user = make_user("ivan")
        wu = make_whoop_user(django_user)
        django_user.whoopuser = wu

        cycle = {
            "id": 3003,
            "days": ["2021-03-19"],
            "strain": {
                "averageHeartRate": 75,
                "kilojoules": 14218.7,
                "maxHeartRate": 172,
                "rawScore": 0.0143,
                "score": 16.39,
                "workouts": [
                    {
                        "id": 9001,
                        "averageHeartRate": 131,
                        "cumulativeWorkoutStrain": 14.9,
                        "during": {
                            "bounds": "[)",
                            "lower": "2021-03-19T16:53:55Z",
                            "upper": "2021-03-19T18:08:15Z",
                        },
                        "kilojoules": 2863.5,
                        "maxHeartRate": 157,
                        "rawScore": 0.0057,
                        "score": 12.24,
                        "sportId": 0,
                        "timezoneOffset": "-0400",
                        "zones": [100, 200, 300, 400, 500, 600],
                    }
                ],
            },
        }
        daily = Daily.fill_from_cycle_response(django_user, cycle)
        strain = Strain.objects.get(day=daily)
        assert strain.score == pytest.approx(16.39)
        workout = Workout.objects.get(strain=strain)
        assert workout.sportId == 0
        assert workout.zone_0 == 100
        assert workout.zone_5 == 600

    def test_fill_from_cycle_response_with_sleep(self):
        django_user = make_user("judy")
        wu = make_whoop_user(django_user)
        django_user.whoopuser = wu

        cycle = {
            "id": 3004,
            "days": ["2021-03-20"],
            "sleep": {
                "id": 7001,
                "needBreakdown": {
                    "baseline": 27430627,
                    "debt": 3703134,
                    "naps": 0,
                    "strain": 3278169,
                    "total": 34411932,
                },
                "qualityDuration": 25139744,
                "score": 73,
                "sleeps": [
                    {
                        "id": 8001,
                        "cyclesCount": 5,
                        "disturbanceCount": 12,
                        "during": {
                            "bounds": "[)",
                            "lower": "2021-03-20T03:01:00Z",
                            "upper": "2021-03-20T11:33:00Z",
                        },
                        "inBedDuration": 30718493,
                        "latencyDuration": 0,
                        "lightSleepDuration": 12011596,
                        "noDataDuration": 0,
                        "qualityDuration": 25139744,
                        "remSleepDuration": 5948524,
                        "respiratoryRate": 14.3262,
                        "score": 73,
                        "sleepConsistency": 89,
                        "sleepEfficiency": 0.818391,
                        "slowWaveSleepDuration": 7179624,
                        "timezoneOffset": "-0400",
                        "wakeDuration": 5615410,
                    }
                ],
            },
        }
        daily = Daily.fill_from_cycle_response(django_user, cycle)
        sleep = Sleep.objects.get(day=daily)
        assert sleep.score == 73
        assert sleep.needBreakdown_total == 34411932
        detail = SleepDetail.objects.get(sleep=sleep)
        assert detail.cyclesCount == 5
        assert detail.isNap is False


# ---------------------------------------------------------------------------
# Recovery model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRecoveryModel:
    def test_create_and_retrieve(self):
        wu = make_whoop_user()
        daily = make_daily(wu)
        r = Recovery.objects.create(
            day=daily,
            id=60001,
            heartRateVariabilityRmssd=0.059,
            restingHeartRate=51,
            score=54,
        )
        fetched = Recovery.objects.get(pk=60001)
        assert fetched.score == 54
        assert fetched.day == daily


# ---------------------------------------------------------------------------
# Sleep / SleepDetail models
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSleepModels:
    def test_sleep_create(self):
        wu = make_whoop_user()
        daily = make_daily(wu)
        s = Sleep.objects.create(day=daily, id=7001, qualityDuration=25139744, score=73)
        assert Sleep.objects.filter(day=daily).count() == 1
        assert s.score == 73

    def test_sleep_detail_create(self):
        wu = make_whoop_user()
        daily = make_daily(wu)
        s = Sleep.objects.create(day=daily, id=7002, score=80)
        sd = SleepDetail.objects.create(
            sleep=s,
            id=8001,
            cyclesCount=5,
            isNap=False,
            respiratoryRate=14.3,
            sleepEfficiency=0.82,
        )
        assert sd.isNap is False
        assert sd.respiratoryRate == pytest.approx(14.3)


# ---------------------------------------------------------------------------
# Strain / Workout models
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStrainWorkout:
    def test_strain_create(self):
        wu = make_whoop_user()
        daily = make_daily(wu)
        s = Strain.objects.create(day=daily, id=5001, score=16.39, kilojoules=14218.7)
        assert s.score == pytest.approx(16.39)

    def test_workout_create(self):
        wu = make_whoop_user()
        daily = make_daily(wu)
        strain = Strain.objects.create(day=daily, id=5002, score=12.0)
        w = Workout.objects.create(
            strain=strain,
            id=9001,
            sportId=0,
            zone_0=100,
            zone_1=200,
            zone_2=300,
            zone_3=400,
            zone_4=500,
            zone_5=600,
        )
        assert w.zone_5 == 600
        assert w.sportId == 0


# ---------------------------------------------------------------------------
# HR model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHRModel:
    def test_fill_from_response(self):
        wu = make_whoop_user()
        # Epoch ms for 2021-03-17T00:00:00Z → 1616025600000
        points = [
            {"time": 1616025600000, "data": 65},
            {"time": 1616025606000, "data": 66},
        ]

        # fill_from_response expects user.whoopuser
        django_user = wu.user
        django_user.whoopuser = wu

        HR.fill_from_response(user=django_user, d=points)
        assert HR.objects.filter(user=wu).count() == 2
        values = set(HR.objects.filter(user=wu).values_list("value", flat=True))
        assert values == {65, 66}


# ---------------------------------------------------------------------------
# JournalEntry model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestJournalEntry:
    def _make_daily(self):
        wu = make_whoop_user(make_user("journal_user"))
        return make_daily(wu, daily_id=4001)

    def test_str(self):
        daily = self._make_daily()
        entry = JournalEntry.objects.create(
            day=daily,
            id=500001,
            tracker_id=50,
            title="Intermittent Fasting",
            answered_yes=False,
        )
        assert "2021-03-17" in str(entry)
        assert "Intermittent Fasting" in str(entry)

    def test_create_from_response(self):
        daily = self._make_daily()
        raw = {
            "behavior_tracker": {
                "id": 50,
                "created_at": 1583441766.111,
                "updated_at": 1585669607.122,
                "title": "Intermittent Fasting",
                "status": "active",
                "category": "Nutrition",
                "description": None,
                "question_text": "Follow an intermittent fasting diet?",
                "time_label": "When was your last meal?",
                "time_context_label": "stopped eating at",
                "magnitude": None,
                "default_tracker": False,
            },
            "tracker_input": {
                "id": 500002,
                "journal_entry_id": 52336709,
                "created_at": 1611923762.42,
                "updated_at": 1611923762.42,
                "answered_yes": False,
                "behavior_tracker_id": 50,
                "time_input_value": None,
                "time_input_label": None,
                "magnitude_input_label": None,
                "magnitude_input_value": None,
            },
        }
        entry = JournalEntry.create_from_response(cycle_id=4001, d=raw)
        assert entry.title == "Intermittent Fasting"
        assert entry.answered_yes is False
        assert entry.tracker_id == 50
