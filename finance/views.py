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
from .services import WalletService # Our new services
from users.permissions import IsVerifiedUser
from .utils import MonnifyAPI

from .vtpass import VTPassClient  # Add this near your other imports

logger = logging.getLogger(__name__)

class WalletDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # SAFETY NET: If user has no account yet, generate it now
        if not wallet.account_number:
            try:
                acc_data = MonnifyAPI.create_virtual_account(request.user)
                if acc_data:
                    wallet.account_number = acc_data['account_number']
                    wallet.bank_name = acc_data['bank_name']
                    wallet.bank_code = acc_data['bank_code']
                    wallet.save()
            except Exception as e:
                logger.error(f"On-the-fly account generation failed: {e}")

        serializer = WalletSerializer(wallet)
        return Response(serializer.data)



from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def monnify_webhook(request):
    # 1. Security Check: Verify Monnify Signature
    signature = request.headers.get('monnify-signature')
    if not signature:
        return Response({"error": "No signature"}, status=status.HTTP_400_BAD_REQUEST)

    # SECURE: Recompute hash and use compare_digest
    computed_hash = hmac.new(
        settings.MONNIFY_SECRET_KEY.encode(),
        request.body,
        hashlib.sha512
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, signature):
        logger.warning(f"Invalid Webhook Signature attempt from {request.META.get('REMOTE_ADDR')}")
        return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

    event_type = request.data.get('eventType')
    data = request.data.get('eventData', {})
    
    # CASE 1: Incoming Deposit (User funding wallet)
    if event_type == 'SUCCESSFUL_TRANSACTION':
        payment_ref = data.get('paymentReference')
        amount_to_credit = Decimal(str(data.get('amountPaid'))) 
        account_ref = data.get('product', {}).get('reference') 

        try:
            # Atomic block with row-level locking
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(account_reference=account_ref)
                
                # IDEMPOTENCY: Check if this payment reference was already processed
                if not Transaction.objects.filter(reference=payment_ref).exists():
                    # Update wallet balance
                    wallet.balance += amount_to_credit
                    wallet.save()
                    
                    # Log the transaction
                    Transaction.objects.create(
                        wallet=wallet,
                        amount=amount_to_credit,
                        transaction_type=Transaction.TransactionType.DEPOSIT,
                        status=Transaction.Status.SUCCESS,
                        reference=payment_ref,
                        description=f"Deposit: {data.get('bankName')} - Ref: {payment_ref}"
                    )
            logger.info(f"✅ Wallet {wallet.id} credited with ₦{amount_to_credit}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)

        except Wallet.DoesNotExist:
            logger.error(f"❌ Webhook Error: Wallet with reference {account_ref} not found.")
            return Response({"error": "Wallet not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"❌ Webhook Processing Error: {str(e)}")
            return Response({"error": "Internal Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # CASE 2: Outgoing Withdrawal (Monnify finished sending money to bank)
    elif event_type == 'DISBURSEMENT_SUCCESS':
        ref = data.get('reference')
        Transaction.objects.filter(reference=ref).update(status=Transaction.Status.SUCCESS)
        logger.info(f"✅ Disbursement successful for ref {ref}")
        return Response({"status": "success"}, status=status.HTTP_200_OK)

    elif event_type == 'DISBURSEMENT_FAILED':
        ref = data.get('reference')
        try:
            with transaction.atomic():
                ledger = Transaction.objects.select_for_update().get(reference=ref)
                if ledger.status != Transaction.Status.FAILED:
                    # Refund the user because the bank transfer failed
                    ledger.wallet.balance += abs(ledger.amount)
                    ledger.wallet.save()
                    ledger.status = Transaction.Status.FAILED
                    ledger.description += " (Failed: Refunded)"
                    ledger.save()
            logger.warning(f"⚠️ Disbursement failed and refunded for ref {ref}")
        except Exception as e:
            logger.error(f"❌ Webhook Refund failure: {e}")

    return Response({"status": "received"}, status=status.HTTP_200_OK)


from .nellobyte import NellobyteClient

class VTPassPurchaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        service_id = request.data.get('service_id')
        data_plan = request.data.get('variation_code')
        phone = request.data.get('phone')
        amount = Decimal(str(request.data.get('amount')))
        
        from .utils import generate_vtpass_request_id
        request_id = request.data.get('request_id') or generate_vtpass_request_id()

        # 1. Idempotency Check
        if Transaction.objects.filter(reference=request_id).exists():
            return Response({"error": "Duplicate transaction request"}, status=400)

        # 2. Pre-debit and log PENDING transaction
        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=request.user)
                if wallet.balance < amount:
                    return Response({"error": "Insufficient balance"}, status=400)

                wallet.balance -= amount
                wallet.save()

                # Create record before calling API
                ledger = Transaction.objects.create(
                    wallet=wallet, 
                    amount=-amount,
                    transaction_type=Transaction.TransactionType.BILL_PAYMENT, 
                    status=Transaction.Status.PENDING,
                    description=f"Purchase: {service_id.upper()} for {phone}",
                    reference=request_id
                )
        except Exception as e:
            return Response({"error": f"Internal Error: {str(e)}"}, status=500)

        # 3. External API Call (OUTSIDE atomic block)
        try:
            client = NellobyteClient()
            resp = client.purchase_data(request_id, service_id, data_plan, phone)
            
            if str(resp.get('statuscode')) == '100':
                ledger.status = Transaction.Status.SUCCESS
                ledger.save()
                return Response({"message": "Purchase successful", "data": resp})
            else:
                # 4. Auto-Refund on API failure
                with transaction.atomic():
                    wallet = Wallet.objects.select_for_update().get(user=request.user)
                    wallet.balance += amount
                    wallet.save()
                    
                    ledger.status = Transaction.Status.FAILED
                    ledger.description += f" (Refunded: {resp.get('status', 'API Error')})"
                    ledger.save()
                return Response({"error": f"Provider error: {resp.get('status')}"}, status=400)

        except Exception as e:
            # Handle unexpected network timeouts/crashes
            logger.error(f"Bill Payment Network Error: {e}")
            return Response({"message": "Transaction pending. Contact support if not received."}, status=500)

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
            account_name = MonnifyAPI.resolve_bank_account(account_number, bank_code)
            return Response({"account_name": account_name}, status=200)
        except Exception as e:
            # 3. Print the EXACT error from Monnify to the console
            print(f"🚨 MONNIFY API FAILURE: {str(e)}")
            # 4. Return the ACTUAL error to your React Native app
            return Response({"error": f"Monnify says: {str(e)}"}, status=400)

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
