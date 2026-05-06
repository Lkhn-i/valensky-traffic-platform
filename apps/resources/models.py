from __future__ import annotations

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        abstract = True


class Resource(TimeStampedModel):
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        ARCHIVED = "archived", "В архиве"

    class ResourceType(models.TextChoices):
        ARTICLE = "article", "Статья"
        WORKSHEET = "worksheet", "Рабочий лист"
        CHECKLIST = "checklist", "Чек-лист"
        TEMPLATE = "template", "Шаблон"
        LINK = "link", "Ссылка"
        DOWNLOAD = "download", "Файл"

    public_id = models.UUIDField("публичный ID", default=uuid.uuid4, editable=False, unique=True)
    slug = models.SlugField("URL-ярлык", max_length=140, unique=True)
    title = models.CharField("название", max_length=255)
    description = models.TextField("описание", blank=True)
    resource_type = models.CharField("тип материала", max_length=24, choices=ResourceType.choices)
    publication_status = models.CharField(
        "статус публикации",
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    source_url = models.URLField("ссылка", max_length=500, blank=True)
    download_key = models.CharField("ключ файла", max_length=255, blank=True)
    tags = models.JSONField("теги", default=list, blank=True)
    metadata = models.JSONField("метаданные", default=dict, blank=True)
    published_at = models.DateTimeField("опубликовано", null=True, blank=True)

    class Meta:
        ordering = ("title", "id")
        verbose_name = "материал"
        verbose_name_plural = "материалы"
        indexes = [
            models.Index(
                fields=("publication_status", "resource_type"),
                name="resources_state_type_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title
