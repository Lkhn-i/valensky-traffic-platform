from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.curriculum.models import Lesson
from apps.curriculum.services import ensure_stage3_preview_course
from apps.events.services import ORMAnalyticsEventService

from .services import (
    create_simulated_diagnostic_handoff,
    resolve_handoff_to_preview_access,
)

PREVIEW_TTL_DAYS = 3


def _lesson0_for_stage3_course() -> Lesson:
    course = ensure_stage3_preview_course()
    return Lesson.objects.select_related("module", "module__course").get(
        module__course=course,
        module__position=0,
        position=0,
    )


@never_cache
def public_preview_entry(request: HttpRequest) -> HttpResponse:
    lesson0 = _lesson0_for_stage3_course()
    preview_path = reverse(
        "curriculum:course_preview",
        kwargs={"course_slug": lesson0.module.course.slug},
    )
    query_string = request.META.get("QUERY_STRING", "")
    if query_string:
        preview_path = f"{preview_path}?{query_string}"
    return redirect(preview_path)


@never_cache
def simulate_diagnostic_submit(request: HttpRequest) -> HttpResponse:
    if settings.ENV_NAME == "production":
        raise Http404("Симуляция входа из диагностики отключена в production.")

    lesson0 = _lesson0_for_stage3_course()
    handoff, raw_token = create_simulated_diagnostic_handoff()
    ORMAnalyticsEventService().record_event(
        name="diagnostic_handoff_created",
        source_app="diagnostic_handoff",
        session_identifier=handoff.external_session_id,
        object_type="diagnostic_handoff",
        object_key=str(handoff.id),
        properties={"course_slug": lesson0.module.course.slug},
    )
    return redirect("diagnostic_handoff:preview_entry", token=raw_token)


@never_cache
def preview_entry(request: HttpRequest, token: str) -> HttpResponse:
    lesson0 = _lesson0_for_stage3_course()
    course = lesson0.module.course
    redirect_path = reverse("curriculum:course_preview", kwargs={"course_slug": course.slug})
    resolution = resolve_handoff_to_preview_access(
        raw_token=token,
        course_id=course.id,
        lesson0_id=lesson0.id,
        preview_expires_at=timezone.now() + timedelta(days=PREVIEW_TTL_DAYS),
        redirect_path=redirect_path,
    )

    if resolution.status == "replayed":
        if (
            request.user.is_authenticated
            and resolution.handoff.user_id is not None
            and request.user.id == resolution.handoff.user_id
        ):
            return redirect(redirect_path)
        return render(
            request,
            "diagnostic_handoff/error.html",
            {"status": "replayed"},
            status=410,
        )

    if not resolution.is_resolved or resolution.lead_profile is None:
        return render(
            request,
            "diagnostic_handoff/error.html",
            {"status": resolution.status},
            status=404 if resolution.status == "missing" else 410,
        )

    login(
        request,
        resolution.lead_profile.user,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    if resolution.created_lead:
        ORMAnalyticsEventService().record_event(
            name="lead_created",
            source_app="diagnostic_handoff",
            actor_identifier=str(resolution.lead_profile.user_id),
            session_identifier=resolution.handoff.external_session_id,
            object_type="lead_profile",
            object_key=str(resolution.lead_profile.id),
            properties={"diagnostic_segment": resolution.handoff.diagnostic_segment},
        )
    return redirect(redirect_path)
