from __future__ import annotations

from typing import Any, Mapping, Protocol

from django.db.models import QuerySet

from .models import AnalyticsEvent, AuditLog


class AnalyticsEventService(Protocol):
    def list_events(
        self,
        *,
        source_app: str | None = None,
        actor_identifier: str | None = None,
    ) -> QuerySet[AnalyticsEvent]:
        ...

    def record_event(
        self,
        *,
        name: str,
        source_app: str,
        actor_identifier: str = "",
        session_identifier: str = "",
        object_type: str = "",
        object_key: str = "",
        properties: Mapping[str, Any] | None = None,
    ) -> AnalyticsEvent:
        ...


class AuditLogService(Protocol):
    def list_logs(
        self,
        *,
        result: str | None = None,
        actor_identifier: str | None = None,
    ) -> QuerySet[AuditLog]:
        ...

    def record_log(
        self,
        *,
        action: str,
        result: str = "info",
        actor_identifier: str = "",
        target_type: str = "",
        target_key: str = "",
        message: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        ...


class ORMAnalyticsEventService:
    def list_events(
        self,
        *,
        source_app: str | None = None,
        actor_identifier: str | None = None,
    ) -> QuerySet[AnalyticsEvent]:
        queryset = AnalyticsEvent.objects.all()
        if source_app:
            queryset = queryset.filter(source_app=source_app)
        if actor_identifier:
            queryset = queryset.filter(actor_identifier=actor_identifier)
        return queryset.order_by(*AnalyticsEvent._meta.ordering)

    def record_event(
        self,
        *,
        name: str,
        source_app: str,
        actor_identifier: str = "",
        session_identifier: str = "",
        object_type: str = "",
        object_key: str = "",
        properties: Mapping[str, Any] | None = None,
    ) -> AnalyticsEvent:
        return AnalyticsEvent.objects.create(
            name=name,
            source_app=source_app,
            actor_identifier=actor_identifier,
            session_identifier=session_identifier,
            object_type=object_type,
            object_key=object_key,
            properties=dict(properties or {}),
        )


class StubAnalyticsEventService:
    def list_events(
        self,
        *,
        source_app: str | None = None,
        actor_identifier: str | None = None,
    ) -> QuerySet[AnalyticsEvent]:
        return AnalyticsEvent.objects.none()

    def record_event(
        self,
        *,
        name: str,
        source_app: str,
        actor_identifier: str = "",
        session_identifier: str = "",
        object_type: str = "",
        object_key: str = "",
        properties: Mapping[str, Any] | None = None,
    ) -> AnalyticsEvent:
        return AnalyticsEvent(
            name=name,
            source_app=source_app,
            actor_identifier=actor_identifier,
            session_identifier=session_identifier,
            object_type=object_type,
            object_key=object_key,
            properties=dict(properties or {}),
        )


class ORMAuditLogService:
    def list_logs(
        self,
        *,
        result: str | None = None,
        actor_identifier: str | None = None,
    ) -> QuerySet[AuditLog]:
        queryset = AuditLog.objects.all()
        if result:
            queryset = queryset.filter(result=result)
        if actor_identifier:
            queryset = queryset.filter(actor_identifier=actor_identifier)
        return queryset.order_by(*AuditLog._meta.ordering)

    def record_log(
        self,
        *,
        action: str,
        result: str = "info",
        actor_identifier: str = "",
        target_type: str = "",
        target_key: str = "",
        message: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        return AuditLog.objects.create(
            action=action,
            result=result,
            actor_identifier=actor_identifier,
            target_type=target_type,
            target_key=target_key,
            message=message,
            payload=dict(payload or {}),
        )


class StubAuditLogService:
    def list_logs(
        self,
        *,
        result: str | None = None,
        actor_identifier: str | None = None,
    ) -> QuerySet[AuditLog]:
        return AuditLog.objects.none()

    def record_log(
        self,
        *,
        action: str,
        result: str = "info",
        actor_identifier: str = "",
        target_type: str = "",
        target_key: str = "",
        message: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        return AuditLog(
            action=action,
            result=result,
            actor_identifier=actor_identifier,
            target_type=target_type,
            target_key=target_key,
            message=message,
            payload=dict(payload or {}),
        )
