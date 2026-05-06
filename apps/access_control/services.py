from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import LeadProfile
from apps.accounts.services import user_has_role
from apps.curriculum.models import Lesson

from .models import AccessGrant, Enrollment, PreviewAccessGrant, Tariff, TariffEntitlement


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    grant_id: int | None = None
    grant_type: str = ""


def _active_grant_window(now: datetime) -> Q:
    return Q(starts_at__lte=now) & (Q(expires_at__isnull=True) | Q(expires_at__gt=now))


def _is_lesson_zero(lesson: Lesson) -> bool:
    return lesson.module.position == 0 and lesson.position == 0


def active_paid_grants_for_user_course(*, user_id: int, course_id: int) -> QuerySet[AccessGrant]:
    now = timezone.now()
    return AccessGrant.objects.filter(
        _active_grant_window(now),
        user_id=user_id,
        course_id=course_id,
        status=AccessGrant.Status.ACTIVE,
        revoked_at__isnull=True,
    )


def _grant_allows_lesson(*, grant: AccessGrant, lesson: Lesson) -> bool:
    if grant.tariff_id is None:
        return True

    entitlements = TariffEntitlement.objects.filter(tariff_id=grant.tariff_id)
    if not entitlements.exists():
        return True

    return entitlements.filter(
        Q(
            entitlement_type=TariffEntitlement.EntitlementType.COURSE,
            course_id=lesson.module.course_id,
        )
        | Q(
            entitlement_type=TariffEntitlement.EntitlementType.MODULE,
            module_id=lesson.module_id,
        )
        | Q(
            entitlement_type=TariffEntitlement.EntitlementType.LESSON,
            lesson_id=lesson.id,
        )
    ).exists()


def active_preview_grants_for_user_lesson(
    *,
    user_id: int,
    lesson_id: int,
) -> QuerySet[PreviewAccessGrant]:
    now = timezone.now()
    return PreviewAccessGrant.objects.filter(
        starts_at__lte=now,
        expires_at__gt=now,
        user_id=user_id,
        lesson_id=lesson_id,
        status=PreviewAccessGrant.Status.ACTIVE,
        revoked_at__isnull=True,
    )


def check_access(*, user_id: int, lesson_id: int) -> AccessDecision:
    if user_has_role(user_id, ["super_admin", "admin", "manager"]):
        return AccessDecision(allowed=True, reason="staff_role")

    lesson = Lesson.objects.select_related("module", "module__course").get(id=lesson_id)
    if lesson.module.course.publication_status != "published":
        return AccessDecision(allowed=False, reason="course_unpublished")
    if lesson.module.publication_status != "published":
        return AccessDecision(allowed=False, reason="module_unpublished")
    if lesson.publication_status != "published":
        return AccessDecision(allowed=False, reason="lesson_unpublished")

    course_id = lesson.module.course_id

    paid_grants = active_paid_grants_for_user_course(user_id=user_id, course_id=course_id)
    has_paid_grant = False
    for paid_grant in paid_grants:
        has_paid_grant = True
        if _grant_allows_lesson(grant=paid_grant, lesson=lesson):
            return AccessDecision(
                allowed=True,
                reason="paid_access_grant",
                grant_id=paid_grant.id,
                grant_type="paid",
            )

    if _is_lesson_zero(lesson):
        preview_grant = active_preview_grants_for_user_lesson(
            user_id=user_id,
            lesson_id=lesson_id,
        ).first()
        if preview_grant is not None:
            return AccessDecision(
                allowed=True,
                reason="lesson0_preview_grant",
                grant_id=preview_grant.id,
                grant_type="preview",
            )

    if has_paid_grant:
        return AccessDecision(allowed=False, reason="not_in_tariff_entitlements")

    return AccessDecision(allowed=False, reason="missing_paid_access_grant")


@transaction.atomic
def grant_preview_access(
    *,
    lead_profile_id: int,
    course_id: int,
    lesson_id: int,
    expires_at: datetime,
    diagnostic_handoff_id: int | None = None,
) -> PreviewAccessGrant:
    lead_profile = LeadProfile.objects.select_related("user").get(id=lead_profile_id)
    lesson = Lesson.objects.select_related("module", "module__course").get(id=lesson_id)

    if lesson.module.course_id != course_id:
        raise ValueError("Пробный урок должен принадлежать выбранному курсу.")
    if not _is_lesson_zero(lesson):
        raise ValueError("Пробный доступ можно выдать только к Уроку 0.")
    if not user_has_role(lead_profile.user_id, ["lead"]):
        raise ValueError("Пробный доступ можно выдать только лиду.")

    grant, _created = PreviewAccessGrant.objects.update_or_create(
        lead_profile=lead_profile,
        lesson=lesson,
        defaults={
            "user": lead_profile.user,
            "course_id": course_id,
            "diagnostic_handoff_id": diagnostic_handoff_id,
            "status": PreviewAccessGrant.Status.ACTIVE,
            "starts_at": timezone.now(),
            "expires_at": expires_at,
            "consumed_at": None,
            "revoked_at": None,
        },
    )
    Enrollment.objects.update_or_create(
        user=lead_profile.user,
        course_id=course_id,
        defaults={
            "source": Enrollment.Source.PREVIEW,
            "status": Enrollment.Status.PREVIEW,
            "tariff": None,
        },
    )
    return grant


