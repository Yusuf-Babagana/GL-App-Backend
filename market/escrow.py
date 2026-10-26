"""
The only code that moves escrowed order money.

An order's payment sits in the seller's wallet.locked_balance from the moment the
buyer pays. It leaves that state in exactly two ways:

  release_to_seller  -> seller.available_balance (minus platform commission)
  refund_buyer       -> buyer.available_balance

Both lock the order and both wallets (always in pk order, so concurrent calls
can't deadlock), re-check the order's state under the lock, and write a
Transaction row for every balance change. Calling either twice is safe: the
second call sees a settled order and raises EscrowError without touching money.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from finance.models import (
    GLAPP_COMMISSION_CAP, GLAPP_COMMISSION_RATE, PlatformRevenue, Transaction, Wallet,
)
from .models import Order, Product

logger = logging.getLogger('payments')


class EscrowError(Exception):
    """The order isn't in a state where this money movement is allowed."""


def _lock_order_and_wallets(order_id, allowed_payment_statuses):
    order = Order.objects.select_for_update().select_related('shop__owner').get(pk=order_id)
    if order.payment_status not in allowed_payment_statuses:
        raise EscrowError(f"Order is '{order.payment_status}', expected one of {sorted(allowed_payment_statuses)}.")
    if order.shop is None:
        raise EscrowError("Order has no shop.")

    seller_id, buyer_id = order.shop.owner_id, order.buyer_id
    wallets = {
        w.user_id: w
        for w in Wallet.objects.select_for_update().filter(user_id__in={seller_id, buyer_id}).order_by('pk')
    }
    if seller_id not in wallets or buyer_id not in wallets:
        raise EscrowError("Wallet not found.")
    return order, wallets[seller_id], wallets[buyer_id]


def release_to_seller(order_id, *, reason):
    """Pay the seller (minus commission) from escrow. Returns (net_payout, commission)."""
    with transaction.atomic():
        order, seller_wallet, _buyer = _lock_order_and_wallets(
            order_id, {Order.PaymentStatus.PAID, Order.PaymentStatus.DISPUTED})
        total = order.total_price
        if seller_wallet.locked_balance < total:
            logger.error("ESCROW SHORTFALL on release: order=%s locked=%s needed=%s",
                         order.pk, seller_wallet.locked_balance, total)
            raise EscrowError("Escrow balance is lower than the order total. Contact support.")

        commission = min(total * GLAPP_COMMISSION_RATE, GLAPP_COMMISSION_CAP)
        net = total - commission

        seller_wallet.locked_balance -= total
        seller_wallet.available_balance += net
        seller_wallet.save()
        PlatformRevenue.add_commission(commission)

        Transaction.objects.create(
            wallet=seller_wallet, amount=net,
            transaction_type=Transaction.TransactionType.ESCROW_RELEASE,
            status=Transaction.Status.SUCCESS,
            related_order_id=str(order.pk),
            description=f"Funds released for Order #{order.order_number or order.pk} "
                        f"(Commission: ₦{commission}) [{reason}]"[:255],
        )
        order.payment_status = Order.PaymentStatus.CONFIRMED
        order.delivery_status = Order.DeliveryStatus.DELIVERED
        order.save()
    logger.info("ESCROW RELEASED order=%s net=%s commission=%s reason=%s", order.pk, net, commission, reason)
    return net, commission


def refund_buyer(order_id, *, reason, restore_stock):
    """Return the order total from escrow to the buyer. Returns the amount refunded."""
    with transaction.atomic():
        order, seller_wallet, buyer_wallet = _lock_order_and_wallets(
            order_id, {Order.PaymentStatus.PAID, Order.PaymentStatus.DISPUTED})
        total = order.total_price
        if seller_wallet.locked_balance < total:
            logger.error("ESCROW SHORTFALL on refund: order=%s locked=%s needed=%s",
                         order.pk, seller_wallet.locked_balance, total)
            raise EscrowError("Escrow balance is lower than the order total. Contact support.")

        seller_wallet.locked_balance -= total
        seller_wallet.save()
        buyer_wallet.available_balance += total
        buyer_wallet.save()

        if restore_stock:
            for item in order.items.all():
                if item.product_id:
                    product = Product.objects.select_for_update().get(pk=item.product_id)
                    product.stock += item.quantity
                    product.save()

        label = f"Order #{order.order_number or order.pk}"
        Transaction.objects.create(
            wallet=seller_wallet, amount=-total,
            transaction_type=Transaction.TransactionType.REFUND,
            status=Transaction.Status.SUCCESS,
            related_order_id=str(order.pk),
            description=f"{label} refunded to buyer — funds reversed [{reason}]"[:255],
        )
        Transaction.objects.create(
            wallet=buyer_wallet, amount=total,
            transaction_type=Transaction.TransactionType.REFUND,
            status=Transaction.Status.SUCCESS,
            related_order_id=str(order.pk),
            description=f"Refund for {label} [{reason}]"[:255],
        )
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.delivery_status = Order.DeliveryStatus.CANCELLED
        order.save()
    logger.info("ESCROW REFUNDED order=%s amount=%s reason=%s", order.pk, total, reason)
    return total
