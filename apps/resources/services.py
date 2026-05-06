from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet

from apps.access_control.services import AccessDecision, check_access
from apps.curriculum.models import Lesson, LessonBlock

from .models import Resource


class ResourceCatalogService(Protocol):
    def list_resources(
        self,
        *,
        publication_status: str | None = None,
        resource_type: str | None = None,
    ) -> QuerySet[Resource]:
        ...

    def get_resource(self, *, slug: str) -> Resource:
        ...


class ORMResourceCatalogService:
    def list_resources(
        self,
        *,
        publication_status: str | None = None,
        resource_type: str | None = None,
    ) -> QuerySet[Resource]:
        queryset = Resource.objects.all()
        if publication_status:
            queryset = queryset.filter(publication_status=publication_status)
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        return queryset.order_by(*Resource._meta.ordering)

    def get_resource(self, *, slug: str) -> Resource:
        return self.list_resources().get(slug=slug)


class StubResourceCatalogService:
    def list_resources(
        self,
        *,
        publication_status: str | None = None,
        resource_type: str | None = None,
    ) -> QuerySet[Resource]:
        return Resource.objects.none()

    def get_resource(self, *, slug: str) -> Resource:
        raise Resource.DoesNotExist(f"Материал со slug={slug!r} недоступен в заглушке")


@dataclass(frozen=True)
class ProtectedLessonResource:
    lesson: Lesson
    block: LessonBlock
    resource: Resource
    access_decision: AccessDecision


class ProtectedLessonResourceNotFound(LookupError):
    pass


class ProtectedLessonResourceAccessDenied(PermissionDenied):
    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ProtectedLessonResourceService(Protocol):
    def resolve_for_user(
        self,
        *,
        user_id: int,
        lesson_id: int,
        resource_slug: str,
    ) -> ProtectedLessonResource:
        ...


def _block_resource_slug(block: LessonBlock) -> str:
    payload = block.payload if isinstance(block.payload, dict) else {}
    return str(payload.get("resource_slug") or "").strip()


class ORMProtectedLessonResourceService:
    def resolve_for_user(
        self,
        *,
        user_id: int,
        lesson_id: int,
        resource_slug: str,
    ) -> ProtectedLessonResource:
        lesson = Lesson.objects.select_related("module", "module__course").prefetch_related(
            "blocks"
        ).get(id=lesson_id)
        normalized_slug = resource_slug.strip()
        block = next(
            (
                candidate
                for candidate in lesson.blocks.all()
                if candidate.block_type == LessonBlock.BlockType.DOWNLOAD
                and _block_resource_slug(candidate) == normalized_slug
            ),
            None,
        )
        if block is None:
            raise ProtectedLessonResourceNotFound(
                "Опубликованный материал не привязан к download-блоку этого урока."
            )

        resource = Resource.objects.filter(
            slug=normalized_slug,
            publication_status=Resource.PublicationStatus.PUBLISHED,
        ).first()
        if resource is None:
            raise ProtectedLessonResourceNotFound(
                "Опубликованный материал для этого урока не найден."
            )

        decision = check_access(user_id=user_id, lesson_id=lesson.id)
        if not decision.allowed:
            raise ProtectedLessonResourceAccessDenied(reason=decision.reason)

        return ProtectedLessonResource(
            lesson=lesson,
            block=block,
            resource=resource,
            access_decision=decision,
        )
