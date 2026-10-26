import json
import requests
from decimal import Decimal
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from finance.models import Transaction, DataMarkup, DataPlanPrice
from finance.utils import WalletManager
from finance.btdataplug import BTDataPlugClient, BTDataPlugError, verify_webhook_signature
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

        client = BTDataPlugClient()
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
        # Check per-plan override first
        try:
            dpp = DataPlanPrice.objects.get(
                network=service_id, variation_code=variation_code,
                is_active=True, selling_price__isnull=False
            )
            verified = round(float(dpp.selling_price), 2)
            return Decimal(str(verified)), None
        except DataPlanPrice.DoesNotExist:
            pass
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

        # Fetch live price from BT DataPlug + admin markup
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

        # Call BT DataPlug API
        from finance.utils import generate_vtpass_request_id
        
        request_id = generate_vtpass_request_id()

        try:
            client = BTDataPlugClient()
            order = client.purchase_data(request_id=request_id, plan_id=variation_code, phone=phone)
            order_status = order.get('status')
            DataTransaction.objects.create(
                user=user,
                request_id=request_id,
                order_id=str(order.get('reference') or request_id),
                service_id=service_id,
                data_plan=variation_code,
                phone=phone,
                amount=amount,
                status=(DataTransaction.Status.SUCCESS if order_status == 'successful'
                        else DataTransaction.Status.PENDING),
                remark=str(order),
            )
            return Response({"message": "Data purchase successful!", "details": order}, status=200)

        except BTDataPlugError as e:
            if e.code not in ('purchase_failed', 'validation_error', 'insufficient_funds',
                              'service_not_permitted', 'service_unavailable'):
                # Ambiguous (timeout, 5xx, ...): keep the funds held, record as pending.
                DataTransaction.objects.create(
                    user=user, request_id=request_id, order_id=request_id,
                    service_id=service_id, data_plan=variation_code, phone=phone,
                    amount=amount, status=DataTransaction.Status.PENDING, remark=str(e),
                )
                return Response({"message": "Transaction submitted. Check history for status updates."}, status=202)
            # AUTO-REFUND: provider clearly did not take the order
            user.wallet.available_balance += float(amount)
            user.wallet.save()
            DataTransaction.objects.create(
                user=user, request_id=request_id, order_id=request_id,
                service_id=service_id, data_plan=variation_code, phone=phone,
                amount=amount, status=DataTransaction.Status.FAILED, remark=str(e),
            )
            return Response({"error": "Provider Error", "details": str(e)}, status=400)

        except Exception as e:
            # SAFETY REFUND if network crashes
            user.wallet.available_balance += float(amount)
            user.wallet.save()
            return Response({"error": f"Connection failed: {str(e)}"}, status=502)


@csrf_exempt
def btdataplug_callback(request):
    if request.method != 'POST' or not verify_webhook_signature(
            request.body, request.headers.get('X-BTDataPlug-Signature', '')):
        return HttpResponse("Invalid signature", status=401)
    try:
        order = json.loads(request.body)['data']
    except (ValueError, KeyError):
        return HttpResponse("Bad payload", status=400)

    try:
        txn = DataTransaction.objects.get(request_id=order.get('client_reference'))
    except DataTransaction.DoesNotExist:
        return HttpResponse("Transaction not found", status=404)

    new_status = {'successful': DataTransaction.Status.SUCCESS,
                  'failed': DataTransaction.Status.FAILED,
                  'reversed': DataTransaction.Status.FAILED}.get(order.get('status'))
    if new_status and txn.status == DataTransaction.Status.PENDING:
        txn.status = new_status
        txn.remark = f"status={order.get('status')} {order.get('failure_reason') or ''}".strip()
        txn.save()
    return HttpResponse("OK", status=200)
