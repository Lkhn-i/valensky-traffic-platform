from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.access_control.models import AccessGrant, Tariff
from apps.accounts.models import LeadProfile, User
from apps.accounts.services import assign_role, ensure_required_roles, user_has_role
from apps.commerce.models import Order, PaymentEvent
from apps.commerce.services import (
    PaymentProviderCode,
    build_checkout_placeholder,
    create_checkout_placeholder,
    manual_mark_order_paid,
    process_robokassa_callback,
    record_checkout_return,
    revoke_order_access,
)
from apps.curriculum.models import Course, Lesson, Module
from apps.events.models import AuditLog
from apps.integrations.models import IntegrationOutboxEvent
from apps.learning_state.models import ProgressRecord
from apps.notifications.models import NotificationJob


def create_checkout_context(*, username: str = "buyer") -> tuple[User, Tariff]:
    user = get_user_model().objects.create_user(username=username)
    course = Course.objects.create(slug=f"{username}-course", title="Gatsa Sales")
    tariff = Tariff.objects.create(
        code=Tariff.Code.BASE,
        course=course,
        title="Базовый",
        price_amount=Decimal("50000.00"),
    )
    return user, tariff


def create_lesson_zero(course: Course) -> Lesson:
    module = Module.objects.create(course=course, slug="module-0", title="Module 0", position=0)
    return Lesson.objects.create(module=module, slug="lesson-0", title="Урок 0", position=0)


def test_build_checkout_placeholder_keeps_future_robokassa_shape() -> None:
    checkout = build_checkout_placeholder(tariff_code="base", return_path="/learn/")

    assert checkout.provider_code == PaymentProviderCode.ROBO_KASSA
    assert checkout.tariff_code == "base"
    assert checkout.status == Order.Status.CREATED
    assert checkout.order_id is None


@pytest.mark.django_db
def test_create_checkout_placeholder_creates_created_order() -> None:
    user, tariff = create_checkout_context()

    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/payments/success/",
    )

    order = Order.objects.get(number=checkout.order_number)

    assert checkout.provider_code == PaymentProviderCode.ROBO_KASSA
    assert checkout.order_id == order.id
    assert checkout.status == Order.Status.CREATED
    assert checkout.metadata["provider_enabled"] is False
    assert order.status == Order.Status.CREATED
    assert order.access_grant_id is None


@pytest.mark.django_db
def test_success_return_marks_order_pending_without_grant() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/payments/success/",
    )

    order = record_checkout_return(
        order_number=checkout.order_number,
        payload={"result": "success"},
    )

    assert order.status == Order.Status.PENDING
    assert order.success_returned_at is not None
    assert AccessGrant.objects.count() == 0


@pytest.mark.django_db
def test_paid_callback_grants_access_and_student_role_once() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/payments/success/",
    )

    result = process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-paid-1",
            "payment_id": "pay-1",
        },
        signature_valid=True,
    )
    order = Order.objects.get(number=checkout.order_number)

    assert result.grant_created is True
    assert result.access_grant_id == order.access_grant_id
    assert order.status == Order.Status.PAID
    assert order.access_granted_at is not None
    assert AccessGrant.objects.count() == 1
    assert user_has_role(user.id, ["student"]) is True


@pytest.mark.django_db
def test_duplicate_paid_callbacks_do_not_duplicate_access_grants() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/payments/success/",
    )

    first = process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-paid-1",
            "payment_id": "pay-1",
        },
        signature_valid=True,
    )
    second = process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-paid-2",
            "payment_id": "pay-1-retry",
        },
        signature_valid=True,
    )

    assert first.grant_created is True
    assert second.grant_created is False
    assert AccessGrant.objects.count() == 1
    assert PaymentEvent.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_paid_callback_queues_paid_access_bot_message_once() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/payments/success/",
    )

    first = process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-stage8-paid-1",
            "payment_id": "pay-stage8-1",
        },
        signature_valid=True,
    )
    second = process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-stage8-paid-2",
            "payment_id": "pay-stage8-2",
        },
        signature_valid=True,
    )

    notification_job = NotificationJob.objects.get(template_key="paid.access_granted")
    outbox_event = IntegrationOutboxEvent.objects.get(event_type="paid_access.granted")

    assert first.grant_created is True
    assert second.grant_created is False
    assert NotificationJob.objects.count() == 1
    assert IntegrationOutboxEvent.objects.count() == 1
    assert notification_job.channel == "telegram"
    assert notification_job.payload["access_path"] == "/learn/"
    assert outbox_event.notification_job_id == notification_job.id
    assert outbox_event.payload["order_number"] == checkout.order_number


@pytest.mark.django_db
def test_invalid_signature_paid_callback_is_recorded_without_access() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/payments/success/",
    )

    result = process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-bad-signature",
            "payment_id": "pay-1",
        },
        signature_valid=False,
    )
    order = Order.objects.get(number=checkout.order_number)
    payment_event = PaymentEvent.objects.get(order=order)

    assert result.grant_created is False
    assert order.status == Order.Status.CREATED
    assert payment_event.signature_status == PaymentEvent.SignatureStatus.INVALID
    assert payment_event.processing_result == "invalid_signature"
    assert AccessGrant.objects.count() == 0


@pytest.mark.django_db
def test_amount_mismatch_callback_is_recorded_without_access() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/payments/success/",
    )

    result = process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "1.00",
            "status": "paid",
            "event_id": "evt-bad-amount",
            "payment_id": "pay-1",
        },
        signature_valid=True,
    )
    order = Order.objects.get(number=checkout.order_number)
    payment_event = PaymentEvent.objects.get(order=order)

    assert result.grant_created is False
    assert order.status == Order.Status.CREATED
    assert payment_event.is_valid is False
    assert payment_event.processing_result == "amount_or_currency_mismatch"
    assert AccessGrant.objects.count() == 0


