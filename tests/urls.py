from django.urls import include, path

urlpatterns = [
    path("whoop/", include("whoop.urls")),
]
