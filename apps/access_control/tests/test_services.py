from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.access_control.models import AccessGrant, Enrollment, Tariff, TariffEntitlement
from apps.access_control.services import (
    check_access,
    grant_paid_access,
    grant_paid_access_once,
    grant_preview_access,
    revoke_access_grant,
)
from apps.accounts.models import LeadProfile
from apps.accounts.services import assign_role, ensure_required_roles
from apps.curriculum.models import Course, Lesson, Module


def create_course_tree() -> tuple[Course, Lesson, Lesson]:
    course = Course.objects.create(
        slug="gatsa-sales",
        title="Gatsa Sales",
        publication_status=Course.PublicationStatus.PUBLISHED,
    )
    module = Module.objects.create(
        course=course,
        slug="start",
        title="Start",
        position=0,
        publication_status=Module.PublicationStatus.PUBLISHED,
    )
    lesson0 = Lesson.objects.create(module=module, slug="lesson-0", title="Урок 0", position=0)
    paid_lesson = Lesson.objects.create(
        module=module,
        slug="lesson-1",
        title="Урок 1",
        position=1,
        publication_status=Lesson.PublicationStatus.PUBLISHED,
    )
    lesson0.publication_status = Lesson.PublicationStatus.PUBLISHED
    lesson0.save(update_fields=["publication_status", "updated_at"])
    return course, lesson0, paid_lesson


@pytest.mark.django_db
def test_lead_preview_grant_opens_only_lesson_zero() -> None:
    ensure_required_roles()
    user = get_user_model().objects.create_user(username="lead")
    assign_role(user.id, "lead")
    lead = LeadProfile.objects.create(user=user, status="new")
    course, lesson0, paid_lesson = create_course_tree()

    grant_preview_access(
        lead_profile_id=lead.id,
        course_id=course.id,
        lesson_id=lesson0.id,
        expires_at=timezone.now() + timedelta(days=3),
    )

    assert check_access(user_id=user.id, lesson_id=lesson0.id).allowed is True
    paid_decision = check_access(user_id=user.id, lesson_id=paid_lesson.id)
    assert paid_decision.allowed is False
    assert paid_decision.reason == "missing_paid_access_grant"


@pytest.mark.django_db
def test_paid_lesson_requires_paid_access_grant() -> None:
    ensure_required_roles()
    user = get_user_model().objects.create_user(username="student")
    assign_role(user.id, "student")
    course, _lesson0, paid_lesson = create_course_tree()
    tariff = Tariff.objects.create(code="base", course=course, title="Base")

    assert check_access(user_id=user.id, lesson_id=paid_lesson.id).allowed is False

    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)

    assert check_access(user_id=user.id, lesson_id=paid_lesson.id).allowed is True


@pytest.mark.django_db
def test_non_staff_access_rejects_unpublished_content_even_with_paid_grant() -> None:
    ensure_required_roles()
    user = get_user_model().objects.create_user(username="draft-student")
    assign_role(user.id, "student")
    course, _lesson0, paid_lesson = create_course_tree()
    tariff = Tariff.objects.create(code="base", course=course, title="Base")
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)

    paid_lesson.publication_status = Lesson.PublicationStatus.DRAFT
    paid_lesson.save(update_fields=["publication_status", "updated_at"])

    decision = check_access(user_id=user.id, lesson_id=paid_lesson.id)

    assert decision.allowed is False
    assert decision.reason == "lesson_unpublished"


@pytest.mark.django_db
def test_paid_access_once_is_idempotent_by_source_reference() -> None:
    ensure_required_roles()
    user = get_user_model().objects.create_user(username="student")
    assign_role(user.id, "student")
    course, _lesson0, _paid_lesson = create_course_tree()
    tariff = Tariff.objects.create(code="base", course=course, title="Base")

    first_grant, first_created = grant_paid_access_once(
        user_id=user.id,
        course_id=course.id,
        tariff_id=tariff.id,
        source_reference="order:1",
    )
    second_grant, second_created = grant_paid_access_once(
        user_id=user.id,
        course_id=course.id,
        tariff_id=tariff.id,
        source_reference="order:1",
    )

    assert first_created is True
    assert second_created is False
    assert first_grant.id == second_grant.id
    assert AccessGrant.objects.count() == 1


@pytest.mark.django_db
def test_revoke_access_grant_preserves_model_history_and_cancels_enrollment() -> None:
    ensure_required_roles()
    user = get_user_model().objects.create_user(username="student")
    assign_role(user.id, "student")
    course, _lesson0, _paid_lesson = create_course_tree()
    tariff = Tariff.objects.create(code="base", course=course, title="Base")
    grant, _created = grant_paid_access_once(
        user_id=user.id,
        course_id=course.id,
        tariff_id=tariff.id,
        source_reference="order:2",
    )

    revoked_grant = revoke_access_grant(
        grant_id=grant.id,
        reason="refund approved",
        revoked_by_id=None,
    )

    assert revoked_grant.status == AccessGrant.Status.REVOKED
    assert revoked_grant.revoked_at is not None
    assert AccessGrant.objects.filter(id=grant.id).exists()
    assert Enrollment.objects.get(user=user, course=course).status == Enrollment.Status.CANCELED


@pytest.mark.django_db
def test_paid_grant_respects_tariff_module_entitlements() -> None:
    ensure_required_roles()
    user = get_user_model().objects.create_user(username="student")
    assign_role(user.id, "student")
    course = Course.objects.create(
        slug="gatsa-sales",
        title="Gatsa Sales",
        publication_status=Course.PublicationStatus.PUBLISHED,
    )
    included_module = Module.objects.create(
        course=course,
        slug="included",
        title="Included",
        position=0,
        publication_status=Module.PublicationStatus.PUBLISHED,
    )
    excluded_module = Module.objects.create(
        course=course,
        slug="excluded",
        title="Excluded",
        position=1,
        publication_status=Module.PublicationStatus.PUBLISHED,
    )
    included_lesson = Lesson.objects.create(
        module=included_module,
        slug="included-lesson",
        title="Included Lesson",
        position=0,
        publication_status=Lesson.PublicationStatus.PUBLISHED,
    )
    excluded_lesson = Lesson.objects.create(
        module=excluded_module,
        slug="excluded-lesson",
        title="Excluded Lesson",
        position=0,
        publication_status=Lesson.PublicationStatus.PUBLISHED,
    )
    tariff = Tariff.objects.create(code="base", course=course, title="Base")
    TariffEntitlement.objects.create(
        tariff=tariff,
        code="included-module",
        title="Included module",
        entitlement_type=TariffEntitlement.EntitlementType.MODULE,
        module=included_module,
    )
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)

    included_decision = check_access(user_id=user.id, lesson_id=included_lesson.id)
    excluded_decision = check_access(user_id=user.id, lesson_id=excluded_lesson.id)

    assert included_decision.allowed is True
    assert included_decision.reason == "paid_access_grant"
    assert excluded_decision.allowed is False
    assert excluded_decision.reason == "not_in_tariff_entitlements"
