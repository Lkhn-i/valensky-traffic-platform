from django.contrib import admin

from .models import Resource


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "resource_type", "publication_status", "published_at")
    list_filter = ("resource_type", "publication_status")
    search_fields = ("title", "slug", "description")
    ordering = ("title",)
