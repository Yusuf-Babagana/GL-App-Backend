from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    """
    Custom User Model for Globalink.
    Supports multiple roles: Buyer, Seller, Job Seeker, Delivery Partner.
    """
    
    class Roles(models.TextChoices):
        BUYER = 'buyer', _('Buyer')
        SELLER = 'seller', _('Seller')
        JOB_SEEKER = 'job_seeker', _('Job Seeker')
        EMPLOYER = 'employer', _('Employer')
        DELIVERY_PARTNER = 'delivery_partner', _('Delivery Partner')
        ADMIN = 'admin', _('Admin')

    class KycStatus(models.TextChoices):
        UNVERIFIED = 'unverified', _('Unverified')
        PENDING = 'pending', _('Pending Review')
        VERIFIED = 'verified', _('Verified')
        REJECTED = 'rejected', _('Rejected')

    # Basic Info
    full_name = models.CharField(_("Full Name"), max_length=255)
    email = models.EmailField(_("Email Address"), unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)

    # Role Management (Users can have multiple roles, stored as a list)
    # We use a JSONField or simple comma-separated string if using SQLite. 
    # For robust Postgres, use ArrayField. Here is a compatible JSON approach:
    roles = models.JSONField(default=list) 
    active_role = models.CharField(
        max_length=20, 
        choices=Roles.choices, 
        default=Roles.BUYER
    )

    # KYC & Trust [cite: 48-51]
    kyc_status = models.CharField(
        max_length=20, 
        choices=KycStatus.choices, 
        default=KycStatus.UNVERIFIED
    )
    
    # KYC Documents (Only visible to Admin)
    id_document_type = models.CharField(max_length=50, blank=True, null=True) # e.g., Passport
    id_document_image = models.ImageField(upload_to='kyc_docs/', blank=True, null=True)
    selfie_image = models.ImageField(upload_to='kyc_docs/', blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)

    # Localization [cite: 80]
    language_preference = models.CharField(
        max_length=10, 
        default='en', 
        choices=[('en', 'English'), ('ar', 'Arabic'), ('ha', 'Hausa')]
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']

    def __str__(self):
        return f"{self.email} ({self.active_role})"

class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50, default='Home') # Home, Work
    full_name = models.CharField(max_length=255)
    street_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='Nigeria')
    zip_code = models.CharField(max_length=20, blank=True)
    phone_number = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    
    # For Delivery Mapping
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.is_default:
            # Set all other addresses for this user to False
            Address.objects.filter(user=self.user).update(is_default=False)
        super().save(*args, **kwargs)