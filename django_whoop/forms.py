from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.forms import UsernameField


class WhoopAuthForm(forms.Form):
    """
    Base class for authenticating a whoop user by username/password.
    """
    username = UsernameField(widget=forms.TextInput(attrs={'autofocus': True}))
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )
