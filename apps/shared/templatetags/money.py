from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value: object, currency: object = "RUB") -> str:
    currency_code = str(currency or "RUB").upper()
    symbol = "₽" if currency_code == "RUB" else currency_code
    try:
        amount = Decimal(str(value)).quantize(Decimal("1"))
    except (InvalidOperation, ValueError):
        return f"{value} {symbol}"

    formatted_amount = f"{int(amount):,}".replace(",", " ")
    return f"{formatted_amount} {symbol}"
