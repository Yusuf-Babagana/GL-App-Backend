import logging
import uuid
from decimal import Decimal
from datetime import timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from finance.utils import MonnifyAPI
from globalink_core.upload_paths import kyc_upload_path

logger = logging.getLogger(__name__)

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.ImageField(upload_to='category_icons/', blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

class Shop(models.Model):
    SHOP_TYPE_CHOICES = (
        ('retailer', 'Retailer'),
        ('wholesaler', 'Wholesaler'),
        ('manufacturer', 'Manufacturer'),
        ('service_provider', 'Service Provider'),
    )
    
    ID_TYPE_CHOICES = (
        ('national_id', 'National ID'),
        ('drivers_license', "Driver's License"),
        ('passport', 'Passport'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='merchant_shop'
    )
    
    # Personal Info Context (Step 1)
    owner_full_name = models.CharField(max_length=255, null=True, blank=True)
    owner_email = models.EmailField(null=True, blank=True)
    owner_phone = models.CharField(max_length=30, null=True, blank=True)
    id_type = models.CharField(max_length=30, choices=ID_TYPE_CHOICES, null=True, blank=True)
    id_number = models.CharField(max_length=100, null=True, blank=True)
    id_image = models.ImageField(upload_to=kyc_upload_path, null=True, blank=True)
    id_document = models.ImageField(upload_to=kyc_upload_path, blank=True, null=True) # Backward compatibility
    
    # Shop Info Context (Step 2)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    shop_type = models.CharField(max_length=30, choices=SHOP_TYPE_CHOICES, null=True, blank=True)
    business_phone = models.CharField(max_length=30, null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    country = models.CharField(max_length=100, default='Nigeria')
    state = models.CharField(max_length=100, default='Kano')
    logo = models.URLField(max_length=500, blank=True, null=True)
    
    # Business Registration Metadata Context
    is_registered = models.BooleanField(default=False)
    cac_number = models.CharField(max_length=100, null=True, blank=True)
    
    # Security Approval Access Flags
    is_active = models.BooleanField(default=False, db_index=True)
    rejection_reason = models.TextField(blank=True, null=True)
    date_applied = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_sales = models.IntegerField(default=0)
    monnify_sub_account_code = models.CharField(max_length=100, null=True, blank=True)

    def save(self, *args, **kwargs):
        """
        Safely intercepts the model save chain to prevent missing relation or API exceptions.
        """
        try:
            # Check if your user object has access to a related bank record descriptor manager and needs activation
            if self.is_active and not self.monnify_sub_account_code:
                if self.owner and hasattr(self.owner, 'bank_accounts'):
                    bank_info = self.owner.bank_accounts.filter(is_primary=True).first()
                    
                    if bank_info:
                        sub_code = MonnifyAPI.create_sub_account(
                            bank_code=bank_info.bank_code,
                            account_number=bank_info.account_number,
                            email=self.owner.email,
                            store_name=self.name
                        )
                        if sub_code:
                            self.monnify_sub_account_code = sub_code
        except Exception as e:
            # Log any quiet runtime background catch events cleanly without stopping the master save transaction
            logger.warning("Non-breaking background finance sync check failed: %s", e)

        # 🚀 CRITICAL: Run the parent save sequence so the entry writes to db.sqlite3!
        super().save(*args, **kwargs)

    def __str__(self):
        # Safely extract email fallback strings to prevent deep-lookup lookup attribute crashes
        owner_email = "No Owner Bound"
        try:
            owner = self.owner
            if owner:
                owner_email = getattr(owner, 'email', str(owner))
        except Exception:
            pass
            
        return f"{self.name or 'Unnamed Shop'} — ({owner_email})"

class MerchantProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='merchant_profile')
    business_phone = models.CharField(max_length=20, blank=True, null=True)
    id_type = models.CharField(max_length=50, blank=True, null=True)
    id_number = models.CharField(max_length=100, blank=True, null=True)
    id_document_image = models.ImageField(upload_to=kyc_upload_path, blank=True, null=True)

    def __str__(self):
        return f"MerchantProfile for {self.user.email}"

class Product(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='products', null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, db_index=True, related_name='products')
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    currency = models.CharField(max_length=3, default='NGN')
    stock = models.IntegerField(default=1)
    
    image = models.CharField(max_length=500, blank=True, null=True)
    video = models.URLField(max_length=500, blank=True, null=True) 
    video_ad_url = models.URLField(max_length=500, blank=True, null=True)
    is_ad = models.BooleanField(default=False)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['category', 'price']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['shop', '-created_at']),
        ]

    def __str__(self):
        return self.name

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    # Change from ImageField to CharField to support full Cloudinary URLs
    image = models.CharField(max_length=500)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"Image for {self.product.name}"

