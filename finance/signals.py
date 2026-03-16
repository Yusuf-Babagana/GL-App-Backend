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
def handle_user_wallet_and_monnify_account(sender, instance, created, **kwargs):
    """
    1. Ensures every user has a wallet.
    2. Automatically triggers Monnify account creation if BVN is present 
       but bank details are missing.
    """
    # Always ensure a wallet exists for the user
    wallet, _ = Wallet.objects.get_or_create(user=instance)

    # Check logic:
    # We trigger Monnify ONLY if the user has a BVN (mandatory for Live)
    # AND the wallet doesn't have an account number yet.
    if instance.bvn and not wallet.account_number:
        # We use threading so the API call doesn't slow down the User's save process
        thread = threading.Thread(
            target=provision_monnify_task, 
            args=(instance, wallet)
        )
        thread.daemon = True
        thread.start()

def provision_monnify_task(user, wallet):
    """Background task to communicate with Monnify API."""
    try:
        # Attempt to create account via our utility
        acc_data = MonnifyAPI.create_virtual_account(user)
        
        if acc_data:
            wallet.account_number = acc_data['account_number']
            wallet.bank_name = acc_data['bank_name']
            wallet.bank_code = acc_data['bank_code']
            wallet.save()
            logger.info(f"✅ Success: Monnify account {wallet.account_number} provisioned for {user.email}")
        else:
            # This usually happens if Monnify rejects the BVN/Name combination
            logger.warning(f"⚠️ Monnify returned None for {user.email}. Check utility logs.")
            
    except Exception as e:
        logger.error(f"CRITICAL: Signal failed to provision account for {user.email} -> {str(e)}")