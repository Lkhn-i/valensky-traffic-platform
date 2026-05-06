from __future__ import annotations

import hashlib
from collections.abc import Iterable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import LeadProfile, Role, UserRole, UserTelegramIdentity

REQUIRED_ROLE_CODES = (
    "super_admin",
    "admin",
    "manager",
    "student",
    "lead",
    "system",
)


@transaction.atomic
def ensure_required_roles() -> list[Role]:
    roles: list[Role] = []
    for code in REQUIRED_ROLE_CODES:
        role, _created = Role.objects.get_or_create(
            code=code,
            defaults={"title": Role.Code(code).label},
        )
        roles.append(role)
    return roles


def user_has_role(user_id: int, role_codes: Iterable[str]) -> bool:
    return UserRole.objects.filter(user_id=user_id, role__code__in=tuple(role_codes)).exists()


@transaction.atomic
def assign_role(user_id: int, role_code: str, *, granted_by_id: int | None = None) -> UserRole:
    role = Role.objects.get(code=role_code)
    user_model = get_user_model()
    user_model.objects.only("id").get(id=user_id)
    if granted_by_id is not None:
        user_model.objects.only("id").get(id=granted_by_id)
    user_role, _created = UserRole.objects.get_or_create(
        user_id=user_id,
        role=role,
        defaults={"granted_by_id": granted_by_id},
    )
    return user_role


@transaction.atomic
def get_or_create_lead_from_diagnostic(
    *,
    external_session_id: str,
    diagnostic_segment: str = "",
    source: str = "diagnostic_site",
    telegram_id: int | None = None,
) -> tuple[LeadProfile, bool]:
    ensure_required_roles()
    user_model = get_user_model()
    existing_lead = (
        LeadProfile.objects.select_related("user")
        .filter(diagnostic_session_id=external_session_id, source=source)
        .first()
    )
    if existing_lead is not None:
        assign_role(existing_lead.user_id, "lead")
        return existing_lead, False

    username_seed = f"{source}:{external_session_id}".encode("utf-8")
    username_hash = hashlib.sha256(username_seed).hexdigest()[:16]
    user = user_model.objects.create_user(
        username=f"lead_{username_hash}",
        display_name="Диагностический лид",
    )
    lead_profile = LeadProfile.objects.create(
        user=user,
        status=LeadProfile.Status.PREVIEW,
        source=source,
        diagnostic_session_id=external_session_id,
        diagnostic_segment=diagnostic_segment,
    )
    assign_role(user.id, "lead")
    if telegram_id is not None:
        UserTelegramIdentity.objects.update_or_create(
            telegram_id=telegram_id,
            defaults={"user": user},
        )
    return lead_profile, True


@transaction.atomic
def convert_lead_to_student(
    *,
    user_id: int,
    reason: str = "payment",
    granted_by_id: int | None = None,
) -> LeadProfile | None:
    ensure_required_roles()
    assign_role(user_id, "student", granted_by_id=granted_by_id)

    lead_profile = LeadProfile.objects.select_for_update().filter(user_id=user_id).first()
    if lead_profile is None:
        return None

    if lead_profile.status != LeadProfile.Status.CONVERTED:
        lead_profile.status = LeadProfile.Status.CONVERTED
    metadata = dict(lead_profile.metadata)
    metadata["converted_to_student"] = {
        "reason": reason,
        "converted_at": timezone.now().isoformat(),
    }
    lead_profile.metadata = metadata
    lead_profile.save(update_fields=["status", "metadata", "updated_at"])
    return lead_profile
