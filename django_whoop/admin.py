from django.contrib import admin

# Register your models here.
from .models import *


@admin.register(WhoopUser)
class WhoopUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'whoop_user_id', 'access_token_updated', 'whoop_createdAt')
    search_fields = ('user__username', 'whoop_user_id')
    readonly_fields = ('access_token_updated', 'whoop_createdAt')


@admin.register(Daily)
class DailyAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'day', 'lastUpdatedAt')
    list_filter = ('user', 'day')
    search_fields = ('id', 'user__user__username')
    date_hierarchy = 'day'


@admin.register(Recovery)
class RecoveryAdmin(admin.ModelAdmin):
    list_display = ('id', 'day', 'score', 'restingHeartRate', 'heartRateVariabilityRmssd', 'timestamp')
    list_filter = ('day__user',)
    search_fields = ('id', 'day__id')


@admin.register(Sleep)
class SleepAdmin(admin.ModelAdmin):
    list_display = ('id', 'day', 'score', 'qualityDuration', 'needBreakdown_total')
    list_filter = ('day__user',)
    search_fields = ('id', 'day__id')


@admin.register(SleepDetail)
class SleepDetailAdmin(admin.ModelAdmin):
    list_display = ('id', 'sleep', 'score', 'during_lower', 'during_upper', 'qualityDuration', 'isNap')
    list_filter = ('isNap', 'sleep__day__user')
    search_fields = ('id', 'sleep__id')
    date_hierarchy = 'during_lower'


@admin.register(Strain)
class StrainAdmin(admin.ModelAdmin):
    list_display = ('id', 'day', 'score', 'averageHeartRate', 'maxHeartRate', 'kilojoules')
    list_filter = ('day__user',)
    search_fields = ('id', 'day__id')


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ('id', 'strain', 'score', 'sportId', 'during_lower', 'during_upper', 'averageHeartRate')
    list_filter = ('sportId', 'strain__day__user')
    search_fields = ('id', 'strain__id')
    date_hierarchy = 'during_lower'


@admin.register(HR)
class HRAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'timestamp', 'value')
    list_filter = ('user',)
    search_fields = ('user__user__username',)
    date_hierarchy = 'timestamp'


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'day', 'title', 'category', 'answered_yes', 'entry_created_at')
    list_filter = ('category', 'answered_yes', 'day__user')
    search_fields = ('title', 'question_text', 'day__id')
