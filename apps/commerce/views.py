from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotFound,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.access_control.models import Tariff

from .models import Order
from .services import (
    RobokassaPaymentProvider,
    create_checkout_placeholder,
    process_robokassa_callback,
    record_checkout_return,
)

_ORDER_STATUS_LABELS = {
    Order.Status.CREATED: "Создан",
    Order.Status.PENDING: "Ожидает подтверждения",
    Order.Status.PAID: "Оплачен",
    Order.Status.FAILED: "Не оплачен",
    Order.Status.REFUNDED: "Возвращён",
    Order.Status.DISPUTED: "На проверке",
}


def _active_tariff_or_404(tariff_code: str) -> Tariff:
    return get_object_or_404(
        Tariff.objects.select_related("course"),
        code=tariff_code,
        course__isnull=False,
        is_active=True,
    )


def _request_payload(request: HttpRequest) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        if not request.body:
            return {}
        parsed_payload = json.loads(request.body.decode("utf-8"))
        if not isinstance(parsed_payload, dict):
            raise ValueError("JSON payload должен быть объектом.")
        return parsed_payload
    source = request.POST if request.method == "POST" else request.GET
    return {key: value for key, value in source.items()}


def _order_number_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("InvId") or payload.get("order_number") or "").strip()


@login_required
@require_POST
def checkout_placeholder(request: HttpRequest, tariff_code: str) -> JsonResponse:
    tariff = _active_tariff_or_404(tariff_code)
    checkout = create_checkout_placeholder(
        user_id=request.user.id,
        tariff_id=tariff.id,
        return_path="/learn/",
        metadata={"source": "stage6_checkout_placeholder"},
    )
    return JsonResponse(
        {
            "provider_code": checkout.provider_code.value,
            "order_id": checkout.order_id,
            "order_number": checkout.order_number,
            "tariff_code": checkout.tariff_code,
            "status": checkout.status,
            "return_path": checkout.return_path,
            "is_live_mode": checkout.is_live_mode,
            "metadata": dict(checkout.metadata),
        },
        status=201,
    )


@login_required
@require_POST
def checkout_start(request: HttpRequest, tariff_code: str) -> HttpResponseRedirect:
    tariff = _active_tariff_or_404(tariff_code)
    checkout = create_checkout_placeholder(
        user_id=request.user.id,
        tariff_id=tariff.id,
        return_path=reverse(
            "curriculum:course_preview",
            kwargs={"course_slug": tariff.course.slug},
        ),
        metadata={"source": "checkout_start_placeholder"},
    )
    order = get_object_or_404(
        Order.objects.only("public_id", "user_id"),
        id=checkout.order_id,
        user_id=request.user.id,
    )
    return redirect("commerce:checkout_order", public_id=order.public_id)


@login_required
@require_GET
def checkout_order(request: HttpRequest, public_id: str) -> HttpResponse:
    order = get_object_or_404(
        Order.objects.select_related("course", "tariff"),
        public_id=public_id,
        user_id=request.user.id,
    )
    return render(
        request,
        "commerce/checkout_placeholder.html",
        {
            "order": order,
            "provider_name": "Robokassa",
            "status_label": _ORDER_STATUS_LABELS.get(order.status, order.status),
        },
    )


@require_GET
def robokassa_success(request: HttpRequest) -> HttpResponse:
    payload = _request_payload(request)
    order_number = _order_number_from_payload(payload)
    if not order_number:
        return HttpResponseBadRequest("Не передан номер заказа.")
    try:
        order = record_checkout_return(order_number=order_number, payload=payload)
    except Order.DoesNotExist:
        return HttpResponseNotFound("Заказ не найден.")
    return HttpResponseRedirect(order.return_path or "/learn/")


@require_GET
def robokassa_fail(request: HttpRequest) -> HttpResponse:
    return HttpResponseRedirect("/learn/")


@csrf_exempt
@require_POST
def robokassa_result_webhook(request: HttpRequest) -> HttpResponse:
    if settings.ENV_NAME == "production":
        return HttpResponseNotFound("Платёжный webhook отключён.")

    try:
        payload = _request_payload(request)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return JsonResponse({"error": "invalid_payload"}, status=400)

    provider = RobokassaPaymentProvider()
    signature_valid = provider.verify_callback_signature(payload=payload)
    try:
        result = process_robokassa_callback(
            payload=payload,
            signature_valid=signature_valid,
        )
    except Order.DoesNotExist:
        return JsonResponse({"error": "order_not_found"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {
            "order_id": result.order_id,
            "order_status": result.order_status,
            "event_id": result.event_id,
            "event_status": result.event_status,
            "processing_result": result.processing_result,
            "grant_created": result.grant_created,
            "access_grant_id": result.access_grant_id,
        }
    )
