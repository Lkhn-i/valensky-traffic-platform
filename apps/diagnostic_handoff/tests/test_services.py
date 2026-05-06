from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import LeadProfile
from apps.diagnostic_handoff.services import create_diagnostic_handoff, resolve_handoff_for_lead


@pytest.mark.django_db
def test_diagnostic_handoff_resolve_is_replay_safe() -> None:
    user = get_user_model().objects.create_user(username="lead")
    lead = LeadProfile.objects.create(user=user)
    handoff = create_diagnostic_handoff(
        source="diagnostic_site",
        external_session_id="session-1",
        raw_token="secret-token",
        expires_at=timezone.now() + timedelta(hours=1),
        diagnostic_segment="warm",
    )

    first_resolution = resolve_handoff_for_lead(raw_token="secret-token", lead_profile_id=lead.id)
    replay_resolution = resolve_handoff_for_lead(raw_token="secret-token", lead_profile_id=lead.id)

    handoff.refresh_from_db()
    assert first_resolution.was_replay is False
    assert replay_resolution.was_replay is True
    assert handoff.status == "resolved"
    assert handoff.lead_profile == lead
    assert handoff.replay_count == 1
