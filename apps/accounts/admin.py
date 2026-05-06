from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LeadProfile, MagicLink, Role, User, UserRole, UserTelegramIdentity


@admin.register(User)
class ProjectUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Профиль обучения", {"fields": ("display_name", "phone", "timezone")}),
    )
    list_display = ("id", "username", "display_name", "email", "is_staff", "is_active")
    search_fields = ("username", "email", "display_name", "telegram_identities__telegram_id")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "title")
    search_fields = ("code", "title")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "granted_by", "granted_at")
    list_filter = ("role",)
    search_fields = ("user__username", "role__code")


@admin.register(UserTelegramIdentity)
class UserTelegramIdentityAdmin(admin.ModelAdmin):
    list_display = ("telegram_id", "username", "user", "linked_at")
    search_fields = ("telegram_id", "username", "user__username")


@admin.register(LeadProfile)
class LeadProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "diagnostic_segment", "created_at")
    list_filter = ("status", "diagnostic_segment")
    search_fields = ("user__username", "diagnostic_session_id")


@admin.register(MagicLink)
class MagicLinkAdmin(admin.ModelAdmin):
    list_display = ("purpose", "user", "expires_at", "consumed_at", "created_at")
    list_filter = ("purpose",)
    search_fields = ("user__username", "token_hash")
