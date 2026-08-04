from datetime import datetime, timedelta, timezone

import pytest
import respx
from httpx import Response

from whoop.client import WhoopAPIError, WhoopClient
from whoop.constants import API_BASE_URL, OAUTH_TOKEN_URL

CYCLE_URL = f"{API_BASE_URL}/v2/cycle"


@pytest.fixture
def client(connection):
    with WhoopClient(connection, sleep=lambda s: None) as c:
        yield c


@pytest.mark.django_db
class TestAuth:
    @respx.mock
    def test_sends_bearer_token(self, client):
        route = respx.get(f"{API_BASE_URL}/v2/user/profile/basic").mock(
            return_value=Response(200, json={"user_id": 10129})
        )
        client.get_profile()
        auth = route.calls.last.request.headers["Authorization"]
        assert auth == "Bearer whoop-initial-access"

    @respx.mock
    def test_expired_token_refreshes_proactively(self, connection):
        connection.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        connection.save()
        respx.post(OAUTH_TOKEN_URL).mock(
            return_value=Response(
                200,
                json={
                    "access_token": "refreshed-access",
                    "expires_in": 3600,
                    "refresh_token": "refreshed-refresh",
                },
            )
        )
        route = respx.get(f"{API_BASE_URL}/v2/user/measurement/body").mock(
            return_value=Response(200, json={"height_meter": 1.8})
        )
        with WhoopClient(connection) as client:
            client.get_body_measurement()
        auth = route.calls.last.request.headers["Authorization"]
        assert auth == "Bearer refreshed-access"

    @respx.mock
    def test_401_refreshes_and_retries_once(self, client, connection):
        respx.post(OAUTH_TOKEN_URL).mock(
            return_value=Response(
                200,
                json={
                    "access_token": "refreshed-access",
                    "expires_in": 3600,
                    "refresh_token": "refreshed-refresh",
                },
            )
        )
        route = respx.get(f"{API_BASE_URL}/v2/user/profile/basic").mock(
            side_effect=[
                Response(401, json={"message": "expired"}),
                Response(200, json={"user_id": 10129}),
            ]
        )
        payload = client.get_profile()
        assert payload == {"user_id": 10129}
        assert route.call_count == 2

    @respx.mock
    def test_second_401_raises(self, client, connection):
        respx.post(OAUTH_TOKEN_URL).mock(
            return_value=Response(
                200, json={"access_token": "still-bad", "expires_in": 3600}
            )
        )
        respx.get(f"{API_BASE_URL}/v2/user/profile/basic").mock(
            return_value=Response(401, json={"message": "nope"})
        )
        with pytest.raises(WhoopAPIError) as excinfo:
            client.get_profile()
        assert excinfo.value.status_code == 401


@pytest.mark.django_db
class TestRetries:
    @respx.mock
    def test_retries_on_5xx_then_succeeds(self, client):
        route = respx.get(CYCLE_URL).mock(
            side_effect=[
                Response(503),
                Response(200, json={"records": [{"id": 1}]}),
            ]
        )
        cycles = list(client.iter_cycles())
        assert cycles == [{"id": 1}]
        assert route.call_count == 2

    @respx.mock
    def test_gives_up_after_max_retries(self, connection):
        respx.get(CYCLE_URL).mock(return_value=Response(500, text="boom"))
        with (
            WhoopClient(connection, max_retries=2, sleep=lambda s: None) as client,
            pytest.raises(WhoopAPIError) as excinfo,
        ):
            list(client.iter_cycles())
        assert excinfo.value.status_code == 500

    @respx.mock
    def test_honors_retry_after(self, connection):
        sleeps = []
        respx.get(CYCLE_URL).mock(
            side_effect=[
                Response(429, headers={"Retry-After": "7"}),
                Response(200, json={"records": []}),
            ]
        )
        with WhoopClient(connection, sleep=sleeps.append) as client:
            list(client.iter_cycles())
        assert sleeps == [7.0]

    @respx.mock
    def test_4xx_error_message_extracted(self, client):
        respx.get(CYCLE_URL).mock(
            return_value=Response(400, json={"message": "bad window"})
        )
        with pytest.raises(WhoopAPIError, match="bad window"):
            list(client.iter_cycles())


@pytest.mark.django_db
class TestPagination:
    @respx.mock
    def test_walks_next_token(self, client):
        route = respx.get(CYCLE_URL).mock(
            side_effect=[
                Response(
                    200, json={"records": [{"id": 1}, {"id": 2}], "next_token": "t2"}
                ),
                Response(200, json={"records": [{"id": 3}]}),
            ]
        )
        cycles = list(
            client.iter_cycles(
                start=datetime(2026, 7, 1, tzinfo=timezone.utc),
                end=datetime(2026, 7, 7, tzinfo=timezone.utc),
            )
        )
        assert [c["id"] for c in cycles] == [1, 2, 3]

        first = route.calls[0].request.url
        assert first.params["start"] == "2026-07-01T00:00:00.000Z"
        assert first.params["end"] == "2026-07-07T00:00:00.000Z"
        assert first.params["limit"] == "25"
        assert "nextToken" not in first.params

        second = route.calls[1].request.url
        assert second.params["nextToken"] == "t2"

    @respx.mock
    def test_page_size_capped_at_25(self, client):
        route = respx.get(CYCLE_URL).mock(
            return_value=Response(200, json={"records": []})
        )
        list(client.iter_cycles(page_size=100))
        assert route.calls.last.request.url.params["limit"] == "25"

    @respx.mock
    def test_collection_paths(self, client):
        for path, iterator in [
            ("v2/activity/sleep", client.iter_sleeps),
            ("v2/recovery", client.iter_recoveries),
            ("v2/activity/workout", client.iter_workouts),
        ]:
            route = respx.get(f"{API_BASE_URL}/{path}").mock(
                return_value=Response(200, json={"records": []})
            )
            list(iterator())
            assert route.called


@pytest.mark.django_db
class TestSingleResources:
    @respx.mock
    def test_get_sleep_by_uuid(self, client):
        sleep_id = "ecfc6a15-4661-442f-a9a4-f160dd7afae8"
        route = respx.get(f"{API_BASE_URL}/v2/activity/sleep/{sleep_id}").mock(
            return_value=Response(200, json={"id": sleep_id})
        )
        assert client.get_sleep(sleep_id) == {"id": sleep_id}
        assert route.called

    @respx.mock
    def test_get_cycle_recovery(self, client):
        route = respx.get(f"{API_BASE_URL}/v2/cycle/93845/recovery").mock(
            return_value=Response(200, json={"cycle_id": 93845})
        )
        assert client.get_cycle_recovery(93845) == {"cycle_id": 93845}
        assert route.called
