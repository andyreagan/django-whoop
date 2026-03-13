"""
Minimal URL config for tests.

django_whoop's templates extend 'base.html' and reference {% url 'home' %},
so we provide a stub base template via a simple view and wire up the whoop
URLs under the same prefix used in a typical integration.
"""
from django.urls import path, include
from django.http import HttpResponse


def stub_home(request):
    return HttpResponse("home")


urlpatterns = [
    path("whoop/", include("django_whoop.urls")),
    path("", stub_home, name="home"),
]
