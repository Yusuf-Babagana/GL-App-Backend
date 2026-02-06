import requests
import base64
from django.conf import settings
from decimal import Decimal
from django.db import transaction
from .models import Wallet, Transaction

class MonnifyAPI:
    """
    Handles communication with Monnify for virtual account creation 
    and authentication.
    """
    @staticmethod
    def get_auth_token():
        """Generates the required Bearer token for Monnify API calls."""
        # Monnify requires Basic Auth: base64(apiKey:secretKey)
        auth_str = f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        
        url = f"{settings.MONNIFY_BASE_URL}/api/v1/auth/login"
        headers = {"Authorization": f"Basic {encoded_auth}"}
        
        try:
            response = requests.post(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()['responseBody']['accessToken']
        except Exception as e:
            print(f"CRITICAL: Monnify Auth Failure -> {e}")
            return None

    @staticmethod
    def create_virtual_account(user):
        """Creates a dedicated bank account for the user to fund their wallet."""
        token = MonnifyAPI.get_auth_token()
        if not token:
            return None

        url = f"{settings.MONNIFY_BASE_URL}/api/v2/bank-transfer/reserved-accounts"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "accountReference": str(user.wallet.account_reference),
            "accountName": user.full_name or user.email,
            "currencyCode": "NGN",
            "contractCode": settings.MONNIFY_CONTRACT_CODE,
            "customerEmail": user.email,
            "customerName": user.full_name or user.email,
            "getAllAvailableBanks": True
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            data = response.json()
            if data.get('requestSuccessful'):
                # We typically take the first account returned (e.g., Wema Bank)
                accounts = data['responseBody']['accounts']
                return {
                    "bank_name": accounts[0]['bankName'],
                    "account_number": accounts[0]['accountNumber'],
                    "bank_code": accounts[0]['bankCode']
                }
        except Exception as e:
            print(f"ERROR: Monnify Account Creation -> {e}")
        return None

class WalletManager:
    """
    Handles all internal wallet movements (Marketplace and Data purchases).
    """
    @staticmethod
    def process_payment(user, amount, transaction_type, description, related_id=None):
        """
        Deducts funds or moves them to escrow. 
        Uses select_for_update to prevent double-spending.
        """
        amount = Decimal(str(amount))
        
        try:
            with transaction.atomic():
                # Lock the wallet row until the transaction finishes
                wallet = Wallet.objects.select_for_update().get(user=user)

                if wallet.balance < amount:
                    return False, "Insufficient wallet balance."

                # 1. Create the Transaction Record (Pending)
                ledger = Transaction.objects.create(
                    wallet=wallet,
                    amount=-amount,
                    transaction_type=transaction_type,
                    status=Transaction.Status.PENDING,
                    description=description,
                    related_order_id=related_id if transaction_type == 'escrow_lock' else None
                )

                # 2. Execute the Movement
                if transaction_type == Transaction.TransactionType.ESCROW_LOCK:
                    wallet.balance -= amount
                    wallet.escrow_balance += amount
                else:
                    wallet.balance -= amount
                
                wallet.save()
                
                # 3. Mark as Success
                ledger.status = Transaction.Status.SUCCESS
                ledger.save()

                return True, "Payment processed successfully."

        except Wallet.DoesNotExist:
            return False, "User wallet not found."
        except Exception as e:
            return False, f"Payment failed: {str(e)}"