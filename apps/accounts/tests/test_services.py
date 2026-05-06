import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import LeadProfile
from apps.accounts.services import (
    assign_role,
    convert_lead_to_student,
    ensure_required_roles,
    user_has_role,
)


@pytest.mark.django_db
def test_required_roles_can_be_seeded_and_assigned() -> None:
    user = get_user_model().objects.create_user(username="student")

    roles = ensure_required_roles()
    assigned_role = assign_role(user.id, "student")

    assert {role.code for role in roles} >= {"super_admin", "student"}
    assert assigned_role.role.code == "student"
    assert user_has_role(user.id, ["student"])


@pytest.mark.django_db
def test_convert_lead_to_student_updates_role_and_lead_status() -> None:
    user = get_user_model().objects.create_user(username="lead")
    ensure_required_roles()
    assign_role(user.id, "lead")
    lead_profile = LeadProfile.objects.create(user=user, status=LeadProfile.Status.PREVIEW)

    converted_profile = convert_lead_to_student(user_id=user.id, reason="payment")

    assert converted_profile is not None
    lead_profile.refresh_from_db()
    assert lead_profile.status == LeadProfile.Status.CONVERTED
    assert lead_profile.metadata["converted_to_student"]["reason"] == "payment"
    assert user_has_role(user.id, ["student"])
