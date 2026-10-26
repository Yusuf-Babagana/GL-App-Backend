"""
Withdrawal tickets: the user asks, an admin pays the bank manually, then marks it done.

The money is taken out of the user's available balance THE MOMENT THEY ASK, and a
PENDING ledger row (reference WDR-<ticket id>) records the hold. From then on:

  approve  -> the ledger row becomes SUCCESS (the money has left for the bank)
  reject   -> the hold is returned to the user (ledger row FAILED + a REFUND row)

Both are idempotent: they lock the ticket first, so a double click, or the same
ticket approved from the API and the dashboard at once, can only ever act once.

Tickets created before this change did not hold anything (no WDR- ledger row).
Those are "legacy": approving one still deducts at approval time, and rejecting one
refunds nothing, because nothing was taken.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Transaction, Wallet, WithdrawalTicket

logger = logging.getLogger('payments')

MIN_WITHDRAWAL = Decimal('100.00')


class WithdrawalError(Exception):
    """A request that can't be honoured; the message is safe to show the user."""


def parse_amount(raw):
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise WithdrawalError("Invalid amount format.")
    if not amount.is_finite() or amount != amount.quantize(Decimal('0.01')):
        raise WithdrawalError("Amount must be a valid naira amount with at most 2 decimal places.")
    if amount < MIN_WITHDRAWAL:
        raise WithdrawalError(f"The minimum withdrawal is ₦{MIN_WITHDRAWAL:,.0f}.")
    return amount


def hold_reference(ticket_id):
    return f"WDR-{ticket_id}"


def create_withdrawal(user, amount, *, bank_code, bank_name, account_number, account_name):
    """Take the money out of the available balance and open a PENDING ticket."""
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(user=user)
        if wallet.is_frozen:
            raise WithdrawalError("This wallet is frozen. Contact support.")
        if wallet.available_balance < amount:
            raise WithdrawalError("Insufficient available balance.")

        ticket = WithdrawalTicket.objects.create(
            user=user, amount=amount, bank_code=bank_code, bank_name=bank_name,
            account_number=account_number, account_name=account_name,
            status=WithdrawalTicket.StatusChoices.PENDING,
        )
        wallet.available_balance -= amount
        wallet.save()
        Transaction.objects.create(
            wallet=wallet, amount=-amount,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.PENDING,
            reference=hold_reference(ticket.pk),
            description=f"Withdrawal to {account_name} - {account_number} ({bank_name}) [awaiting payout]"[:255],
        )
    logger.info("WITHDRAWAL REQUESTED ticket=%s user=%s amount=%s", ticket.pk, user.pk, amount)
    return ticket


def _locked_pending_ticket(ticket_id):
    ticket = WithdrawalTicket.objects.select_for_update().select_related('user').get(pk=ticket_id)
    if ticket.status != WithdrawalTicket.StatusChoices.PENDING:
        raise WithdrawalError("Ticket already processed.")
    return ticket


def approve_ticket(ticket_id, admin_user=None):
    with transaction.atomic():
        ticket = _locked_pending_ticket(ticket_id)
        hold = Transaction.objects.select_for_update().filter(reference=hold_reference(ticket.pk)).first()
        wallet = Wallet.objects.select_for_update().get(user=ticket.user)
        if hold is not None:
            hold.status = Transaction.Status.SUCCESS
            hold.description = hold.description.replace("[awaiting payout]", "[paid]")[:255]
            hold.save()
        else:
            # Legacy ticket: nothing was held, so take the money now.
            if wallet.available_balance < ticket.amount:
                raise WithdrawalError("Insufficient balance. User funds may have been used elsewhere.")
            wallet.available_balance -= ticket.amount
            wallet.save()
            Transaction.objects.create(
                wallet=wallet, amount=-ticket.amount,
                transaction_type=Transaction.TransactionType.WITHDRAWAL,
                status=Transaction.Status.SUCCESS,
                reference=hold_reference(ticket.pk),
                description=f"Withdrawal to {ticket.account_name} - {ticket.account_number} ({ticket.bank_name}) [paid]"[:255],
            )
        ticket.status = WithdrawalTicket.StatusChoices.SUCCESSFUL
        ticket.save()
    logger.info("WITHDRAWAL PAID ticket=%s amount=%s by=%s", ticket.pk, ticket.amount, getattr(admin_user, 'pk', None))
    return ticket


def reject_ticket(ticket_id, admin_user=None):
    with transaction.atomic():
        ticket = _locked_pending_ticket(ticket_id)
        hold = Transaction.objects.select_for_update().filter(reference=hold_reference(ticket.pk)).first()
        if hold is not None and hold.status == Transaction.Status.PENDING:
            wallet = Wallet.objects.select_for_update().get(user=ticket.user)
            wallet.available_balance += ticket.amount
            wallet.save()
            hold.status = Transaction.Status.FAILED
            hold.description = hold.description.replace("[awaiting payout]", "[rejected, refunded]")[:255]
            hold.save()
            Transaction.objects.create(
                wallet=wallet, amount=ticket.amount,
                transaction_type=Transaction.TransactionType.REFUND,
                status=Transaction.Status.SUCCESS,
                reference=f"{hold_reference(ticket.pk)}-REFUND",
                description=f"Refund: withdrawal ticket #{ticket.pk} rejected"[:255],
            )
        # else: legacy ticket, nothing was held, so there is nothing to give back.
        ticket.status = WithdrawalTicket.StatusChoices.REJECTED
        ticket.save()
    logger.info("WITHDRAWAL REJECTED ticket=%s amount=%s by=%s", ticket.pk, ticket.amount, getattr(admin_user, 'pk', None))
    return ticket
