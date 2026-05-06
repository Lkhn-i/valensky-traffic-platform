from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        abstract = True


class MediaAsset(TimeStampedModel):
    class AssetKind(models.TextChoices):
        VIDEO = "video", "Видео"
        AUDIO = "audio", "Аудио"
        IMAGE = "image", "Изображение"
        DOCUMENT = "document", "Документ"
        ARCHIVE = "archive", "Архив"
        OTHER = "other", "Другое"

    class AvailabilityStatus(models.TextChoices):
        PROCESSING = "processing", "Обрабатывается"
        QUEUED = "queued", "В очереди"
        READY = "ready", "Готово"
        FAILED = "failed", "Ошибка"
        ARCHIVED = "archived", "В архиве"

    class StorageBackend(models.TextChoices):
        LOCAL = "local", "Локальное хранилище"
        S3 = "s3", "S3"
        EXTERNAL = "external", "Внешний сервис"
        UNKNOWN = "unknown", "Не указано"

    public_id = models.UUIDField("публичный ID", default=uuid.uuid4, editable=False, unique=True)
    slug = models.SlugField("URL-ярлык", max_length=140, unique=True)
    title = models.CharField("название", max_length=255)
    description = models.TextField("описание", blank=True)
    asset_kind = models.CharField("тип медиа", max_length=24, choices=AssetKind.choices)
    availability_status = models.CharField(
        "статус доступности",
        max_length=16,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.PROCESSING,
    )
    storage_backend = models.CharField(
        "хранилище",
        max_length=16,
        choices=StorageBackend.choices,
        default=StorageBackend.UNKNOWN,
    )
    storage_key = models.CharField("ключ в хранилище", max_length=255, blank=True)
    source_url = models.URLField("ссылка на источник", max_length=500, blank=True)
    mime_type = models.CharField("MIME-тип", max_length=127, blank=True)
    checksum_sha256 = models.CharField("SHA-256", max_length=64, blank=True)
    file_size_bytes = models.PositiveBigIntegerField("размер файла, байт", null=True, blank=True)
    duration_seconds = models.PositiveIntegerField("длительность, секунд", null=True, blank=True)
    metadata = models.JSONField("метаданные", default=dict, blank=True)

    class Meta:
        ordering = ("title", "id")
        verbose_name = "медиафайл"
        verbose_name_plural = "медиафайлы"
        indexes = [
            models.Index(
                fields=("availability_status", "asset_kind"),
                name="media_state_kind_idx",
            ),
            models.Index(fields=("storage_backend",), name="media_storage_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class LessonMediaAttachment(TimeStampedModel):
    class Purpose(models.TextChoices):
        PRIMARY_VIDEO = "primary_video", "Основное видео"
        CAPTION = "caption", "Субтитры"
        TRANSCRIPT = "transcript", "Транскрипт"
        SUPPLEMENT = "supplement", "Дополнительный материал"

    lesson = models.ForeignKey(
        "curriculum.Lesson",
        verbose_name="урок",
        on_delete=models.CASCADE,
        related_name="media_attachments",
    )
    media_asset = models.ForeignKey(
        MediaAsset,
        verbose_name="медиафайл",
        on_delete=models.CASCADE,
        related_name="lesson_attachments",
    )
    purpose = models.CharField(
        "назначение",
        max_length=32,
        choices=Purpose.choices,
        default=Purpose.PRIMARY_VIDEO,
    )
    position = models.PositiveIntegerField("позиция", default=0)
    is_required = models.BooleanField("обязательное", default=True)

    class Meta:
        ordering = ("lesson_id", "purpose", "position", "id")
        verbose_name = "медиа в уроке"
        verbose_name_plural = "медиа в уроках"
        constraints = [
            models.UniqueConstraint(
                fields=("lesson", "media_asset"),
                name="media_attach_lesson_asset_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"Медиа урока {self.lesson_id}: {self.media_asset}"


class PlaybackTicket(TimeStampedModel):
    attachment = models.ForeignKey(
        LessonMediaAttachment,
        verbose_name="медиа в уроке",
        on_delete=models.CASCADE,
        related_name="playback_tickets",
    )
    token_hash = models.CharField("хэш токена", max_length=128, unique=True)
    expires_at = models.DateTimeField("истекает")
    consumed = models.BooleanField("использован", default=False)
    metadata = models.JSONField("метаданные", default=dict, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "билет воспроизведения"
        verbose_name_plural = "билеты воспроизведения"
        indexes = [
            models.Index(fields=("expires_at", "consumed"), name="media_ticket_exp_cons_idx"),
        ]

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    def __str__(self) -> str:
        return f"Билет воспроизведения {self.id}"
