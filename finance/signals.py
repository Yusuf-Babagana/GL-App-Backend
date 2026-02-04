import uuid
import requests
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_wallet_and_virtual_account(sender, instance, created, **kwargs):
    if created:
        # 1. Create the Wallet Object with a unique reference
        # We use get_or_create just to be safe, setting the default reference
        Wallet.objects.get_or_create(
            user=instance, 
            defaults={'account_reference': str(uuid.uuid4())}
        )
        
        # 2. Call Monnify to generate Virtual Account
        # (We will implement the actual API call in a utility file later)
        # For now, this ensures the wallet exists immediately.