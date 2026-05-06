from __future__ import annotations

from django.contrib import admin

from .models import NotificationJob


@admin.register(NotificationJob)
class NotificationJobAdmin(admin.ModelAdmin):
    list_display = (
        "channel",
        "template_key",
        "dedupe_key",
        "user",
        "status",
        "scheduled_at",
        "attempts",
    )
    list_filter = ("channel", "status")
    search_fields = ("template_key", "dedupe_key", "user__username")
    readonly_fields = ("created_at", "updated_at")
