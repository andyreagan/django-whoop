"""
Tests for django_whoop views.

The views extend a 'base.html' template that lives in the consuming project,
not inside django_whoop itself.  We inject a stub via Django's locmem loader
using the pytest-django ``settings`` fixture.

WHOOP API calls (requests.post / requests.get) are mocked throughout.
"""
import pytest
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client

from django_whoop.models import WhoopUser


# ---------------------------------------------------------------------------
# Stub base template injected via the ``settings`` fixture
# ---------------------------------------------------------------------------

STUB_BASE = "{% block body %}{% endblock %}"

PATCHED_TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "OPTIONS": {
            "context_processors": ["django.template.context_processors.request"],
            "loaders": [
                (
                    "django.template.loaders.locmem.Loader",
                    {"base.html": STUB_BASE},
                ),
                "django.template.loaders.app_directories.Loader",
            ],
        },
    }
]


@pytest.fixture
def tmpl_settings(settings):
    """Override TEMPLATES to include a stub base.html."""
    settings.TEMPLATES = PATCHED_TEMPLATES


@pytest.fixture
def logged_in_user(db):
    return User.objects.create_user(username="viewer", password="pass")


@pytest.fixture
def logged_in_client(logged_in_user):
    c = Client()
    c.force_login(logged_in_user)
    return c


# ---------------------------------------------------------------------------
# URL routing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestURLRouting:
    def test_login_url_resolves(self):
        from django.urls import reverse
        assert reverse("whooplogin") == "/whoop/login"

    def test_reauth_url_resolves(self):
        from django.urls import reverse
        assert reverse("whoopreauth") == "/whoop/reauth"

    def test_logout_url_resolves(self):
        from django.urls import reverse
        assert reverse("whooplogout") == "/whoop/logout"

    def test_success_url_resolves(self):
        from django.urls import reverse
        assert reverse("whoopsuccess") == "/whoop/success"


# ---------------------------------------------------------------------------
# login view
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLoginView:
    def test_get_returns_200(self, tmpl_settings, logged_in_client):
        response = logged_in_client.get("/whoop/login")
        assert response.status_code == 200

    def test_get_contains_form(self, tmpl_settings, logged_in_client):
        response = logged_in_client.get("/whoop/login")
        assert b"username" in response.content.lower()
        assert b"password" in response.content.lower()

    @patch("django_whoop.models.requests.post")
    def test_post_redirects_to_success(self, mock_post, tmpl_settings, logged_in_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "tok123",
            "expires_in": 3600,
            "refresh_token": "ref123",
            "user": {"id": 77, "createdAt": "2020-10-18T00:57:18.609Z"},
        }
        mock_post.return_value = mock_resp

        response = logged_in_client.post(
            "/whoop/login",
            {"username": "whoop@example.com", "password": "secret"},
        )
        assert response.status_code == 302
        assert response["Location"] == "/whoop/success"

    @patch("django_whoop.models.requests.post")
    def test_post_saves_token_to_db(self, mock_post, tmpl_settings, logged_in_client, logged_in_user):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "saved_tok",
            "expires_in": 3600,
            "refresh_token": "saved_ref",
            "user": {"id": 88, "createdAt": "2020-01-01T00:00:00.000Z"},
        }
        mock_post.return_value = mock_resp

        logged_in_client.post(
            "/whoop/login",
            {"username": "w@example.com", "password": "pw"},
        )
        wu = WhoopUser.objects.get(user=logged_in_user)
        assert wu.access_token == "saved_tok"
        assert wu.whoop_user_id == 88


# ---------------------------------------------------------------------------
# reauth view
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReauthView:
    def _make_whoop_user(self, django_user):
        return WhoopUser.objects.create(
            user=django_user,
            access_token="old_tok",
            refresh_token="old_ref",
            whoop_user_id=42,
        )

    def test_get_returns_200(self, tmpl_settings, logged_in_client, logged_in_user):
        self._make_whoop_user(logged_in_user)
        response = logged_in_client.get("/whoop/reauth")
        assert response.status_code == 200

    def test_get_contains_form(self, tmpl_settings, logged_in_client, logged_in_user):
        self._make_whoop_user(logged_in_user)
        response = logged_in_client.get("/whoop/reauth")
        assert b"username" in response.content.lower()

    @patch("django_whoop.models.requests.post")
    def test_post_updates_token_and_redirects(self, mock_post, tmpl_settings, logged_in_client, logged_in_user):
        wu = self._make_whoop_user(logged_in_user)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_tok",
            "expires_in": 3600,
            "refresh_token": "new_ref",
        }
        mock_post.return_value = mock_resp

        response = logged_in_client.post(
            "/whoop/reauth",
            {"username": "w@example.com", "password": "newpw"},
        )
        assert response.status_code == 302
        assert response["Location"] == "/whoop/success"

        wu.refresh_from_db()
        assert wu.access_token == "new_tok"


# ---------------------------------------------------------------------------
# success view
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSuccessView:
    def test_get_returns_200(self, tmpl_settings, logged_in_client):
        response = logged_in_client.get("/whoop/success")
        assert response.status_code == 200

    def test_content(self, tmpl_settings, logged_in_client):
        response = logged_in_client.get("/whoop/success")
        assert b"WHOOP successfully connected" in response.content
