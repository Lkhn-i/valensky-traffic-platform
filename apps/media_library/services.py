from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from .models import LessonMediaAttachment, MediaAsset, PlaybackTicket


class MediaLibraryService(Protocol):
    def list_assets(
        self,
        *,
        availability_status: str | None = None,
        asset_kind: str | None = None,
    ) -> QuerySet[MediaAsset]:
        ...

    def get_asset(self, *, slug: str) -> MediaAsset:
        ...


def hash_playback_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class PlaybackState(StrEnum):
    MISSING = "missing"
    PROCESSING = "processing"
    FAILED = "failed"
    READY = "ready"


@dataclass(frozen=True)
class PlaybackProviderContract:
    playback_url: str
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlaybackSession:
    state: PlaybackState
    attachment_id: int | None = None
    asset_id: int | None = None
    provider: str | None = None
    playback_url: str | None = None
    ticket_token: str | None = None
    expires_at: datetime | None = None
    headers: dict[str, str] = field(default_factory=dict)
    detail: str = ""

    @property
    def is_ready(self) -> bool:
        return self.state == PlaybackState.READY


class PlaybackTicketError(Exception):
    """Base error for playback ticket validation."""


class PlaybackTicketNotFoundError(PlaybackTicketError):
    """Raised when a playback token does not match an existing ticket."""


class ExpiredPlaybackTicketError(PlaybackTicketError):
    """Raised when a playback ticket exists but is no longer valid."""


class ConsumedPlaybackTicketError(PlaybackTicketError):
    """Raised when a playback ticket was already consumed."""


class PlaybackProviderAdapter(Protocol):
    provider_name: str

    def supports(self, *, asset: MediaAsset) -> bool:
        ...

    def issue_contract(
        self,
        *,
        asset: MediaAsset,
        ticket: PlaybackTicket,
        raw_token: str,
    ) -> PlaybackProviderContract:
        ...


class ORMMediaLibraryService:
    def list_assets(
        self,
        *,
        availability_status: str | None = None,
        asset_kind: str | None = None,
    ) -> QuerySet[MediaAsset]:
        queryset = MediaAsset.objects.all()
        if availability_status:
            queryset = queryset.filter(availability_status=availability_status)
        if asset_kind:
            queryset = queryset.filter(asset_kind=asset_kind)
        return queryset.order_by(*MediaAsset._meta.ordering)

    def get_asset(self, *, slug: str) -> MediaAsset:
        return self.list_assets().get(slug=slug)


class StubMediaLibraryService:
    def list_assets(
        self,
        *,
        availability_status: str | None = None,
        asset_kind: str | None = None,
    ) -> QuerySet[MediaAsset]:
        return MediaAsset.objects.none()

    def get_asset(self, *, slug: str) -> MediaAsset:
        raise MediaAsset.DoesNotExist(f"Медиафайл со slug={slug!r} недоступен")


class LocalPlaybackProvider:
    provider_name = "local"

    def supports(self, *, asset: MediaAsset) -> bool:
        return asset.storage_backend == MediaAsset.StorageBackend.LOCAL

    def issue_contract(
        self,
        *,
        asset: MediaAsset,
        ticket: PlaybackTicket,
        raw_token: str,
    ) -> PlaybackProviderContract:
        metadata: dict[str, Any] = {
            "storage_backend": asset.storage_backend,
        }
        if asset.storage_key:
            metadata["storage_key"] = asset.storage_key
        if asset.source_url:
            metadata["source_url"] = asset.source_url

        return PlaybackProviderContract(
            playback_url=f"/media-library/playback/{ticket.id}/stream",
            headers={"X-Playback-Token": raw_token},
            metadata=metadata,
        )


