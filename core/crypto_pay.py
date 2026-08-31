"""CryptoBot Crypto Pay API integration."""
import hashlib
import hmac
import json
import time

import httpx

from core.config import settings

BASE_URL = "https://pay.crypt.bot/api"
PRICE_USDT = "7.00"


async def create_invoice(telegram_id: int) -> dict | None:
    """Create a USDT invoice. Returns {pay_url, invoice_id} or None."""
    payload = {
        "asset": "USDT",
        "amount": PRICE_USDT,
        "description": "SafeOut Premium — 1 месяц безлимитного доступа",
        "payload": f"premium_{telegram_id}_{int(time.time())}",
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 3600,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/createInvoice",
                json=payload,
                headers={"Crypto-Pay-API-Token": settings.cryptobot_token},
            )
            data = resp.json()
            if data.get("ok") and data.get("result"):
                result = data["result"]
                return {"pay_url": result["pay_url"], "invoice_id": result["invoice_id"]}
    except Exception:
        pass
    return None


def verify_webhook(body: bytes, secret: str) -> bool:
    """Verify CryptoBot webhook signature (HMAC-SHA256 of body with token hash)."""
    token_hash = hashlib.sha256(settings.cryptobot_token.encode()).digest()
    expected = hmac.new(token_hash, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, secret)
