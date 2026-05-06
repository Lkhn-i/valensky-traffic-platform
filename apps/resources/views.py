from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET

from apps.curriculum.models import Lesson

from .services import (
    ORMProtectedLessonResourceService,
    ProtectedLessonResourceAccessDenied,
    ProtectedLessonResourceNotFound,
)


@login_required
@require_GET
def protected_lesson_resource(
    request: HttpRequest,
    lesson_id: int,
    resource_slug: str,
) -> HttpResponse:
    try:
        protected_resource = ORMProtectedLessonResourceService().resolve_for_user(
            user_id=request.user.id,
            lesson_id=lesson_id,
            resource_slug=resource_slug,
        )
    except Lesson.DoesNotExist as exc:
        raise Http404("Урок не найден.") from exc
    except ProtectedLessonResourceNotFound as exc:
        raise Http404(str(exc)) from exc
    except ProtectedLessonResourceAccessDenied as exc:
        return HttpResponseForbidden(f"Материал недоступен: {exc.reason}")

    resource = protected_resource.resource
    if resource.source_url:
        response = HttpResponse(status=302)
        response["Location"] = resource.source_url
        return response

    if resource.download_key:
        return HttpResponse(
            (
                "Заглушка защищённой загрузки\n"
                f"Материал: {resource.title}\n"
                "Файл будет выдан через серверную загрузку без раскрытия ключа хранения.\n"
            ),
            content_type="text/plain; charset=utf-8",
        )

    raise Http404("Материал не содержит доступного источника.")