class PlaybackService:
    def __init__(
        self,
        *,
        provider: PlaybackProviderAdapter | None = None,
        ticket_ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        self.provider = provider or LocalPlaybackProvider()
        self.ticket_ttl = ticket_ttl

    def issue_for_attachment(self, *, attachment_id: int) -> PlaybackSession:
        attachment = (
            LessonMediaAttachment.objects.select_related("media_asset")
            .filter(id=attachment_id)
            .first()
        )
        if attachment is None:
            return self._missing_session()

        return self._issue_from_attachment(attachment=attachment)

    def issue_for_lesson(self, *, lesson_id: int) -> PlaybackSession:
        attachment = (
            LessonMediaAttachment.objects.select_related("media_asset")
            .filter(
                lesson_id=lesson_id,
                purpose=LessonMediaAttachment.Purpose.PRIMARY_VIDEO,
                media_asset__asset_kind=MediaAsset.AssetKind.VIDEO,
            )
            .order_by("position", "id")
            .first()
        )
        if attachment is None:
            return self._missing_session()

        return self._issue_from_attachment(attachment=attachment)

    def _missing_session(self) -> PlaybackSession:
        return PlaybackSession(
            state=PlaybackState.MISSING,
            detail="Медиафайл урока не найден.",
        )

    def _issue_from_attachment(self, *, attachment: LessonMediaAttachment) -> PlaybackSession:
        asset = attachment.media_asset
        if asset.availability_status in {
            MediaAsset.AvailabilityStatus.PROCESSING,
            MediaAsset.AvailabilityStatus.QUEUED,
        }:
            return PlaybackSession(
                state=PlaybackState.PROCESSING,
                attachment_id=attachment.id,
                asset_id=asset.id,
                detail="Медиафайл ещё обрабатывается.",
            )

        if asset.availability_status == MediaAsset.AvailabilityStatus.FAILED:
            return PlaybackSession(
                state=PlaybackState.FAILED,
                attachment_id=attachment.id,
                asset_id=asset.id,
                detail="Ошибка обработки медиафайла.",
            )

        if asset.availability_status != MediaAsset.AvailabilityStatus.READY:
            return PlaybackSession(
                state=PlaybackState.FAILED,
                attachment_id=attachment.id,
                asset_id=asset.id,
                detail=(
                    "Медиафайл недоступен для воспроизведения "
                    f"в статусе {asset.availability_status}."
                ),
            )

        if asset.asset_kind != MediaAsset.AssetKind.VIDEO:
            return PlaybackSession(
                state=PlaybackState.FAILED,
                attachment_id=attachment.id,
                asset_id=asset.id,
                detail="Воспроизведение доступно только для видео.",
            )

        if not self.provider.supports(asset=asset):
            return PlaybackSession(
                state=PlaybackState.FAILED,
                attachment_id=attachment.id,
                asset_id=asset.id,
                detail=(
                    "Для этого хранилища не настроен провайдер воспроизведения: "
                    f"{asset.storage_backend}."
                ),
            )

        return self._create_ready_session(attachment=attachment, asset=asset)

    def get_valid_ticket(self, *, raw_token: str) -> PlaybackTicket:
        ticket = self._get_ticket(raw_token=raw_token)
        if ticket.is_expired:
            raise ExpiredPlaybackTicketError("Токен воспроизведения истёк.")
        if ticket.consumed:
            raise ConsumedPlaybackTicketError("Токен воспроизведения уже использован.")
        return ticket

    @transaction.atomic
    def consume_ticket(self, *, raw_token: str) -> PlaybackTicket:
        ticket = self._get_ticket(raw_token=raw_token, for_update=True)
        if ticket.is_expired:
            raise ExpiredPlaybackTicketError("Токен воспроизведения истёк.")
        if ticket.consumed:
            raise ConsumedPlaybackTicketError("Токен воспроизведения уже использован.")

        ticket.consumed = True
        ticket.save(update_fields=["consumed", "updated_at"])
        return ticket

    def _create_ready_session(
        self,
        *,
        attachment: LessonMediaAttachment,
        asset: MediaAsset,
    ) -> PlaybackSession:
        raw_token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + self.ticket_ttl
        ticket = PlaybackTicket.objects.create(
            attachment=attachment,
            token_hash=hash_playback_token(raw_token),
            expires_at=expires_at,
            metadata={
                "provider": self.provider.provider_name,
                "asset_public_id": str(asset.public_id),
            },
        )
        provider_contract = self.provider.issue_contract(
            asset=asset,
            ticket=ticket,
            raw_token=raw_token,
        )
        ticket.metadata = {
            **ticket.metadata,
            "provider_context": dict(provider_contract.metadata),
        }
        ticket.save(update_fields=["metadata", "updated_at"])

        return PlaybackSession(
            state=PlaybackState.READY,
            attachment_id=attachment.id,
            asset_id=asset.id,
            provider=self.provider.provider_name,
            playback_url=provider_contract.playback_url,
            ticket_token=raw_token,
            expires_at=ticket.expires_at,
            headers=dict(provider_contract.headers),
        )

    def _get_ticket(self, *, raw_token: str, for_update: bool = False) -> PlaybackTicket:
        queryset = PlaybackTicket.objects.select_related("attachment", "attachment__media_asset")
        if for_update:
            queryset = queryset.select_for_update()
        ticket = queryset.filter(token_hash=hash_playback_token(raw_token)).first()
        if ticket is None:
            raise PlaybackTicketNotFoundError("Токен воспроизведения не найден.")
        return ticket
