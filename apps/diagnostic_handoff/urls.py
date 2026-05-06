from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver

from . import views

app_name = "diagnostic_handoff"
urlpatterns: list[URLPattern | URLResolver] = [
    path("preview/", views.public_preview_entry, name="public_preview_entry"),
    path("preview/simulate/", views.simulate_diagnostic_submit, name="simulate_submit"),
    path("preview/<str:token>/", views.preview_entry, name="preview_entry"),
]
