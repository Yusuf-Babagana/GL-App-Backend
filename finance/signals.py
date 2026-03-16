# finance/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet
from .utils import MonnifyAPI
import threading

User = get_user_model()

@receiver(post_save, sender=User)
def auto_provision_account(sender, instance, created, **kwargs):
    if created:
        wallet, _ = Wallet.objects.get_or_create(user=instance)
        # Run in background to keep registration fast
        thread = threading.Thread(target=create_monnify_task, args=(instance, wallet))
        thread.start()

def create_monnify_task(user, wallet):
    try:
        acc_data = MonnifyAPI.create_virtual_account(user)
        if acc_data:
            wallet.account_number = acc_data['account_number']
            wallet.bank_name = acc_data['bank_name']
            wallet.bank_code = acc_data['bank_code']
            wallet.save()
    except Exception as e:
        print(f"Provisioning Error: {e}")