"""
Dispute endpoints.

Buyer:   open / withdraw / view a dispute on a paid, dispatched order.
Seller:  respond to a dispute on their order.
Admin:   list disputes and decide them (refund the buyer or release to the seller).
"""
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from globalink_core.notify import notify_admins, notify_user
from .escrow import EscrowError, refund_buyer, release_to_seller
from .models import Dispute, Order

logger = logging.getLogger('payments')


def _dispute_dict(d):
    return {
        "id": d.pk,
        "order_id": d.order_id,
        "order_number": d.order.order_number,
        "amount": str(d.order.total_price),
        "reason": d.reason,
        "reason_label": d.get_reason_display(),
        "description": d.description,
        "seller_response": d.seller_response,
        "status": d.status,
        "resolution_note": d.resolution_note,
        "buyer": d.opened_by.email,
        "seller": d.order.shop.owner.email if d.order.shop_id else None,
        "created_at": d.created_at,
        "resolved_at": d.resolved_at,
    }


class BuyerOpenDisputeView(APIView):
    """POST: open a dispute (freezes the escrowed funds). GET: latest dispute on the order."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        d = (Dispute.objects.select_related('order__shop__owner', 'opened_by')
             .filter(order_id=order_id).filter(order__buyer=request.user).first())
        if not d:
            return Response({"status": "error", "message": "No dispute on this order."}, status=404)
        return Response(_dispute_dict(d))

    def post(self, request, order_id):
        reason = request.data.get('reason')
        description = (request.data.get('description') or '').strip()
        if reason not in Dispute.Reason.values:
            return Response({"status": "error", "message": "Choose a valid reason."}, status=400)
        if len(description) < 10:
            return Response({"status": "error", "message": "Please describe the problem (at least 10 characters)."},
                            status=400)

        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order_id, buyer=request.user)
                if order.payment_status == Order.PaymentStatus.DISPUTED:
                    return Response({"status": "error", "message": "This order already has an open dispute."},
                                    status=400)
                if order.payment_status != Order.PaymentStatus.PAID:
                    return Response({"status": "error",
                                     "message": "Only paid orders that haven't been confirmed can be disputed."},
                                    status=400)
                if order.delivery_status not in Order.DISPATCHED_STATUSES:
                    return Response({"status": "error",
                                     "message": "The seller hasn't dispatched this order yet. You can cancel it for a full refund."},
                                    status=400)
                dispute = Dispute.objects.create(
                    order=order, opened_by=request.user, reason=reason, description=description)
                order.payment_status = Order.PaymentStatus.DISPUTED
                order.save()
        except Order.DoesNotExist:
            return Response({"status": "error", "message": "Order not found."}, status=404)
        except IntegrityError:
            return Response({"status": "error", "message": "This order already has an open dispute."}, status=400)

        logger.warning("DISPUTE OPENED id=%s order=%s reason=%s", dispute.pk, order.pk, reason)
        label = f"#{order.order_number or order.pk}"
        notify_user(order.shop.owner, "A buyer opened a dispute",
                    f"Order {label} (₦{order.total_price:,.2f}) was disputed: {dispute.get_reason_display()}. "
                    "The payment is frozen. Open the order and reply with your side.",
                    {"type": "dispute", "order_id": order.pk})
        notify_user(request.user, "Dispute opened",
                    f"Your dispute on order {label} was received. The payment is frozen until we review it.",
                    {"type": "dispute", "order_id": order.pk})
        notify_admins("Dispute needs review",
                      f"Dispute #{dispute.pk} on order {label} (₦{order.total_price:,.2f}). "
                      f"Reason: {dispute.get_reason_display()}.\n\n{dispute.description}")
        return Response({
            "status": "success",
            "message": "Dispute opened. The funds are frozen until our team reviews it.",
            "dispute_id": dispute.pk,
        }, status=status.HTTP_201_CREATED)


class BuyerWithdrawDisputeView(APIView):
    """The buyer changed their mind (e.g. the item arrived): unfreeze the order."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=order_id, buyer=request.user)
            except Order.DoesNotExist:
                return Response({"status": "error", "message": "Order not found."}, status=404)
            dispute = Dispute.objects.select_for_update().filter(order=order, status=Dispute.Status.OPEN).first()
            if not dispute or order.payment_status != Order.PaymentStatus.DISPUTED:
                return Response({"status": "error", "message": "There is no open dispute to withdraw."}, status=400)
            dispute.status = Dispute.Status.WITHDRAWN
            dispute.resolved_at = timezone.now()
            dispute.save()
            order.payment_status = Order.PaymentStatus.PAID
            order.save()
        notify_user(order.shop.owner, "Dispute withdrawn",
                    f"The buyer withdrew the dispute on order #{order.order_number or order.pk}.",
                    {"type": "dispute", "order_id": order.pk})
        return Response({"status": "success", "message": "Dispute withdrawn. You can now confirm receipt."})


