from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    """
    Custom manager for the User model where email is the unique identifier
    for authentication instead of usernames.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        
        # AbstractUser still has a username field by default. 
        # We sync it with email to keep it unique and valid.
        extra_fields.setdefault('username', email)
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)

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
    push_token = models.CharField(max_length=255, blank=True, null=True)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    
    roles = models.JSONField(default=list) 
    active_role = models.CharField(
        max_length=20, 
        choices=Roles.choices, 
        default=Roles.BUYER
    )

    # --- FINANCIAL KYC DATA (Added for Monnify Production) ---
    bvn = models.CharField(max_length=11, blank=True, null=True, help_text="11-digit Bank Verification Number")
    nin = models.CharField(max_length=11, blank=True, null=True, help_text="11-digit National Identification Number")
    # ---------------------------------------------------------

    # KYC & Trust
    kyc_status = models.CharField(
        max_length=20, 
        choices=KycStatus.choices, 
        default=KycStatus.UNVERIFIED
    )
    
    id_document_type = models.CharField(max_length=50, blank=True, null=True) 
    id_document_image = models.ImageField(upload_to='kyc_docs/', blank=True, null=True)
    selfie_image = models.ImageField(upload_to='kyc_docs/', blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)

    # Localization
    language_preference = models.CharField(
        max_length=10, 
        default='en', 
        choices=[('en', 'English'), ('ar', 'Arabic'), ('ha', 'Hausa')]
    )

    transaction_pin = models.CharField(max_length=128, null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return f"{self.email} ({self.active_role})"

    def set_transaction_pin(self, raw_pin):
        from django.contrib.auth.hashers import make_password
        self.transaction_pin = make_password(raw_pin)

    def check_transaction_pin(self, raw_pin):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_pin, self.transaction_pin)

class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50, default='Home') 
    full_name = models.CharField(max_length=255)
    street_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='Nigeria')
    zip_code = models.CharField(max_length=20, blank=True)
    phone_number = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user).update(is_default=False)
        super().save(*args, **kwargs)