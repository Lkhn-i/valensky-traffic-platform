import pytest
from django.test import Client

from apps.curriculum.models import Course, Lesson, Module
from apps.media_library.models import LessonMediaAttachment, MediaAsset
from apps.media_library.services import PlaybackService


def _build_ready_session() -> tuple[str, str]:
    course = Course.objects.create(slug="course-stream", title="Gatsa Sales")
    module = Module.objects.create(course=course, slug="module-stream", title="Start", position=0)
    lesson = Lesson.objects.create(module=module, slug="lesson-stream", title="Урок", position=0)
    asset = MediaAsset.objects.create(
        slug="ready-stream-video",
        title="Ready Stream Video",
        asset_kind=MediaAsset.AssetKind.VIDEO,
        availability_status=MediaAsset.AvailabilityStatus.READY,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
        storage_key="videos/ready-stream-video.mp4",
        source_url="https://cdn.example.invalid/videos/ready-stream-video.mp4",
        mime_type="video/mp4",
    )
    attachment = LessonMediaAttachment.objects.create(lesson=lesson, media_asset=asset)
    session = PlaybackService().issue_for_attachment(attachment_id=attachment.id)

    assert session.playback_url is not None
    assert session.ticket_token is not None
    return session.playback_url, session.ticket_token


@pytest.mark.django_db
def test_local_playback_stream_requires_token(client: Client) -> None:
    playback_url, _raw_token = _build_ready_session()

    response = client.get(playback_url)

    assert response.status_code == 401
    assert response.json() == {"status": "locked", "reason": "playback_token_required"}


@pytest.mark.django_db
def test_local_playback_stream_validates_token_without_leaking_provider_fields(
    client: Client,
) -> None:
    playback_url, raw_token = _build_ready_session()

    response = client.get(playback_url, HTTP_X_PLAYBACK_TOKEN=raw_token)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["stream"] == "local_provider_placeholder"
    assert {
        "storage_key",
        "source_url",
        "provider",
        "provider_context",
        "metadata",
    }.isdisjoint(payload)
