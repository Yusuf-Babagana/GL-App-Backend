"""
Settles Pending Nellobyte data orders when the provider's callback never
arrives (or arrives before the transaction row exists).

Mirrors the outcome rules in views.webhook_data_callback:
  - delivered      -> Transaction SUCCESS
  - cancelled/failed -> Transaction FAILED and the wallet is refunded
  - anything else  -> left Pending, retried on the next run
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Transaction, Wallet
from .nellobyte import NellobyteClient

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {'ORDER_COMPLETED'}
FAILED_STATUSES = {'ORDER_CANCELLED', 'ORDER_ERROR', 'ORDER_FAILED', 'ORDER_REJECTED'}


def _settle(txn_id, outcome, detail):
    with transaction.atomic():
        txn = Transaction.objects.select_for_update().get(pk=txn_id)
        if txn.status != Transaction.Status.PENDING:
            return False  # the callback (or another run) got there first

        if outcome == 'success':
            txn.status = Transaction.Status.SUCCESS
            txn.description = f"{txn.description} (Confirmed)"[:255]
        else:
            txn.status = Transaction.Status.FAILED
            if txn.amount < 0 and 'Refunded' not in txn.description:
                wallet = Wallet.objects.select_for_update().get(pk=txn.wallet_id)
                wallet.available_balance += abs(txn.amount)
                wallet.save()
                txn.description = f"{txn.description} (Failed, Wallet Refunded)"[:255]
            else:
                txn.description = f"{txn.description} (Failed)"[:255]
        txn.save()
    logger.info(f"Reconcile: txn {txn_id} -> {outcome} ({detail})")
    return True


def reconcile_pending_data_orders(wallet=None, min_age_minutes=3, max_orders=10):
    """Returns the number of transactions that were settled."""
    cutoff = timezone.now() - timedelta(minutes=min_age_minutes)
    pending = Transaction.objects.filter(
        transaction_type=Transaction.TransactionType.BILL_PAYMENT,
        status=Transaction.Status.PENDING,
        created_at__lte=cutoff,
        reference__isnull=False,
    ).order_by('created_at')
    if wallet is not None:
        pending = pending.filter(wallet=wallet)

    client = NellobyteClient()
    settled = 0
    for txn in pending[:max_orders]:
        try:
            resp = client.query_transaction(order_id=txn.reference)
        except Exception as e:
            logger.error(f"Reconcile: query failed for {txn.reference}: {e}")
            continue

        order_status = str(resp.get('orderstatus') or resp.get('status') or '').upper()
        if order_status in SUCCESS_STATUSES:
            outcome = 'success'
        elif order_status in FAILED_STATUSES:
            outcome = 'failed'
        else:
            logger.info(f"Reconcile: {txn.reference} still unresolved, response={resp}")
            continue

        if _settle(txn.pk, outcome, order_status):
            settled += 1
    return settled
