from __future__ import annotations

from django.contrib import admin

from .models import ProgressRecord


@admin.register(ProgressRecord)
class ProgressRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "module", "lesson", "status", "completed_at")
    list_filter = ("status", "course")
    search_fields = ("user__username", "course__title", "lesson__title")
    readonly_fields = ("created_at", "updated_at")
