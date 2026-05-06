from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone


class ProgressRecord(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Не начато"
        OPENED = "opened", "Открыто"
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершено"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="progress_records",
    )
    course = models.ForeignKey(
        "curriculum.Course",
        verbose_name="курс",
        on_delete=models.CASCADE,
        related_name="progress_records",
    )
    module = models.ForeignKey(
        "curriculum.Module",
        verbose_name="модуль",
        on_delete=models.CASCADE,
        related_name="progress_records",
    )
    lesson = models.ForeignKey(
        "curriculum.Lesson",
        verbose_name="урок",
        on_delete=models.CASCADE,
        related_name="progress_records",
    )
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    first_opened_at = models.DateTimeField("первое открытие", null=True, blank=True)
    last_opened_at = models.DateTimeField("последнее открытие", null=True, blank=True)
    completed_at = models.DateTimeField("завершено", null=True, blank=True)
    source = models.CharField("источник", max_length=64, blank=True)
    metadata = models.JSONField("метаданные", default=dict, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        ordering = ["user_id", "course_id", "module_id", "lesson_id"]
        verbose_name = "прогресс обучения"
        verbose_name_plural = "прогресс обучения"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lesson"],
                name="learning_progress_user_lesson_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["course", "status"], name="learn_prog_course_stat_idx"),
            models.Index(fields=["user", "status"], name="learn_prog_user_stat_idx"),
        ]

    @property
    def is_completed(self) -> bool:
        return self.status == self.Status.COMPLETED

    def mark_opened(self, *, when: datetime | None = None) -> None:
        when = when or timezone.now()
        if self.first_opened_at is None:
            self.first_opened_at = when
        self.last_opened_at = when

    def mark_completed(self, *, when: datetime | None = None) -> None:
        when = when or timezone.now()
        self.mark_opened(when=when)
        self.status = self.Status.COMPLETED
        if self.completed_at is None:
            self.completed_at = when

    def __str__(self) -> str:
        return f"Прогресс {self.user_id}: {self.get_status_display()}"
