# django-whoop

django-whoop is a comprehensive Django app for integrating WHOOP data into your Django application. Track and visualize your recovery, sleep, strain, workouts, heart rate, and journal entries.

## Features

- **Complete WHOOP Data Integration**: Sync recovery, sleep, strain, workouts, heart rate, and journal entries
- **Dashboard**: View your WHOOP data with summary statistics and recent trends
- **Data Views**: Detailed views for each data type (recovery, sleep, strain, workouts)
- **Automatic Token Refresh**: Handles WHOOP API authentication automatically
- **Management Commands**: Sync data via command line
- **Django Admin**: Full admin interface for all WHOOP data models
- **Historical Data Sync**: Pull all your historical WHOOP data or just recent days

## Installation

1. Install the package:

```bash
pip install django-whoop
```

2. Add `django_whoop` to your `INSTALLED_APPS` setting:

```python
INSTALLED_APPS = [
    ...,
    'django_whoop',
]
```

3. Include the WHOOP URLconf in your project's `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    ...,
    path('whoop/', include('django_whoop.urls')),
]
```

4. Run migrations to create the database models:

```bash
python manage.py migrate
```

## Quick Start

### 1. Authenticate with WHOOP

Visit `/whoop/login` and enter your WHOOP credentials to link your account.

### 2. Sync Your Data

After authentication, you have several options:

**Via Web Interface:**
- Visit `/whoop/dashboard` to see your dashboard
- Click "Sync Recent Data (7 days)" for quick updates
- Click "Sync All Historical Data" for complete history

**Via Management Command:**
```bash
# Sync recent data (last 7 days)
python manage.py sync_whoop --username <your_django_username> --recent

# Sync all historical data
python manage.py sync_whoop --username <your_django_username> --historical

# Sync specific number of days
python manage.py sync_whoop --username <your_django_username> --days 30
```

### 3. View Your Data

Navigate to:
- `/whoop/` or `/whoop/dashboard` - Main dashboard with summary stats
- `/whoop/data/recovery` - Recovery scores and metrics
- `/whoop/data/sleep` - Sleep scores and duration
- `/whoop/data/strain` - Daily strain scores
- `/whoop/data/workouts` - Workout details

## URL Endpoints

| URL | Description |
|-----|-------------|
| `/whoop/` | Dashboard (main view) |
| `/whoop/login` | Authenticate with WHOOP |
| `/whoop/reauth` | Re-authenticate (refresh credentials) |
| `/whoop/sync/recent` | Sync last 7 days of data |
| `/whoop/sync/historical` | Sync all historical data |
| `/whoop/data/recovery` | View recovery data |
| `/whoop/data/sleep` | View sleep data |
| `/whoop/data/strain` | View strain data |
| `/whoop/data/workouts` | View workout data |

## Models

The app includes the following Django models:

- **WhoopUser**: Links Django user to WHOOP account with OAuth tokens
- **Daily**: Daily cycle data
- **Recovery**: Recovery scores and metrics (HRV, resting HR)
- **Sleep**: Sleep scores and duration breakdown
- **SleepDetail**: Detailed sleep session data
- **Strain**: Daily strain scores and heart rate data
- **Workout**: Individual workout sessions with zones
- **HR**: Heart rate measurements (6-second intervals)
- **JournalEntry**: Journal entries and behavior tracking

## Management Commands

### sync_whoop

Sync WHOOP data from the command line:

```bash
# Sync recent data (last 7 days)
python manage.py sync_whoop --username john --recent

# Sync all historical data
python manage.py sync_whoop --username john --historical

# Sync specific number of days
python manage.py sync_whoop --username john --days 30
```

## Admin Interface

All models are registered in Django admin with custom list displays and filters. Access at `/admin/` after logging in as a superuser.

## API Version

This package uses WHOOP API v7 (`api-7.whoop.com`).

## Requirements

- Django 3.2+
- Python 3.8+
- requests
- pytz
- python-dateutil

## Notes

- WHOOP credentials are required for authentication
- Access tokens are automatically refreshed when needed
- Historical data sync may take several minutes depending on account age
- Heart rate data is stored at 6-second intervals

## Troubleshooting

**Authentication Issues:**
- Ensure your WHOOP credentials are correct
- Try re-authenticating at `/whoop/reauth`

**Data Not Syncing:**
- Check that your access token is valid (visible in admin)
- Try manual re-authentication
- Check Django logs for API errors

## License

See LICENSE file for details.
