from django.urls import path

from . import views

app_name = "operator"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("content/", views.content, name="content"),
    path("learners/", views.learners, name="learners"),
    path("learners/<int:user_id>/", views.learner_detail, name="learner_detail"),
    path(
        "learners/<int:user_id>/resend-access-link/",
        views.resend_access_link,
        name="resend_access_link",
    ),
    path("homework/", views.homework_queue, name="homework_queue"),
    path(
        "homework/submissions/<int:submission_id>/review/",
        views.review_homework,
        name="review_homework",
    ),
    path("orders/", views.orders, name="orders"),
    path("audit/", views.audit, name="audit"),
]
