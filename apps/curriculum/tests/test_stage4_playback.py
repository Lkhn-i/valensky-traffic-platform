import json
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.curriculum.models import Course, Lesson
from apps.events.models import AnalyticsEvent
from apps.media_library.models import LessonMediaAttachment, MediaAsset, PlaybackTicket
from apps.media_library.services import hash_playback_token


def _lesson0() -> Lesson:
    return Lesson.objects.select_related("module", "module__course").get(
        module__position=0,
        position=0,
    )


def _paid_lesson() -> Lesson:
    course = Course.objects.get(slug="gatsa-sales")
    return Lesson.objects.select_related("module", "module__course").get(
        module__course=course,
        module__position=1,
        position=0,
    )


def _attach_video(
    *,
    lesson: Lesson,
    slug: str,
    status: str = "ready",
) -> LessonMediaAttachment:
    asset = MediaAsset.objects.create(
        slug=slug,
        title=f"Video {slug}",
        asset_kind=MediaAsset.AssetKind.VIDEO,
        availability_status=status,
        storage_backend=MediaAsset.StorageBackend.LOCAL,
        storage_key=f"videos/{slug}.mp4",
        source_url=f"https://cdn.example.invalid/videos/{slug}.mp4",
    )
    return LessonMediaAttachment.objects.create(
        lesson=lesson,
        media_asset=asset,
        purpose=LessonMediaAttachment.Purpose.PRIMARY_VIDEO,
    )


@pytest.mark.django_db
def test_lesson0_playback_returns_short_lived_contract_without_provider_fields(
    client: Client,
) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = _lesson0()
    _attach_video(lesson=lesson0, slug="lesson0-ready")

    response = client.get(reverse("curriculum:lesson_playback", args=[lesson0.id]))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["playback_url"].startswith("/media-library/playback/")
    assert payload["playback_token"]
    assert payload["expires_at"]
    assert {
        "storage_key",
        "source_url",
        "provider",
        "provider_context",
        "metadata",
        "asset_id",
    }.isdisjoint(payload)
    assert AnalyticsEvent.objects.filter(name="video_started", object_key=str(lesson0.id)).exists()


@pytest.mark.django_db
def test_lead_cannot_request_locked_paid_lesson_video(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    paid_lesson = _paid_lesson()
    _attach_video(lesson=paid_lesson, slug="paid-lesson-ready")

    response = client.get(reverse("curriculum:lesson_playback", args=[paid_lesson.id]))

    assert response.status_code == 403
    payload = response.json()
    assert payload == {
        "status": "locked",
        "error": "access_denied",
        "reason": "missing_paid_access_grant",
    }
    assert "playback_url" not in payload
    assert "playback_token" not in payload


@pytest.mark.django_db
def test_lesson0_playback_reports_missing_and_processing_video(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = _lesson0()

    missing_response = client.get(reverse("curriculum:lesson_playback", args=[lesson0.id]))

    assert missing_response.status_code == 404
    assert missing_response.json()["status"] == "missing"
    assert missing_response.json()["reason"] == "media_missing"

    _attach_video(
        lesson=lesson0,
        slug="lesson0-processing",
        status="processing",
    )
    processing_response = client.get(reverse("curriculum:lesson_playback", args=[lesson0.id]))

    assert processing_response.status_code == 409
    assert processing_response.json()["status"] == "processing"
    assert processing_response.json()["reason"] == "media_processing"


@pytest.mark.django_db
def test_expired_playback_token_is_reported_explicitly(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = _lesson0()
    _attach_video(lesson=lesson0, slug="lesson0-expired")
    playback_response = client.get(reverse("curriculum:lesson_playback", args=[lesson0.id]))
    raw_token = playback_response.json()["playback_token"]

    ticket = PlaybackTicket.objects.get(token_hash=hash_playback_token(raw_token))
    ticket.expires_at = timezone.now() - timedelta(seconds=1)
    ticket.save(update_fields=["expires_at"])

    response = client.get(
        reverse("curriculum:playback_ticket_status"),
        HTTP_X_PLAYBACK_TOKEN=raw_token,
    )

    assert response.status_code == 410
    assert response.json() == {
        "status": "token_expired",
        "reason": "playback_ticket_expired",
    }
    assert AnalyticsEvent.objects.filter(name="video_token_expired").exists()


@pytest.mark.django_db
def test_video_progress_event_is_recorded_after_access_check(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = _lesson0()

    response = client.post(
        reverse("curriculum:lesson_video_event", args=[lesson0.id]),
        data=json.dumps({"event": "progressed", "position_seconds": 42, "percent": 35}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"status": "recorded", "event": "progressed"}
    event = AnalyticsEvent.objects.get(name="video_progressed")
    assert event.properties["position_seconds"] == 42
    assert event.properties["percent"] == 35
