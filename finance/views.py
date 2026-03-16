import logging
import re
from django.contrib.auth import get_user_model
from datetime import datetime
import pytz
import uuid
import hashlib
import hmac
from decimal import Decimal
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework import permissions, status
from django.db import transaction
from .models import Wallet, Transaction, BankAccount
from market.models import Order
from .serializers import WalletSerializer
from .services import PaystackService, WalletService # Our new services
from users.permissions import IsVerifiedUser
from .utils import MonnifyAPI

from .vtpass import VTPassClient  # Add this near your other imports

logger = logging.getLogger(__name__)

class WalletDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # PROFESSIONAL LOGIC: If account is missing, generate it via Monnify
        if not wallet.account_number:
            account_data = MonnifyAPI.create_virtual_account(request.user)
            if account_data:
                wallet.account_number = account_data['account_number']
                wallet.bank_name = account_data['bank_name']
                wallet.bank_code = account_data['bank_code']
                wallet.save()

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

class MonnifyWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # 1. Security Check: Use hmac to verify the signature from Monnify
        monnify_signature = request.headers.get('monnify-signature')
        computed_hash = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode(), 
            request.body, 
            hashlib.sha512
        ).hexdigest()

        if monnify_signature != computed_hash:
            return Response({"error": "Unauthorized"}, status=401)

        data = request.data
        if data.get('eventType') == "SUCCESSFUL_TRANSACTION":
            body = data.get('eventData', {})
            payment_ref = body.get('paymentReference')
            
            # Use the accountReference to find the specific wallet
            acc_ref = body.get('product', {}).get('reference')
            
            try:
                wallet = Wallet.objects.get(account_reference=acc_ref)
                amount = Decimal(str(body.get('amountPaid')))

                # 2. Idempotency Check (Don't process twice)
                if not Transaction.objects.filter(reference=payment_ref).exists():
                    with transaction.atomic():
                        wallet.balance += amount
                        wallet.save()

                        Transaction.objects.create(
                            wallet=wallet,
                            amount=amount,
                            transaction_type='deposit',
                            status='success',
                            reference=payment_ref,
                            description=f"Automated Deposit via {body.get('bankName')}"
                        )
                return Response({"status": "success"}, status=200)
            except Wallet.DoesNotExist:
                return Response({"error": "Wallet not found"}, status=404)

        return Response({"status": "accepted"}, status=200)


from .nellobyte import NellobyteClient

class VTPassPurchaseView(APIView):
    """Refactored to Nellobyte Systems"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        service_id = request.data.get('service_id')
        data_plan = request.data.get('variation_code')
        phone = request.data.get('phone')
        amount = Decimal(str(request.data.get('amount')))

        from .utils import generate_vtpass_request_id
        request_id = generate_vtpass_request_id()

        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=request.user)
                if wallet.balance < amount:
                    return Response({"error": "Insufficient balance"}, status=400)

                wallet.balance -= amount
                wallet.save()

                client = NellobyteClient()
                resp = client.purchase_data(request_id, service_id, data_plan, phone)

                # 100 = Order Received (Nellobyte success code)
                if str(resp.get('statuscode')) == '100':
                    Transaction.objects.create(
                        wallet=wallet, amount=-amount,
                        transaction_type='bill_payment', status='success',
                        description=f"Nellobyte: {service_id.upper()} to {phone}",
                        reference=request_id
                    )
                    return Response({"message": "Purchase successful", "data": resp})
                else:
                    raise Exception(resp.get('status', 'API Error'))
        except Exception as e:
            return Response({"error": str(e)}, status=400)

class VTPassVariationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        service_id = request.query_params.get('service_id')
        client = NellobyteClient()
        network_code = client._get_network_code(service_id)
        
        # If API is failing, this returns [], which our Layer 1 frontend handles
        raw_plans = client.fetch_plans(network_code)

        formatted = [{
            "variation_code": str(p.get("ID")),
            "name": p.get("Name"),
            "variation_amount": str(p.get("Amount"))
        } for p in raw_plans]

        return Response({"content": {"variations": formatted}})

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

class DepositNotificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        sender = request.data.get('sender_name')
        
        # Create a PENDING transaction record
        Transaction.objects.create(
            wallet=request.user.wallet,
            amount=amount,
            transaction_type='deposit',
            status='pending', # <--- Important
            description=f"Manual Deposit: {sender} ({request.user.username})"
        )
        # Optional: Send yourself an email or Telegram alert here!
        return Response({"message": "Admin notified"}, status=200)



@api_view(['GET', 'POST']) # Clubkonnect usually uses GET for callbacks
@permission_classes([AllowAny]) # Must be public so Clubkonnect can reach it
def clubkonnect_deposit_webhook(request):
    # Clubkonnect typically sends: orderid, statuscode, amount, and orderremark
    # The 'orderremark' usually contains the account name we set up: "NELLOBYTE-YUS (username)"
    User = get_user_model()
    
    remark = request.query_params.get('orderremark', '')
    amount = request.query_params.get('amount', 0)
    status_code = request.query_params.get('statuscode')

    if status_code == '200': # 200 usually means success in their callbacks
        # 1. Extract username from the remark "NELLOBYTE-YUS (username)"
        try:
            match = re.search(r'\((.*?)\)', remark)
            if not match:
                return Response("Username not found in remark", status=400)
            
            username = match.group(1)
            
            # 2. Find the user and their wallet
            user = User.objects.get(username=username)
            wallet, _ = Wallet.objects.get_or_create(user=user)
            
            # 3. Credit the wallet
            wallet.balance += Decimal(str(amount))
            wallet.save()
            
            # 4. Record the transaction
            Transaction.objects.create(
                wallet=wallet, 
                amount=Decimal(str(amount)), 
                transaction_type='deposit', 
                status='success',
                description=f"Auto-Fund: {remark}"
            )
            return Response("Wallet Updated", status=200)
        except User.DoesNotExist:
            return Response(f"User {username} not found", status=404)
        except Exception as e:
            return Response(f"Error: {str(e)}", status=400)

    return Response("Invalid Status", status=400)
