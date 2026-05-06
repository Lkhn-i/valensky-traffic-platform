from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.access_control.models import AccessGrant, Tariff
from apps.access_control.services import grant_paid_access, revoke_access_grant
from apps.accounts.services import convert_lead_to_student
from apps.events.services import ORMAuditLogService
from apps.integrations.services import enqueue_bot_outbox_from_notification
from apps.notifications.services import TELEGRAM_CHANNEL, enqueue_paid_access_notification

from .models import Order, PaymentEvent


class PaymentProviderCode(StrEnum):
    ROBO_KASSA = "robokassa"

_TWO_PLACES = Decimal("0.01")
_STATUS_CREATED = str(Order.Status.CREATED)
_STATUS_PENDING = str(Order.Status.PENDING)
_STATUS_PAID = str(Order.Status.PAID)
_STATUS_FAILED = str(Order.Status.FAILED)
_STATUS_REFUNDED = str(Order.Status.REFUNDED)
_STATUS_DISPUTED = str(Order.Status.DISPUTED)
_VALID_ORDER_STATUSES = frozenset(
    {
        _STATUS_CREATED,
        _STATUS_PENDING,
        _STATUS_PAID,
        _STATUS_FAILED,
        _STATUS_REFUNDED,
        _STATUS_DISPUTED,
    }
)


@dataclass(frozen=True)
class CheckoutPlaceholder:
    provider_code: PaymentProviderCode
    order_id: int | None
    order_number: str
    tariff_code: str
    status: str
    return_path: str
    is_live_mode: bool
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class NormalizedPaymentEvent:
    provider_code: PaymentProviderCode
    order_number: str
    status: str
    amount: Decimal
    currency: str
    dedupe_key: str
    provider_event_id: str = ""
    provider_payment_id: str = ""
    signature_valid: bool = False
    is_valid: bool = True
    invalid_reason: str = ""
    occurred_at: datetime | None = None
    raw_payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentProcessingResult:
    order_id: int
    order_status: str
    event_id: int
    event_status: str
    processing_result: str
    grant_created: bool
    access_grant_id: int | None


@dataclass(frozen=True)
class AccessRevocationResult:
    order_id: int
    order_status: str
    payment_event_id: int
    access_grant_id: int | None
    access_revoked: bool


class PaymentProvider(Protocol):
    code: PaymentProviderCode
    is_enabled: bool

    def create_checkout(
        self,
        *,
        order: Order,
        metadata: Mapping[str, Any] | None = None,
    ) -> CheckoutPlaceholder: ...

    def normalize_callback(
        self,
        *,
        payload: Mapping[str, Any],
        signature_valid: bool = False,
    ) -> NormalizedPaymentEvent: ...

    def verify_callback_signature(self, *, payload: Mapping[str, Any]) -> bool: ...


def _quantize_money(amount: Decimal) -> Decimal:
    return amount.quantize(_TWO_PLACES)


def _coerce_decimal(value: Any) -> Decimal:
    try:
        return _quantize_money(Decimal(str(value)))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Неподдерживаемая сумма платежа: {value!r}") from exc


def _normalize_order_status(value: str) -> str:
    normalized_value = value.strip().lower()
    if normalized_value not in _VALID_ORDER_STATUSES:
        raise ValueError(f"Неподдерживаемый статус платежа: {value!r}")
    return normalized_value


def _build_event_dedupe_key(
    *,
    provider_code: PaymentProviderCode,
    order_number: str,
    status: str,
    amount: Decimal,
    currency: str,
    provider_event_id: str,
    provider_payment_id: str,
) -> str:
    if provider_event_id:
        return f"{provider_code}:{provider_event_id}"
    if provider_payment_id:
        return f"{provider_code}:{provider_payment_id}:{status}"
    normalized_amount = _quantize_money(amount)
    return f"{provider_code}:{order_number}:{status}:{normalized_amount}:{currency}"


def build_checkout_placeholder(
    *,
    tariff_code: str,
    return_path: str,
    metadata: Mapping[str, Any] | None = None,
) -> CheckoutPlaceholder:
    return CheckoutPlaceholder(
        provider_code=PaymentProviderCode.ROBO_KASSA,
        order_id=None,
        order_number="",
        tariff_code=tariff_code,
        status=_STATUS_CREATED,
        return_path=return_path,
        is_live_mode=False,
        metadata=dict(metadata or {}),
    )


