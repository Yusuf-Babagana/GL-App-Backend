from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet
from .utils import MonnifyAPI

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_wallet_and_virtual_account(sender, instance, created, **kwargs):
    if created:
        # 1. Create the Wallet object first
        wallet, _ = Wallet.objects.get_or_create(user=instance)
        
        # 2. Call Monnify to get the real account number
        try:
            account_info = MonnifyAPI.create_virtual_account(instance)
            if account_info:
                wallet.account_number = account_info['account_number']
                wallet.bank_name = account_info['bank_name']
                wallet.bank_code = account_info['bank_code']
                wallet.save()
                print(f"Successfully generated account for {instance.email}")
            else:
                print(f"Monnify returned None for {instance.email}")
        except Exception as e:
            print(f"Error calling Monnify during registration: {e}")