from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import uuid

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
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Funds locked in ongoing orders/jobs (Escrow)
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
    def total_assets(self):
        return self.balance + self.escrow_balance

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
    """
    Saved bank details for Sellers/Workers to withdraw their funds.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=100)
    
    is_verified = models.BooleanField(default=False) # Integration check
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"

class WithdrawalRequest(models.Model):
    """
    Requests from users to move money from Wallet -> Bank Account.
    """
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20, 
        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='pending'
    )
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)