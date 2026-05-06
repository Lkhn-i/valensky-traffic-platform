from dataclasses import asdict
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.curriculum.models import Course, Lesson, Module
from apps.media_library.models import LessonMediaAttachment, MediaAsset, PlaybackTicket
from apps.media_library.services import (
    ExpiredPlaybackTicketError,
    ORMMediaLibraryService,
    PlaybackService,
    PlaybackState,
    StubMediaLibraryService,
    hash_playback_token,
)


def build_lesson(*, lesson_slug: str = "lesson-0") -> Lesson:
    course = Course.objects.create(slug=f"course-{lesson_slug}", title="Gatsa Sales")
    module = Module.objects.create(
        course=course,
        slug=f"module-{lesson_slug}",
        title="Start",
        position=0,
    )
    return Lesson.objects.create(module=module, slug=lesson_slug, title="Урок", position=0)


@pytest.mark.django_db
def test_media_library_filters_available_assets() -> None:
    MediaAsset.objects.create(
        slug="queued-video",
        title="Queued Video",
        asset_kind="video",
    )
    ready = MediaAsset.objects.create(
        slug="ready-image",
        title="Ready Image",
        asset_kind="image",
        availability_status="ready",
        storage_backend="local",
    )

    service = ORMMediaLibraryService()

    assert list(
        service.list_assets(availability_status="ready")
    ) == [ready]
    assert service.get_asset(slug=ready.slug) == ready


def test_media_library_stub_service_is_empty() -> None:
    service = StubMediaLibraryService()

    assert list(service.list_assets()) == []


@pytest.mark.django_db
def test_playback_service_returns_missing_when_attachment_does_not_exist() -> None:
    result = PlaybackService().issue_for_attachment(attachment_id=9999)

    assert result.state == PlaybackState.MISSING
    assert result.ticket_token is None
    assert PlaybackTicket.objects.count() == 0


@pytest.mark.django_db
def test_playback_service_returns_processing_for_unready_video() -> None:
    lesson = build_lesson()
    asset = MediaAsset.objects.create(
        slug="processing-playback-video",
        title="Processing Playback Video",
        asset_kind=MediaAsset.AssetKind.VIDEO,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
    )
    attachment = LessonMediaAttachment.objects.create(lesson=lesson, media_asset=asset)

    result = PlaybackService().issue_for_attachment(attachment_id=attachment.id)

    assert result.state == PlaybackState.PROCESSING
    assert result.asset_id == asset.id
    assert result.ticket_token is None
    assert PlaybackTicket.objects.count() == 0


@pytest.mark.django_db
def test_playback_service_returns_failed_for_failed_video() -> None:
    lesson = build_lesson(lesson_slug="lesson-failed")
    asset = MediaAsset.objects.create(
        slug="failed-playback-video",
        title="Failed Playback Video",
        asset_kind=MediaAsset.AssetKind.VIDEO,
        availability_status=MediaAsset.AvailabilityStatus.FAILED,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
    )
    attachment = LessonMediaAttachment.objects.create(lesson=lesson, media_asset=asset)

    result = PlaybackService().issue_for_attachment(attachment_id=attachment.id)

    assert result.state == PlaybackState.FAILED
    assert "ошибка" in result.detail.lower()
    assert result.ticket_token is None
    assert PlaybackTicket.objects.count() == 0


@pytest.mark.django_db
def test_playback_service_fails_for_ready_non_video_assets() -> None:
    lesson = build_lesson(lesson_slug="lesson-image")
    asset = MediaAsset.objects.create(
        slug="ready-image-playback",
        title="Ready Image",
        asset_kind=MediaAsset.AssetKind.IMAGE,
        availability_status=MediaAsset.AvailabilityStatus.READY,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
    )
    attachment = LessonMediaAttachment.objects.create(lesson=lesson, media_asset=asset)

    result = PlaybackService().issue_for_attachment(attachment_id=attachment.id)

    assert result.state == PlaybackState.FAILED
    assert "только для видео" in result.detail.lower()
    assert PlaybackTicket.objects.count() == 0


