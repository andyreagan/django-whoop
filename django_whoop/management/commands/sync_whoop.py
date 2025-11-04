"""
Management command to sync WHOOP data.

Usage:
    python manage.py sync_whoop --username <username> --recent
    python manage.py sync_whoop --username <username> --historical
    python manage.py sync_whoop --username <username> --days 30
"""

import datetime
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from django_whoop.models import WhoopUser
from django_whoop.views import (
    pull_daily, pull_hr, pull_journal, pull_all_journals,
    loop_historical, get_weekly_ranges
)


class Command(BaseCommand):
    help = 'Sync WHOOP data for a user'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            required=True,
            help='Django username to sync data for'
        )
        parser.add_argument(
            '--recent',
            action='store_true',
            help='Sync recent data (last 7 days)'
        )
        parser.add_argument(
            '--historical',
            action='store_true',
            help='Sync all historical data'
        )
        parser.add_argument(
            '--days',
            type=int,
            help='Number of days back to sync'
        )

    def handle(self, *args, **options):
        username = options['username']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist')

        if not hasattr(user, 'whoopuser'):
            raise CommandError(f'User "{username}" does not have a WHOOP account linked')

        whoopuser = user.whoopuser

        # Refresh token if needed
        self.stdout.write(self.style.SUCCESS('Checking token validity...'))
        whoopuser.refreshIfNeeded()

        if options['historical']:
            self.stdout.write(self.style.SUCCESS('Syncing all historical data...'))
            try:
                loop_historical(user, pull_daily)
                self.stdout.write(self.style.SUCCESS('✓ Daily data synced'))

                loop_historical(user, pull_hr)
                self.stdout.write(self.style.SUCCESS('✓ Heart rate data synced'))

                pull_all_journals(user)
                self.stdout.write(self.style.SUCCESS('✓ Journal entries synced'))

                self.stdout.write(self.style.SUCCESS('Historical sync completed successfully!'))
            except Exception as e:
                raise CommandError(f'Error syncing historical data: {str(e)}')

        elif options['recent'] or options.get('days'):
            days_back = options.get('days', 7)
            self.stdout.write(self.style.SUCCESS(f'Syncing last {days_back} days...'))

            try:
                days_back_dt = datetime.date.today() - datetime.timedelta(days=days_back)
                dates = [
                    days_back_dt.strftime('%Y-%m-%dT00:00:00.000Z'),
                    datetime.date.today().strftime('%Y-%m-%dT23:59:59.999Z')
                ]

                pull_daily(dates, user)
                self.stdout.write(self.style.SUCCESS('✓ Daily data synced'))

                pull_hr(dates, user)
                self.stdout.write(self.style.SUCCESS('✓ Heart rate data synced'))

                # Pull journal entries for synced days
                cycle_ids = {x.id for x in whoopuser.daily_set.filter(day__gte=days_back_dt)}
                for cycle_id in cycle_ids:
                    pull_journal(user, cycle_id)
                self.stdout.write(self.style.SUCCESS('✓ Journal entries synced'))

                self.stdout.write(self.style.SUCCESS(f'Successfully synced last {days_back} days!'))
            except Exception as e:
                raise CommandError(f'Error syncing data: {str(e)}')
        else:
            raise CommandError('Please specify --recent, --historical, or --days <n>')
