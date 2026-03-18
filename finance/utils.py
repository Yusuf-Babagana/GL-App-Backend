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
import logging

logger = logging.getLogger(__name__)

class MonnifyAPI:
    """
    Unified Monnify Service for Virtual Accounts, Withdrawals, and Split Payments.
    """
    @staticmethod
    def _get_url(path):
        # 1. Get base URL from settings
        base = settings.MONNIFY_BASE_URL.strip().rstrip('/')
        
        # 2. Fix the "https:https://" bug by ensuring we only have one protocol
        if "://" in base:
            # Split by :// and take the last part (the actual host)
            parts = base.split("://")
            host = parts[-1] 
            base = f"https://{host}"
        
        # 3. Clean up any existing versioning in the base URL
        base = re.sub(r'/api/v(1|2)$', '', base)
        
        # 4. Ensure path starts with /
        if not path.startswith('/'):
            path = f"/{path}"
            
        return f"{base}{path}"

    @staticmethod
    def get_auth_token():
        # This will now return 'https://api.monnify.com/api/v1/auth/login' correctly
        url = MonnifyAPI._get_url("/api/v1/auth/login")
        
        auth_str = f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json"
        }
        
        try:
            # We use verify=True to ensure SSL is valid on PythonAnywhere
            response = requests.post(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json()['responseBody']['accessToken']
            else:
                logger.error(f"❌ Monnify Auth Rejected: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"❌ Monnify Connection Error: {e} | URL used: {url}")
            return None

    @staticmethod
    def create_virtual_account(user):
        token = MonnifyAPI.get_auth_token()
        if not token: 
            return None, "Auth Failed"

        url = MonnifyAPI._get_url("/api/v2/bank-transfer/reserved-accounts")
        
        # Clean name: Only letters and spaces. Max 50 chars.
        raw_name = user.full_name or user.username
        clean_name = re.sub(r'[^a-zA-Z\s]', '', raw_name).strip()[:50]

        # Ensure BVN is a clean string
        clean_bvn = str(user.bvn).strip()

        payload = {
            "accountReference": str(user.wallet.account_reference),
            "accountName": clean_name,
            "currencyCode": "NGN",
            "contractCode": settings.MONNIFY_CONTRACT_CODE,
            "customerEmail": user.email,
            "customerName": clean_name,
            "getAllAvailableBanks": True,
            # We send all three to satisfy different Monnify validator versions
            "customerBvn": clean_bvn,
            "bvn": clean_bvn,
            "nin": getattr(user, 'nin', clean_bvn) # Use BVN as fallback if NIN isn't set
        }

        try:
            response = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=20)
            data = response.json()
            
            # SUCCESS CASE
            if data.get('requestSuccessful'):
                accounts = data['responseBody']['accounts']
                return {
                    "bank_name": accounts[0]['bankName'],
                    "account_number": accounts[0]['accountNumber'],
                    "bank_code": accounts[0]['bankCode']
                }, None

            # SELF-HEALING CASE: Account already exists on Monnify
            if "already exists" in str(data.get('responseMessage')).lower():
                # Manually fetch existing account details
                fetch_url = MonnifyAPI._get_url(f"/api/v2/bank-transfer/reserved-accounts/{user.wallet.account_reference}")
                fetch_resp = requests.get(fetch_url, headers={"Authorization": f"Bearer {token}"})
                fetch_data = fetch_resp.json()
                
                if fetch_data.get('requestSuccessful'):
                    accounts = fetch_data['responseBody']['accounts']
                    return {
                        "bank_name": accounts[0]['bankName'],
                        "account_number": accounts[0]['accountNumber'],
                        "bank_code": accounts[0]['bankCode']
                    }, None

            return None, data.get('responseMessage', 'Unknown Error')
        except Exception as e:
            return None, str(e)

    @staticmethod
    def initiate_order_payment(order, customer_name, customer_email):
        """Handled the Split Payment logic previously in monnify.py"""
        token = MonnifyAPI.get_auth_token()
        url = MonnifyAPI._get_url("/api/v1/merchant/transactions/init-transaction")
        
        total_amount = float(order.total_price)
        commission = min(total_amount * 0.03, 15000.0)
        vendor_share = total_amount - commission

        payload = {
            "amount": total_amount,
            "customerName": customer_name,
            "customerEmail": customer_email,
            "paymentReference": f"ORD-{order.id}-{uuid.uuid4().hex[:8]}",
            "paymentDescription": f"Order #{order.id}",
            "currencyCode": "NGN",
            "contractCode": settings.MONNIFY_CONTRACT_CODE,
            "incomeSplitConfig": [{
                "subAccountCode": order.store.monnify_sub_account_code,
                "splitAmount": vendor_share,
                "feeBearer": True
            }],
            "methods": ["CARD", "ACCOUNT_TRANSFER"]
        }
        
        response = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
        return response.json()

    @staticmethod
    def create_sub_account(bank_code, account_number, email, store_name):
        """
        Creates a sub-account on Monnify for a vendor.
        Returns the subAccountCode if successful.
        """
        token = MonnifyAPI.get_auth_token()
        if not token:
            return None

        url = MonnifyAPI._get_url("/api/v1/sub-accounts")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        data = [{
            "currencyCode": "NGN",
            "bankCode": bank_code,
            "accountNumber": account_number,
            "email": email,
            "defaultSplitPercentage": 100 
        }]

        response = requests.post(url, headers=headers, json=data)
        res_json = response.json()

        if res_json.get('requestSuccessful') and res_json['responseBody']:
            return res_json['responseBody'][0].get('subAccountCode')
        
        logger.error(f"Sub-Account Creation Failed: {res_json}")
        return None

    @staticmethod
    def resolve_bank_account(account_number, bank_code):
        """Verifies the account number and returns the account name"""
        token = MonnifyAPI.get_auth_token()
        if not token:
            return None

        url = MonnifyAPI._get_url("/api/v1/bank-transfer/reserved-accounts/lookup")
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "accountNumber": account_number,
            "bankCode": bank_code
        }

        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            return response.json().get('responseBody') # Contains 'accountName'
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

    @staticmethod
    def process_direct_payment(buyer, amount, seller, order_id):
        """
        Instant Settlement: Deducts from Buyer's balance and credits Seller directly.
        No escrow involved.
        """
        amount = Decimal(str(amount))

        try:
            with transaction.atomic():
                buyer_wallet = Wallet.objects.select_for_update().get(user=buyer)
                seller_wallet = Wallet.objects.select_for_update().get(user=seller)

                if buyer_wallet.balance < amount:
                    return False, "Insufficient wallet balance."

                # 1. Deduct from Buyer
                buyer_wallet.balance -= amount
                buyer_wallet.save()

                # 2. Credit Seller (Instant Settlement)
                seller_wallet.balance += amount
                seller_wallet.save()

                # 3. Audit Trail: Buyer debit
                Transaction.objects.create(
                    wallet=buyer_wallet,
                    amount=-amount,
                    transaction_type=Transaction.TransactionType.PAYMENT,
                    status=Transaction.Status.SUCCESS,
                    related_order_id=str(order_id),
                    description=f"Paid for Order #{order_id}"
                )

                # 4. Audit Trail: Seller credit
                Transaction.objects.create(
                    wallet=seller_wallet,
                    amount=amount,
                    transaction_type=Transaction.TransactionType.DEPOSIT,
                    status=Transaction.Status.SUCCESS,
                    related_order_id=str(order_id),
                    description=f"Received payment for Order #{order_id}"
                )

                return True, "Payment settled successfully."

        except Wallet.DoesNotExist:
            return False, "Wallet not found for buyer or seller."
        except Exception as e:
            return False, f"Payment failed: {str(e)}"

    @staticmethod
    def settle_to_pending(buyer, seller, amount, order_id):
        """
        Deferred Settlement (Step 1 of 2):
        - Deducts from Buyer's available balance
        - Credits Seller's pending_balance (locked until buyer confirms receipt)
        """
        amount = Decimal(str(amount))

        try:
            with transaction.atomic():
                b_wallet = Wallet.objects.select_for_update().get(user=buyer)
                s_wallet = Wallet.objects.select_for_update().get(user=seller)

                if b_wallet.balance < amount:
                    return False, "Insufficient wallet balance."

                # 1. Deduct from Buyer
                b_wallet.balance -= amount
                b_wallet.save()

                # 2. Lock in Seller's "Waiting Room"
                s_wallet.pending_balance += amount
                s_wallet.save()

                # 3. Audit Trail: Buyer debit
                Transaction.objects.create(
                    wallet=b_wallet,
                    amount=-amount,
                    transaction_type=Transaction.TransactionType.PAYMENT,
                    status=Transaction.Status.SUCCESS,
                    related_order_id=str(order_id),
                    description=f"Paid for Order #{order_id} (pending seller confirmation)"
                )

                # 4. Audit Trail: Seller credit (pending)
                Transaction.objects.create(
                    wallet=s_wallet,
                    amount=amount,
                    transaction_type=Transaction.TransactionType.ESCROW_LOCK,
                    status=Transaction.Status.PENDING,
                    related_order_id=str(order_id),
                    description=f"Pending earnings for Order #{order_id} (locked)"
                )

                return True, "Funds locked in pending."

        except Wallet.DoesNotExist:
            return False, "Wallet not found for buyer or seller."
        except Exception as e:
            return False, f"Payment failed: {str(e)}"

    @staticmethod
    def finalize_settlement(order):
        """
        Deferred Settlement (Step 2 of 2):
        Called when Buyer confirms receipt OR 7-day auto-release triggers.
        Moves funds from Seller's pending_balance → available balance.
        """
        amount = Decimal(str(order.total_price))

        try:
            with transaction.atomic():
                s_wallet = Wallet.objects.select_for_update().get(user=order.store.owner)

                if s_wallet.pending_balance < amount:
                    return False, "Pending balance insufficient for this order."

                # Move from Pending → Available
                s_wallet.pending_balance -= amount
                s_wallet.balance += amount
                s_wallet.save()

                # Audit Trail: Seller's funds unlocked
                Transaction.objects.create(
                    wallet=s_wallet,
                    amount=amount,
                    transaction_type=Transaction.TransactionType.ESCROW_RELEASE,
                    status=Transaction.Status.SUCCESS,
                    related_order_id=str(order.id),
                    description=f"Earnings released for Order #{order.id}"
                )

                return True, "Funds released to seller."

        except Wallet.DoesNotExist:
            return False, "Seller wallet not found."
        except Exception as e:
            return False, f"Release failed: {str(e)}"

def generate_vtpass_request_id():
    lagos_tz = pytz.timezone('Africa/Lagos')
    now_in_lagos = datetime.datetime.now(lagos_tz)
    timestamp = now_in_lagos.strftime('%Y%m%d%H%M')
    unique_suffix = uuid.uuid4().hex[:10]
    return f"{timestamp}{unique_suffix}"