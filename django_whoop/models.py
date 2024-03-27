import datetime
import pytz

from django.contrib.auth.models import User
from django.db import models
import requests


def get_date(raw: str, tzinfo=None):
    if raw is None:
        return None
    datetime_formats = ['%Y', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S+00:00", '%Y-%m-%d %H:%M:%S.%fZ', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%SZ', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', "%Y-%m-%d %H:%M:%S.%f+00:00", "%Y-%m-%d %H:%M:%S+00:00"]
    for dt_format in datetime_formats:
        try:
            d = datetime.datetime.strptime(raw, dt_format)
        except ValueError:
            d = None
        if d is not None:
            if tzinfo is not None:
                return d.replace(tzinfo=tzinfo)
            else:
                return d
    return d


def get_utc_time(raw):
    # raw can be int, float, str convertable to float, or null
    # will try to divide by 1000 if it doesn't work out of the box
    if raw is not None:
        try:
            d = datetime.datetime.utcfromtimestamp(float(raw)).replace(tzinfo=pytz.UTC)
        except ValueError:
            d = datetime.datetime.utcfromtimestamp(float(raw)/1000).replace(tzinfo=pytz.UTC)
        return d
    else:
        return None


class WhoopUser(models.Model):
    """Adds a token to a django User."""

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = models.CharField(max_length=1024)
    access_token_updated = models.DateTimeField(default=datetime.datetime(1, 1, 1, 0, 0).replace(tzinfo=pytz.UTC))
    access_token_expires_in = models.IntegerField(default=0)
    refresh_token = models.CharField(max_length=1024)
    whoop_user_id = models.IntegerField(default=-1)
    whoop_createdAt = models.DateTimeField(default=datetime.datetime(1, 1, 1, 0, 0).replace(tzinfo=pytz.UTC))

    def __str__(self):
        return self.user.username

    @classmethod
    def createWithPassword(cls, loggedInUser, username, password):
        headers = {
            "username": username,
            "password": password,
            "grant_type": "password",
            "issueRefresh": True
        }
        auth = requests.post("https://api-7.whoop.com/oauth/token", json=headers)
        print(auth)
        print(auth.text)
        print(auth.status_code)
        # should check we got a 200...
        resp = auth.json()
        whoopUser = cls(
            user=loggedInUser,
            access_token=resp['access_token'],
            access_token_updated=datetime.datetime.now().replace(tzinfo=pytz.UTC),
            access_token_expires_in=resp['expires_in'],
            refresh_token=resp['refresh_token'],
            whoop_user_id=resp['user']['id'],
            # there are two dates to choose from, the profile is 3 days later
            # in my case (ex: '2020-10-18T00:57:18.609Z')
            # createdAt=resp['user']['profile']['createdAt']
            whoop_createdAt=get_date(resp['user']['createdAt'], tzinfo=pytz.UTC)
        )
        return whoopUser


    def refreshWithPassword(self, username, password):
        headers = {
            "username": username,
            "password": password,
            "grant_type": "password",
            "issueRefresh": True
        }
        auth = requests.post("https://api-7.whoop.com/oauth/token", json=headers)
        print(auth)
        print(auth.text)
        print(auth.status_code)
        # should check we got a 200...
        resp = auth.json()
        self.access_token = resp['access_token']
        self.access_token_updated = datetime.datetime.now().replace(tzinfo=pytz.UTC)
        self.access_token_expires_in = resp['expires_in']
        self.refresh_token=resp['refresh_token']
        self.save()

    def refreshIfNeeded(self, check_api=False):
        if check_api:
            # check the api
            pass
        else:
            # check the timestamps...
            pass
        self.refreshToken()

    def refreshToken(self):
        headers = {
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"
        }
        auth = requests.post("https://api-7.whoop.com/oauth/token", json=headers)
        print(auth.status_code)
        resp = auth.json()
        print(resp)
        self.access_token = resp['access_token']
        self.access_token_updated = datetime.datetime.now().replace(tzinfo=pytz.UTC)
        self.access_token_expires_in = resp['expires_in']
        self.save()


class Daily(models.Model):
    id = models.IntegerField(primary_key=True)
    user = models.ForeignKey(WhoopUser, on_delete=models.CASCADE)
    day = models.DateField()

    during_bounds = models.CharField(max_length=10, null=True)
    during_lower = models.DateTimeField(null=True)
    during_upper = models.DateTimeField(null=True)

    lastUpdatedAt = models.DateTimeField(null=True)
    predictedEnd = models.DateTimeField(null=True)

    def __str__(self):
        return self.day.strftime('%Y-%m-%d')

    @classmethod
    def fill_from_cycle_response(cls, user, d):
        assert 'id' in d
        assert 'days' in d and len(d['days']) == 1
        during = d.get('during') or dict()
        daily, created = cls.objects.update_or_create(
            user=user.whoopuser,
            id=d['id'],
            defaults={
                'day': get_date(d['days'][0]),
                'during_bounds': during.get('bounds'),
                'during_lower': get_date(during.get('lower'), tzinfo=pytz.UTC),
                'during_upper': get_date(during.get('upper'), tzinfo=pytz.UTC),
                'lastUpdatedAt': get_date(d.get('lastUpdatedAt'), tzinfo=pytz.UTC),
                'predictedEnd': get_date(d.get('predictedEnd'), tzinfo=pytz.UTC)
            }
        )
        daily.save()
        print(f"{('found', 'created')[created]} the day {daily=}")
        if 'recovery' in d and d['recovery'] is not None:
            recovery, created = Recovery.objects.update_or_create(
                day=daily,
                id=d['recovery'].get('id'),
                defaults={
                    'heartRateVariabilityRmssd': d['recovery'].get('heartRateVariabilityRmssd'),
                    'restingHeartRate': d['recovery'].get('restingHeartRate'),
                    'score': d['recovery'].get('score'),
                    'timestamp': get_date(d['recovery'].get('timestamp'), tzinfo=pytz.UTC)
                }
            )
            recovery.save()
            print(f"{('found', 'created')[created]} {recovery=}")
        if 'sleep' in d and d['sleep'] is not None and d['sleep'].get('id') is not None:
            needBreakdown = d['sleep'].get('needBreakdown') or dict()
            sleep, created = Sleep.objects.update_or_create(
                day=daily,
                id=d['sleep']['id'],
                defaults={
                    'needBreakdown_baseline': needBreakdown.get('baseline'),
                    'needBreakdown_debt': needBreakdown.get('debt'),
                    'needBreakdown_naps': needBreakdown.get('naps'),
                    'needBreakdown_strain': needBreakdown.get('strain'),
                    'needBreakdown_total': needBreakdown.get('total'),
                    'qualityDuration': d['sleep'].get('qualityDuration'),
                    'score': d['sleep'].get('score')
                }
            )
            print(f"{('found', 'created')[created]} {sleep=}")
            sleep.save()
            if d['sleep'].get('naps') is not None:
                for sleepdetail in d['sleep']['naps']:
                    # could do the below with isNap=True
                    pass
            if d['sleep'].get('sleeps') is not None:
                for sleepdetail in d['sleep']['sleeps']:
                    during = sleepdetail.get('during') or dict()
                    if sleepdetail.get('id') is not None:
                        sleepdetail_obj, created = SleepDetail.objects.update_or_create(
                            sleep=sleep,
                            id=sleepdetail['id'], # = models.IntegerField() # 131838178,
                            defaults={
                                'cyclesCount': sleepdetail.get('cyclesCount'), # = models.IntegerField(null=True) # 5,
                                'disturbanceCount': sleepdetail.get('disturbanceCount'), # = models.IntegerField(null=True) # 12,
                                'during_bounds': during.get('bounds'), # = models.CharField(null=True) # "[)",
                                'during_lower': get_date(during.get('lower'), tzinfo=pytz.UTC), # = models.DateTimeField(null=True) # "2020-10-25T03:01:00+00:00",
                                'during_upper': get_date(during.get('upper'), tzinfo=pytz.UTC), # = models.DateTimeField(null=True) # "2020-10-25T11:33:00+00:00",
                                'inBedDuration': sleepdetail.get('inBedDuration'), # = models.IntegerField(null=True) # 30718493,
                                'isNap': False, # = models.BooleanField(default=False) # false,
                                'latencyDuration': sleepdetail.get('latencyDuration'), # = models.IntegerField(null=True) # 0,
                                'lightSleepDuration': sleepdetail.get('lightSleepDuration'), # = models.IntegerField(null=True) # 12011596,
                                'noDataDuration': sleepdetail.get('noDataDuration'), # = models.IntegerField(null=True) # 0,
                                'qualityDuration': sleepdetail.get('qualityDuration'), # = models.IntegerField(null=True) # 25139744,
                                'remSleepDuration': sleepdetail.get('remSleepDuration'), # = models.IntegerField(null=True) # 5948524,
                                'respiratoryRate': sleepdetail.get('respiratoryRate'), # = models.FloatField(null=True) # 14.3262,
                                'score': sleepdetail.get('score'), # = models.IntegerField(null=True) # 73,
                                'sleepConsistency': sleepdetail.get('sleepConsistency'), # = models.IntegerField(null=True) # 89,
                                'sleepEfficiency': sleepdetail.get('sleepEfficiency'), # = models.FloatField(null=True) # 0.818391,
                                'slowWaveSleepDuration': sleepdetail.get('slowWaveSleepDuration'), # = models.IntegerField(null=True) # 7179624,
                                'timezoneOffset': sleepdetail.get('timezoneOffset'), # = models.CharField(null=True) # "-0400",
                                'wakeDuration': sleepdetail.get('wakeDuration') # = models.IntegerField(null=True) # 5615410
                            }
                        )
                        sleepdetail_obj.save()
                        print(f"{('found', 'created')[created]} {sleepdetail_obj=}")
        if 'strain' in d and d['strain'] is not None:
            strain, created = Strain.objects.update_or_create(
                day=daily,
                id=d['id'],
                defaults={
                    'averageHeartRate': d['strain'].get('averageHeartRate'), # models.FloatField(null=True) # 75,
                    'kilojoules': d['strain'].get('kilojoules'), # models.FloatField(null=True) # 14218.7,
                    'maxHeartRate': d['strain'].get('maxHeartRate'), # models.FloatField(null=True) # 172,
                    'rawScore': d['strain'].get('rawScore'), # models.FloatField(null=True) # 0.0143161574422024,
                    'score': d['strain'].get('score') # models.FloatField(null=True) # 16.3900610678999,
                }
            )
            strain.save()
            print(f"{('found', 'created')[created]} {strain=}")
            if d['strain'].get('workouts') is not None:
                for workout in d['strain']['workouts']:
                    during = workout.get('during') or dict()
                    zones = workout.get('zones')
                    if zones is None or len(zones) < 6:
                        zones = [0 for i in range(6)]
                    if workout.get('id') is not None:
                        workout_obj, created = Workout.objects.update_or_create(
                            strain=strain, # = models.ForeignKey(Strain, on_delete=models.CASCADE)
                            id=workout['id'], # = models.IntegerField(null=True), # 132062158,
                            defaults={
                                'averageHeartRate': workout.get('averageHeartRate'), # = models.FloatField(null=True), # 131,
                                'cumulativeWorkoutStrain': workout.get('cumulativeWorkoutStrain'), # = models.FloatField(null=True), # 14.9973,
                                'during_bounds': during.get('bounds'), # = models.CharField(null=True) # "[)",
                                'during_lower': get_date(during.get('lower'), tzinfo=pytz.UTC), # = models.DateTimeField(null=True) # "2020-10-25T03:01:00+00:00",
                                'during_upper': get_date(during.get('upper'), tzinfo=pytz.UTC), # = models.DateTimeField(null=True) # "2020-10-25T11:33:00+00:00",
                                'kilojoules': workout.get('kilojoules'), # = models.FloatField(null=True), # 2863.52,
                                'maxHeartRate': workout.get('maxHeartRate'), # = models.FloatField(null=True), # 157,
                                'rawScore': workout.get('rawScore'), # = models.FloatField(null=True), # 0.00579152500086973,
                                'score': workout.get('score'), # = models.FloatField(null=True), # 12.2451922891289,
                                'sportId': workout.get('sportId'), # = models.IntegerField(null=True), # 0,
                                'timezoneOffset': workout.get('timezoneOffset'), # = models.CharField(max_length=10, null=True), # "-0400",
                                'zone_0': zones[0], # = models.IntegerField(null=True)
                                'zone_1': zones[1], # = models.IntegerField(null=True)
                                'zone_2': zones[2], # = models.IntegerField(null=True)
                                'zone_3': zones[3], # = models.IntegerField(null=True)
                                'zone_4': zones[4], # = models.IntegerField(null=True)
                                'zone_5': zones[5] # = models.IntegerField(null=True)
                            }
                        )
                        workout_obj.save()
                        print(f"{('found', 'created')[created]} {workout_obj=}")
        return daily


class Recovery(models.Model):
    day = models.ForeignKey(Daily, on_delete=models.CASCADE)
    # blackoutUntil = models.FloatField(null=True) # null,
    # calibrating = models.FloatField(null=True) # false,
    heartRateVariabilityRmssd = models.FloatField(null=True) # 0.0590787,
    id = models.IntegerField(primary_key=True) # 60322913,
    # responded = models.FloatField(null=True) # false,
    restingHeartRate = models.FloatField(null=True) # 51,
    score = models.FloatField(null=True) # 54,
    # state = models.FloatField(null=True) # "complete",
    # surveyResponseId = models.FloatField(null=True) # null,
    timestamp = models.DateTimeField(null=True) # "2020-10-25T11:33:00+00:00",


class Sleep(models.Model):
    day = models.ForeignKey(Daily, on_delete=models.CASCADE)
    id = models.IntegerField(primary_key=True)
    needBreakdown_baseline = models.IntegerField(null=True) # 27430627,
    needBreakdown_debt = models.IntegerField(null=True) # 3703134,
    needBreakdown_naps = models.IntegerField(null=True) # 0,
    needBreakdown_strain = models.IntegerField(null=True) # 3278169,
    needBreakdown_total = models.IntegerField(null=True) # 34411932,
    qualityDuration = models.IntegerField(null=True) # 25139744,
    score = models.IntegerField(null=True) # 73,


class SleepDetail(models.Model):
    sleep = models.ForeignKey(Sleep, on_delete=models.CASCADE)
    id = models.IntegerField(primary_key=True) # 131838178,
    cyclesCount = models.IntegerField(null=True) # 5,
    disturbanceCount = models.IntegerField(null=True) # 12,
    during_bounds = models.CharField(max_length=20, null=True) # "[)",
    during_lower = models.DateTimeField(null=True) # "2020-10-25T03:01:00+00:00",
    during_upper = models.DateTimeField(null=True) # "2020-10-25T11:33:00+00:00",
    inBedDuration = models.IntegerField(null=True) # 30718493,
    isNap = models.BooleanField(default=False) # false,
    latencyDuration = models.IntegerField(null=True) # 0,
    lightSleepDuration = models.IntegerField(null=True) # 12011596,
    noDataDuration = models.IntegerField(null=True) # 0,
    qualityDuration = models.IntegerField(null=True) # 25139744,
    remSleepDuration = models.IntegerField(null=True) # 5948524,
    respiratoryRate = models.FloatField(null=True) # 14.3262,
    # responded = models.FloatField(null=True) # false,
    score = models.IntegerField(null=True) # 73,
    sleepConsistency = models.IntegerField(null=True) # 89,
    sleepEfficiency = models.FloatField(null=True) # 0.818391,
    slowWaveSleepDuration = models.IntegerField(null=True) # 7179624,
    # source = models.FloatField(null=True) # "user",
    # state = models.FloatField(null=True) # "complete",
    # surveyResponseId = models.FloatField(null=True) # null,
    timezoneOffset = models.CharField(max_length=20, null=True) # "-0400",
    wakeDuration = models.IntegerField(null=True) # 5615410

class Strain(models.Model):
    day = models.ForeignKey(Daily, on_delete=models.CASCADE)
    id = models.IntegerField(primary_key=True) #
    averageHeartRate = models.FloatField(null=True) # 75,
    kilojoules = models.FloatField(null=True) # 14218.7,
    maxHeartRate = models.FloatField(null=True) # 172,
    rawScore = models.FloatField(null=True) # 0.0143161574422024,
    score = models.FloatField(null=True) # 16.3900610678999,
    # state = models.FloatField(null=True) # "complete",


class Workout(models.Model):
    strain = models.ForeignKey(Strain, on_delete=models.CASCADE)
    # "altitudeChange": null,
    # "altitudeGain": null,
    averageHeartRate = models.FloatField(null=True) # 131,
    cumulativeWorkoutStrain = models.FloatField(null=True) # 14.9973,
    # distance = models.FloatField(null=True) # null,
    during_bounds = models.CharField(max_length=20, null=True) # "[)",
    during_lower = models.DateTimeField(null=True) # "2020-10-25T16:53:55.099+00:00",
    during_upper = models.DateTimeField(null=True) # "2020-10-25T18:08:15.545+00:00",
    # gpsEnabled = models.FloatField(null=True) # false,
    id = models.IntegerField(primary_key=True) # 132062158,
    kilojoules = models.FloatField(null=True) # 2863.52,
    maxHeartRate = models.FloatField(null=True) # 157,
    rawScore = models.FloatField(null=True) # 0.00579152500086973,
    # responded = models.FloatField(null=True) # false,
    score = models.FloatField(null=True) # 12.2451922891289,
    # source = models.FloatField(null=True) # "auto",
    sportId = models.IntegerField(null=True) # 0,
    # state = models.FloatField(null=True) # "complete",
    # surveyResponseId = models.FloatField(null=True) # null,
    timezoneOffset = models.CharField(max_length=10, null=True) # "-0400",
    zone_0 = models.IntegerField(null=True)
    zone_1 = models.IntegerField(null=True)
    zone_2 = models.IntegerField(null=True)
    zone_3 = models.IntegerField(null=True)
    zone_4 = models.IntegerField(null=True)
    zone_5 = models.IntegerField(null=True)


class HR(models.Model):
    user = models.ForeignKey(WhoopUser, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    value = models.IntegerField()

    @classmethod
    def fill_from_response(cls, user, d, batch_size=500):
        # for point in d:
        #     hr, created = cls.objects.update_or_create(
        #         user = user.whoopuser,
        #         timestamp = datetime.datetime.utcfromtimestamp(point['time']/1000).replace(tzinfo=pytz.UTC),
        #         defaults = {'value': point['data']}
        #     )
        #     hr.save()

        # bulk create:
        objects = [cls(user = user.whoopuser,timestamp = datetime.datetime.utcfromtimestamp(point['time']/1000).replace(tzinfo=pytz.UTC), value=point['data']) for point in d]
        cls.objects.bulk_create(objects, batch_size)


class JournalEntry(models.Model):
    # user = models.ForeignKey(WhoopUser, on_delete=models.CASCADE)
    # it's pulled using the day's id, as "cycle_id"
    day = models.ForeignKey(Daily, on_delete=models.CASCADE)

    tracker_id = models.IntegerField() # "id": 50,
    created_at = models.DateTimeField(null=True, max_length=200) # "created_at": 1583441766.111,
    updated_at = models.DateTimeField(null=True, max_length=200) # "updated_at": 1585669607.122,
    title = models.CharField(max_length=200) # "title": "Intermittent Fasting",
    status = models.CharField(null=True, max_length=200) # "status": "active",
    category = models.CharField(null=True, max_length=200) # "category": "Nutrition",
    # sticky = models.BooleanField(null=True, max_length=200) # "sticky": false,
    description = models.CharField(null=True, max_length=200) # "description": null,
    question_text = models.CharField(null=True, max_length=200) # "question_text": "Follow an intermittent fasting diet?",
    time_label = models.CharField(null=True, max_length=200) # "time_label": "When was your last meal?",
    time_context_label = models.CharField(null=True, max_length=200) # "time_context_label": "stopped eating at",
    magnitude = models.JSONField(null=True) # "magnitude": ...
    default_tracker = models.BooleanField(null=True) # "default_tracker": false

    id = models.IntegerField(primary_key=True) # "id": 434680106,
    journal_entry_id = models.IntegerField(null=True) # "journal_entry_id": 52336709,
    entry_created_at = models.DateTimeField(null=True) # "created_at": 1611923762.42,
    entry_updated_at = models.DateTimeField(null=True) # "updated_at": 1611923762.42,
    answered_yes = models.BooleanField(null=True) # "answered_yes": false,
    behavior_tracker_id = models.IntegerField(null=True) # "behavior_tracker_id": 50,
    time_input_value = models.DateTimeField(null=True) # "time_input_value": null,
    time_input_label = models.CharField(max_length=200, null=True) # "time_input_label": null,
    magnitude_input_label = models.CharField(max_length=200, null=True) # "magnitude_input_label": null,
    magnitude_input_value = models.IntegerField(null=True) # "magnitude_input_value": null

    def __str__(self):
        return f"{str(self.day.day)} {self.title}. answered_yes: {self.answered_yes}"

    @classmethod
    def create_from_response(cls, cycle_id, d):
        behavior_tracker = d.get('behavior_tracker') or dict()
        tracker_input = d.get('tracker_input') or dict()
        journalentry, created = cls.objects.update_or_create(
            day=Daily.objects.get(id=cycle_id),
            id=tracker_input.get('id'),
            defaults={
                'tracker_id': behavior_tracker.get('id'),
                'created_at': get_utc_time(behavior_tracker.get('created_at')),
                'updated_at': get_utc_time(behavior_tracker.get('updated_at')),
                'title': behavior_tracker.get('title'),
                'status': behavior_tracker.get('status'),
                'category': behavior_tracker.get('category'),
                # 'sticky': behavior_tracker.get('sticky'),
                'description': behavior_tracker.get('description'),
                'question_text': behavior_tracker.get('question_text'),
                'time_label': behavior_tracker.get('time_label'),
                'time_context_label': behavior_tracker.get('time_context_label'),
                'magnitude': behavior_tracker.get('magnitude'),
                'default_tracker': behavior_tracker.get('default_tracker'),
                'journal_entry_id': tracker_input.get('journal_entry_id'),
                'entry_created_at': get_utc_time(tracker_input.get('created_at')),
                'entry_updated_at': get_utc_time(tracker_input.get('updated_at')),
                'answered_yes': tracker_input.get('answered_yes'),
                'behavior_tracker_id': tracker_input.get('behavior_tracker_id'),
                'time_input_value': get_utc_time(tracker_input.get('time_input_value')),
                'time_input_label': tracker_input.get('time_input_label'),
                'magnitude_input_label': tracker_input.get('magnitude_input_label'),
                'magnitude_input_value': tracker_input.get('magnitude_input_value')
            }
        )
        print(f"{('found', 'created')[created]} {journalentry=}")
        journalentry.save()
        return journalentry
