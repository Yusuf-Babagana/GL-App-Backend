# finance/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet
from .utils import MonnifyAPI
import threading

User = get_user_model()

@receiver(post_save, sender=User)
def provision_monnify_account(sender, instance, created, **kwargs):
    if created:
        # 1. Ensure Wallet exists
        wallet, _ = Wallet.objects.get_or_create(user=instance)
        
        # 2. Call Monnify in a background thread to prevent registration delay
        def task():
            try:
                account_data = MonnifyAPI.create_virtual_account(instance)
                if account_data:
                    wallet.account_number = account_data['account_number']
                    wallet.bank_name = account_data['bank_name']
                    wallet.bank_code = account_data['bank_code']
                    wallet.save()
            except Exception as e:
                print(f"FAILED TO PROVISION MONNIFY: {e}")

        threading.Thread(target=task).start()