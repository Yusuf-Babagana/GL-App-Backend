import requests
from datetime import datetime
import pytz
import uuid
import hashlib
import hmac
from decimal import Decimal
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db import transaction
from .models import Wallet, Transaction, BankAccount
from .serializers import WalletSerializer
from .monnify import MonnifyClient
from users.permissions import IsVerifiedUser
# finance/views.py

from .vtpass import VTPassClient  # Add this near your other imports

PAYSTACK_SECRET_KEY = "sk_test_f4bc777ea48e3fe932aecea60f0ebd8db0e7cd3c" # REPLACE WITH YOUR KEY
PAYSTACK_INITIATE_URL = "https://api.paystack.co/transaction/initialize"
PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify/"

class WalletDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # If we have a reference but no account number, sync it now!
        if wallet.account_reference and not wallet.account_number:
            try:
                client = MonnifyClient()
                resp = client.get_reserved_account_details(wallet.account_reference)
                
                if resp.get('requestSuccessful'):
                    # The response body for reserved-accounts/{reference} might be a single object
                    # or it might contain further nested fields. The user code assumes:
                    # body = { "accounts": [...] } or similar.
                    # Let's use the user's logic exactly for now.
                    body = resp.get('responseBody')
                    
                    # If body is dict and has accounts, assume list.
                    # If body is list, user logic might fail?
                    # User code: accounts = body.get('accounts', [])
                    # Let's trust user knows Monnify returns: { "accounts": [...] } within responseBody
                    
                    # Wait, if responseBody IS the account object (which is common for single fetch),
                    # then body.get('accounts') would be None if 'accounts' key doesn't exist.
                    # But often reserved accounts have multiple banks.
                    
                    accounts = body.get('accounts', []) if isinstance(body, dict) else []
                    if not accounts and isinstance(body, dict) and 'accountNumber' in body:
                         # Fallback: maybe body IS the account
                         accounts = [body]
                    
                    if accounts:
                        wallet.account_number = accounts[0].get('accountNumber')
                        wallet.bank_name = accounts[0].get('bankName')
                        wallet.bank_code = accounts[0].get('bankCode')
                        wallet.save() # This updates your UI instantly
                        print(f"✅ Auto-Healed Wallet: {wallet.account_number}")
            except Exception as e:
                print(f"Sync Error: {e}")

        wallet.transactions_preview = wallet.transactions.all().order_by('-created_at')[:20]
        serializer = WalletSerializer(wallet)
        return Response(serializer.data)

class InitiateDepositView(APIView):
    """
    Step 1: User requests to deposit money.
    Returns: A Paystack authorization URL for the user to click.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        email = request.user.email

        if not amount:
            return Response({"error": "Amount is required"}, status=400)

        # Paystack expects amount in Kobo (multiply NGN by 100)
        amount_kobo = int(float(amount) * 100)
        reference = str(uuid.uuid4())

        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        
        data = {
            "email": email,
            "amount": amount_kobo,
            "reference": reference,
            "callback_url": "https://standard.paystack.co/close"
        }

        try:
            # 1. Create a Pending Transaction in our DB
            wallet = request.user.wallet
            Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type='deposit',
                status='pending',
                reference=reference,
                description="Wallet Top-up"
            )

            # 2. Call Paystack
            response = requests.post(PAYSTACK_INITIATE_URL, json=data, headers=headers)
            res_data = response.json()

            if response.status_code == 200 and res_data['status']:
                return Response({
                    "authorization_url": res_data['data']['authorization_url'],
                    "access_code": res_data['data']['access_code'],
                    "reference": reference
                })
            return Response({"error": "Paystack initialization failed"}, status=400)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

class VerifyDepositView(APIView):
    """
    Step 2: Verify the payment after the user returns.
    If success, update wallet balance.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        reference = request.data.get('reference')

        if not reference:
            return Response({"error": "Reference required"}, status=400)

        try:
            txn = Transaction.objects.get(reference=reference)
            
            if txn.status == 'success':
                return Response({"message": "Transaction already verified"}, status=200)

            # Verify with Paystack
            headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
            response = requests.get(f"{PAYSTACK_VERIFY_URL}{reference}", headers=headers)
            res_data = response.json()

            if response.status_code == 200 and res_data['data']['status'] == 'success':
                # ATOMIC UPDATE
                with transaction.atomic():
                    # 1. Update Transaction
                    txn.status = 'success'
                    txn.save()

                    # 2. Credit Wallet
                    txn.wallet.balance += txn.amount
                    txn.wallet.save()

                return Response({"message": "Deposit successful!", "new_balance": txn.wallet.balance})
            
            else:
                txn.status = 'failed'
                txn.save()
                return Response({"error": "Payment verification failed"}, status=400)

        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found"}, status=404)

