"""Wallet Pay API integration (https://docs.wallet.tg/pay/)"""
import hashlib
import hmac
import time
import httpx

from core.config import settings

_BASE = "https://pay.wallet.tg"
_HEADERS = {
    "Wpay-Store-Api-Key": settings.wallet_pay_api_key,
    "Content-Type": "application/json",
}

PRICE_USDT = "7.00"
SUBSCRIPTION_DESCRIPTION = "SafeOut Premium — безлимитные свидания"


async def create_order(telegram_id: int) -> dict | None:
    """Create a Wallet Pay order and return {payLink, orderId} or None on error."""
    external_id = f"premium_{telegram_id}_{int(time.time())}"
    payload = {
        "amount": {"currencyCode": "USDT", "amount": PRICE_USDT},
        "description": SUBSCRIPTION_DESCRIPTION,
        "externalId": external_id,
        "timeoutSeconds": 3600,
        "customerTelegramUserId": telegram_id,
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{_BASE}/wpay/store-api/v1/order",
                json=payload,
                headers=_HEADERS,
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "SUCCESS":
                order = data["data"]
                return {"payLink": order["payLink"], "orderId": order["id"]}
        except Exception:
            pass
    return None


def verify_webhook(body: bytes, signature: str) -> bool:
    """Verify Wallet Pay webhook signature."""
    if not settings.wallet_pay_webhook_secret:
        return True  # dev mode: skip verification
    expected = hmac.HMAC(
        settings.wallet_pay_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
