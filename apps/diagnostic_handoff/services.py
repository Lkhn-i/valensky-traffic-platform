from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.access_control.models import PreviewAccessGrant
from apps.access_control.services import grant_preview_access
from apps.accounts.models import LeadProfile, MagicLink
from apps.accounts.services import get_or_create_lead_from_diagnostic
from apps.integrations.services import enqueue_bot_outbox_from_notification
from apps.notifications.services import TELEGRAM_CHANNEL, enqueue_lesson_zero_entry_notification

from .models import DiagnosticHandoff


def hash_handoff_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HandoffResolution:
    handoff: DiagnosticHandoff
    was_replay: bool


@dataclass(frozen=True)
class PreviewHandoffResolution:
    handoff: DiagnosticHandoff
    lead_profile: LeadProfile | None
    preview_grant: PreviewAccessGrant | None
    magic_link: MagicLink | None
    created_lead: bool = False
    status: str = "resolved"

    @property
    def is_resolved(self) -> bool:
        return self.status == "resolved"


@transaction.atomic
def create_diagnostic_handoff(
    *,
    source: str,
    external_session_id: str,
    raw_token: str,
    expires_at: datetime,
    diagnostic_segment: str = "",
    raw_payload: Mapping[str, Any] | None = None,
) -> DiagnosticHandoff:
    token_hash = hash_handoff_token(raw_token)
    handoff, _created = DiagnosticHandoff.objects.update_or_create(
        source=source,
        external_session_id=external_session_id,
        defaults={
            "idempotency_key": f"{source}:{external_session_id}",
            "token_hash": token_hash,
            "diagnostic_segment": diagnostic_segment,
            "raw_payload": dict(raw_payload or {}),
            "expires_at": expires_at,
        },
    )
    return handoff


def _extract_telegram_id(payload: Mapping[str, Any]) -> int | None:
    raw_value = payload.get("tg_user_id") or payload.get("telegram_id")
    if raw_value is None:
        return None
    try:
        telegram_id = int(raw_value)
    except (TypeError, ValueError):
        return None
    return telegram_id if telegram_id > 0 else None


def _queue_lesson_zero_entry_message(
    *,
    user_id: int,
    handoff_id: int,
    preview_grant_id: int,
    course_slug: str,
    lesson_slug: str,
    redirect_path: str,
) -> None:
    notification_job = enqueue_lesson_zero_entry_notification(
        user_id=user_id,
        course_slug=course_slug,
        lesson_slug=lesson_slug,
        channel=TELEGRAM_CHANNEL,
        payload={
            "handoff_id": handoff_id,
            "preview_grant_id": preview_grant_id,
            "access_path": redirect_path,
        },
        dedupe_key=f"lesson0-entry:{handoff_id}",
    )
    enqueue_bot_outbox_from_notification(
        notification_job_id=notification_job.id,
        template_key=notification_job.template_key,
        idempotency_key=f"bot:lesson0-entry:{handoff_id}",
        event_type="lesson0.entry_link",
        user_id=user_id,
        payload={
            "handoff_id": handoff_id,
            "preview_grant_id": preview_grant_id,
            "access_path": redirect_path,
        },
    )


def create_simulated_diagnostic_handoff(
    *,
    diagnostic_segment: str = "stage3_preview",
    ttl_hours: int = 1,
) -> tuple[DiagnosticHandoff, str]:
    raw_token = secrets.token_urlsafe(32)
    external_session_id = f"sim-{uuid.uuid4()}"
    handoff = create_diagnostic_handoff(
        source="diagnostic_site",
        external_session_id=external_session_id,
        raw_token=raw_token,
        expires_at=timezone.now() + timedelta(hours=ttl_hours),
        diagnostic_segment=diagnostic_segment,
        raw_payload={
            "source": "stage3_simulated_submit",
            "external_session_id": external_session_id,
        },
    )
    return handoff, raw_token