class Order(models.Model):
    class DeliveryStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        READY = 'ready_for_pickup', _('Ready for Pickup') # Seller has packed it
        PICKED_UP = 'picked_up', _('Picked Up')           # Rider has it
        IN_TRANSIT = 'in_transit', _('In Transit')        # On the way
        SHIPPED = 'shipped', _('Shipped')
        DELIVERED = 'delivered', _('Delivered')           # Done
        CANCELLED = 'cancelled', _('Cancelled')

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        PAID = 'paid', _('Paid (Settled)')
        CONFIRMED = 'confirmed', _('Confirmed by Buyer')
        ESCROW_HELD = 'escrow_held', _('Held in Escrow')  # Legacy
        RELEASED = 'released', _('Released to Seller')     # Legacy
        REFUNDED = 'refunded', _('Refunded')

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='received_orders', null=True, blank=True)
    
    shipping_address_json = models.JSONField(null=True, blank=True, default=dict)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    delivery_status = models.CharField(
        max_length=20, 
        choices=DeliveryStatus.choices, 
        default=DeliveryStatus.PENDING
    )
    
    payment_status = models.CharField(
        max_length=20, 
        choices=PaymentStatus.choices, 
        default=PaymentStatus.PENDING
    )
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Add this to track the Monnify transaction for this specific order
    monnify_reference = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    # We keep PaymentStatus.ESCROW_HELD but it now signifies 
    # "Paid but not yet settled/released by Monnify"

    order_number = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['buyer', 'order_number']

    def save(self, *args, **kwargs):
        if self.order_number is None:
            from django.db.models import Max
            max_num = Order.objects.filter(buyer=self.buyer).aggregate(
                Max('order_number')
            )['order_number__max']
            self.order_number = (max_num or 0) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order #{self.order_number or self.id} - {self.delivery_status}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField(default=1)
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product.name if self.product else 'Deleted Product'}"

class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart of {self.user.email}"

    @property
    def total_price(self):
        return sum(item.total_price for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('cart', 'product')

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def total_price(self):
        return self.product.price * self.quantity



class PromotedPost(models.Model):
    """
    A paid announcement/ticker slot. Payment tiers are fixed and mirrored
    in PromotedPostSerializer/the creation view — keep both in sync.
    """
    class DurationType(models.TextChoices):
        ONE_DAY = '24h', _('24 Hours')
        THREE_DAYS = '3days', _('3 Days')
        ONE_WEEK = '1wk', _('1 Week')

    PRICING = {
        DurationType.ONE_DAY: Decimal('1000.00'),
        DurationType.THREE_DAYS: Decimal('2000.00'),
        DurationType.ONE_WEEK: Decimal('4000.00'),
    }

    DURATION_TIMEDELTAS = {
        DurationType.ONE_DAY: timedelta(hours=24),
        DurationType.THREE_DAYS: timedelta(days=3),
        DurationType.ONE_WEEK: timedelta(weeks=1),
    }

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='promoted_posts')
    text_content = models.CharField(max_length=300)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='promoted_posts')
    duration_type = models.CharField(max_length=10, choices=DurationType.choices)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"PromotedPost({self.user.email}, {self.duration_type})"

    def save(self, *args, **kwargs):
        if self.is_active and not self.expires_at:
            self.expires_at = timezone.now() + self.DURATION_TIMEDELTAS[self.duration_type]
        super().save(*args, **kwargs)

    @classmethod
    def get_price(cls, duration_type):
        """Admin-configurable price for a tier, falling back to the hardcoded default."""
        override = PromotedPostPricing.objects.filter(
            duration_type=duration_type, is_active=True
        ).first()
        if override:
            return override.price
        return cls.PRICING[duration_type]


class PromotedPostPricing(models.Model):
    """
    Optional admin override for a PromotedPost duration tier's price.
    Leave a tier unconfigured (or inactive) to keep using PromotedPost.PRICING.
    """
    duration_type = models.CharField(
        max_length=10, choices=PromotedPost.DurationType.choices, unique=True
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True, help_text="Uncheck to fall back to the default price")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Promoted Post Pricing"
        verbose_name_plural = "Promoted Post Pricing"

    def __str__(self):
        return f"{self.get_duration_type_display()} — ₦{self.price}"


# Deprecated: Chat models moved to chat app. See chat/models.py.