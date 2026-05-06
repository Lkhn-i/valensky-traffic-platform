from __future__ import annotations

from django.contrib import admin

from .models import DiagnosticHandoff


@admin.register(DiagnosticHandoff)
class DiagnosticHandoffAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "external_session_id",
        "status",
        "lead_profile",
        "expires_at",
        "replay_count",
    )
    list_filter = ("source", "status")
    search_fields = ("external_session_id", "idempotency_key", "token_hash")
    readonly_fields = ("created_at", "updated_at", "resolved_at", "replay_count")
