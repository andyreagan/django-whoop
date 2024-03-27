## this helps with weird ipython completion error
# get_ipython().run_line_magic('config', 'IPCompleter.use_jedi = False')

## start django setup

from pathlib import Path
import sys; sys.path.insert(0, str(Path(sys.path[0]) / '../..'))
print(sys.path)
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
# from asgiref.sync import sync_to_async
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
import django
django.setup()

## completed django setup

import json

from django.contrib.auth.models import User

from django_whoop.models import *
from django_whoop.views import *

user = User.objects.get(username='andyreagan')
user.whoopuser.refreshIfNeeded()


def full_history():
    loop_historical(user, pull_daily)
    loop_historical(user, pull_hr)
    # cycle_id = user.whoopuser.daily_set.all()[100].id
    # pull_journal(user, cycle_id)
    pull_all_journals(user)


def last_n_days(days_back):
    days_back_dt = datetime.date.today() - datetime.timedelta(days=days_back)
    dates = [days_back_dt.strftime('%Y-%m-%dT00:00:00.000Z'), datetime.date.today().strftime('%Y-%m-%dT23:59:59.999Z')]
    print(f"{dates=}")
    pull_daily(dates, user)
    pull_hr(dates, user)

    cycle_ids = {x.id for x in user.whoopuser.daily_set.filter(day__gte=days_back_dt)}
    for cycle_id in cycle_ids:
        pull_journal(user, cycle_id)

last_n_days(3)