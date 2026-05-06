from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        abstract = True


class HomeworkAssignment(TimeStampedModel):
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликовано"
        ARCHIVED = "archived", "В архиве"

    public_id = models.UUIDField("публичный ID", default=uuid.uuid4, editable=False, unique=True)
    slug = models.SlugField("URL-ярлык", max_length=140, unique=True)
    title = models.CharField("название", max_length=255)
    summary = models.TextField("краткое описание", blank=True)
    prompt = models.TextField("задание", blank=True)
    publication_status = models.CharField(
        "статус публикации",
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    target_reference_type = models.CharField("тип привязки", max_length=64, blank=True)
    target_reference_key = models.CharField("ключ привязки", max_length=140, blank=True)
    submission_schema = models.JSONField("схема ответа", default=dict, blank=True)
    opens_at = models.DateTimeField("открывается", null=True, blank=True)
    due_at = models.DateTimeField("срок сдачи", null=True, blank=True)
    max_attempts = models.PositiveSmallIntegerField("максимум попыток", default=1)

    class Meta:
        ordering = ("title", "id")
        verbose_name = "домашнее задание"
        verbose_name_plural = "домашние задания"
        constraints = [
            models.CheckConstraint(
                condition=Q(max_attempts__gte=1),
                name="homework_assignment_max_attempts_gte_1",
            ),
        ]
        indexes = [
            models.Index(
                fields=("publication_status", "due_at"),
                name="homework_state_due_idx",
            ),
            models.Index(
                fields=("target_reference_type", "target_reference_key"),
                name="homework_target_ref_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class HomeworkSubmission(TimeStampedModel):
    class SubmissionState(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SUBMITTED = "submitted", "Отправлено"
        REVIEWED = "reviewed", "Проверено"
        RETURNED = "returned", "Возвращено на доработку"

    assignment = models.ForeignKey(
        HomeworkAssignment,
        verbose_name="домашнее задание",
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    author_identifier = models.CharField("автор", max_length=128)
    attempt_number = models.PositiveSmallIntegerField("номер попытки", default=1)
    submission_state = models.CharField(
        "статус ответа",
        max_length=16,
        choices=SubmissionState.choices,
        default=SubmissionState.DRAFT,
    )
    payload = models.JSONField("данные ответа", default=dict, blank=True)
    notes = models.TextField("заметки", blank=True)
    submitted_at = models.DateTimeField("отправлено", null=True, blank=True)

    class Meta:
        ordering = ("assignment_id", "author_identifier", "-attempt_number", "id")
        verbose_name = "ответ на домашнее задание"
        verbose_name_plural = "ответы на домашние задания"
        constraints = [
            models.UniqueConstraint(
                fields=("assignment", "author_identifier", "attempt_number"),
                name="homework_submission_attempt_uniq",
            ),
            models.CheckConstraint(
                condition=Q(attempt_number__gte=1),
                name="homework_submission_attempt_gte_1",
            ),
        ]
        indexes = [
            models.Index(
                fields=("assignment", "author_identifier"),
                name="homework_submission_author_idx",
            ),
            models.Index(
                fields=("submission_state", "submitted_at"),
                name="homework_submission_state_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.assignment.title} / {self.author_identifier} / #{self.attempt_number}"


class HomeworkReview(TimeStampedModel):
    class ReviewDecision(models.TextChoices):
        APPROVED = "approved", "Принято"
        CHANGES_REQUESTED = "changes_requested", "Нужны правки"
        REJECTED = "rejected", "Отклонено"

    submission = models.ForeignKey(
        HomeworkSubmission,
        verbose_name="ответ",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    reviewer_identifier = models.CharField("проверяющий", max_length=128)
    decision = models.CharField("решение", max_length=24, choices=ReviewDecision.choices)
    score = models.DecimalField("оценка", max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField("обратная связь", blank=True)
    rubric_snapshot = models.JSONField("рубрика проверки", default=dict, blank=True)
    reviewed_at = models.DateTimeField("проверено", default=timezone.now)

    class Meta:
        ordering = ("-reviewed_at", "-id")
        verbose_name = "проверка домашнего задания"
        verbose_name_plural = "проверки домашних заданий"
        constraints = [
            models.UniqueConstraint(
                fields=("submission", "reviewer_identifier"),
                name="homework_review_submission_reviewer_uniq",
            ),
            models.CheckConstraint(
                condition=Q(score__isnull=True) | (Q(score__gte=0) & Q(score__lte=100)),
                name="homework_review_score_between_0_100",
            ),
        ]
        indexes = [
            models.Index(
                fields=("decision", "reviewed_at"),
                name="homework_review_decision_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.submission} / {self.get_decision_display()}"
