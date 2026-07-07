from django.contrib import admin

from .models import WhoopConnection


@admin.register(WhoopConnection)
class WhoopConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "whoop_user_id",
        "status",
        "connected_at",
        "last_sync_at",
    )
    list_filter = ("status",)
    search_fields = ("customer__username", "whoop_user_id")
    readonly_fields = ("connected_at",)
