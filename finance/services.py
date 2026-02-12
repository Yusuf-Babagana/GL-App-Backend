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
        """
        The critical logic to safely add money to a user's wallet.
        Uses select_for_update to lock the wallet row.
        """
        # 1. Get transaction and lock it
        txn = Transaction.objects.select_for_update().get(reference=reference)

        # 2. Idempotency Check: Prevent double-crediting
        if txn.status == 'success':
            return txn.wallet, False # Already processed

        # 3. Lock and update wallet
        wallet = Wallet.objects.select_for_update().get(id=txn.wallet.id)
        
        # If amount_kobo is provided (from webhook/API), verify it matches
        if amount_kobo:
            actual_amount = Decimal(amount_kobo) / 100
            if actual_amount != txn.amount:
                txn.status = 'failed'
                txn.description = f"Amount mismatch: Expected {txn.amount}, got {actual_amount}"
                txn.save()
                return wallet, False

        # 4. Perform the credit
        wallet.balance += txn.amount
        wallet.save()

        # 5. Finalize Transaction Ledger
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