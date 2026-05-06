from django.contrib import admin

from .models import HomeworkAssignment, HomeworkReview, HomeworkSubmission


@admin.register(HomeworkAssignment)
class HomeworkAssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "publication_status", "due_at", "max_attempts")
    list_filter = ("publication_status",)
    search_fields = ("title", "slug", "target_reference_key")
    ordering = ("title",)


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "assignment",
        "author_identifier",
        "attempt_number",
        "submission_state",
        "submitted_at",
    )
    list_filter = ("submission_state",)
    search_fields = ("assignment__title", "author_identifier")
    ordering = ("assignment_id", "author_identifier", "-attempt_number")


@admin.register(HomeworkReview)
class HomeworkReviewAdmin(admin.ModelAdmin):
    list_display = ("submission", "reviewer_identifier", "decision", "score", "reviewed_at")
    list_filter = ("decision",)
    search_fields = ("submission__assignment__title", "reviewer_identifier")
    ordering = ("-reviewed_at",)
