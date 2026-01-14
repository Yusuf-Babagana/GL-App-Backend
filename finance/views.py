import requests
import uuid
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db import transaction
from .models import Wallet, Transaction
from .serializers import WalletSerializer

PAYSTACK_SECRET_KEY = "sk_test_f4bc777ea48e3fe932aecea60f0ebd8db0e7cd3c" # REPLACE WITH YOUR KEY
PAYSTACK_INITIATE_URL = "https://api.paystack.co/transaction/initialize"
PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify/"

class WalletDetailView(APIView):
    """
    Get the current user's wallet balance and history.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        # Limit to last 20 transactions for performance
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