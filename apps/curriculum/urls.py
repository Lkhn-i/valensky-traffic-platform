from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver

from . import views

app_name = "curriculum"
urlpatterns: list[URLPattern | URLResolver] = [
    path("", views.learner_dashboard, name="learner_dashboard"),
    path("courses/<slug:course_slug>/", views.course_preview, name="course_preview"),
    path("modules/<int:module_id>/", views.module_detail, name="module_detail"),
    path("modules/<int:module_id>/complete/", views.module_complete, name="module_complete"),
    path("playback/tickets/status/", views.playback_ticket_status, name="playback_ticket_status"),
    path("lessons/<int:lesson_id>/", views.lesson_detail, name="lesson_detail"),
    path("lessons/<int:lesson_id>/materials/", views.lesson_materials, name="lesson_materials"),
    path(
        "lessons/<int:lesson_id>/homework/",
        views.lesson_homework_submit,
        name="lesson_homework_submit",
    ),
    path("lessons/<int:lesson_id>/complete/", views.lesson_complete, name="lesson_complete"),
    path("lessons/<int:lesson_id>/playback/", views.lesson_playback, name="lesson_playback"),
    path(
        "lessons/<int:lesson_id>/video-events/",
        views.lesson_video_event,
        name="lesson_video_event",
    ),
]