@pytest.mark.django_db
def test_playback_service_issues_ready_contract_and_keeps_provider_context_internal() -> None:
    lesson = build_lesson(lesson_slug="lesson-video")
    asset = MediaAsset.objects.create(
        slug="ready-video-playback",
        title="Ready Video",
        asset_kind=MediaAsset.AssetKind.VIDEO,
        availability_status=MediaAsset.AvailabilityStatus.READY,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
        storage_key="videos/lesson-video.mp4",
        source_url="https://cdn.example.com/videos/lesson-video.mp4",
    )
    attachment = LessonMediaAttachment.objects.create(lesson=lesson, media_asset=asset)
    service = PlaybackService(ticket_ttl=timedelta(minutes=5))

    result = service.issue_for_attachment(attachment_id=attachment.id)

    assert result.state == PlaybackState.READY
    assert result.is_ready is True
    assert result.provider == MediaAsset.StorageBackend.LOCAL
    assert result.ticket_token is not None
    assert result.headers == {"X-Playback-Token": result.ticket_token}

    ticket = PlaybackTicket.objects.get(token_hash=hash_playback_token(result.ticket_token))
    assert result.playback_url == f"/media-library/playback/{ticket.id}/stream"
    assert ticket.attachment == attachment
    assert ticket.metadata["provider"] == MediaAsset.StorageBackend.LOCAL
    assert ticket.metadata["provider_context"]["storage_key"] == asset.storage_key
    assert ticket.metadata["provider_context"]["source_url"] == asset.source_url

    payload = asdict(result)
    assert "storage_key" not in payload
    assert "source_url" not in payload
    assert "provider_context" not in payload


@pytest.mark.django_db
def test_playback_service_issues_primary_video_for_lesson() -> None:
    lesson = build_lesson(lesson_slug="lesson-primary-video")
    video_asset = MediaAsset.objects.create(
        slug="ready-primary-video",
        title="Ready Primary Video",
        asset_kind=MediaAsset.AssetKind.VIDEO,
        availability_status=MediaAsset.AvailabilityStatus.READY,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
    )
    transcript_asset = MediaAsset.objects.create(
        slug="ready-primary-transcript",
        title="Ready Primary Transcript",
        asset_kind=MediaAsset.AssetKind.DOCUMENT,
        availability_status=MediaAsset.AvailabilityStatus.READY,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
    )
    LessonMediaAttachment.objects.create(
        lesson=lesson,
        media_asset=transcript_asset,
        purpose=LessonMediaAttachment.Purpose.TRANSCRIPT,
    )
    LessonMediaAttachment.objects.create(
        lesson=lesson,
        media_asset=video_asset,
        purpose=LessonMediaAttachment.Purpose.PRIMARY_VIDEO,
    )

    result = PlaybackService().issue_for_lesson(lesson_id=lesson.id)

    assert result.state == PlaybackState.READY
    assert result.asset_id == video_asset.id


@pytest.mark.django_db
def test_playback_service_raises_explicit_error_for_expired_ticket() -> None:
    lesson = build_lesson(lesson_slug="lesson-expired")
    asset = MediaAsset.objects.create(
        slug="ready-video-expired",
        title="Ready Video Expired",
        asset_kind=MediaAsset.AssetKind.VIDEO,
        availability_status=MediaAsset.AvailabilityStatus.READY,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
    )
    attachment = LessonMediaAttachment.objects.create(lesson=lesson, media_asset=asset)
    service = PlaybackService(ticket_ttl=timedelta(minutes=5))
    result = service.issue_for_attachment(attachment_id=attachment.id)

    assert result.ticket_token is not None

    ticket = PlaybackTicket.objects.get(token_hash=hash_playback_token(result.ticket_token))
    ticket.expires_at = timezone.now() - timedelta(seconds=1)
    ticket.save(update_fields=["expires_at"])

    with pytest.raises(ExpiredPlaybackTicketError, match="истёк"):
        service.get_valid_ticket(raw_token=result.ticket_token)
