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
from rest_framework import permissions, status, generics
from django.db import transaction
from .models import Wallet, Transaction, BankAccount
from market.models import Order
from .serializers import WalletSerializer, TransactionSerializer
from .services import WalletService, WithdrawalService # Our new services
from users.permissions import IsVerifiedUser
from .utils import MonnifyAPI

from .vtpass import VTPassClient  # Add this near your other imports

logger = logging.getLogger(__name__)

class TransactionListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.filter(wallet=self.request.user.wallet).order_by('-created_at')

class WalletDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            # 1. get_or_create ensures no crash if the user somehow has no wallet
            wallet, created = Wallet.objects.get_or_create(user=request.user)
            
            # 2. Safety Net for Virtual Account
            if not wallet.account_number:
                try:
                    acc_data = MonnifyAPI.create_virtual_account(request.user)
                    if acc_data:
                        wallet.account_number = acc_data.get('account_number')
                        wallet.bank_name = acc_data.get('bank_name')
                        wallet.bank_code = acc_data.get('bank_code')
                        # VERY IMPORTANT: Monnify Webhook needs this reference to find the wallet
                        wallet.account_reference = acc_data.get('account_reference')
                        wallet.save()
                except Exception as e:
                    logger.error(f"Monnify Account Generation Error: {e}")

            # 3. Serialize and return
            serializer = WalletSerializer(wallet)
            return Response(serializer.data)
            
        except Exception as e:
            # This will show up in your PythonAnywhere "Error Log"
            logger.error(f"WalletDetailView 500 Error: {str(e)}")
            return Response({"error": "Internal Server Error", "details": str(e)}, status=500)



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
        amount_paid = Decimal(str(data.get('amountPaid')))       # Gross (e.g., 500)
        settlement_amt = Decimal(str(data.get('settlementAmount'))) # Net (e.g., 491.94)
        fee = amount_paid - settlement_amt                       # The Fee (e.g., 8.06)
        
        account_ref = data.get('product', {}).get('reference') 

        try:
            # Atomic block with row-level locking
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(account_reference=account_ref)
                
                # IDEMPOTENCY: Check if this payment reference was already processed
                if not Transaction.objects.filter(reference=payment_ref).exists():
                    # We credit the SETTLEMENT amount (minus fee)
                    wallet.balance += settlement_amt
                    wallet.save()
                    
                    # Log the transaction
                    Transaction.objects.create(
                        wallet=wallet,
                        amount=settlement_amt,
                        transaction_type=Transaction.TransactionType.DEPOSIT,
                        status=Transaction.Status.SUCCESS,
                        reference=payment_ref,
                        # Better description for the user
                        description=f"Bank Deposit (Fee: ₦{fee})" 
                    )
            logger.info(f"✅ Wallet {wallet.id} credited with ₦{settlement_amt} (Settlement)")
            return Response({"status": "success"}, status=200)

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

