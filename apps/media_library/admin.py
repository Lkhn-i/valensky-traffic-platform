from django.contrib import admin

from .models import LessonMediaAttachment, MediaAsset, PlaybackTicket


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "asset_kind",
        "availability_status",
        "storage_backend",
    )
    list_filter = ("asset_kind", "availability_status", "storage_backend")
    search_fields = ("title", "slug", "storage_key", "source_url")
    ordering = ("title",)


@admin.register(LessonMediaAttachment)
class LessonMediaAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lesson",
        "media_asset",
        "purpose",
        "position",
        "is_required",
        "created_at",
    )
    list_filter = ("purpose", "is_required")
    list_select_related = ("lesson", "media_asset")
    raw_id_fields = ("lesson", "media_asset")
    search_fields = ("lesson__title", "lesson__slug", "media_asset__title", "media_asset__slug")
    ordering = ("lesson_id", "purpose", "position", "id")


@admin.register(PlaybackTicket)
class PlaybackTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "attachment", "expires_at", "consumed", "created_at")
    list_filter = ("consumed", "expires_at")
    list_select_related = ("attachment", "attachment__lesson", "attachment__media_asset")
    raw_id_fields = ("attachment",)
    readonly_fields = ("token_hash", "metadata", "created_at", "updated_at")
    search_fields = ("token_hash", "attachment__lesson__slug", "attachment__media_asset__slug")
    ordering = ("-created_at", "-id")
