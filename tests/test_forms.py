"""
Tests for django_whoop forms.
"""
import pytest
from django_whoop.forms import WhoopAuthForm


class TestWhoopAuthForm:
    def test_valid_data(self):
        form = WhoopAuthForm(data={"username": "user@example.com", "password": "s3cr3t"})
        assert form.is_valid()

    def test_missing_username(self):
        form = WhoopAuthForm(data={"password": "s3cr3t"})
        assert not form.is_valid()
        assert "username" in form.errors

    def test_missing_password(self):
        form = WhoopAuthForm(data={"username": "user@example.com"})
        assert not form.is_valid()
        assert "password" in form.errors

    def test_empty_form_invalid(self):
        form = WhoopAuthForm(data={})
        assert not form.is_valid()

    def test_password_field_is_password_input(self):
        from django.forms import PasswordInput
        form = WhoopAuthForm()
        assert isinstance(form.fields["password"].widget, PasswordInput)

    def test_username_field_has_autofocus(self):
        form = WhoopAuthForm()
        widget_attrs = form.fields["username"].widget.attrs
        assert widget_attrs.get("autofocus") is True
