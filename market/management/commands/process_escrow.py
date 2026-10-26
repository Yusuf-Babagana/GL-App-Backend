from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from market.escrow import EscrowError, refund_buyer, release_to_seller
from globalink_core.notify import notify_user
from market.models import Order


class Command(BaseCommand):
    help = (
        "Settle escrow that nobody acted on. Schedule this daily.\n"
        "  - Dispatched orders the buyer never confirmed or disputed for ESCROW_AUTO_RELEASE_DAYS "
        "(default 7) are released to the seller.\n"
        "  - Paid orders the seller never dispatched for UNSHIPPED_REFUND_DAYS (default 14) "
        "are refunded to the buyer.\n"
        "Disputed orders are never touched."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="List what would happen, move no money.")

    def handle(self, *args, dry_run=False, **opts):
        now = timezone.now()
        release_days = getattr(settings, 'ESCROW_AUTO_RELEASE_DAYS', 7)
        refund_days = getattr(settings, 'UNSHIPPED_REFUND_DAYS', 14)

        to_release = Order.objects.filter(
            payment_status=Order.PaymentStatus.PAID,
            dispatched_at__isnull=False,
            dispatched_at__lte=now - timedelta(days=release_days),
        )
        to_refund = Order.objects.filter(
            payment_status=Order.PaymentStatus.PAID,
            dispatched_at__isnull=True,
            delivery_status=Order.DeliveryStatus.PENDING,
            created_at__lte=now - timedelta(days=refund_days),
        )

        done = failed = 0
        for label, qs, action in (
            ("auto-release", to_release, lambda o: release_to_seller(o.pk, reason=f"auto-release after {release_days} days")),
            ("auto-refund", to_refund, lambda o: refund_buyer(o.pk, reason=f"seller did not ship within {refund_days} days", restore_stock=True)),
        ):
            for order in qs:
                if dry_run:
                    self.stdout.write(f"[dry-run] {label} order #{order.pk} ₦{order.total_price}")
                    continue
                try:
                    action(order)
                    done += 1
                    self._notify(label, order)
                    self.stdout.write(f"{label} order #{order.pk} ₦{order.total_price}")
                except EscrowError as e:
                    failed += 1
                    self.stderr.write(f"{label} order #{order.pk} skipped: {e}")
        self.stdout.write(f"Done: {done} settled, {failed} skipped.")

    def _notify(self, label, order):
        ref = f"#{order.order_number or order.pk}"
        if label == "auto-release":
            notify_user(order.buyer, "Order payment released",
                        f"Order {ref} was not confirmed or disputed in time, so the payment was released to the seller.",
                        {"type": "order", "order_id": order.pk})
            notify_user(order.shop.owner, "Payment released",
                        f"Order {ref} was automatically released to your wallet.", {"type": "order", "order_id": order.pk})
        else:
            notify_user(order.buyer, "Order refunded",
                        f"The seller did not ship order {ref} in time. ₦{order.total_price:,.2f} was refunded to your wallet.",
                        {"type": "order", "order_id": order.pk})
            notify_user(order.shop.owner, "Order cancelled",
                        f"Order {ref} was cancelled and refunded because it was not shipped in time.",
                        {"type": "order", "order_id": order.pk})
