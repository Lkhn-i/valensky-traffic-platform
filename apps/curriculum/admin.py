from django.contrib import admin

from .models import Course, Lesson, LessonBlock, Module


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "publication_status", "position", "updated_at")
    list_filter = ("publication_status",)
    search_fields = ("title", "slug")
    ordering = ("position", "title")


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "publication_status", "position", "updated_at")
    list_filter = ("publication_status", "course")
    search_fields = ("title", "slug", "course__title")
    ordering = ("course_id", "position", "title")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "publication_status", "position", "updated_at")
    list_filter = ("publication_status", "module")
    search_fields = ("title", "slug", "module__title", "module__course__title")
    ordering = ("module_id", "position", "title")


@admin.register(LessonBlock)
class LessonBlockAdmin(admin.ModelAdmin):
    list_display = ("__str__", "lesson", "block_type", "position", "is_required")
    list_filter = ("block_type", "is_required")
    search_fields = ("title", "lesson__title")
    ordering = ("lesson_id", "position")
