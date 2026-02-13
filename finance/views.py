import requests
import logging
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
from .services import PaystackService, WalletService # Our new services
from users.permissions import IsVerifiedUser
# finance/views.py

from .vtpass import VTPassClient  # Add this near your other imports

class WalletDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        wallet.transactions_preview = wallet.transactions.all().order_by('-created_at')[:20]
        serializer = WalletSerializer(wallet)
        return Response(serializer.data)

class InitiateDepositView(APIView):
    """
    Step 1: User requests to deposit money.
    Uses PaystackService to get authorization URL.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # DEBUG: This will show up in your PythonAnywhere "Server Log"
        print(f"--- DEPOSIT LOG ---")
        print(f"Data received: {request.data}")
        print(f"User: {request.user.email}")

        amount = request.data.get('amount')
        
        if not amount:
            return Response({"error": "Amount is missing in request"}, status=400)

        try:
            # Check if amount is a valid number
            clean_amount = Decimal(str(amount))
            if clean_amount <= 0:
                return Response({"error": "Deposit amount must be greater than zero"}, status=400)
        except Exception:
            return Response({"error": f"Invalid amount format: {amount}"}, status=400)

        reference = f"DEP-{uuid.uuid4().hex[:12].upper()}"
        
        try:
            # 1. Create a Pending Transaction Ledger Entry
            Transaction.objects.create(
                wallet=request.user.wallet,
                amount=Decimal(str(amount)),
                transaction_type='deposit',
                status='pending',
                reference=reference,
                description="Wallet Top-up via Paystack"
            )

            # 2. Call Service to get Paystack URL
            auth_data = PaystackService.initiate_deposit(
                wallet=request.user.wallet,
                email=request.user.email,
                amount=amount,
                reference=reference
            )

            return Response(auth_data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

class VerifyDepositView(APIView):
    """
    Step 2: Client-side verification (After redirection).
    Provides immediate feedback to the UI.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        reference = request.data.get('reference')
        if not reference:
            return Response({"error": "Reference is required"}, status=400)

        # Call service to verify and credit
        # Note: We still rely on webhooks for the final truth
        data = PaystackService.verify_payment(reference)
        
        if data and data.get('status') == 'success':
            wallet, created = PaystackService.credit_wallet(
                reference=reference, 
                amount_kobo=data.get('amount')
            )
            return Response({
                "message": "Deposit verified", 
                "balance": wallet.balance
            }, status=status.HTTP_200_OK)
        
        return Response({"error": "Payment not successful"}, status=400)

class PaystackWebhookView(APIView):
    """
    The Source of Truth. Paystack calls this directly.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        signature = request.headers.get('x-paystack-signature')
        payload = request.body

        # 1. Security Check
        if not PaystackService.verify_webhook(payload, signature):
            return Response({"error": "Invalid signature"}, status=400)

        data = request.data
        event = data.get('event')

        # 2. Handle successful charge
        if event == "charge.success":
            reference = data['data']['reference']
            amount_kobo = data['data']['amount']
            
            try:
                PaystackService.credit_wallet(reference, amount_kobo)
            except Exception as e:
                # We log this for the admin but tell Paystack we got it
                # This prevents Paystack from hammering your server with retries
                logger = logging.getLogger(__name__)
                logger.error(f"Critical Webhook Failure: {str(e)} for Ref: {reference}")
                return Response({"status": "error", "message": "Processed with errors"}, status=200)

        return Response({"status": "accepted"}, status=200)


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

class VerifyBankAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # 1. Log what we received
        print(f"DEBUG: Data received from App: {request.data}")
        
        account_number = request.data.get('account_number')
        bank_code = request.data.get('bank_code')

        if not account_number or not bank_code:
            return Response({
                "error": f"Missing data. Need account_number and bank_code. Received: {request.data}"
            }, status=400)

        try:
            # 2. Call the service and catch the specific error
            account_name = PaystackService.resolve_bank_account(account_number, bank_code)
            return Response({"account_name": account_name}, status=200)
        except Exception as e:
            # 3. Print the EXACT error from Paystack to the console
            print(f"🚨 PAYSTACK API FAILURE: {str(e)}")
            # 4. Return the ACTUAL error to your React Native app
            return Response({"error": f"Paystack says: {str(e)}"}, status=400)

class WithdrawalView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # 1. Debug: What did we actually get?
        print(f"DEBUG WITHDRAW DATA: {request.data}")
        
        pin = request.data.get('pin')
        amount = request.data.get('amount')
        account_number = request.data.get('account_number')
        bank_code = request.data.get('bank_code')

        if not all([pin, amount, account_number, bank_code]):
            # This will show you exactly what is missing
            missing = [k for k in ['pin', 'amount', 'account_number', 'bank_code'] if not request.data.get(k)]
            return Response({"error": f"Missing fields: {', '.join(missing)}"}, status=400)

        # 2. Check PIN
        if not request.user.transaction_pin:
            return Response({"error": "No PIN set. Visit profile to set one."}, status=400)

        if not request.user.check_transaction_pin(pin):
            return Response({"error": "Incorrect Transaction PIN"}, status=400)

        try:
            # 3. Process
            amount_decimal = Decimal(str(amount))
            WalletService.initiate_withdrawal(
                user=request.user,
                amount=amount_decimal,
                account_number=account_number,
                bank_code=bank_code
            )
            return Response({"message": "Withdrawal successful"}, status=200)
        except Exception as e:
            # 4. If Paystack or WalletService fails, we need to know why
            print(f"WITHDRAWAL FAILURE: {str(e)}")
            return Response({"error": str(e)}, status=400)