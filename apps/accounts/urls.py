from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver

from . import views

app_name = "accounts"
urlpatterns: list[URLPattern | URLResolver] = [
    path("login/", views.ChalkboardLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
]
