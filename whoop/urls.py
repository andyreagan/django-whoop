from django.urls import path

from . import views

app_name = "whoop"

urlpatterns = [
    path("connect/", views.connect, name="connect"),
    path("callback/", views.callback, name="callback"),
    path("disconnect/", views.disconnect, name="disconnect"),
    path("webhooks/", views.webhook_receiver, name="webhooks"),
]
