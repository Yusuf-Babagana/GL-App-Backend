# finance/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet
from .utils import MonnifyAPI
import threading
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_user_wallet_and_account(sender, instance, created, **kwargs):
    """
    Automates account creation immediately upon user registration.
    """
    if created:
        # 1. Ensure the wallet exists first
        wallet, _ = Wallet.objects.get_or_create(user=instance)
        
        # 2. Trigger Monnify API in a background thread
        thread = threading.Thread(target=provision_monnify_task, args=(instance, wallet))
        thread.daemon = True
        thread.start()

def provision_monnify_task(user, wallet):
    try:
        # Call your existing utility
        acc_data = MonnifyAPI.create_virtual_account(user)
        if acc_data:
            wallet.account_number = acc_data['account_number']
            wallet.bank_name = acc_data['bank_name']
            wallet.bank_code = acc_data['bank_code']
            wallet.save()
            print(f"✅ Success: Reserved account created for {user.email}")
        else:
            print(f"❌ Failed: Monnify returned None for {user.email}")
    except Exception as e:
        logger.error(f"CRITICAL: Signal failed to provision account for {user.email} -> {e}")