from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver

from . import views

app_name = "resources"
urlpatterns: list[URLPattern | URLResolver] = [
    path(
        "lessons/<int:lesson_id>/<slug:resource_slug>/",
        views.protected_lesson_resource,
        name="protected_lesson_resource",
    ),
]
