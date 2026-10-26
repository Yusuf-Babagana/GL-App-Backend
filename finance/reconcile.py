"""
Settles Pending data orders from BT DataPlug, either from a webhook event or by
polling the provider when the webhook never arrives.

Outcome rules:
  - successful          -> Transaction SUCCESS
  - failed / reversed   -> Transaction FAILED and the wallet is refunded
  - pending             -> left Pending, retried on the next run
"""
import logging
import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .btdataplug import BTDataPlugClient
from .models import DataPlanPrice, Transaction, Wallet

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {'successful'}
FAILED_STATUSES = {'failed', 'reversed'}


def _settle(txn_id, outcome, detail, note=''):
    """Moves a Pending (or, for reversals, Success) transaction to its final state."""
    with transaction.atomic():
        txn = Transaction.objects.select_for_update().get(pk=txn_id)
        reversal = outcome == 'failed' and detail.startswith('reversed')
        if txn.status != Transaction.Status.PENDING and not (reversal and txn.status == Transaction.Status.SUCCESS):
            return False  # the webhook (or another run) got there first

        if outcome == 'success':
            txn.status = Transaction.Status.SUCCESS
            txn.description = f"{txn.description} (Confirmed){note}"[:255]
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


def _maybe_disable_plan(txn, reason):
    """Auto-disable plans the provider rejects with a SIM-level error."""
    if not any(kw in reason.lower() for kw in ('no active sim', 'inactive sim', 'not have an active sim')):
        return
    match = re.search(r'([A-Z0-9]+-DATA)\s*\(([^)]+)\)', txn.description)
    if match:
        service_id, variation_code = match.group(1).lower(), match.group(2)
        DataPlanPrice.objects.update_or_create(
            network=service_id,
            variation_code=variation_code,
            defaults={'is_active': False, 'plan_name': f'Auto-disabled: {reason}'[:255]},
        )
        logger.info(f"Auto-disabled plan {service_id}/{variation_code} due to provider error")


def settle_from_order(order):
    """
    Applies a BT DataPlug order dict (from a webhook or a status query) to the
    matching Transaction. Returns True if anything changed.
    """
    status = str(order.get('status') or '').lower()
    ref = order.get('client_reference')
    if not ref:
        return False
    if status in SUCCESS_STATUSES:
        outcome = 'success'
    elif status in FAILED_STATUSES:
        outcome = 'failed'
    else:
        return False

    txn = Transaction.objects.filter(
        reference=ref, transaction_type=Transaction.TransactionType.BILL_PAYMENT
    ).first()
    if txn is None:
        logger.error(f"Reconcile: no transaction for client_reference={ref}")
        return False

    token = (order.get('result') or {}).get('token')  # electricity tokens arrive here when the order was pending
    note = f" | Token: {token}" if token else ''
    changed = _settle(txn.pk, outcome, f"{status} {order.get('failure_reason') or ''}".strip(), note)
    if changed and outcome == 'failed':
        _maybe_disable_plan(txn, order.get('failure_reason') or '')
    return changed


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

    client = BTDataPlugClient()
    settled = 0
    for txn in pending[:max_orders]:
        try:
            order = client.query_transaction(client_reference=txn.reference)
        except Exception as e:
            logger.error(f"Reconcile: query failed for {txn.reference}: {e}")
            continue

        if order is None:
            # Not auto-refunded: this also matches legacy (pre-BT DataPlug) orders,
            # which the provider has never heard of. Needs a human decision.
            logger.warning(f"Reconcile: {txn.reference} not found at provider, leaving Pending")
            continue
        if settle_from_order(order):
            settled += 1
    return settled
