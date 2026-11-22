"""
Transaction notifications. One function, called only where the backend has just learned a
transaction's real outcome (webhook, provider answer, reconcile job), never from a client guess.

    notify_transaction(txn)                 # reads status/amount/description off the row
    notify_transaction(txn, amount=Decimal) # when the row amount is 0 (a failed purchase)

Wording by status:
  success  -> "<Thing> successful"
  pending  -> "<Thing> processing"            (money reserved, outcome not final yet)
  failed   -> "<Thing> failed" (+ "refunded" when the wallet was credited back)

Every push carries `notification_id` (transaction id + status). The app drops a repeat of the
same id, and the callers only fire on a state change, so retries/duplicate webhooks stay quiet.
Best effort like everything in notify.py: it never raises.
"""
import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction as db_transaction
from django.utils import timezone

from globalink_core.notify import notify_user

from .models import Transaction

logger = logging.getLogger('payments')

T = Transaction.TransactionType
S = Transaction.Status

# description prefix written by the purchase views -> (app category, label)
_BILL_CATEGORIES = (
    ('airtime', 'airtime', 'Airtime purchase'),
    ('data', 'data', 'Data purchase'),
    ('electricity', 'electricity', 'Electricity payment'),
    ('cable', 'cable', 'Cable TV subscription'),
)


def classify(txn):
    """(category, label) for a transaction. Categories drive the icon in the app."""
    if txn.transaction_type == T.DEPOSIT:
        return 'deposit', 'Wallet funding'
    if txn.transaction_type == T.WITHDRAWAL:
        return 'withdrawal', 'Withdrawal'
    if txn.transaction_type == T.BILL_PAYMENT:
        desc = (txn.description or '').lower()
        for prefix, category, label in _BILL_CATEGORIES:
            if desc.startswith(prefix):
                return category, label
        return 'bill', 'Bill payment'
    if txn.transaction_type == T.PAYMENT:
        return 'purchase', 'Order payment'
    if txn.transaction_type == T.PROMOTION:
        return 'service', 'Promotion payment'
    if txn.transaction_type == T.REFUND:
        return 'refund', 'Refund'
    return 'service', 'Transaction'


def _naira(value):
    return f"₦{Decimal(value):,.2f}"


def build_message(txn, amount=None, refunded=False, detail=''):
    """(title, body) for the transaction's current state."""
    category, label = classify(txn)
    amt = abs(Decimal(amount if amount is not None else txn.amount))
    money = f" of {_naira(amt)}" if amt else ''
    if txn.status == S.SUCCESS:
        if category == 'deposit':
            return "Wallet funded", f"{_naira(amt)} has been added to your wallet."
        if category == 'withdrawal':
            return "Withdrawal successful", f"Your withdrawal{money} has been sent to your bank."
        return f"{label} successful", f"Your {label.lower()}{money} was completed successfully."
    if txn.status == S.PENDING:
        return f"{label} processing", f"Your {label.lower()}{money} is being processed. We'll tell you as soon as it's done."
    tail = (" Your wallet has been refunded." if refunded
            else " You were not charged.")
    reason = f" ({detail})" if detail else ''
    return f"{label} failed", f"Your {label.lower()}{money} could not be completed{reason}.{tail}"


def notify_transaction(txn, amount=None, refunded=False, detail=''):
    try:
        user = txn.wallet.user
        category, _ = classify(txn)
        title, body = build_message(txn, amount, refunded, detail)
        amt = abs(Decimal(amount if amount is not None else txn.amount))
        data = {
            'type': 'transaction',
            'category': category,
            'status': txn.status,
            'amount': str(amt.quantize(Decimal('0.01'))),
            'transaction_id': str(txn.pk),
            'reference': txn.reference,
            'timestamp': (txn.created_at if txn.status == S.PENDING else timezone.now()).isoformat(),
            'notification_id': f"txn-{txn.pk}-{txn.status}",
        }
        if not cache.add(f"push-{data['notification_id']}", 1, 24 * 3600):
            return  # already sent (a retried webhook, a double click)
        # Never push for a transaction that is not (yet) committed: wait for the outer commit.
        def send():
            try:
                notify_user(user, title, body, data, email=False)
            except Exception as e:  # a push problem must never surface in a payment request
                logger.warning("transaction push failed: %s", e)

        db_transaction.on_commit(send)
    except Exception as e:
        logger.warning("notify_transaction failed: %s", e)
