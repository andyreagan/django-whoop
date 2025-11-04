from dateutil import relativedelta, parser, rrule
from dateutil.rrule import WEEKLY
from pathlib import Path
import json

from django.http import HttpResponse, HttpRequest, HttpResponseRedirect, Http404
from django.shortcuts import redirect, render
import requests

from .models import *
from .forms import WhoopAuthForm


def pull_api(user, uri: str) -> dict:
    auth_code = user.whoopuser.access_token
    headers = {'authorization': f'bearer {auth_code}'}
    pull = requests.get(uri, headers=headers)
    # pull.raise_for_status()
    if pull.status_code == 404:
        return dict()
    elif pull.status_code != 200:
        print(pull.status_code)
        return dict()
    elif len(pull.text) == 0:
        print(pull.status_code)
        return dict()
    else:
        return pull.json() or dict()


def pull_sleep_detail(user, sleep_id):
    whoop_user_id = user.whoopuser.whoop_user_id
    uri = f'https://api-7.whoop.com/users/{whoop_user_id}/sleeps/{sleep_id}'
    return pull_api(user, uri)

def get_weekly_ranges(start_date, end_date):
    end_time = 'T23:59:59.999Z'
    start_time = 'T00:00:00.000Z'
    intervals = rrule.rrule(
        freq = WEEKLY,
        interval = 1,
        until = end_date,
        dtstart = start_date
    )
    date_ranges = [
        [
            d.strftime('%Y-%m-%d') + start_time,
            (d + relativedelta.relativedelta(weeks = 1)).strftime('%Y-%m-%d') + end_time
        ]
        for d in intervals
    ]
    return date_ranges


def pull_daily(dates, user, save_json=False):
    cycle_uri = f'https://api-7.whoop.com/users/{user.whoopuser.whoop_user_id}/cycles?end={dates[1]}&start={dates[0]}'
    data = pull_api(user, cycle_uri)

    if save_json:
        Path(f'daily-{dates[0]}--{dates[1]}.json').write_text(json.dumps(data))

    # stuff it all into the database
    for day in data:
        Daily.fill_from_cycle_response(user, day)


def pull_hr(dates, user, save_json=False):
    uri = f'https://api-7.whoop.com/users/{user.whoopuser.whoop_user_id}/metrics/heart_rate?end={dates[1]}&order=t&start={dates[0]}&step=6'
    data = pull_api(user, uri)
    hr_vals = data['values']

    if save_json:
        Path(f'hr-{dates[0]}--{dates[1]}.json').write_text(json.dumps(data))

    HR.fill_from_response(user=user, d=hr_vals)


def loop_historical(user, pull_fun):
    weekly_date_ranges = get_weekly_ranges(
        start_date = user.whoopuser.whoop_createdAt,
        end_date = datetime.datetime.now().replace(tzinfo=pytz.timezone('US/Eastern'))
    )
    for dates in weekly_date_ranges:
        print(f"{dates=}")
        pull_fun(dates, user)


def pull_journal(user, cycle_id):
    uri = f'https://api-7.whoop.com/activities-service/v1/journals/entries/user/cycle/{cycle_id}'
    d = pull_api(user, uri)
    for entry in d.get('tracked_behaviors') or {}:
        JournalEntry.create_from_response(cycle_id, entry)


def pull_all_journals(user):
    cycle_ids = {x.id for x in user.whoopuser.daily_set.all()}

    for cycle_id in cycle_ids:
        pull_journal(user, cycle_id)


def login(request: HttpRequest):
    if request.method == 'POST':
        try:
            whoopUser = WhoopUser.createWithPassword(
                loggedInUser=request.user,
                username=request.POST['username'],
                password=request.POST['password']
            )
            whoopUser.save()
            return redirect('whoopsuccess')
        except Exception as e:
            form = WhoopAuthForm()
            return render(request, 'whoop/login.html', {
                'form': form,
                'error': f'Authentication failed: {str(e)}'
            })
    form = WhoopAuthForm()
    return render(request, 'whoop/login.html', {'form': form})


def reauth(request: HttpRequest):
    if request.method == 'POST':
        try:
            request.user.whoopuser.refreshWithPassword(
                username=request.POST['username'],
                password=request.POST['password']
            )
            return redirect('whoopsuccess')
        except Exception as e:
            form = WhoopAuthForm()
            return render(request, 'whoop/reauth.html', {
                'form': form,
                'error': f'Re-authentication failed: {str(e)}'
            })
    form = WhoopAuthForm()
    return render(request, 'whoop/reauth.html', {'form': form})


def success(request: HttpRequest) -> HttpResponseRedirect:
    # fire off the refresh of all data
    return render(request, "whoop/success.html")


