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
# finance/views.py

from .vtpass import VTPassClient  # Add this near your other imports

PAYSTACK_SECRET_KEY = "sk_test_f4bc777ea48e3fe932aecea60f0ebd8db0e7cd3c" # REPLACE WITH YOUR KEY
PAYSTACK_INITIATE_URL = "https://api.paystack.co/transaction/initialize"
PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify/"

class WalletDetailView(APIView):
    """
    Get the current user's wallet balance and history.
    If no virtual account exists, it attempts to generate one.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        if not wallet.account_number:
            # 1. Ensure we have a reference
            if not wallet.account_reference:
                wallet.account_reference = str(uuid.uuid4())
                wallet.save()

            # 2. Hard Fallback for Name/Email
            user_name = request.user.full_name or f"Globalink User {request.user.id}"
            user_email = request.user.email # email is unique/required in your model

            try:
                client = MonnifyClient()
                resp = client.generate_virtual_account(
                    user_name, 
                    user_email, 
                    wallet.account_reference
                )
                
                if resp and resp.get('requestSuccessful') is True: # Changed this line
                    body = resp.get('responseBody')
                    if body:
                        # Monnify returns the details directly in responseBody for this endpoint
                        wallet.account_number = body.get('accountNumber')
                        wallet.bank_name = body.get('bankName')
                        wallet.bank_code = body.get('bankCode')
                        wallet.save()
                        print(f">>> SUCCESS: Wallet updated with Account: {wallet.account_number}")
                else:
                    # This was triggering because we checked the wrong key
                    print(f">>> FAILED: Monnify returned {resp.get('responseMessage')}")

            except Exception as e:
                print(f"!!! Monnify Error: {str(e)}")

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
    permission_classes = [permissions.AllowAny] 

    def post(self, request):
        data = request.data
        # 1. Monnify sends events wrapped in 'eventData'
        event_type = data.get('eventType')
        event_data = data.get('eventData', {})

        # 2. Check for successful transaction event
        if event_type == "SUCCESSFUL_TRANSACTION" or event_data.get('paymentStatus') == 'PAID':
            
            # 3. Monnify Reserved Accounts use 'product' -> 'reference'
            # This must match the 'account_reference' (UUID) in your Wallet model
            account_ref = event_data.get('product', {}).get('reference')
            amount_paid = event_data.get('amountPaid')

            if not account_ref:
                return Response({"status": "error", "message": "No reference found"}, status=400)

            try:
                # We use the existing 'transaction' import from line 12
                with transaction.atomic():
                    # Find wallet by the UUID reference
                    wallet = Wallet.objects.select_for_update().get(account_reference=account_ref)
                    
                    # Update balance
                    wallet.balance += Decimal(str(amount_paid))
                    wallet.save()

                    # Create Transaction history
                    Transaction.objects.create(
                        wallet=wallet,
                        amount=amount_paid,
                        transaction_type='deposit',
                        status='success',
                        reference=event_data.get('transactionReference'),
                        description=f"Deposit: {event_data.get('bankName', 'Bank Transfer')}"
                    )
                
                return Response({"status": "success"}, status=200)

            except Wallet.DoesNotExist:
                return Response({"status": "error", "message": "Wallet not found"}, status=404)
        
        return Response({"status": "ignored"}, status=200)

class WithdrawalView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        print(f"DEBUG: Incoming Purchase Data: {request.data}")

        service_id = request.data.get('service_id')
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