class RobokassaPaymentProvider:
    code = PaymentProviderCode.ROBO_KASSA
    is_enabled = False
    stage6_valid_signature = "stage6-valid"

    def create_checkout(
        self,
        *,
        order: Order,
        metadata: Mapping[str, Any] | None = None,
    ) -> CheckoutPlaceholder:
        checkout_metadata = dict(metadata or {})
        checkout_metadata["provider_enabled"] = self.is_enabled
        checkout_metadata["order_public_id"] = str(order.public_id)
        checkout_metadata["provider_name"] = "robokassa"
        return CheckoutPlaceholder(
            provider_code=self.code,
            order_id=order.id,
            order_number=order.number,
            tariff_code=order.tariff.code,
            status=order.status,
            return_path=order.return_path,
            is_live_mode=False,
            metadata=checkout_metadata,
        )

    def normalize_callback(
        self,
        *,
        payload: Mapping[str, Any],
        signature_valid: bool = False,
    ) -> NormalizedPaymentEvent:
        order_number = str(
            payload.get("InvId")
            or payload.get("order_number")
            or payload.get("invoice_id")
            or ""
        ).strip()
        if not order_number:
            raise ValueError("Callback Robokassa должен содержать идентификатор заказа.")

        invalid_reason = ""
        raw_status = str(payload.get("status") or _STATUS_PENDING)
        try:
            status = _normalize_order_status(raw_status)
        except ValueError as exc:
            status = _STATUS_FAILED
            invalid_reason = str(exc)

        raw_amount = payload.get("OutSum", payload.get("amount", "0.00"))
        try:
            amount = _coerce_decimal(raw_amount)
        except ValueError as exc:
            amount = Decimal("0.00")
            invalid_reason = str(exc) if not invalid_reason else f"{invalid_reason}; {exc}"

        currency = str(payload.get("currency") or "RUB").upper()
        provider_event_id = str(
            payload.get("event_id") or payload.get("notification_id") or ""
        ).strip()
        provider_payment_id = str(payload.get("payment_id") or payload.get("OpKey") or "").strip()
        dedupe_key = str(
            payload.get("dedupe_key")
            or _build_event_dedupe_key(
                provider_code=self.code,
                order_number=order_number,
                status=status,
                amount=amount,
                currency=currency,
                provider_event_id=provider_event_id,
                provider_payment_id=provider_payment_id,
            )
        ).strip()

        return NormalizedPaymentEvent(
            provider_code=self.code,
            order_number=order_number,
            status=status,
            amount=amount,
            currency=currency,
            dedupe_key=dedupe_key,
            provider_event_id=provider_event_id,
            provider_payment_id=provider_payment_id,
            signature_valid=signature_valid,
            is_valid=not invalid_reason,
            invalid_reason=invalid_reason,
            raw_payload=dict(payload),
        )

    def verify_callback_signature(self, *, payload: Mapping[str, Any]) -> bool:
        signature_value = str(
            payload.get("SignatureValue") or payload.get("signature") or ""
        ).strip()
        return signature_value == self.stage6_valid_signature


def get_payment_provider(
    provider_code: PaymentProviderCode = PaymentProviderCode.ROBO_KASSA,
) -> PaymentProvider:
    if provider_code == PaymentProviderCode.ROBO_KASSA:
        return RobokassaPaymentProvider()
    raise ValueError(f"Неподдерживаемый платёжный провайдер: {provider_code}")


def _build_order_number() -> str:
    return f"ord_{uuid4().hex[:12]}"


@transaction.atomic
def create_checkout_placeholder(
    *,
    user_id: int,
    tariff_id: int,
    return_path: str,
    provider_code: PaymentProviderCode = PaymentProviderCode.ROBO_KASSA,
    metadata: Mapping[str, Any] | None = None,
) -> CheckoutPlaceholder:
    provider = get_payment_provider(provider_code)
    user_model = get_user_model()
    user_model.objects.only("id").get(id=user_id)
    tariff = Tariff.objects.select_related("course").get(id=tariff_id)
    if tariff.course_id is None:
        raise ValueError("Перед созданием заказа тариф должен быть привязан к курсу.")

    order = Order.objects.create(
        number=_build_order_number(),
        provider_code=provider.code.value,
        user_id=user_id,
        course_id=tariff.course_id,
        tariff=tariff,
        status=_STATUS_CREATED,
        amount=tariff.price_amount,
        currency=tariff.currency,
        return_path=return_path,
        metadata=dict(metadata or {}),
    )
    return provider.create_checkout(order=order, metadata=metadata)


