from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model

from whoop.models import WhoopConnection


@pytest.fixture
def customer(db):
    User = get_user_model()
    return User.objects.create_user(username="test-customer")


@pytest.fixture
def connection(customer):
    return WhoopConnection.objects.create(
        customer=customer,
        whoop_user_id="10129",
        access_token="whoop-initial-access",
        refresh_token="whoop-initial-refresh",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=[
            "read:cycles",
            "read:sleep",
            "read:recovery",
            "read:workout",
            "offline",
        ],
    )