class SellerDisputeRespondView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        text = (request.data.get('response') or '').strip()
        if len(text) < 5:
            return Response({"status": "error", "message": "Please write a response."}, status=400)
        dispute = Dispute.objects.select_related('order', 'opened_by').filter(
            order_id=order_id, order__shop__owner=request.user, status=Dispute.Status.OPEN).first()
        if not dispute:
            return Response({"status": "error", "message": "No open dispute on this order."}, status=404)
        dispute.seller_response = text
        dispute.save(update_fields=['seller_response'])
        notify_user(dispute.opened_by, "The seller replied to your dispute",
                    f"On order #{dispute.order.order_number or dispute.order_id}: {text[:200]}",
                    {"type": "dispute", "order_id": dispute.order_id})
        return Response({"status": "success", "message": "Response recorded."})


class SellerDisputeDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        d = (Dispute.objects.select_related('order__shop__owner', 'opened_by')
             .filter(order_id=order_id, order__shop__owner=request.user).first())
        if not d:
            return Response({"status": "error", "message": "No dispute on this order."}, status=404)
        return Response(_dispute_dict(d))


class AdminDisputeListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        qs = Dispute.objects.select_related('order__shop__owner', 'opened_by')
        st = request.query_params.get('status')
        if st:
            qs = qs.filter(status=st)
        return Response({"results": [_dispute_dict(d) for d in qs[:200]]})


def resolve_dispute(dispute_id, decision, note, admin_user):
    """
    decision: 'refund' (money back to buyer) or 'release' (pay the seller).
    Raises EscrowError / ValueError; callers turn those into responses.
    """
    if decision not in ('refund', 'release'):
        raise ValueError("decision must be 'refund' or 'release'")
    with transaction.atomic():
        dispute = Dispute.objects.select_for_update().select_related('order__shop__owner', 'opened_by').get(pk=dispute_id)
        if dispute.status != Dispute.Status.OPEN:
            raise EscrowError("This dispute has already been resolved.")
        reason = f"dispute #{dispute.pk}"
        if decision == 'refund':
            refund_buyer(dispute.order_id, reason=reason, restore_stock=False)
            dispute.status = Dispute.Status.RESOLVED_REFUND
        else:
            release_to_seller(dispute.order_id, reason=reason)
            dispute.status = Dispute.Status.RESOLVED_RELEASE
        dispute.resolution_note = note
        dispute.resolved_by = admin_user
        dispute.resolved_at = timezone.now()
        dispute.save()
    logger.warning("DISPUTE RESOLVED id=%s decision=%s by=%s", dispute.pk, decision, admin_user.pk)
    order = dispute.order
    label = f"#{order.order_number or order.pk}"
    if decision == 'refund':
        buyer_msg = f"We decided in your favour on order {label}. ₦{order.total_price:,.2f} was refunded to your wallet."
        seller_msg = f"The dispute on order {label} was decided for the buyer and the payment was refunded."
    else:
        buyer_msg = f"We reviewed order {label} and released the payment to the seller."
        seller_msg = f"The dispute on order {label} was decided for you. The payment was released to your wallet."
    notify_user(dispute.opened_by, "Dispute resolved", f"{buyer_msg} Note: {note}", {"type": "dispute", "order_id": order.pk})
    if order.shop_id:
        notify_user(order.shop.owner, "Dispute resolved", f"{seller_msg} Note: {note}", {"type": "dispute", "order_id": order.pk})
    return dispute


class AdminResolveDisputeView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, dispute_id):
        note = (request.data.get('note') or '').strip()
        if len(note) < 5:
            return Response({"status": "error", "message": "A resolution note is required."}, status=400)
        try:
            d = resolve_dispute(dispute_id, request.data.get('decision'), note, request.user)
        except Dispute.DoesNotExist:
            return Response({"status": "error", "message": "Dispute not found."}, status=404)
        except (EscrowError, ValueError) as e:
            return Response({"status": "error", "message": str(e)}, status=400)
        return Response({"status": "success", "dispute": _dispute_dict(d)})
