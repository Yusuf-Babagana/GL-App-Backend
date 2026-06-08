from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import uuid

# ---------------------------------------------------------------------------
# Financial Constants
# ---------------------------------------------------------------------------
MONNIFY_DEPOSIT_RATE = Decimal('0.01')
MONNIFY_DEPOSIT_CAP  = Decimal('300.00')

GLAPP_COMMISSION_RATE = Decimal('0.05')
GLAPP_COMMISSION_CAP  = Decimal('2500.00')

class Wallet(models.Model):
    """
    The digital wallet for every user.
    Holds their available balance and funds currently locked in escrow.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='wallet'
    )
    currency = models.CharField(max_length=3, default='NGN')
    
    # Funds that can be withdrawn or used immediately
    available_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Funds earned by Seller but locked until Buyer confirms receipt (or 7-day auto-release)
    locked_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Legacy: Funds locked in ongoing orders/jobs (Escrow) — kept for backward compatibility
    escrow_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # --- ADD THESE MONNIFY FIELDS ---
    account_number = models.CharField(max_length=20, null=True, blank=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    account_reference = models.CharField(
        max_length=100, 
        unique=True, 
        default=uuid.uuid4
    )
    bank_code = models.CharField(max_length=10, null=True, blank=True)
    # --------------------------------
    
    is_frozen = models.BooleanField(default=False) # Security freeze
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        name = self.user.full_name if self.user.full_name else self.user.email
        return f"{name}'s Wallet ({self.currency})"

    @property
    def balance(self):
        return self.available_balance + self.locked_balance

    @property
    def total_assets(self):
        return self.available_balance + self.locked_balance + self.escrow_balance

class Transaction(models.Model):
    """
    An immutable record of every financial movement.
    """
    class TransactionType(models.TextChoices):
        DEPOSIT = 'deposit', _('Deposit (Top-up)')
        PAYMENT = 'payment', _('Payment for Order/Job')
        ESCROW_LOCK = 'escrow_lock', _('Locked in Escrow')
        ESCROW_RELEASE = 'escrow_release', _('Released from Escrow')
        REFUND = 'refund', _('Refund')
        WITHDRAWAL = 'withdrawal', _('Withdrawal to Bank')
        FEE = 'fee', _('Platform Fee')
        BILL_PAYMENT = 'bill_payment', _('VTpass Bill Payment')

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        SUCCESS = 'success', _('Success')
        FAILED = 'failed', _('Failed')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    
    # Amount can be positive (credit) or negative (debit)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # External References (e.g., Opay Reference ID)
    reference = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    
    # Linking to internal objects (Generic or direct optional links)
    # Keeping it simple with direct optional links for now
    related_order_id = models.CharField(max_length=50, blank=True, null=True) # ID of the Order
    related_job_id = models.CharField(max_length=50, blank=True, null=True)   # ID of the Job

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"

class BankAccount(models.Model):
    wallet = models.ForeignKey(
        'Wallet', 
        on_delete=models.CASCADE, 
        related_name='bank_accounts',
        null=True, 
        blank=True)
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=10, unique=True)
    account_name = models.CharField(max_length=200)
    reference = models.CharField(max_length=100, unique=True, null=True, blank=True) # Monnify reference



class WithdrawalTicket(models.Model):
    """
    Admin-payout-queue entry. Funds are pre-deducted from the user's
    available_balance at creation time. An admin processes the batch
    offline and flips the status to SUCCESSFUL or REJECTED.
    """

    class StatusChoices(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESSFUL = 'SUCCESSFUL', 'Successful'
        REJECTED = 'REJECTED', 'Rejected'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='withdrawal_tickets')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    bank_code = models.CharField(max_length=3)
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=10)
    account_name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"#{self.pk} {self.user.email} ₦{self.amount} [{self.status}]"


class PlatformRevenue(models.Model):
    """
    Single-row ledger tracking cumulative platform commission income.
    """
    total_commission = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Platform revenues"

    def __str__(self):
        return f"Platform Revenue: ₦{self.total_commission}"

    @classmethod
    def get_singleton(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def add_commission(cls, amount):
        with transaction.atomic():
            row = cls.objects.select_for_update().get_or_create(pk=1)[0]
            row.total_commission += amount
            row.save()
        return row.total_commission


class DataMarkup(models.Model):
    network = models.CharField(
        max_length=50, unique=True,
        help_text="e.g. mtn-data, glo-data, airtel-data, 9mobile-data"
    )
    network_label = models.CharField(
        max_length=50,
        help_text="Display name e.g. MTN, Glo"
    )
    markup_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('50.00'),
        help_text="Fixed markup amount added to the original price (₦) — legacy, use price_factor instead"
    )
    price_factor = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1.10'),
        help_text="Multiplier on Nellobyte price (e.g. 1.10 = sell at 110% of original)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Data Markup"
        verbose_name_plural = "Data Markups"

    def __str__(self):
        return f"{self.network_label} (×{self.price_factor})"