class MonnifyWebhookView(APIView):
    permission_classes = [permissions.AllowAny] # Monnify can't log in

    def post(self, request):
        # 1. SECURITY: Verify Monnify Signature
        monnify_signature = request.headers.get('monnify-signature')
        if not monnify_signature:
            return Response({"status": "error", "message": "No signature"}, status=400)

        secret = settings.MONNIFY_SECRET_KEY 
        computed_hash = hmac.new(
            secret.encode(), 
            request.body, 
            digestmod=hashlib.sha512
        ).hexdigest()

        if not hmac.compare_digest(computed_hash, monnify_signature):
            print("🚨 SECURITY ALERT: Invalid Webhook Signature!")
            return Response({"status": "error", "message": "Invalid signature"}, status=400)

        data = request.data
        event_data = data.get('eventData', {})
        
        # 1. Capture the Reference (Simulator uses transactionReference)
        txn_ref = event_data.get('transactionReference')
        
        # 2. Capture the Account Reference (This links the payment to the User)
        # In Monnify Webhooks, this is usually under 'product' -> 'reference'
        product_data = event_data.get('product', {})
        account_ref = product_data.get('reference')

        print(f"DEBUG: Webhook Received. Txn: {txn_ref}, WalletRef: {account_ref}")

        if not txn_ref or not account_ref:
            return Response({"status": "error", "message": "Incomplete data"}, status=400)

        try:
            with transaction.atomic():
                # Locate the wallet using the reference assigned during creation
                wallet = Wallet.objects.select_for_update().get(account_reference=account_ref)
                
                # Prevent double-crediting
                if Transaction.objects.filter(reference=txn_ref).exists():
                    return Response({"status": "ignored"}, status=200)

                amount = Decimal(str(event_data.get('amountPaid', 0)))
                
                # Update Balance
                wallet.balance += amount
                wallet.save()

                # Create History Record
                Transaction.objects.create(
                    wallet=wallet,
                    amount=amount,
                    transaction_type='deposit',
                    status='success',
                    reference=txn_ref,
                    description=f"Deposit: {event_data.get('bankName', 'Transfer')}"
                )
                
            return Response({"status": "success"}, status=200)
        except Wallet.DoesNotExist:
            print(f"❌ Wallet not found for ref: {account_ref}")
            return Response({"status": "error", "message": "Wallet not found"}, status=404)