@transaction.atomic
def record_checkout_return(
    *,
    order_number: str,
    payload: Mapping[str, Any] | None = None,
) -> Order:
    order = Order.objects.select_for_update().get(number=order_number)
    metadata = dict(order.metadata)
    if payload:
        metadata["last_success_return_payload"] = dict(payload)
        order.metadata = metadata
    if order.status == _STATUS_CREATED:
        order.status = _STATUS_PENDING
    order.success_returned_at = timezone.now()

    update_fields = ["success_returned_at", "status", "updated_at"]
    if payload:
        update_fields.append("metadata")
    order.save(update_fields=update_fields)
    return order


def _apply_order_status_from_event(*, order: Order, status: str, processed_at: datetime) -> None:
    if status == _STATUS_PENDING and order.status == _STATUS_CREATED:
        order.status = _STATUS_PENDING
        return

    if status == _STATUS_FAILED:
        if order.status in {
            _STATUS_CREATED,
            _STATUS_PENDING,
            _STATUS_FAILED,
        }:
            order.status = _STATUS_FAILED
            if order.failed_at is None:
                order.failed_at = processed_at
        return

    if status == _STATUS_PAID:
        if order.status not in {_STATUS_REFUNDED, _STATUS_DISPUTED}:
            order.status = _STATUS_PAID
        if order.paid_at is None:
            order.paid_at = processed_at
        return

    if status == _STATUS_REFUNDED:
        order.status = _STATUS_REFUNDED
        if order.refunded_at is None:
            order.refunded_at = processed_at
        return

    if status == _STATUS_DISPUTED:
        order.status = _STATUS_DISPUTED
        if order.disputed_at is None:
            order.disputed_at = processed_at


def _grant_order_access(*, order: Order, processed_at: datetime) -> None:
    if order.access_grant_id is not None:
        return

    access_grant = grant_paid_access(
        user_id=order.user_id,
        course_id=order.course_id,
        tariff_id=order.tariff_id,
        source_reference=order.number,
    )
    convert_lead_to_student(user_id=order.user_id, reason="payment")
    order.access_grant = access_grant
    order.access_granted_at = processed_at


def _learning_access_path(*, return_path: str) -> str:
    return return_path if return_path.startswith("/learn") else "/learn/"


def _queue_paid_access_message(
    *,
    user_id: int,
    order_id: int,
    order_number: str,
    access_grant_id: int,
    access_path: str,
    course_id: int,
    tariff_code: str,
) -> None:
    notification_job = enqueue_paid_access_notification(
        user_id=user_id,
        order_number=order_number,
        access_path=access_path,
        channel=TELEGRAM_CHANNEL,
        payload={
            "order_id": order_id,
            "access_grant_id": access_grant_id,
            "course_id": course_id,
            "tariff_code": tariff_code,
        },
        dedupe_key=f"paid-access:{order_number}:{access_grant_id}",
    )
    enqueue_bot_outbox_from_notification(
        notification_job_id=notification_job.id,
        template_key=notification_job.template_key,
        idempotency_key=f"bot:paid-access:{order_number}:{access_grant_id}",
        event_type="paid_access.granted",
        user_id=user_id,
        payload={
            "order_id": order_id,
            "order_number": order_number,
            "access_grant_id": access_grant_id,
            "access_path": access_path,
            "course_id": course_id,
            "tariff_code": tariff_code,
        },
    )


def _build_processing_result(
    *,
    order: Order,
    payment_event: PaymentEvent,
    grant_created: bool,
) -> PaymentProcessingResult:
    return PaymentProcessingResult(
        order_id=order.id,
        order_status=order.status,
        event_id=payment_event.id,
        event_status=payment_event.status,
        processing_result=payment_event.processing_result,
        grant_created=grant_created,
        access_grant_id=order.access_grant_id,
    )