def dashboard(request: HttpRequest):
    """Display WHOOP dashboard with user's data."""
    if not hasattr(request.user, 'whoopuser'):
        return redirect('whooplogin')

    whoopuser = request.user.whoopuser

    # Get recent data (last 30 days)
    thirty_days_ago = datetime.date.today() - datetime.timedelta(days=30)
    recent_days = Daily.objects.filter(
        user=whoopuser,
        day__gte=thirty_days_ago
    ).order_by('-day')[:30]

    # Get summary statistics
    stats = {
        'total_days': Daily.objects.filter(user=whoopuser).count(),
        'avg_recovery': Recovery.objects.filter(day__user=whoopuser).aggregate(
            avg=models.Avg('score')
        )['avg'],
        'avg_sleep_score': Sleep.objects.filter(day__user=whoopuser).aggregate(
            avg=models.Avg('score')
        )['avg'],
        'avg_strain': Strain.objects.filter(day__user=whoopuser).aggregate(
            avg=models.Avg('score')
        )['avg'],
        'total_workouts': Workout.objects.filter(strain__day__user=whoopuser).count(),
    }

    context = {
        'whoopuser': whoopuser,
        'recent_days': recent_days,
        'stats': stats,
    }

    return render(request, 'whoop/dashboard.html', context)


def sync_recent(request: HttpRequest):
    """Sync recent WHOOP data (last 7 days)."""
    if not hasattr(request.user, 'whoopuser'):
        return redirect('whooplogin')

    # Refresh token if needed
    request.user.whoopuser.refreshIfNeeded()

    # Pull last 7 days
    days_back = 7
    days_back_dt = datetime.date.today() - datetime.timedelta(days=days_back)
    dates = [
        days_back_dt.strftime('%Y-%m-%dT00:00:00.000Z'),
        datetime.date.today().strftime('%Y-%m-%dT23:59:59.999Z')
    ]

    try:
        pull_daily(dates, request.user)
        pull_hr(dates, request.user)

        # Pull journal entries for synced days
        cycle_ids = {x.id for x in request.user.whoopuser.daily_set.filter(day__gte=days_back_dt)}
        for cycle_id in cycle_ids:
            pull_journal(request.user, cycle_id)

        return render(request, 'whoop/sync_success.html', {
            'message': f'Successfully synced last {days_back} days of data.',
            'days': days_back
        })
    except Exception as e:
        return render(request, 'whoop/sync_error.html', {
            'error': str(e)
        })


def sync_historical(request: HttpRequest):
    """Sync all historical WHOOP data."""
    if not hasattr(request.user, 'whoopuser'):
        return redirect('whooplogin')

    # Refresh token if needed
    request.user.whoopuser.refreshIfNeeded()

    try:
        loop_historical(request.user, pull_daily)
        loop_historical(request.user, pull_hr)
        pull_all_journals(request.user)

        return render(request, 'whoop/sync_success.html', {
            'message': 'Successfully synced all historical data.',
            'days': 'all'
        })
    except Exception as e:
        return render(request, 'whoop/sync_error.html', {
            'error': str(e)
        })


def data_recovery(request: HttpRequest):
    """View recovery data."""
    if not hasattr(request.user, 'whoopuser'):
        return redirect('whooplogin')

    whoopuser = request.user.whoopuser
    recoveries = Recovery.objects.filter(
        day__user=whoopuser
    ).select_related('day').order_by('-day__day')[:30]

    return render(request, 'whoop/data_recovery.html', {
        'recoveries': recoveries
    })


def data_sleep(request: HttpRequest):
    """View sleep data."""
    if not hasattr(request.user, 'whoopuser'):
        return redirect('whooplogin')

    whoopuser = request.user.whoopuser
    sleeps = Sleep.objects.filter(
        day__user=whoopuser
    ).select_related('day').order_by('-day__day')[:30]

    return render(request, 'whoop/data_sleep.html', {
        'sleeps': sleeps
    })


def data_strain(request: HttpRequest):
    """View strain data."""
    if not hasattr(request.user, 'whoopuser'):
        return redirect('whooplogin')

    whoopuser = request.user.whoopuser
    strains = Strain.objects.filter(
        day__user=whoopuser
    ).select_related('day').order_by('-day__day')[:30]

    return render(request, 'whoop/data_strain.html', {
        'strains': strains
    })


def data_workouts(request: HttpRequest):
    """View workout data."""
    if not hasattr(request.user, 'whoopuser'):
        return redirect('whooplogin')

    whoopuser = request.user.whoopuser
    workouts = Workout.objects.filter(
        strain__day__user=whoopuser
    ).select_related('strain__day').order_by('-during_lower')[:50]

    return render(request, 'whoop/data_workouts.html', {
        'workouts': workouts
    })
