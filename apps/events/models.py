from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class RecordedModel(models.Model):
    public_id = models.UUIDField("публичный ID", default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        abstract = True


class AnalyticsEvent(RecordedModel):
    name = models.CharField("название", max_length=100)
    source_app = models.CharField("модуль-источник", max_length=50)
    occurred_at = models.DateTimeField("произошло", default=timezone.now)
    actor_identifier = models.CharField("инициатор", max_length=128, blank=True)
    session_identifier = models.CharField("сессия", max_length=128, blank=True)
    object_type = models.CharField("тип объекта", max_length=64, blank=True)
    object_key = models.CharField("ключ объекта", max_length=140, blank=True)
    properties = models.JSONField("свойства", default=dict, blank=True)

    class Meta:
        ordering = ("-occurred_at", "-id")
        verbose_name = "аналитическое событие"
        verbose_name_plural = "аналитические события"
        indexes = [
            models.Index(fields=("source_app", "name"), name="events_source_name_idx"),
            models.Index(
                fields=("actor_identifier", "occurred_at"),
                name="events_actor_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_app}:{self.name}"


class AuditLog(RecordedModel):
    class Result(models.TextChoices):
        SUCCESS = "success", "Успешно"
        WARNING = "warning", "Предупреждение"
        FAILURE = "failure", "Ошибка"
        INFO = "info", "Информация"

    action = models.CharField("действие", max_length=100)
    result = models.CharField(
        "результат",
        max_length=16,
        choices=Result.choices,
        default=Result.INFO,
    )
    occurred_at = models.DateTimeField("произошло", default=timezone.now)
    actor_identifier = models.CharField("инициатор", max_length=128, blank=True)
    target_type = models.CharField("тип объекта", max_length=64, blank=True)
    target_key = models.CharField("ключ объекта", max_length=140, blank=True)
    message = models.TextField("сообщение", blank=True)
    payload = models.JSONField("данные", default=dict, blank=True)

    class Meta:
        ordering = ("-occurred_at", "-id")
        verbose_name = "запись аудита"
        verbose_name_plural = "записи аудита"
        indexes = [
            models.Index(fields=("action", "result"), name="audit_action_result_idx"),
            models.Index(
                fields=("actor_identifier", "occurred_at"),
                name="audit_actor_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} [{self.result}]"
