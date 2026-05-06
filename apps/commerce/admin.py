from django.contrib import admin, messages

from .models import Order, PaymentEvent
from .services import manual_mark_order_paid


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    actions = ("mark_selected_orders_paid_for_stage6",)
    list_display = (
        "number",
        "provider_code",
        "status",
        "user",
        "tariff",
        "amount",
        "currency",
        "access_grant",
        "created_at",
    )
    list_filter = ("provider_code", "status", "currency", "created_at")
    search_fields = (
        "number",
        "user__username",
        "user__display_name",
        "provider_payment_id",
    )
    autocomplete_fields = ("user", "course", "tariff", "access_grant")
    readonly_fields = (
        "public_id",
        "number",
        "created_at",
        "updated_at",
        "access_granted_at",
        "success_returned_at",
        "last_event_at",
        "paid_at",
        "failed_at",
        "refunded_at",
        "disputed_at",
    )

    @admin.action(description="Отметить выбранные заказы оплаченными с записью в аудит")
    def mark_selected_orders_paid_for_stage6(self, request, queryset) -> None:
        paid_count = 0
        for order in queryset:
            try:
                manual_mark_order_paid(
                    order_id=order.id,
                    actor_user_id=request.user.id,
                    reason="admin_action_stage6_manual_mark_paid",
                )
            except (PermissionError, ValueError) as exc:
                self.message_user(request, str(exc), level=messages.ERROR)
                continue
            paid_count += 1
        self.message_user(
            request,
            f"Заказов отмечено оплаченными: {paid_count}. Действие записано в аудит.",
            level=messages.SUCCESS,
        )


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "status",
        "signature_status",
        "is_valid",
        "processing_result",
        "provider_event_id",
        "processed_at",
    )
    list_filter = (
        "provider_code",
        "status",
        "signature_status",
        "is_valid",
        "processed_at",
    )
    search_fields = (
        "order__number",
        "provider_event_id",
        "provider_payment_id",
        "dedupe_key",
    )
    autocomplete_fields = ("order",)
    readonly_fields = ("created_at", "updated_at", "processed_at")