@transaction.atomic
def process_payment_event(*, event: NormalizedPaymentEvent) -> PaymentProcessingResult:
    order = (
        Order.objects.select_for_update()
        .select_related("tariff", "access_grant")
        .get(number=event.order_number)
    )
    processed_at = timezone.now()
    signature_status = (
        PaymentEvent.SignatureStatus.VALID
        if event.signature_valid
        else PaymentEvent.SignatureStatus.INVALID
    )
    payment_event, created = PaymentEvent.objects.get_or_create(
        order=order,
        dedupe_key=event.dedupe_key,
        defaults={
            "provider_code": event.provider_code.value,
            "status": event.status,
            "provider_event_id": event.provider_event_id,
            "provider_payment_id": event.provider_payment_id,
            "amount": event.amount,
            "currency": event.currency,
            "signature_status": signature_status,
            "is_valid": event.is_valid,
            "invalid_reason": event.invalid_reason,
            "occurred_at": event.occurred_at,
            "payload": dict(event.raw_payload),
        },
    )
    if not created and payment_event.processed_at is not None:
        return _build_processing_result(
            order=order,
            payment_event=payment_event,
            grant_created=False,
        )

    payment_event.provider_code = event.provider_code.value
    payment_event.status = event.status
    payment_event.provider_event_id = event.provider_event_id
    payment_event.provider_payment_id = event.provider_payment_id
    payment_event.amount = event.amount
    payment_event.currency = event.currency
    payment_event.signature_status = signature_status
    payment_event.is_valid = event.is_valid
    payment_event.invalid_reason = event.invalid_reason
    payment_event.occurred_at = event.occurred_at
    payment_event.payload = dict(event.raw_payload)
    payment_event.processed_at = processed_at

    order.last_event_at = event.occurred_at or processed_at
    if event.provider_payment_id:
        order.provider_payment_id = event.provider_payment_id

    grant_created = False
    payment_event.processing_result = "recorded"

    if order.provider_code != event.provider_code.value:
        payment_event.is_valid = False
        payment_event.invalid_reason = "Код платёжного провайдера не совпал."
        payment_event.processing_result = "provider_mismatch"
    elif not event.signature_valid:
        payment_event.is_valid = False
        if not payment_event.invalid_reason:
            payment_event.invalid_reason = "Проверка подписи не прошла."
        payment_event.processing_result = "invalid_signature"
    elif not event.is_valid:
        payment_event.processing_result = "invalid_event"
    elif event.amount != _quantize_money(order.amount) or event.currency != order.currency:
        payment_event.is_valid = False
        payment_event.invalid_reason = "Сумма или валюта не совпали."
        payment_event.processing_result = "amount_or_currency_mismatch"
    else:
        _apply_order_status_from_event(order=order, status=event.status, processed_at=processed_at)
        if event.status == _STATUS_PAID:
            previous_access_grant_id = order.access_grant_id
            _grant_order_access(order=order, processed_at=processed_at)
            grant_created = previous_access_grant_id is None and order.access_grant_id is not None
            payment_event.processing_result = (
                "paid_access_granted" if grant_created else "paid_already_granted"
            )
        elif event.status == _STATUS_PENDING:
            payment_event.processing_result = "payment_pending"
        elif event.status == _STATUS_FAILED:
            payment_event.processing_result = "payment_failed"
        elif event.status == _STATUS_REFUNDED:
            # Refunds are recorded for finance reconciliation only.
            payment_event.processing_result = "refund_recorded"
        elif event.status == _STATUS_DISPUTED:
            payment_event.processing_result = "dispute_recorded"

    payment_event.save()
    order.save()
    if grant_created and order.access_grant_id is not None:
        transaction.on_commit(
            lambda: _queue_paid_access_message(
                user_id=order.user_id,
                order_id=order.id,
                order_number=order.number,
                access_grant_id=order.access_grant_id or 0,
                access_path=_learning_access_path(return_path=order.return_path),
                course_id=order.course_id,
                tariff_code=order.tariff.code,
            )
        )
    return _build_processing_result(
        order=order,
        payment_event=payment_event,
        grant_created=grant_created,
    )


def process_robokassa_callback(
    *,
    payload: Mapping[str, Any],
    signature_valid: bool = False,
) -> PaymentProcessingResult:
    provider = RobokassaPaymentProvider()
    event = provider.normalize_callback(payload=payload, signature_valid=signature_valid)
    return process_payment_event(event=event)


def _ensure_non_production_manual_payment_action() -> None:
    if settings.ENV_NAME == "production":
        raise PermissionError("Ручные действия с оплатой отключены в production.")


def _record_commerce_audit(
    *,
    action: str,
    result: str,
    actor_user_id: int | None,
    order: Order,
    message: str,
    payload: Mapping[str, Any] | None = None,
) -> None:
    ORMAuditLogService().record_log(
        action=action,
        result=result,
        actor_identifier=str(actor_user_id or ""),
        target_type="commerce.Order",
        target_key=order.number,
        message=message,
        payload=dict(payload or {}),
    )


