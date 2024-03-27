from django.urls import path

from . import views

urlpatterns = [
    path('login', views.login, name='whooplogin'),
    path('reauth', views.reauth, name='whoopreauth'),
    path('logout', views.login, name='whooplogout'),
    path('success', views.success, name='whoopsuccess')
]
