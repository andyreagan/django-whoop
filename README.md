# django-whoop

django-whoop is a Django WHOOP App

Detailed documentation is in the "docs" directory.

Quick start
-----------

1. Add "whoop" to your INSTALLED_APPS setting like this:

```
INSTALLED_APPS = [
    ...,
    "django_whoop",
]
```

2. Include the WHOOP URLconf in your project urls.py like this:

```
path("whoop/", include("django_whoop.urls")),
```

3. Run ``python manage.py migrate`` to create the models.

4. Visit the ``/whoop/login`` URL to sign in with WHOOP.
