from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.diagnostic_handoff import views as diagnostic_handoff_views

admin.site.site_header = "Администрирование платформы обучения"
admin.site.site_title = "Платформа обучения"
admin.site.index_title = "Панель управления"

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        RedirectView.as_view(pattern_name="accounts:login"),
        name="legacy_login",
    ),
    path(
        "accounts/logout/",
        RedirectView.as_view(pattern_name="accounts:logout"),
        name="legacy_logout",
    ),
    path("preview/", diagnostic_handoff_views.public_preview_entry, name="public_preview"),
    path("", include("apps.accounts.urls")),
    path("diagnostic/", include("apps.diagnostic_handoff.urls")),
    path("learn/", include("apps.curriculum.urls")),
    path("protected-resources/", include("apps.resources.urls")),
    path("media-library/", include("apps.media_library.urls")),
    path("operator/", include("apps.operator.urls")),
    path("", include("apps.commerce.urls")),
    path("", include("apps.shared.urls")),
]
