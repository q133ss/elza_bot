from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
import uuid
from typing import Any

from yookassa import Configuration, Payment


@dataclass(frozen=True)
class CreatedPayment:
    payment_id: str
    status: str
    confirmation_url: str
    amount_rub: int


class PaymentService:
    def __init__(self, shop_id: str, secret_key: str, return_url: str) -> None:
        if not shop_id or not secret_key:
            raise ValueError("YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY are required")
        if not return_url:
            raise ValueError("YOOKASSA_RETURN_URL is required")

        self._return_url = return_url
        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key

    def create_payment(self, *, amount_rub: int, description: str, metadata: dict[str, Any]) -> CreatedPayment:
        payload = {
            "amount": {
                "value": f"{Decimal(amount_rub):.2f}",
                "currency": "RUB",
            },
            "confirmation": {"type": "redirect", "return_url": self._return_url},
            "capture": True,
            "description": description,
            "metadata": metadata,
        }
        idempotence_key = str(uuid.uuid4())
        try:
            payment = Payment.create(payload, idempotence_key)
        except Exception as exc:
            logging.exception("YooKassa create payment error: %s", exc)
            raise

        confirmation_url = ""
        confirmation = getattr(payment, "confirmation", None)
        if confirmation:
            confirmation_url = getattr(confirmation, "confirmation_url", "") or ""

        return CreatedPayment(
            payment_id=str(payment.id),
            status=str(payment.status),
            confirmation_url=confirmation_url,
            amount_rub=amount_rub,
        )

    def get_payment_status(self, payment_id: str) -> str:
        try:
            payment = Payment.find_one(payment_id)
        except Exception as exc:
            logging.exception("YooKassa fetch payment error: %s", exc)
            raise
        return str(payment.status)
