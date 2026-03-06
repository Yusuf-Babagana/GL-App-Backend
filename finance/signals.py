# finance/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet, UserVirtualAccount
from .nellobyte import NellobyteClient
import threading
from decimal import Decimal

User = get_user_model()

@receiver(post_save, sender=User)
def provision_user_wallet_and_account(sender, instance, created, **kwargs):
    if created:
        # 1. Create the Local Wallet immediately
        wallet, _ = Wallet.objects.get_or_create(user=instance)
        
        # 2. Call Nellobyte in a background thread so registration doesn't feel slow
        # We pass the user details to Nellobyte to get the unique bank account
        thread = threading.Thread(target=get_nellobyte_account, args=(instance, wallet))
        thread.start()

def get_nellobyte_account(user, wallet):
    """Background task to fetch account from Nellobyte"""
    client = NellobyteClient()
    
    # We use the user's name, email, and phone for registration
    first_name = getattr(user, 'first_name', '')
    last_name = getattr(user, 'last_name', '')
    full_name = f"{first_name} {last_name}".strip() or user.username

    resp = client.create_reserved_account(
        user_full_name=full_name,
        user_email=user.email,
        user_phone=getattr(user, 'phone', '08000000000') # Ensure field exists
    )

    if resp and resp.get('status') == 'SUCCESS':
        # Nellobyte returns account details
        UserVirtualAccount.objects.create(
            wallet=wallet,
            bank_name=resp.get('bank_name', 'Moniepoint'),
            account_number=resp.get('account_number'),
            account_name=resp.get('account_name')
        )