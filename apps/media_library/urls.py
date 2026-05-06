from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver

from . import views

app_name = "media_library"
urlpatterns: list[URLPattern | URLResolver] = [
    path("playback/<int:ticket_id>/stream", views.local_playback_stream, name="local_stream"),
]
