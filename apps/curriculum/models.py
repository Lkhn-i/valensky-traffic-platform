from __future__ import annotations

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        abstract = True


class Course(TimeStampedModel):
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        ARCHIVED = "archived", "В архиве"

    public_id = models.UUIDField("публичный ID", default=uuid.uuid4, editable=False, unique=True)
    slug = models.SlugField("URL-ярлык", max_length=140, unique=True)
    title = models.CharField("название", max_length=255)
    summary = models.TextField("краткое описание", blank=True)
    description = models.TextField("описание", blank=True)
    publication_status = models.CharField(
        "статус публикации",
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    position = models.PositiveIntegerField("позиция", default=0)
    estimated_duration_minutes = models.PositiveIntegerField("длительность в минутах", default=0)

    class Meta:
        ordering = ("position", "title", "id")
        verbose_name = "курс"
        verbose_name_plural = "курсы"
        indexes = [
            models.Index(
                fields=("publication_status", "position"),
                name="curr_course_state_pos_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Module(TimeStampedModel):
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        ARCHIVED = "archived", "В архиве"

    course = models.ForeignKey(
        Course,
        verbose_name="курс",
        on_delete=models.CASCADE,
        related_name="modules",
    )
    slug = models.SlugField("URL-ярлык", max_length=140)
    title = models.CharField("название", max_length=255)
    summary = models.TextField("краткое описание", blank=True)
    publication_status = models.CharField(
        "статус публикации",
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    position = models.PositiveIntegerField("позиция", default=0)

    class Meta:
        ordering = ("course_id", "position", "title", "id")
        verbose_name = "модуль"
        verbose_name_plural = "модули"
        constraints = [
            models.UniqueConstraint(
                fields=("course", "slug"),
                name="curr_module_course_slug_uniq",
            ),
            models.UniqueConstraint(
                fields=("course", "position"),
                name="curr_module_course_pos_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("course", "publication_status"),
                name="curr_module_course_state_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Lesson(TimeStampedModel):
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        ARCHIVED = "archived", "В архиве"

    module = models.ForeignKey(
        Module,
        verbose_name="модуль",
        on_delete=models.CASCADE,
        related_name="lessons",
    )
    slug = models.SlugField("URL-ярлык", max_length=140)
    title = models.CharField("название", max_length=255)
    summary = models.TextField("краткое описание", blank=True)
    publication_status = models.CharField(
        "статус публикации",
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    position = models.PositiveIntegerField("позиция", default=0)
    estimated_duration_minutes = models.PositiveIntegerField("длительность в минутах", default=0)

    class Meta:
        ordering = ("module_id", "position", "title", "id")
        verbose_name = "урок"
        verbose_name_plural = "уроки"
        constraints = [
            models.UniqueConstraint(
                fields=("module", "slug"),
                name="curr_lesson_module_slug_uniq",
            ),
            models.UniqueConstraint(
                fields=("module", "position"),
                name="curr_lesson_module_pos_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("module", "publication_status"),
                name="curr_lesson_module_state_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class LessonBlock(TimeStampedModel):
    class BlockType(models.TextChoices):
        RICH_TEXT = "rich_text", "Текст"
        VIDEO = "video", "Видео"
        EMBED = "embed", "Встраивание"
        DOWNLOAD = "download", "Файл"
        ACTION = "action", "Действие"

    lesson = models.ForeignKey(
        Lesson,
        verbose_name="урок",
        on_delete=models.CASCADE,
        related_name="blocks",
    )
    block_type = models.CharField("тип блока", max_length=24, choices=BlockType.choices)
    title = models.CharField("название", max_length=255, blank=True)
    body = models.TextField("содержимое", blank=True)
    payload = models.JSONField("данные блока", default=dict, blank=True)
    position = models.PositiveIntegerField("позиция", default=0)
    is_required = models.BooleanField("обязательный", default=True)

    class Meta:
        ordering = ("lesson_id", "position", "id")
        verbose_name = "блок урока"
        verbose_name_plural = "блоки уроков"
        constraints = [
            models.UniqueConstraint(
                fields=("lesson", "position"),
                name="curr_block_lesson_pos_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("lesson", "block_type"),
                name="curr_block_lesson_type_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title or f"Блок: {self.get_block_type_display()}"
