from __future__ import annotations

from django.contrib import admin

from .models import ExternalEvent, IntegrationOutboxEvent


@admin.register(ExternalEvent)
class ExternalEventAdmin(admin.ModelAdmin):
    list_display = ("source", "event_type", "processing_status", "received_at", "processed_at")
    list_filter = ("source", "processing_status")
    search_fields = ("event_type", "idempotency_key")


@admin.register(IntegrationOutboxEvent)
class IntegrationOutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "destination",
        "event_type",
        "user",
        "processing_status",
        "scheduled_at",
        "attempts",
    )
    list_filter = ("destination", "processing_status")
    search_fields = ("event_type", "idempotency_key", "user__username")
    readonly_fields = ("created_at", "updated_at")
