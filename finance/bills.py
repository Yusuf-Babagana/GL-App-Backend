"""
Airtime, electricity and cable TV purchases through BT DataPlug.

Same money flow as DataPurchaseView: the provider is called first, then the wallet is
debited. An unclear outcome (timeout, 5xx) holds the funds as PENDING and is settled
later by the webhook / reconcile job via client_reference.
"""
import hashlib
import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .btdataplug import BTDataPlugClient, BTDataPlugError
from .models import Transaction, Wallet

logger = logging.getLogger(__name__)

# Provider answers meaning "order not taken, nothing charged (or already refunded)"
REJECTED_CODES = ('purchase_failed', 'validation_error', 'insufficient_funds',
                  'service_not_permitted', 'service_unavailable')

AIRTIME_NETWORKS = {
    'mtn-airtime': 'MTN', 'glo-airtime': 'GLO',
    'airtel-airtime': 'AIRTEL', '9mobile-airtime': '9MOBILE',
}


def _money(value):
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return None
    return d if d.is_finite() and d == d.quantize(Decimal('0.01')) and d > 0 else None


def _provider_error(e):
    """Message that is safe to show an end user."""
    if e.code == 'insufficient_funds':
        return "Service temporarily unavailable. Please try again later."
    return str(e)


def _cable_factor():
    return Decimal(str(getattr(settings, 'CABLE_PRICE_FACTOR', '1.00')))


def idempotent_request_id(request):
    """
    The order id sent to the provider and stored as Transaction.reference.

    If the client sends an Idempotency-Key (header or body), the id is derived from
    it, so a retry of the same purchase after a dropped connection maps to the same
    order instead of buying twice. Without a key every call is a new purchase.
    """
    key = request.headers.get('Idempotency-Key') or request.data.get('idempotency_key')
    if key:
        return hashlib.sha256(f"{request.user.id}:{str(key).strip()}".encode()).hexdigest()[:32]
    return uuid.uuid4().hex[:12]


def replay_response(request, request_id):
    """The original outcome, if this request_id was already processed; else None."""
    txn = Transaction.objects.filter(reference=request_id, wallet__user=request.user).first()
    if txn is None:
        return None
    logger.info(f"Idempotent replay of purchase {request_id}: {txn.status}")
    wallet = Wallet.objects.get(user=request.user)
    if txn.status == Transaction.Status.FAILED:
        return Response({"error": "This purchase failed earlier.", "duplicate": True}, status=400)
    ok = txn.status == Transaction.Status.SUCCESS
    return Response({
        "message": "Purchase successful!" if ok else "Order submitted for processing. Check history for status updates.",
        "order_id": txn.reference,
        "new_balance": float(wallet.available_balance),
        "duplicate": True,
    }, status=200 if ok else 202)


def run_bill_purchase(request, label, amount, call):
    """
    label: short description for history, e.g. "Airtime: MTN N500 to 0801..."
    amount: Decimal the user is charged
    call: fn(request_id) -> BT DataPlug order dict (raises BTDataPlugError)
    """
    request_id = idempotent_request_id(request)
    replay = replay_response(request, request_id)
    if replay:
        return replay
    try:
        wallet = Wallet.objects.get(user=request.user)
    except Wallet.DoesNotExist:
        return Response({"error": "Wallet not found."}, status=400)
    if wallet.available_balance < amount:
        return Response({"error": "Insufficient wallet balance."}, status=400)

    def reserve_pending(exc):
        logger.error(f"BTDataPlug bill purchase unclear outcome ({label}): {exc}")
        with transaction.atomic():
            w = Wallet.objects.select_for_update().get(user=request.user)
            if w.available_balance >= amount:
                w.available_balance -= amount
                w.save()
            Transaction.objects.create(
                wallet=w, amount=-amount,
                transaction_type=Transaction.TransactionType.BILL_PAYMENT,
                status=Transaction.Status.PENDING,
                description=f"{label} (Pending: connection error, needs reconciliation)"[:255],
                reference=request_id,
            )
        return Response({"message": "Transaction submitted. Check history for status updates."}, status=202)

    try:
        order = call(request_id)
    except IntegrityError:
        return replay_response(request, request_id) or Response({"error": "Please try again."}, status=409)
    except BTDataPlugError as e:
        if e.code not in REJECTED_CODES:
            return reserve_pending(e)
        logger.error(f"Bill purchase rejected ({label}): {e} | code={e.code}")
        msg = _provider_error(e)
        Transaction.objects.create(
            wallet=wallet, amount=0,
            transaction_type=Transaction.TransactionType.BILL_PAYMENT,
            status=Transaction.Status.FAILED,
            description=f"{label} (Failed: {msg})"[:255],
            reference=request_id,
        )
        return Response({"error": f"Purchase failed: {msg}"}, status=400)
    except Exception as e:
        return reserve_pending(e)

    order_status = order.get('status')
    if order_status not in ('successful', 'pending'):
        return reserve_pending(f"unexpected status {order_status!r}")

    is_success = order_status == 'successful'
    token = (order.get('result') or {}).get('token')
    try:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            if wallet.available_balance < amount:
                return Response({"error": "Insufficient wallet balance."}, status=400)
            wallet.available_balance -= amount
            wallet.save()
            desc = label if is_success else f"{label} (Pending)"
            if token:
                desc += f" | Token: {token}"
            Transaction.objects.create(
                wallet=wallet, amount=-amount,
                transaction_type=Transaction.TransactionType.BILL_PAYMENT,
                status=Transaction.Status.SUCCESS if is_success else Transaction.Status.PENDING,
                description=desc[:255],
                reference=request_id,
            )
    except IntegrityError:
        # A concurrent request with the same key recorded it first (our debit rolled back).
        return replay_response(request, request_id) or Response({"error": "Please try again."}, status=409)

    body = {
        "message": "Purchase successful!" if is_success else "Order submitted for processing. Check history for status updates.",
        "order_id": order.get('reference'),
        "new_balance": float(wallet.available_balance),
    }
    if token:
        body["token"] = token
    return Response(body, status=200 if is_success else 202)


class AirtimePurchaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        network = AIRTIME_NETWORKS.get(request.data.get('service_id'))
        phone = str(request.data.get('phone') or '').strip()
        amount = _money(request.data.get('amount'))
        if not network or not phone or amount is None:
            return Response({"error": "Missing or invalid service_id, phone or amount."}, status=400)
        if not 50 <= amount <= 50000:
            return Response({"error": "Airtime amount must be between 50 and 50,000."}, status=400)

        client = BTDataPlugClient()
        return run_bill_purchase(
            request, f"Airtime: {network} N{amount} to {phone}", amount,
            lambda rid: client.purchase_airtime(rid, network, phone, amount),
        )


class ElectricityDiscosView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            return Response(BTDataPlugClient().get_discos())
        except BTDataPlugError as e:
            return Response({"error": _provider_error(e)}, status=502)


class VerifyMeterView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        q = request.query_params
        try:
            return Response(BTDataPlugClient().verify_meter(
                q.get('disco', ''), q.get('meter_no', ''), q.get('meter_type', '')))
        except BTDataPlugError as e:
            return Response({"error": _provider_error(e)}, status=422 if e.http_status == 422 else 502)


class ElectricityPurchaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        d = request.data
        disco = str(d.get('disco') or '').strip()
        meter_no = str(d.get('meter_no') or '').strip()
        meter_type = str(d.get('meter_type') or '').strip().lower()
        phone = str(d.get('phone') or '').strip()
        base = _money(d.get('amount'))
        if not (disco and meter_no and meter_type in ('prepaid', 'postpaid') and phone) or base is None:
            return Response({"error": "Missing or invalid disco, meter_no, meter_type, phone or amount."}, status=400)

        client = BTDataPlugClient()
        try:
            info = client.get_discos()
        except BTDataPlugError as e:
            return Response({"error": _provider_error(e)}, status=502)
        if base < Decimal(info['minimum_amount']):
            return Response({"error": f"Minimum amount is {info['minimum_amount']}."}, status=400)
        total = base + Decimal(info['service_fee'])  # the user pays the provider's service fee

        return run_bill_purchase(
            request, f"Electricity: {disco} {meter_type} {meter_no} N{base}", total,
            lambda rid: client.purchase_electricity(rid, disco, meter_no, meter_type, base, phone),
        )


class CablePlansView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cable_tv = request.query_params.get('cable_tv', '').lower()
        try:
            plans = BTDataPlugClient().get_cable_plans(cable_tv)
        except BTDataPlugError as e:
            return Response({"error": _provider_error(e)}, status=502)
        factor = _cable_factor()
        return Response({"results": [
            {**p, "price": str((Decimal(p['price']) * factor).quantize(Decimal('0.01')))} for p in plans
        ]})


class VerifyCableView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        q = request.query_params
        try:
            return Response(BTDataPlugClient().verify_cable(q.get('cable_tv', '').lower(), q.get('smartcard', '')))
        except BTDataPlugError as e:
            return Response({"error": _provider_error(e)}, status=422 if e.http_status == 422 else 502)


class CablePurchaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        d = request.data
        cable_tv = str(d.get('cable_tv') or '').strip().lower()
        package_id = str(d.get('package_id') or '').strip()
        smartcard = str(d.get('smartcard') or '').strip()
        phone = str(d.get('phone') or '').strip()
        if not all([cable_tv, package_id, smartcard, phone]):
            return Response({"error": "Missing cable_tv, package_id, smartcard or phone."}, status=400)

        client = BTDataPlugClient()
        # Price comes from the provider, never from the client.
        try:
            plan = next((p for p in client.get_cable_plans(cable_tv) if p['package_id'] == package_id), None)
        except BTDataPlugError as e:
            return Response({"error": _provider_error(e)}, status=502)
        if plan is None:
            return Response({"error": f"Package '{package_id}' not found for {cable_tv}."}, status=400)
        amount = (Decimal(plan['price']) * _cable_factor()).quantize(Decimal('0.01'))

        return run_bill_purchase(
            request, f"Cable: {cable_tv.upper()} {plan['name']} for {smartcard}", amount,
            lambda rid: client.purchase_cable(rid, cable_tv, package_id, smartcard, phone),
        )