class WithdrawalView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedUser]

    def post(self, request):
        amount = Decimal(str(request.data.get('amount', 0)))
        bank_account_id = request.data.get('bank_account_id')
        
        # 1. Validation
        if amount < 500: # Example minimum withdrawal
            return Response({"error": "Minimum withdrawal is ₦500"}, status=400)
            
        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=request.user)
                bank_acc = BankAccount.objects.get(id=bank_account_id, user=request.user)

                if wallet.balance < amount:
                    return Response({"error": "Insufficient balance"}, status=400)

                # 2. Deduct from wallet immediately
                wallet.balance -= amount
                wallet.save()

                # 3. Create Transaction Record (Pending)
                ref = f"WD-{uuid.uuid4().hex[:10]}"
                txn = Transaction.objects.create(
                    wallet=wallet,
                    amount=-amount,
                    transaction_type='withdrawal',
                    status='pending',
                    reference=ref,
                    description=f"Withdrawal to {bank_acc.bank_name}"
                )

                # 4. Call Monnify
                client = MonnifyClient()
                resp = client.initiate_withdrawal(
                    amount, ref, bank_acc.bank_code, 
                    bank_acc.account_number, f"Globalink Payout: {request.user.full_name}"
                )

                if resp and resp.get('requestStatus') == "HTTP_OK":
                    return Response({"message": "Withdrawal initiated successfully"}, status=200)
                else:
                    # If Monnify fails, roll back the balance
                    raise Exception("Monnify payout failed")

        except Exception as e:
            return Response({"error": str(e)}, status=500)

class VerifyBankAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account_number = request.data.get('account_number')
        bank_code = request.data.get('bank_code')

        if not account_number or not bank_code:
            return Response({"error": "Account number and bank code are required"}, status=400)

        client = MonnifyClient()
        account_data = client.verify_bank_account(account_number, bank_code)

        if account_data:
            return Response({
                "account_name": account_data.get('accountName'),
                "status": "success"
            })
        
        return Response({"error": "Could not verify account. Please check details."}, status=400)

class VTPassPurchaseView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsVerifiedUser]

    def post(self, request):
        print(f"DEBUG: Incoming Purchase Data: {request.data}")

        service_id = request.data.get('service_id') or request.data.get('serviceID')
        variation_code = request.data.get('variation_code')
        phone = request.data.get('phone')
        amount_raw = request.data.get('amount')

        # 1. Basic Validation
        if not all([service_id, variation_code, phone, amount_raw]):
            return Response({"error": "Missing required fields"}, status=400)

        # 2. Logic Check: Prevent Mismatched Networks
        # If service is mtn-data but code starts with 'glo', stop it here.
        if "mtn" in service_id and "glo" in variation_code:
            return Response({"error": "Network mismatch: MTN service cannot use Glo plan"}, status=400)

        amount = Decimal(str(amount_raw))
        wallet = request.user.wallet

        # 3. Generate Request ID
        now = datetime.now(pytz.timezone('Africa/Lagos'))
        request_id = now.strftime('%Y%m%d%H%M') + uuid.uuid4().hex[:10]

        try:
            with transaction.atomic():
                # Lock the wallet row so no other process can touch it during this second
                wallet = Wallet.objects.select_for_update().get(user=request.user)

                if wallet.balance < amount:
                    return Response({"error": "Insufficient wallet balance"}, status=400)

                wallet.balance -= amount
                wallet.save()

                client = VTPassClient()
                resp = client.purchase_data(request_id, service_id, variation_code, phone, amount)
                
                print(f"DEBUG: VTpass API Response: {resp}")

                # VTpass Response Check
                if resp.get('code') == '000' or resp.get('response_description') == 'TRANSACTION SUCCESSFUL':
                    Transaction.objects.create(
                        wallet=wallet, amount=-amount,
                        transaction_type='bill_payment', status='success',
                        description=f"{service_id.upper()} {variation_code} to {phone}",
                        reference=request_id
                    )
                    return Response({"message": "Purchase successful", "data": resp})
                else:
                    # API FAILED: Raise an error to trigger the ROLLBACK
                    # This automatically puts the money back into wallet.balance
                    raise Exception(resp.get('response_description', 'Transaction Failed'))

        except Exception as e:
            import traceback
            print("!!! CRITICAL ERROR TRACEBACK:")
            print(traceback.format_exc()) 
            return Response({"error": str(e)}, status=400)

class VTPassVariationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        service_id = request.query_params.get('service_id')
        if not service_id:
            return Response({"error": "service_id is required"}, status=400)
        
        from .vtpass import VTPassClient
        client = VTPassClient()
        data = client.get_data_plans(service_id)
        return Response(data)