from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        abstract = True


class ProviderCode(models.TextChoices):
    ROBO_KASSA = "robokassa", "Robokassa"


class CommerceStatus(models.TextChoices):
    CREATED = "created", "Создан"
    PENDING = "pending", "Ожидает подтверждения"
    PAID = "paid", "Оплачен"
    FAILED = "failed", "Не оплачен"
    REFUNDED = "refunded", "Возвращён"
    DISPUTED = "disputed", "На проверке"


class PaymentSignatureStatus(models.TextChoices):
    VALID = "valid", "Проверена"
    INVALID = "invalid", "Ошибка подписи"
    SKIPPED = "skipped", "Не проверялась"


class Order(TimeStampedModel):
    ProviderCode = ProviderCode
    Status = CommerceStatus

    public_id = models.UUIDField("публичный ID", default=uuid.uuid4, editable=False, unique=True)
    number = models.CharField("номер", max_length=64, unique=True)
    provider_code = models.CharField(
        "провайдер",
        max_length=32,
        choices=ProviderCode.choices,
        default=ProviderCode.ROBO_KASSA,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="commerce_orders",
    )
    course = models.ForeignKey(
        "curriculum.Course",
        verbose_name="курс",
        on_delete=models.CASCADE,
        related_name="commerce_orders",
    )
    tariff = models.ForeignKey(
        "access_control.Tariff",
        verbose_name="тариф",
        on_delete=models.PROTECT,
        related_name="commerce_orders",
    )
    status = models.CharField(
        "статус",
        max_length=16,
        choices=CommerceStatus.choices,
        default=CommerceStatus.CREATED,
    )
    amount = models.DecimalField("сумма", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField("валюта", max_length=3, default="RUB")
    return_path = models.CharField("путь возврата", max_length=255)
    provider_payment_id = models.CharField("ID платежа у провайдера", max_length=128, blank=True)
    access_grant = models.OneToOneField(
        "access_control.AccessGrant",
        verbose_name="доступ",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commerce_order",
    )
    access_granted_at = models.DateTimeField("доступ выдан", null=True, blank=True)
    success_returned_at = models.DateTimeField("успешный возврат", null=True, blank=True)
    last_event_at = models.DateTimeField("последнее событие", null=True, blank=True)
    paid_at = models.DateTimeField("оплачено", null=True, blank=True)
    failed_at = models.DateTimeField("ошибка оплаты", null=True, blank=True)
    refunded_at = models.DateTimeField("возвращено", null=True, blank=True)
    disputed_at = models.DateTimeField("спор", null=True, blank=True)
    metadata = models.JSONField("метаданные", default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "заказ"
        verbose_name_plural = "заказы"
        indexes = [
            models.Index(fields=["user", "status"], name="comm_order_user_stat_idx"),
            models.Index(
                fields=["provider_code", "status"],
                name="comm_order_provider_stat_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Заказ {self.number}: {self.get_status_display()}"


class PaymentEvent(TimeStampedModel):
    Status = CommerceStatus
    SignatureStatus = PaymentSignatureStatus

    order = models.ForeignKey(
        Order,
        verbose_name="заказ",
        on_delete=models.CASCADE,
        related_name="payment_events",
    )
    provider_code = models.CharField(
        "провайдер",
        max_length=32,
        choices=ProviderCode.choices,
        default=ProviderCode.ROBO_KASSA,
    )
    status = models.CharField(
        "статус",
        max_length=16,
        choices=CommerceStatus.choices,
        default=CommerceStatus.PENDING,
    )
    dedupe_key = models.CharField("ключ идемпотентности", max_length=160)
    provider_event_id = models.CharField("ID события у провайдера", max_length=128, blank=True)
    provider_payment_id = models.CharField("ID платежа у провайдера", max_length=128, blank=True)
    amount = models.DecimalField("сумма", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField("валюта", max_length=3, default="RUB")
    signature_status = models.CharField(
        "статус подписи",
        max_length=16,
        choices=PaymentSignatureStatus.choices,
        default=PaymentSignatureStatus.SKIPPED,
    )
    is_valid = models.BooleanField("валидно", default=True)
    invalid_reason = models.TextField("причина ошибки", blank=True)
    processing_result = models.CharField("результат обработки", max_length=64, blank=True)
    occurred_at = models.DateTimeField("произошло", null=True, blank=True)
    processed_at = models.DateTimeField("обработано", null=True, blank=True)
    payload = models.JSONField("данные события", default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "платёжное событие"
        verbose_name_plural = "платёжные события"
        constraints = [
            models.UniqueConstraint(
                fields=["order", "dedupe_key"],
                name="comm_event_order_dedupe_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["order", "status", "processed_at"],
                name="comm_event_order_stat_idx",
            ),
            models.Index(
                fields=["provider_code", "provider_event_id"],
                name="comm_event_provider_evt_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Платёжное событие {self.order_id}: {self.get_status_display()}"