class DataPurchaseView(APIView):
    """
    Handles Data Bundle purchases using NellobyteClient.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        logger.info(f"Data Purchase Request: {request.data}")
        service_id = request.data.get('service_id')
        data_plan = request.data.get('variation_code')
        phone = request.data.get('phone')
        
        raw_amount = request.data.get('amount')
        if not all([service_id, data_plan, phone, raw_amount]):
            logger.error("Data Purchase 400: Missing required fields.")
            return Response({"error": "Missing service_id, variation_code, phone, or amount."}, status=400)

        try:
            amount = Decimal(str(raw_amount))
        except Exception as e:
            logger.error(f"Data Purchase 400: Invalid amount format: {raw_amount}")
            return Response({"error": "Invalid amount format.", "details": str(e)}, status=400)
        
        request_id = str(uuid.uuid4().hex)[:12]

        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=request.user)
                if wallet.balance < amount:
                    logger.error(f"Data Purchase 400: Insufficient Balance. Need {amount}, have {wallet.balance}")
                    return Response({"error": "Insufficient wallet balance."}, status=400)

                wallet.balance -= amount
                wallet.save()

                ledger = Transaction.objects.create(
                    wallet=wallet, 
                    amount=-amount,
                    transaction_type=Transaction.TransactionType.BILL_PAYMENT, 
                    status=Transaction.Status.PENDING,
                    description=f"Nellobyte Data: {service_id.upper()} ({data_plan}) to {phone}",
                    reference=request_id
                )
        except Exception as e:
            logger.error(f"Data Purchase 500: Internal Wallet Error: {e}")
            return Response({"error": f"Internal Wallet Error: {str(e)}"}, status=500)

        # 3. Call Nellobyte
        try:
            client = NellobyteClient()
            logger.info(f"Calling Nellobyte with req_id={request_id}, svc={service_id}, plan={data_plan}, ph={phone}")
            resp = client.purchase_data(request_id, service_id, data_plan, phone)
            
            status_code = str(resp.get('statuscode'))
            
            if status_code == '100':
                ledger.status = Transaction.Status.SUCCESS
                ledger.save()
                return Response({
                    "message": "Data purchase successful!",
                    "order_id": resp.get('orderid'),
                    "new_balance": float(wallet.balance)
                }, status=200)
            else:
                with transaction.atomic():
                    w = Wallet.objects.select_for_update().get(user=request.user)
                    w.balance += amount
                    w.save()
                    
                    ledger.status = Transaction.Status.FAILED
                    error_msg = resp.get('status', 'Provider rejected request')
                    ledger.description += f" (Refunded: {error_msg})"
                    ledger.save()
                
                logger.error(f"Data Purchase 400: Nellobyte Error: {error_msg} | Code: {status_code} | Raw: {resp}")
                return Response({"error": f"Nellobyte Error: {error_msg}"}, status=400)

        except Exception as e:
            logger.error(f"Nellobyte Network/Critical Failure: {e}")
            return Response({"message": "Transaction submitted. Check history for status updates."}, status=202)

class DataVariationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        service_id = request.query_params.get('service_id') # e.g., 'mtn-data'
        client = NellobyteClient()
        
        # Map your frontend string to Nellobyte's numeric network ID
        network_mapping = {'mtn-data': '1', 'glo-data': '2', 'airtel-data': '3', '9mobile-data': '4'}
        network_id = network_mapping.get(service_id)

        if not network_id:
            return Response({"error": "Invalid service"}, status=400)

        all_plans = client.fetch_all_variations(network_id)

        formatted_plans = []
        for plan in all_plans:
            # Add your profit margin (e.g., ₦50)
            original_price = float(plan.get('price', 0))
            selling_price = original_price + 50 

            formatted_plans.append({
                "variation_code": str(plan.get('ID')),
                "name": str(plan.get('name', '')).upper(),
                "variation_amount": str(int(selling_price)),
                "type": plan.get('type', 'Standard') # e.g., 'SME' or 'Gifting'
            })

        return Response({"plans": formatted_plans})


class VerifyBankAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # 1. Log what we received
        print(f"DEBUG: Params received from App: {request.query_params}")
        
        account_number = request.query_params.get('account_number')
        bank_code = request.query_params.get('bank_code')

        if not account_number or not bank_code:
            return Response({
                "error": f"Missing query params. Need account_number and bank_code."
            }, status=400)

        try:
            # 2. Call the service and catch the specific error
            account_name, error_msg = MonnifyAPI.resolve_bank_account(account_number, bank_code)
            if account_name:
                return Response({"account_name": account_name}, status=200)
            return Response({"error": error_msg}, status=400)
        except Exception as e:
            # 3. Print the EXACT error from Monnify to the console
            print(f"🚨 MONNIFY API FAILURE: {str(e)}")
            # 4. Return the ACTUAL error to your React Native app
            return Response({"error": f"Monnify says: {str(e)}"}, status=400)

class BankListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            # Call Monnify utility to get the bank list
            banks = MonnifyAPI.get_banks()
            return Response(banks, status=200)
        except Exception as e:
            logger.error(f"Failed to fetch banks: {e}")
            return Response({"error": "Could not load bank list"}, status=500)

class WithdrawalView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        bank_code = request.data.get('bank_code')
        account_number = request.data.get('account_number')
        pin = request.data.get('pin')

        if not all([amount, bank_code, account_number, pin]):
            return Response({"error": "Missing required fields (amount, bank_code, account_number, pin)"}, status=400)

        # Security: Check PIN
        if not request.user.transaction_pin:
            return Response({"error": "No PIN set. Visit profile to set one."}, status=400)

        if not request.user.check_transaction_pin(pin):
            return Response({"error": "Invalid Transaction PIN"}, status=400)

        try:
            success, result = WithdrawalService.initiate_payout(
                user=request.user,
                amount=amount,
                bank_code=bank_code,
                account_number=account_number
            )

            if success:
                return Response({"message": result.get("message", "Success")}, status=200)
            
            # Error Formatting Strategy for the Frontend
            error_msg = result.get("error", "Transaction rejected by provider")
            error_code = result.get("code", "UNKNOWN")
            
            logger.error(f"Monnify Payout Blocked: {error_code} - {error_msg}")
            return Response({
                "error": error_msg,
                "code": error_code
            }, status=400)

        except Exception as e:
            logger.error(f"WITHDRAWAL FAILURE: {str(e)}")
            return Response({"error": "Internal Error Handling Withdrawal", "details": str(e)}, status=500)

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
