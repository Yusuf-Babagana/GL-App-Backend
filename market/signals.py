from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
import random

@receiver(post_save, sender=Order)
def generate_delivery_code(sender, instance, created, **kwargs):
    if created and not instance.delivery_code:
        # Generate a simple 4-digit PIN
        pin = str(random.randint(1000, 9999))
        instance.delivery_code = pin
        instance.save()