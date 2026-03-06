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

        # 2. Call Nellobyte API
        from finance. nellobyte import NellobyteClient
        from finance.utils import generate_vtpass_request_id
        
        request_id = generate_vtpass_request_id()

        try:
            client = NellobyteClient()
            res_data = client.purchase_data(
                request_id=request_id,
                service_id=service_id,
                data_plan=variation_code,
                phone=phone
            )

            status_msg = str(res_data.get('status', '')).upper()
            
            if res_data.get('statuscode') == '100' or "RECEIVED" in status_msg or "SUCCESSFUL" in status_msg:
                return Response({
                    "message": "Data purchase successful!",
                    "details": res_data
                }, status=200)
            else:
                # 3. AUTO-REFUND if Nellobyte fails
                # Logic: Add money back to balance and record the failure
                user.wallet.balance += float(amount) # Type safety
                user.wallet.save()
                return Response({
                    "error": "Provider Error",
                    "details": res_data.get("remark") or res_data.get("status")
                }, status=400)

        except Exception as e:
            # 4. SAFETY REFUND if network crashes
            user.wallet.balance += float(amount)
            user.wallet.save()
            return Response({"error": f"Connection failed: {str(e)}"}, status=502)