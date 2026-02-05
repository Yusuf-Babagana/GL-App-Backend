import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from finance.models import Transaction
from finance.utils import WalletManager

class PurchaseDataView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        service_id = request.data.get("serviceID") # e.g., 'glo-data'
        variation_code = request.data.get("variation_code") # e.g., 'glo-100mb'
        phone = request.data.get("phone")
        amount = request.data.get("amount") # The price of the plan

        if not all([service_id, variation_code, phone, amount]):
            return Response({"error": "Missing required fields"}, status=400)

        # 1. Deduct from Wallet locally first
        description = f"Data Purchase: {service_id} for {phone}"
        payment_success, message = WalletManager.process_payment(
            user=user,
            amount=amount,
            transaction_type=Transaction.TransactionType.BILL_PAYMENT,
            description=description
        )

        if not payment_success:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Call VTpass API
        vtpass_url = f"{settings.VTPASS_BASE_URL}/pay"
        payload = {
            "request_id": f"GL-{Transaction.objects.filter(wallet__user=user).count() + 1}", # Unique ID
            "serviceID": service_id,
            "billersCode": phone,
            "variation_code": variation_code,
            "amount": amount,
            "phone": phone
        }
        headers = {
            "api-key": settings.VTPASS_API_KEY,
            "secret-key": settings.VTPASS_SECRET_KEY,
        }

        try:
            # We use a 30s timeout for stability
            response = requests.post(vtpass_url, json=payload, headers=headers, timeout=30)
            res_data = response.json()

            if res_data.get("code") == "000": # VTpass Success Code
                return Response({
                    "message": "Data purchase successful!",
                    "details": res_data
                }, status=200)
            else:
                # 3. AUTO-REFUND if VTpass fails
                # Logic: Add money back to balance and record the failure
                user.wallet.balance += float(amount) # Type safety
                user.wallet.save()
                return Response({
                    "error": "VTpass Provider Error",
                    "details": res_data.get("response_description")
                }, status=400)

        except Exception as e:
            # 4. SAFETY REFUND if network crashes
            user.wallet.balance += float(amount)
            user.wallet.save()
            return Response({"error": f"Connection failed: {str(e)}"}, status=502)