def _get_existing_order_for_manual_action(*, order_id: int, actor_user_id: int | None) -> Order:
    user_model = get_user_model()
    if actor_user_id is not None:
        user_model.objects.only("id").get(id=actor_user_id)
    return Order.objects.select_related("tariff").get(id=order_id)


def manual_mark_order_paid(
    *,
    order_id: int,
    actor_user_id: int | None,
    reason: str,
) -> PaymentProcessingResult:
    _ensure_non_production_manual_payment_action()
    reason = reason.strip()
    if not reason:
        raise ValueError("Для ручной отметки оплаты нужна причина.")

    order = _get_existing_order_for_manual_action(
        order_id=order_id,
        actor_user_id=actor_user_id,
    )
    event = NormalizedPaymentEvent(
        provider_code=PaymentProviderCode.ROBO_KASSA,
        order_number=order.number,
        status=_STATUS_PAID,
        amount=_quantize_money(order.amount),
        currency=order.currency,
        dedupe_key=f"manual_paid:{order.number}",
        provider_event_id=f"manual_paid:{order.number}",
        signature_valid=True,
        is_valid=True,
        raw_payload={
            "manual": True,
            "reason": reason,
            "actor_user_id": actor_user_id,
        },
    )
    processing_result = process_payment_event(event=event)
    _record_commerce_audit(
        action="commerce.manual_mark_order_paid",
        result="success",
        actor_user_id=actor_user_id,
        order=order,
        message=reason,
        payload={
            "event_id": processing_result.event_id,
            "grant_created": processing_result.grant_created,
        },
    )
    return processing_result


@transaction.atomic
def revoke_order_access(
    *,
    order_id: int,
    actor_user_id: int | None,
    reason: str,
) -> AccessRevocationResult:
    reason = reason.strip()
    if not reason:
        raise ValueError("Для отзыва доступа по заказу нужна причина.")

    order = (
        Order.objects.select_for_update()
        .select_related("access_grant", "tariff")
        .get(id=order_id)
    )
    user_model = get_user_model()
    if actor_user_id is not None:
        user_model.objects.only("id").get(id=actor_user_id)

    processed_at = timezone.now()
    access_revoked = False
    if order.access_grant_id is not None:
        revoked_grant = revoke_access_grant(
            grant_id=order.access_grant_id,
            reason=reason,
            revoked_by_id=actor_user_id,
        )
        access_revoked = revoked_grant.status == AccessGrant.Status.REVOKED

    order.status = _STATUS_REFUNDED
    if order.refunded_at is None:
        order.refunded_at = processed_at
    order.last_event_at = processed_at
    order.save(update_fields=["status", "refunded_at", "last_event_at", "updated_at"])

    payment_event, _created = PaymentEvent.objects.get_or_create(
        order=order,
        dedupe_key=f"manual_revoke:{order.number}",
        defaults={
            "provider_code": PaymentProviderCode.ROBO_KASSA.value,
            "status": _STATUS_REFUNDED,
            "provider_event_id": f"manual_revoke:{order.number}",
            "amount": order.amount,
            "currency": order.currency,
            "signature_status": PaymentEvent.SignatureStatus.SKIPPED,
            "is_valid": True,
            "processing_result": "access_revoked" if access_revoked else "no_access_to_revoke",
            "processed_at": processed_at,
            "payload": {
                "manual": True,
                "reason": reason,
                "actor_user_id": actor_user_id,
            },
        },
    )
    if payment_event.processed_at is None:
        payment_event.processed_at = processed_at
        payment_event.processing_result = (
            "access_revoked" if access_revoked else "no_access_to_revoke"
        )
        payment_event.save(update_fields=["processed_at", "processing_result", "updated_at"])

    _record_commerce_audit(
        action="commerce.revoke_order_access",
        result="success",
        actor_user_id=actor_user_id,
        order=order,
        message=reason,
        payload={
            "payment_event_id": payment_event.id,
            "access_grant_id": order.access_grant_id,
            "access_revoked": access_revoked,
        },
    )
    return AccessRevocationResult(
        order_id=order.id,
        order_status=order.status,
        payment_event_id=payment_event.id,
        access_grant_id=order.access_grant_id,
        access_revoked=access_revoked,
    )
