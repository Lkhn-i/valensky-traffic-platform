from django.urls import path

from . import views

app_name = "commerce"

urlpatterns = [
    path(
        "commerce/checkout/<str:tariff_code>/",
        views.checkout_placeholder,
        name="checkout_placeholder",
    ),
    path(
        "commerce/checkout/<str:tariff_code>/start/",
        views.checkout_start,
        name="checkout_start",
    ),
    path(
        "commerce/orders/<uuid:public_id>/",
        views.checkout_order,
        name="checkout_order",
    ),
    path("commerce/robokassa/success/", views.robokassa_success, name="robokassa_success"),
    path("commerce/robokassa/fail/", views.robokassa_fail, name="robokassa_fail"),
    path(
        "webhooks/payments/robokassa/result",
        views.robokassa_result_webhook,
        name="robokassa_result_webhook",
    ),
]
