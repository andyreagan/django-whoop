from django.urls import path

from . import views

urlpatterns = [
    # Authentication
    path('login', views.login, name='whooplogin'),
    path('reauth', views.reauth, name='whoopreauth'),
    path('logout', views.login, name='whooplogout'),
    path('success', views.success, name='whoopsuccess'),

    # Dashboard
    path('', views.dashboard, name='whoopdashboard'),
    path('dashboard', views.dashboard, name='whoopdashboard_alt'),

    # Data syncing
    path('sync/recent', views.sync_recent, name='whoopsyncrecent'),
    path('sync/historical', views.sync_historical, name='whoopsynchistorical'),

    # Data views
    path('data/recovery', views.data_recovery, name='whooprecovery'),
    path('data/sleep', views.data_sleep, name='whoopsleep'),
    path('data/strain', views.data_strain, name='whoopstrain'),
    path('data/workouts', views.data_workouts, name='whoopworkouts'),
]
