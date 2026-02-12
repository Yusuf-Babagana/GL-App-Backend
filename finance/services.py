import hmac
import hashlib
import requests
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from .models import Wallet, Transaction

class PaystackService:
    """
    Service layer for Paystack integration.
    Handles transaction initialization, verification, and wallet crediting.
    """
    BASE_URL = "https://api.paystack.co"
    SECRET_KEY = settings.PAYSTACK_SECRET_KEY

    @classmethod
    def _get_headers(cls):
        return {
            "Authorization": f"Bearer {cls.SECRET_KEY}",
            "Content-Type": "application/json",
        }

    @classmethod
    def initiate_deposit(cls, wallet, email, amount, reference):
        """
        Initializes a transaction with Paystack.
        Returns: {authorization_url, access_code, reference}
        """
        url = f"{cls.BASE_URL}/transaction/initialize"
        # Paystack expects amount in kobo
        payload = {
            "email": email,
            "amount": int(Decimal(str(amount)) * 100),
            "reference": reference,
            "callback_url": "https://standard.paystack.co/close" # Handled by Mobile SDK
        }

        response = requests.post(url, json=payload, headers=cls._get_headers())
        res_data = response.json()

        if response.status_code == 200 and res_data.get('status'):
            return res_data['data']
        raise Exception(f"Paystack Init Error: {res_data.get('message')}")

    @classmethod
    def verify_payment(cls, reference):
        """
        Checks Paystack API to verify the status of a transaction.
        """
        url = f"{cls.BASE_URL}/transaction/verify/{reference}"
        response = requests.get(url, headers=cls._get_headers())
        res_data = response.json()

        if response.status_code == 200 and res_data.get('status'):
            return res_data['data'] # Contains status, amount, etc.
        return None

    @classmethod
    @transaction.atomic
    def credit_wallet(cls, reference, amount_kobo=None):
        # Use select_for_update() to lock the transaction row immediately
        txn = Transaction.objects.select_for_update().get(reference=reference)

        if txn.status == 'success':
            return txn.wallet, False  # Already processed, do nothing

        # Lock the wallet row to prevent concurrent balance updates
        wallet = Wallet.objects.select_for_update().get(id=txn.wallet.id)
        
        # Standardize the amount logic
        if amount_kobo:
            actual_amount = Decimal(amount_kobo) / 100
            # If Paystack reports a different amount than we initiated, mark as failed for safety
            if actual_amount != txn.amount:
                txn.status = 'failed'
                txn.description = f"Fraud Alert: Expected {txn.amount}, got {actual_amount}"
                txn.save()
                return wallet, False

        wallet.balance += txn.amount
        wallet.save()

        txn.status = 'success'
        txn.save()
        return wallet, True

    @classmethod
    def verify_webhook(cls, payload, signature):
        """
        Validates Paystack Webhook signature (HMAC SHA512).
        """
        computed_hash = hmac.new(
            cls.SECRET_KEY.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(computed_hash, signature)