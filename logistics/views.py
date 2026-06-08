import requests
from decimal import Decimal
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, status, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from finance.models import Transaction, DataMarkup
from finance.utils import WalletManager
from finance.nellobyte import NellobyteClient
from market.models import Order
from market.serializers import OrderSerializer
from .models import DataTransaction

logger = logging.getLogger(__name__)

class PurchaseDataView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    SERVICE_TO_NETWORK = {
        'mtn-data': 'MTN',
        'glo-data': 'Glo',
        'airtel-data': 'Airtel',
        '9mobile-data': '9mobile',
    }

    def _fetch_live_price(self, service_id, variation_code):
        network_key = self.SERVICE_TO_NETWORK.get(service_id)
        if not network_key:
            return None, f"Unknown service: {service_id}"

        client = NellobyteClient()
        plans = client.fetch_all_variations(network_key)

        matched = None
        for plan in plans:
            pid = str(plan.get('PRODUCT_ID', '') or plan.get('ID', '') or '')
            if pid == variation_code:
                matched = plan
                break

        if not matched:
            return None, f"Plan '{variation_code}' not found for {service_id}"

        raw_price = None
        for key in ('PRODUCT_AMOUNT', 'price', 'Price', 'amount', 'Amount', 'variation_amount'):
            val = matched.get(key)
            if val is not None:
                raw_price = val
                break

        if raw_price is None:
            return None, "Could not determine plan price from provider"

        original_price = float(str(raw_price).replace(',', ''))
        factor = 1.10
        try:
            dm = DataMarkup.objects.get(network=service_id, is_active=True)
            factor = float(dm.price_factor)
        except DataMarkup.DoesNotExist:
            pass

        verified = round(original_price * factor, 2)
        return Decimal(str(verified)), None

    def post(self, request):
        user = request.user
        service_id = request.data.get("serviceID")
        variation_code = request.data.get("variation_code")
        phone = request.data.get("phone")

        if not all([service_id, variation_code, phone]):
            return Response({"error": "Missing required fields: serviceID, variation_code, phone"}, status=400)

        # Fetch live price from Nellobyte + admin markup
        amount, error = self._fetch_live_price(service_id, variation_code)
        if error:
            return Response({"error": error}, status=400)

        # Deduct from Wallet locally first
        description = f"Data Purchase: {service_id} for {phone}"
        payment_success, message = WalletManager.process_payment(
            user=user,
            amount=amount,
            transaction_type=Transaction.TransactionType.BILL_PAYMENT,
            description=description
        )

        if not payment_success:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        # Call Nellobyte API
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
                # AUTO-REFUND if Nellobyte fails
                user.wallet.available_balance += float(amount)
                user.wallet.save()
                return Response({
                    "error": "Provider Error",
                    "details": res_data.get("remark") or res_data.get("status")
                }, status=400)

        except Exception as e:
            # SAFETY REFUND if network crashes
            user.wallet.available_balance += float(amount)
            user.wallet.save()
            return Response({"error": f"Connection failed: {str(e)}"}, status=502)


@csrf_exempt
def nellobyte_callback(request):
    orderid = request.GET.get('orderid')
    statuscode = request.GET.get('statuscode')
    orderstatus = request.GET.get('orderstatus', '')

    logger.info(f"Nellobyte callback: orderid={orderid} statuscode={statuscode} orderstatus={orderstatus}")

    if not orderid:
        return HttpResponse("Missing orderid", status=400)

    try:
        txn = DataTransaction.objects.get(order_id=orderid)
    except DataTransaction.DoesNotExist:
        logger.error(f"Nellobyte callback: DataTransaction not found for orderid={orderid}")
        return HttpResponse("Transaction not found", status=404)

    if statuscode == '100':
        txn.status = DataTransaction.Status.SUCCESS
        txn.remark = f"statuscode={statuscode} orderstatus={orderstatus}"
        txn.save()
        logger.info(f"DataTransaction {txn.id} marked SUCCESS (orderid={orderid})")
    else:
        txn.status = DataTransaction.Status.FAILED
        txn.remark = f"statuscode={statuscode} orderstatus={orderstatus}"
        txn.save()
        logger.warning(f"DataTransaction {txn.id} marked FAILED (orderid={orderid}, code={statuscode})")

    return HttpResponse("OK", status=200)


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