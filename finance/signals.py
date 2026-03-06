# finance/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet, UserVirtualAccount
from .nellobyte import NellobyteClient

User = get_user_model()

@receiver(post_save, sender=User)
def provision_user_wallet_and_account(sender, instance, created, **kwargs):
    if created:
        # 1. Create the Local Wallet
        wallet, _ = Wallet.objects.get_or_create(user=instance)
        
        # 2. Call Nellobyte directly (No threading on PythonAnywhere)
        client = NellobyteClient()
        try:
            resp = client.create_reserved_account(
                user_full_name=f"{instance.first_name} {instance.last_name}" or instance.username,
                user_email=instance.email,
                user_phone=getattr(instance, 'phone', '08000000000')
            )

            # Check if Nellobyte actually returned a success code
            if resp and resp.get('status') == 'SUCCESS':
                UserVirtualAccount.objects.create(
                    wallet=wallet,
                    bank_name=resp.get('bank_name', 'Moniepoint'),
                    account_number=resp.get('account_number'),
                    account_name=resp.get('account_name')
                )
        except Exception as e:
            print(f"CRITICAL: Signal failed for {instance.email}: {e}")