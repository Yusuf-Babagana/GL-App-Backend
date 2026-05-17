import requests
from decimal import Decimal
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, status, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from finance.models import Transaction
from finance.utils import WalletManager
from market.models import Order
from market.serializers import OrderSerializer

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
        from finance.nellobyte import NellobyteClient
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


# ---------------------------------------------------------------------------
# Rider Delivery Management (migrated from market/views.py)
# ---------------------------------------------------------------------------

class AvailableDeliveriesView(generics.ListAPIView):
    """
    RIDER: List orders that are 'ready_for_pickup' and have NO rider assigned yet.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(
            delivery_status='ready_for_pickup',
            rider__isnull=True
        ).order_by('-created_at')


class RiderMyDeliveriesView(generics.ListAPIView):
    """
    RIDER: List orders assigned to the logged-in rider.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(rider=self.request.user).order_by('-created_at')


class AcceptDeliveryView(APIView):
    """
    RIDER: Accept a delivery job and lock the order.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)

        if order.rider is not None:
            return Response(
                {"error": "This order has already been taken by another rider."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if order.delivery_status != 'ready_for_pickup':
            return Response(
                {"error": "Order is not ready for pickup yet."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            order.rider = request.user
            order.delivery_fee = Decimal('1500.00')
            order.save()

            if not request.user.roles:
                request.user.roles = []
            if 'rider' not in request.user.roles:
                request.user.roles.append('rider')
                request.user.save()

        return Response(
            {"message": "Job accepted! Head to the store for pickup."},
            status=status.HTTP_200_OK
        )


class RiderUpdateStatusView(APIView):
    """
    Rider updates delivery status.
    Payment is already settled at checkout; PIN gates the delivery confirmation.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, rider=request.user)
        new_status = request.data.get('status')
        provided_pin = request.data.get('pin')

        if new_status == 'picked_up':
            order.delivery_status = 'picked_up'
            order.save()
            return Response({"message": "Picked up successfully"})

        elif new_status == 'delivered':
            if not provided_pin:
                return Response({"error": "PIN is missing"}, status=400)

            if str(provided_pin).strip() != str(order.delivery_code).strip():
                return Response({"error": "Incorrect PIN"}, status=400)

            order.delivery_status = Order.DeliveryStatus.DELIVERED
            order.save()
            return Response({"message": "Delivery confirmed successfully!"})

        return Response({"error": "Invalid status"}, status=400)