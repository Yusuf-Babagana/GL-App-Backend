# finance/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet

User = get_user_model()

@receiver(post_save, sender=User)
def provision_user_wallet(sender, instance, created, **kwargs):
    if created:
        # Create the Local Wallet
        Wallet.objects.get_or_create(user=instance)