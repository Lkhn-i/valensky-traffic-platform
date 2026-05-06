from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.access_control.models import PreviewAccessGrant
from apps.accounts.models import LeadProfile
from apps.curriculum.models import Course, Lesson
from apps.curriculum.services import ensure_stage3_preview_course
from apps.diagnostic_handoff.services import create_diagnostic_handoff
from apps.events.models import AnalyticsEvent
from apps.integrations.models import IntegrationOutboxEvent
from apps.notifications.models import NotificationJob


def _paid_lesson() -> Lesson:
    course = Course.objects.get(slug="gatsa-sales")
    return Lesson.objects.select_related("module", "module__course").get(
        module__course=course,
        module__position=1,
        position=0,
    )


@pytest.mark.django_db
def test_simulated_diagnostic_submit_lands_lead_on_preview_dashboard(client: Client) -> None:
    response = client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)

    body = response.content.decode()
    assert response.status_code == 200
    assert response.resolver_match.view_name == "curriculum:course_preview"
    assert LeadProfile.objects.count() == 1
    assert PreviewAccessGrant.objects.count() == 1
    assert "Урок 0. Вход после диагностики" in body
    assert "Откроется после регистрации и оплаты обучения." in body
    assert set(AnalyticsEvent.objects.values_list("name", flat=True)) >= {
        "diagnostic_handoff_created",
        "lead_created",
    }


@pytest.mark.django_db
def test_public_course_preview_creates_lead_access_without_manual_login(client: Client) -> None:
    course = ensure_stage3_preview_course()

    response = client.get(
        reverse("curriculum:course_preview", args=[course.slug]),
        follow=True,
    )

    body = response.content.decode()
    assert response.status_code == 200
    assert response.resolver_match.view_name == "curriculum:course_preview"
    assert LeadProfile.objects.count() == 1
    assert PreviewAccessGrant.objects.count() == 1
    assert "_auth_user_id" in client.session
    assert "Урок 0. Вход после диагностики" in body
    assert "Откроется после регистрации и оплаты обучения." in body
    assert AnalyticsEvent.objects.filter(name="public_preview_opened").exists()


@pytest.mark.django_db
def test_public_preview_short_link_lands_on_course_preview(client: Client) -> None:
    response = client.get(
        f"{reverse('diagnostic_handoff:public_preview_entry')}?session_id=survey-123&segment=warm",
        follow=True,
    )

    assert response.status_code == 200
    assert response.resolver_match.view_name == "curriculum:course_preview"
    assert LeadProfile.objects.count() == 1
    assert PreviewAccessGrant.objects.count() == 1
    assert LeadProfile.objects.get().diagnostic_session_id == "survey-123"


@pytest.mark.django_db
def test_lesson0_opens_after_handoff_and_paid_lesson_direct_url_is_denied(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = Lesson.objects.get(module__position=0, position=0)
    paid_lesson = _paid_lesson()

    lesson0_response = client.get(reverse("curriculum:lesson_detail", args=[lesson0.id]))
    paid_response = client.get(reverse("curriculum:lesson_detail", args=[paid_lesson.id]))

    assert lesson0_response.status_code == 200
    assert "Стартовый урок" in lesson0_response.content.decode()
    assert paid_response.status_code == 403
    assert "Доступ закрыт" in paid_response.content.decode()
    assert set(AnalyticsEvent.objects.values_list("name", flat=True)) >= {
        "lesson0_opened",
        "locked_module_clicked",
    }


@pytest.mark.django_db
def test_paid_lesson_playback_endpoint_does_not_return_token(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    paid_lesson = _paid_lesson()

    response = client.get(reverse("curriculum:lesson_playback", args=[paid_lesson.id]))

    assert response.status_code == 403
    payload = response.json()
    assert payload == {
        "status": "locked",
        "error": "access_denied",
        "reason": "missing_paid_access_grant",
    }
    assert "token" not in payload
    assert "playback_token" not in payload
    assert "playback_url" not in payload


@pytest.mark.django_db
def test_replayed_handoff_does_not_create_duplicate_leads(client: Client) -> None:
    raw_token = "manual-stage3-token"
    create_diagnostic_handoff(
        source="diagnostic_site",
        external_session_id="session-replay",
        raw_token=raw_token,
        expires_at=timezone.now() + timedelta(hours=1),
        diagnostic_segment="warm",
    )
    entry_url = reverse("diagnostic_handoff:preview_entry", args=[raw_token])

    first_response = client.get(entry_url, follow=True)
    second_client = Client()
    replay_response = second_client.get(entry_url)

    assert first_response.status_code == 200
    assert replay_response.status_code == 410
    assert LeadProfile.objects.count() == 1
    assert PreviewAccessGrant.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_preview_handoff_queues_lesson_zero_bot_entry_once(client: Client) -> None:
    raw_token = "stage8-entry-token"
    create_diagnostic_handoff(
        source="diagnostic_site",
        external_session_id="session-stage8",
        raw_token=raw_token,
        expires_at=timezone.now() + timedelta(hours=1),
        diagnostic_segment="warm",
        raw_payload={"telegram_id": 123456},
    )
    entry_url = reverse("diagnostic_handoff:preview_entry", args=[raw_token])

    first_response = client.get(entry_url, follow=True)
    replay_response = Client().get(entry_url)

    notification_job = NotificationJob.objects.get(template_key="lesson0.opened")
    outbox_event = IntegrationOutboxEvent.objects.get(event_type="lesson0.entry_link")

    assert first_response.status_code == 200
    assert replay_response.status_code == 410
    assert NotificationJob.objects.count() == 1
    assert IntegrationOutboxEvent.objects.count() == 1
    assert notification_job.channel == "telegram"
    assert notification_job.dedupe_key.startswith("lesson0-entry:")
    assert outbox_event.notification_job_id == notification_job.id
    assert outbox_event.idempotency_key.startswith("bot:lesson0-entry:")
    assert outbox_event.payload["access_path"].startswith("/learn/courses/")


@pytest.mark.django_db
def test_missing_and_expired_handoffs_do_not_create_access(client: Client) -> None:
    ensure_stage3_preview_course()
    expired_token = "expired-stage3-token"
    create_diagnostic_handoff(
        source="diagnostic_site",
        external_session_id="session-expired",
        raw_token=expired_token,
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    missing_response = client.get(
        reverse("diagnostic_handoff:preview_entry", args=["missing-token"])
    )
    expired_response = client.get(reverse("diagnostic_handoff:preview_entry", args=[expired_token]))

    assert missing_response.status_code == 404
    assert expired_response.status_code == 410
    assert LeadProfile.objects.count() == 0
    assert PreviewAccessGrant.objects.count() == 0
