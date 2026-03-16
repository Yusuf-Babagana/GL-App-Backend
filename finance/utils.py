import requests
import base64
import datetime
import pytz
import uuid
import re
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
        # Strip trailing slashes and common path errors to prevent doubling
        base = settings.MONNIFY_BASE_URL.strip().rstrip('/')
        if "api/v1" in base:
            base = base.replace("/api/v1", "")
            
        url = f"{base}/api/v1/auth/login"
        
        auth_str = f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        
        headers = {"Authorization": f"Basic {encoded_auth}"}
        try:
            response = requests.post(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()['responseBody']['accessToken']
        except Exception as e:
            print(f"CRITICAL Auth Failure: {e} | URL: {url}")
            return None

    @staticmethod
    def create_virtual_account(user):
        token = MonnifyAPI.get_auth_token()
        if not token: return None

        base = settings.MONNIFY_BASE_URL.strip().rstrip('/')
        if "api/v1" in base: base = base.replace("/api/v1", "")
        if "api/v2" in base: base = base.replace("/api/v2", "")

        url = f"{base}/api/v2/bank-transfer/reserved-accounts"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Clean name (Remove special characters for API compliance)
        raw_name = f"GLAPP-{user.full_name or user.username}"
        clean_name = re.sub(r'[^a-zA-Z0-9\s-]', '', raw_name)[:50]
        
        # Explicitly fetch BVN or NIN from the user object
        user_bvn = getattr(user, 'bvn', None)
        user_nin = getattr(user, 'nin', None)
        
        payload = {
            "accountReference": str(user.wallet.account_reference),
            "accountName": clean_name,
            "currencyCode": "NGN",
            "contractCode": settings.MONNIFY_CONTRACT_CODE,
            "customerEmail": user.email,
            "customerName": user.full_name or user.username,
            "getAllAvailableBanks": True,
        }

        # Compliance: Add BVN or NIN (One is mandatory in Production)
        if user_bvn:
            payload["customerBvn"] = user_bvn
        elif user_nin:
            payload["customerNin"] = user_nin
        else:
            print(f"❌ CANCELLED: No BVN/NIN provided for {user.email}")
            return None

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            data = response.json()
            
            if data.get('requestSuccessful'):
                accounts = data['responseBody']['accounts']
                # Returns the first available account (usually Wema or Moniepoint)
                return {
                    "bank_name": accounts[0]['bankName'],
                    "account_number": accounts[0]['accountNumber'],
                    "bank_code": accounts[0]['bankCode']
                }
            else:
                print(f"❌ Monnify API Error: {data.get('responseMessage')}")
                return None
                
        except Exception as e:
            print(f"ERROR: Monnify Account Creation -> {e}")
            return None

class WalletManager:
    """
    Handles all internal wallet movements (Marketplace and Data purchases).
    """
    @staticmethod
    def process_payment(user, amount, transaction_type, description, related_id=None):
        amount = Decimal(str(amount))
        
        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=user)

                if wallet.balance < amount:
                    return False, "Insufficient wallet balance."

                ledger = Transaction.objects.create(
                    wallet=wallet,
                    amount=-amount,
                    transaction_type=transaction_type,
                    status=Transaction.Status.PENDING,
                    description=description,
                    related_order_id=related_id if transaction_type == 'escrow_lock' else None
                )

                if transaction_type == Transaction.TransactionType.ESCROW_LOCK:
                    wallet.balance -= amount
                    wallet.escrow_balance += amount
                else:
                    wallet.balance -= amount
                
                wallet.save()
                ledger.status = Transaction.Status.SUCCESS
                ledger.save()

                return True, "Payment processed successfully."

        except Wallet.DoesNotExist:
            return False, "User wallet not found."
        except Exception as e:
            return False, f"Payment failed: {str(e)}"

def generate_vtpass_request_id():
    lagos_tz = pytz.timezone('Africa/Lagos')
    now_in_lagos = datetime.datetime.now(lagos_tz)
    timestamp = now_in_lagos.strftime('%Y%m%d%H%M')
    unique_suffix = uuid.uuid4().hex[:10]
    return f"{timestamp}{unique_suffix}"