from django.contrib import admin

# Register your models here.
from .models import *

admin.site.register(WhoopUser)
admin.site.register(Daily)
admin.site.register(Recovery)
admin.site.register(JournalEntry)