@transaction.atomic
def grant_paid_access(
    *,
    user_id: int,
    course_id: int,
    tariff_id: int,
    source: str = "payment",
    source_reference: str = "",
    starts_at: datetime | None = None,
    created_by_id: int | None = None,
) -> AccessGrant:
    if source_reference:
        grant, _created = grant_paid_access_once(
            user_id=user_id,
            course_id=course_id,
            tariff_id=tariff_id,
            source=source,
            source_reference=source_reference,
            starts_at=starts_at,
            created_by_id=created_by_id,
        )
        return grant

    starts_at = starts_at or timezone.now()
    tariff = Tariff.objects.get(id=tariff_id)
    expires_at = None
    if tariff.access_duration_days:
        expires_at = starts_at + timedelta(days=tariff.access_duration_days)

    grant = AccessGrant.objects.create(
        user_id=user_id,
        course_id=course_id,
        tariff=tariff,
        source=source,
        source_reference=source_reference,
        starts_at=starts_at,
        expires_at=expires_at,
        created_by_id=created_by_id,
    )
    Enrollment.objects.update_or_create(
        user_id=user_id,
        course_id=course_id,
        defaults={
            "tariff": tariff,
            "source": (
                Enrollment.Source.PAYMENT
                if source == "payment"
                else Enrollment.Source.MANUAL
            ),
            "status": Enrollment.Status.ACTIVE,
        },
    )
    return grant


@transaction.atomic
def grant_paid_access_once(
    *,
    user_id: int,
    course_id: int,
    tariff_id: int,
    source: str = "payment",
    source_reference: str,
    starts_at: datetime | None = None,
    created_by_id: int | None = None,
) -> tuple[AccessGrant, bool]:
    source_reference = source_reference.strip()
    if not source_reference:
        raise ValueError("Для идемпотентной выдачи платного доступа нужен source_reference.")

    starts_at = starts_at or timezone.now()
    tariff = Tariff.objects.get(id=tariff_id)
    existing_grant = (
        AccessGrant.objects.select_for_update()
        .filter(source=source, source_reference=source_reference)
        .first()
    )
    if existing_grant is not None:
        if (
            existing_grant.user_id != user_id
            or existing_grant.course_id != course_id
            or existing_grant.tariff_id != tariff_id
        ):
            raise ValueError(
                "Существующий source_reference платного доступа относится к другому доступу."
            )
        if (
            existing_grant.status == AccessGrant.Status.ACTIVE
            and existing_grant.revoked_at is None
        ):
            Enrollment.objects.update_or_create(
                user_id=user_id,
                course_id=course_id,
                defaults={
                    "tariff": tariff,
                    "source": (
                        Enrollment.Source.PAYMENT
                        if source == AccessGrant.Source.PAYMENT
                        else Enrollment.Source.MANUAL
                    ),
                    "status": Enrollment.Status.ACTIVE,
                },
            )
        return existing_grant, False

    expires_at = None
    if tariff.access_duration_days:
        expires_at = starts_at + timedelta(days=tariff.access_duration_days)

    grant = AccessGrant.objects.create(
        user_id=user_id,
        course_id=course_id,
        tariff=tariff,
        source=source,
        source_reference=source_reference,
        starts_at=starts_at,
        expires_at=expires_at,
        created_by_id=created_by_id,
    )
    Enrollment.objects.update_or_create(
        user_id=user_id,
        course_id=course_id,
        defaults={
            "tariff": tariff,
            "source": (
                Enrollment.Source.PAYMENT
                if source == AccessGrant.Source.PAYMENT
                else Enrollment.Source.MANUAL
            ),
            "status": Enrollment.Status.ACTIVE,
        },
    )
    return grant, True


@transaction.atomic
def revoke_access_grant(
    *,
    grant_id: int,
    reason: str,
    revoked_by_id: int | None = None,
) -> AccessGrant:
    reason = reason.strip()
    if not reason:
        raise ValueError("Для отзыва доступа нужна причина.")

    grant = AccessGrant.objects.select_for_update().get(id=grant_id)
    if grant.status != AccessGrant.Status.REVOKED:
        grant.status = AccessGrant.Status.REVOKED
        grant.revoked_at = timezone.now()
    grant.reason = reason
    metadata = dict(grant.metadata)
    metadata["revocation"] = {
        "reason": reason,
        "revoked_by_id": revoked_by_id,
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else "",
    }
    grant.metadata = metadata
    grant.save(update_fields=["status", "revoked_at", "reason", "metadata", "updated_at"])

    has_other_active_grants = (
        AccessGrant.objects.filter(
            _active_grant_window(timezone.now()),
            user_id=grant.user_id,
            course_id=grant.course_id,
            status=AccessGrant.Status.ACTIVE,
            revoked_at__isnull=True,
        )
        .exclude(id=grant.id)
        .exists()
    )
    if not has_other_active_grants:
        Enrollment.objects.filter(
            user_id=grant.user_id,
            course_id=grant.course_id,
            status=Enrollment.Status.ACTIVE,
        ).update(status=Enrollment.Status.CANCELED)
    return grant
