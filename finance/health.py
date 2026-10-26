"""
Payment health report: the checks someone would run by hand to find money problems.

build_health_report() returns plain data plus an `alerts` list (empty == healthy).
It is read-only. Used by the `payment_health` command (cron / email) and the
staff-only /api/finance/admin/health/ endpoint.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Transaction, Wallet, WithdrawalTicket

logger = logging.getLogger('payments')

STUCK_PENDING_MINUTES = 30
STUCK_WITHDRAWAL_HOURS = 24
DISPUTE_SLA_DAYS = 3
FAILED_RATE_ALERT = 0.25      # more than 25% of last-24h bill/data purchases failing
FAILED_RATE_MIN_SAMPLE = 8


def _ledger_checks():
    from market.models import Order
    alerts, details = [], {}

    # 1. No wallet may be negative.
    negative = (
        list(Wallet.objects.filter(available_balance__lt=0).values_list('user__email', 'available_balance'))
        + list(Wallet.objects.filter(locked_balance__lt=0).values_list('user__email', 'locked_balance'))
    )
    details['negative_wallets'] = [(e, str(b)) for e, b in negative]
    if negative:
        alerts.append(f"{len(negative)} wallet(s) have a negative balance")

    # 1b. Pending withdrawal tickets must each have a hold row (WDR-<id>). Older tickets
    # that predate the hold have none: approving one deducts at approval time.
    pending = WithdrawalTicket.objects.filter(status='PENDING')
    held = set(Transaction.objects.filter(reference__startswith='WDR-', status='pending').values_list('reference', flat=True))
    details['pending_withdrawals_without_hold'] = [t.pk for t in pending if f"WDR-{t.pk}" not in held]

    # 2. A seller's locked_balance must equal the escrowed orders they are owed.
    owed = {
        row['shop__owner']: row['t'] or Decimal('0')
        for row in Order.objects.filter(payment_status__in=['paid', 'disputed'])
        .values('shop__owner').annotate(t=Sum('total_price'))
    }
    mismatches = []
    wallets = Wallet.objects.filter(Q(locked_balance__gt=0) | Q(user_id__in=list(owed.keys()))).select_related('user')
    for w in wallets:
        expected = owed.get(w.user_id, Decimal('0'))
        if w.locked_balance != expected:
            mismatches.append({
                'user': w.user.email,
                'locked_balance': str(w.locked_balance),
                'escrowed_orders_total': str(expected),
            })
    details['escrow_mismatches'] = mismatches
    if mismatches:
        alerts.append(f"{len(mismatches)} seller wallet(s) where locked_balance != escrowed orders")

    # 3. Orders that should have auto-settled by now (is the scheduled job running?).
    cutoff = timezone.now() - timedelta(days=settings.ESCROW_AUTO_RELEASE_DAYS + 1)
    overdue = Order.objects.filter(payment_status='paid', dispatched_at__lte=cutoff).count()
    details['orders_overdue_for_auto_release'] = overdue
    if overdue:
        alerts.append(f"{overdue} order(s) overdue for auto-release — is `process_escrow` scheduled?")
    return alerts, details


def _dispute_checks():
    from market.models import Dispute
    open_qs = Dispute.objects.filter(status='open')
    stale = open_qs.filter(created_at__lte=timezone.now() - timedelta(days=DISPUTE_SLA_DAYS)).count()
    info = {'open': open_qs.count(), 'older_than_sla': stale}
    alerts = [f"{stale} dispute(s) open for more than {DISPUTE_SLA_DAYS} days"] if stale else []
    return alerts, info


def _provider_check():
    """BT DataPlug wallet: purchases fail for every user when it runs dry."""
    try:
        from .btdataplug import BTDataPlugClient
        bal = Decimal(str(BTDataPlugClient().get_balance()['balance']))
    except Exception as e:
        return [f"Could not read BT DataPlug balance: {e}"], {'error': str(e)}
    info = {'balance': str(bal), 'low_threshold': settings.BTDATAPLUG_LOW_BALANCE}
    alerts = []
    if bal < Decimal(str(settings.BTDATAPLUG_LOW_BALANCE)):
        alerts.append(f"BT DataPlug wallet low: NGN {bal}")
    return alerts, info


def build_health_report(check_provider=True):
    now = timezone.now()
    alerts = []

    purchases = Transaction.objects.filter(
        transaction_type=Transaction.TransactionType.BILL_PAYMENT,
        created_at__gte=now - timedelta(hours=24),
    )
    by_status = {r['status']: r['n'] for r in purchases.values('status').annotate(n=Count('id'))}
    total = sum(by_status.values())
    failed = by_status.get('failed', 0)
    if total >= FAILED_RATE_MIN_SAMPLE and failed / total > FAILED_RATE_ALERT:
        alerts.append(f"{failed}/{total} data/bill purchases failed in the last 24h")

    stuck = Transaction.objects.filter(
        transaction_type=Transaction.TransactionType.BILL_PAYMENT, status='pending',
        created_at__lte=now - timedelta(minutes=STUCK_PENDING_MINUTES),
    ).count()
    if stuck:
        alerts.append(f"{stuck} purchase(s) pending for more than {STUCK_PENDING_MINUTES} minutes")

    stuck_withdrawals = WithdrawalTicket.objects.filter(
        status='PENDING', created_at__lte=now - timedelta(hours=STUCK_WITHDRAWAL_HOURS),
    ).count()
    if stuck_withdrawals:
        alerts.append(f"{stuck_withdrawals} withdrawal(s) unpaid for more than {STUCK_WITHDRAWAL_HOURS}h")

    ledger_alerts, ledger = _ledger_checks()
    dispute_alerts, disputes = _dispute_checks()
    alerts += ledger_alerts + dispute_alerts

    provider = None
    if check_provider:
        provider_alerts, provider = _provider_check()
        alerts += provider_alerts

    report = {
        'generated_at': now.isoformat(),
        'healthy': not alerts,
        'alerts': alerts,
        'purchases_24h': {'total': total, 'by_status': by_status, 'stuck_pending': stuck},
        'withdrawals_unpaid_over_24h': stuck_withdrawals,
        'ledger': ledger,
        'disputes': disputes,
        'provider': provider,
    }
    if alerts:
        logger.error("PAYMENT HEALTH ALERTS: %s", "; ".join(alerts))
    return report


class PaymentHealthView(APIView):
    """Staff-only JSON health report (add ?skip_provider=1 to avoid the BT DataPlug call)."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        return Response(build_health_report(check_provider=not request.query_params.get('skip_provider')))