@pytest.mark.django_db
def test_refund_records_event_without_revoking_existing_access() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/payments/success/",
    )
    process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-paid-1",
            "payment_id": "pay-1",
        },
        signature_valid=True,
    )

    refund = process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "refunded",
            "event_id": "evt-refund-1",
            "payment_id": "pay-1",
        },
        signature_valid=True,
    )
    order = Order.objects.get(number=checkout.order_number)
    access_grant = AccessGrant.objects.get(id=order.access_grant_id)

    assert refund.grant_created is False
    assert order.status == Order.Status.REFUNDED
    assert order.access_grant_id == access_grant.id
    assert access_grant.status == AccessGrant.Status.ACTIVE
    assert PaymentEvent.objects.filter(order=order).count() == 2


@pytest.mark.django_db
def test_robokassa_success_endpoint_redirects_without_access_grant() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/learn/",
    )

    response = Client().get(
        "/commerce/robokassa/success/",
        {"InvId": checkout.order_number, "OutSum": "50000.00"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/learn/"
    assert Order.objects.get(number=checkout.order_number).status == Order.Status.PENDING
    assert AccessGrant.objects.count() == 0


@pytest.mark.django_db
def test_robokassa_webhook_endpoint_grants_only_with_stage6_stub_signature() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/learn/",
    )

    bad_response = Client().post(
        "/webhooks/payments/robokassa/result",
        {
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-webhook-bad",
            "SignatureValue": "bad-signature",
        },
    )
    good_response = Client().post(
        "/webhooks/payments/robokassa/result",
        {
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-webhook-good",
            "SignatureValue": "stage6-valid",
        },
    )

    assert bad_response.status_code == 200
    assert bad_response.json()["processing_result"] == "invalid_signature"
    assert good_response.status_code == 200
    assert good_response.json()["processing_result"] == "paid_access_granted"
    assert AccessGrant.objects.count() == 1


@pytest.mark.django_db
@override_settings(ENV_NAME="production")
def test_robokassa_webhook_endpoint_is_disabled_in_production() -> None:
    user, tariff = create_checkout_context()
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/learn/",
    )

    response = Client().post(
        "/webhooks/payments/robokassa/result",
        {
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "SignatureValue": "stage6-valid",
        },
    )

    assert response.status_code == 404
    assert PaymentEvent.objects.count() == 0
    assert AccessGrant.objects.count() == 0


@pytest.mark.django_db
def test_manual_mark_paid_requires_reason_and_records_audit_log() -> None:
    admin_user, tariff = create_checkout_context(username="admin-user")
    buyer = get_user_model().objects.create_user(username="manual-buyer")
    checkout = create_checkout_placeholder(
        user_id=buyer.id,
        tariff_id=tariff.id,
        return_path="/learn/",
    )
    order = Order.objects.get(number=checkout.order_number)

    with pytest.raises(ValueError):
        manual_mark_order_paid(order_id=order.id, actor_user_id=admin_user.id, reason=" ")

    result = manual_mark_order_paid(
        order_id=order.id,
        actor_user_id=admin_user.id,
        reason="test manager confirmed bank payment",
    )

    assert result.grant_created is True
    assert AccessGrant.objects.count() == 1
    assert AuditLog.objects.filter(action="commerce.manual_mark_order_paid").exists()


@pytest.mark.django_db
@override_settings(ENV_NAME="production")
def test_manual_mark_paid_is_disabled_in_production() -> None:
    admin_user, tariff = create_checkout_context(username="admin-prod")
    buyer = get_user_model().objects.create_user(username="prod-buyer")
    checkout = create_checkout_placeholder(
        user_id=buyer.id,
        tariff_id=tariff.id,
        return_path="/learn/",
    )
    order = Order.objects.get(number=checkout.order_number)

    with pytest.raises(PermissionError):
        manual_mark_order_paid(
            order_id=order.id,
            actor_user_id=admin_user.id,
            reason="production guard",
        )


@pytest.mark.django_db
def test_paid_event_converts_lead_and_revoke_preserves_lesson_zero_progress() -> None:
    ensure_required_roles()
    user, tariff = create_checkout_context(username="lead-buyer")
    assign_role(user.id, "lead")
    lead_profile = LeadProfile.objects.create(user=user, status=LeadProfile.Status.PREVIEW)
    lesson0 = create_lesson_zero(tariff.course)
    ProgressRecord.objects.create(
        user=user,
        course=tariff.course,
        module=lesson0.module,
        lesson=lesson0,
        status=ProgressRecord.Status.COMPLETED,
        source="lesson0_preview",
    )
    checkout = create_checkout_placeholder(
        user_id=user.id,
        tariff_id=tariff.id,
        return_path="/learn/",
    )
    process_robokassa_callback(
        payload={
            "InvId": checkout.order_number,
            "OutSum": "50000.00",
            "status": "paid",
            "event_id": "evt-lead-paid",
            "payment_id": "pay-lead",
        },
        signature_valid=True,
    )
    order = Order.objects.get(number=checkout.order_number)

    lead_profile.refresh_from_db()
    revoke_result = revoke_order_access(
        order_id=order.id,
        actor_user_id=None,
        reason="refund approved by manager",
    )

    assert lead_profile.status == LeadProfile.Status.CONVERTED
    assert user_has_role(user.id, ["student"]) is True
    assert revoke_result.access_revoked is True
    assert AccessGrant.objects.get(id=order.access_grant_id).status == AccessGrant.Status.REVOKED
    assert ProgressRecord.objects.filter(user=user, lesson=lesson0).count() == 1
    assert ProgressRecord.objects.get(user=user, lesson=lesson0).status == (
        ProgressRecord.Status.COMPLETED
    )
