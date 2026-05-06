from django.contrib import admin

from .models import AnalyticsEvent, AuditLog


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("name", "source_app", "actor_identifier", "occurred_at")
    list_filter = ("source_app",)
    search_fields = ("name", "actor_identifier", "object_type", "object_key")
    ordering = ("-occurred_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "result", "actor_identifier", "target_type", "occurred_at")
    list_filter = ("result",)
    search_fields = ("action", "actor_identifier", "target_type", "target_key")
    ordering = ("-occurred_at",)