@transaction.atomic
def resolve_handoff_for_lead(
    *,
    raw_token: str,
    lead_profile_id: int,
) -> HandoffResolution:
    token_hash = hash_handoff_token(raw_token)
    handoff = DiagnosticHandoff.objects.select_for_update().get(token_hash=token_hash)
    lead_profile = LeadProfile.objects.select_related("user").get(id=lead_profile_id)

    if handoff.status == DiagnosticHandoff.Status.RESOLVED:
        handoff.replay_count += 1
        handoff.save(update_fields=["replay_count", "updated_at"])
        return HandoffResolution(handoff=handoff, was_replay=True)

    if handoff.is_expired:
        handoff.status = DiagnosticHandoff.Status.EXPIRED
        handoff.save(update_fields=["status", "updated_at"])
        return HandoffResolution(handoff=handoff, was_replay=False)

    handoff.status = DiagnosticHandoff.Status.RESOLVED
    handoff.lead_profile = lead_profile
    handoff.user = lead_profile.user
    handoff.resolved_at = timezone.now()
    handoff.save(
        update_fields=[
            "status",
            "lead_profile",
            "user",
            "resolved_at",
            "updated_at",
        ]
    )
    return HandoffResolution(handoff=handoff, was_replay=False)


@transaction.atomic
def resolve_handoff_to_preview_access(
    *,
    raw_token: str,
    course_id: int,
    lesson0_id: int,
    preview_expires_at: datetime,
    redirect_path: str,
) -> PreviewHandoffResolution:
    token_hash = hash_handoff_token(raw_token)
    handoff = DiagnosticHandoff.objects.select_for_update().filter(token_hash=token_hash).first()
    if handoff is None:
        return PreviewHandoffResolution(
            handoff=DiagnosticHandoff(token_hash=token_hash, expires_at=timezone.now()),
            lead_profile=None,
            preview_grant=None,
            magic_link=None,
            status="missing",
        )

    if handoff.status != DiagnosticHandoff.Status.CREATED:
        handoff.replay_count += 1
        handoff.save(update_fields=["replay_count", "updated_at"])
        return PreviewHandoffResolution(
            handoff=handoff,
            lead_profile=handoff.lead_profile,
            preview_grant=None,
            magic_link=None,
            status="replayed",
        )

    if handoff.is_expired:
        handoff.status = DiagnosticHandoff.Status.EXPIRED
        handoff.save(update_fields=["status", "updated_at"])
        return PreviewHandoffResolution(
            handoff=handoff,
            lead_profile=None,
            preview_grant=None,
            magic_link=None,
            status="expired",
        )

    lead_profile, created_lead = get_or_create_lead_from_diagnostic(
        external_session_id=handoff.external_session_id,
        diagnostic_segment=handoff.diagnostic_segment,
        source=handoff.source,
        telegram_id=_extract_telegram_id(handoff.raw_payload),
    )
    preview_grant = grant_preview_access(
        lead_profile_id=lead_profile.id,
        course_id=course_id,
        lesson_id=lesson0_id,
        expires_at=preview_expires_at,
        diagnostic_handoff_id=handoff.id,
    )
    magic_link, _created_magic_link = MagicLink.objects.update_or_create(
        token_hash=token_hash,
        defaults={
            "user": lead_profile.user,
            "purpose": "diagnostic_preview",
            "redirect_path": redirect_path,
            "expires_at": preview_expires_at,
            "consumed_at": timezone.now(),
        },
    )

    handoff.status = DiagnosticHandoff.Status.RESOLVED
    handoff.user = lead_profile.user
    handoff.lead_profile = lead_profile
    handoff.resolved_at = timezone.now()
    handoff.save(
        update_fields=[
            "status",
            "user",
            "lead_profile",
            "resolved_at",
            "updated_at",
        ]
    )
    transaction.on_commit(
        lambda: _queue_lesson_zero_entry_message(
            user_id=lead_profile.user_id,
            handoff_id=handoff.id,
            preview_grant_id=preview_grant.id,
            course_slug=preview_grant.course.slug,
            lesson_slug=preview_grant.lesson.slug,
            redirect_path=redirect_path,
        )
    )
    get_user_model().objects.only("id").get(id=lead_profile.user_id)
    return PreviewHandoffResolution(
        handoff=handoff,
        lead_profile=lead_profile,
        preview_grant=preview_grant,
        magic_link=magic_link,
        created_lead=created_lead,
    )
