from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet
from .monnify import MonnifyClient
import uuid

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        # 1. Create the Wallet locally first
        wallet = Wallet.objects.create(
            user=instance,
            account_reference=str(uuid.uuid4())
        )
        
        # 2. Trigger Monnify Account Generation
        try:
            client = MonnifyClient()
            user_name = instance.full_name or f"User_{instance.id}"
            
            resp = client.generate_virtual_account(
                user_name,
                instance.email,
                wallet.account_reference
            )

            if resp and resp.get('requestSuccessful'):
                body = resp.get('responseBody')
                wallet.account_number = body.get('accountNumber')
                wallet.bank_name = body.get('bankName')
                wallet.bank_code = body.get('bankCode')
                wallet.save()
                print(f"✅ Monnify Account Assigned: {wallet.account_number}")
        except Exception as e:
            print(f"❌ Monnify Auto-Generation Error: {str(e)}")