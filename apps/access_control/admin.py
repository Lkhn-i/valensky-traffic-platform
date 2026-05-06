from __future__ import annotations

from django.contrib import admin

from .models import (
    AccessGrant,
    BonusAccess,
    Enrollment,
    PreviewAccessGrant,
    Tariff,
    TariffEntitlement,
)


class TariffEntitlementInline(admin.TabularInline):
    model = TariffEntitlement
    extra = 0


class BonusAccessInline(admin.TabularInline):
    model = BonusAccess
    extra = 0


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    inlines = (TariffEntitlementInline, BonusAccessInline)
    list_display = ("code", "title", "course", "price_amount", "currency", "is_active")
    list_filter = ("is_active", "currency")
    search_fields = ("code", "title")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "status", "source", "tariff", "started_at")
    list_filter = ("status", "source")
    search_fields = ("user__username", "course__title")


@admin.register(PreviewAccessGrant)
class PreviewAccessGrantAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "lesson", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("user__username", "lesson__title")


@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "tariff", "source", "status", "starts_at", "expires_at")
    list_filter = ("source", "status")
    search_fields = ("user__username", "course__title", "source_reference")
