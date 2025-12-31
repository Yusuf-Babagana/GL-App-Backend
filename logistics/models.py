from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

# We reference the Order model using a string to avoid circular import issues
# if market.models imports logistics.models later.

class DeliveryJob(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', _('Available for Pickup')
        ACCEPTED = 'accepted', _('Accepted by Driver')
        PICKED_UP = 'picked_up', _('Picked Up')
        IN_TRANSIT = 'in_transit', _('In Transit')
        DELIVERED = 'delivered', _('Delivered')
        FAILED = 'failed', _('Delivery Failed')

    # Link to the Market Order
    order = models.OneToOneField(
        'market.Order', 
        on_delete=models.CASCADE, 
        related_name='delivery_job'
    )
    
    # The Driver (User with Delivery Partner role)
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_deliveries'
    )

    # Status Tracking
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.AVAILABLE
    )
    
    # Financials
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Timestamps for Performance Tracking
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Proof of Delivery (Critical for releasing Escrow) [cite: 30]
    proof_of_delivery_image = models.ImageField(upload_to='delivery_proofs/', blank=True, null=True)
    delivery_code = models.CharField(
        max_length=6, 
        blank=True, 
        null=True, 
        help_text="Code provided by buyer to confirm receipt"
    )
    
    # Location Snapshots (In case user changes address mid-delivery)
    pickup_address_text = models.TextField(help_text="Store Address")
    delivery_address_text = models.TextField(help_text="Buyer Address")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Delivery for Order #{self.order.id} - {self.status}"

class Vehicle(models.Model):
    """
    Optional: To track what kind of vehicle the partner is using.
    """
    class VehicleType(models.TextChoices):
        BIKE = 'bike', _('Motorbike')
        CAR = 'car', _('Car')
        VAN = 'van', _('Van')
        TRUCK = 'truck', _('Truck')

    driver = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='vehicle'
    )
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices)
    plate_number = models.CharField(max_length=20)
    color = models.CharField(max_length=30)
    
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.driver.full_name}'s {self.vehicle_type}"