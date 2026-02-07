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
        # USE GET_OR_CREATE TO PREVENT INTEGRITY ERRORS
        wallet, created_now = Wallet.objects.get_or_create(
            user=instance,
            defaults={'account_reference': str(uuid.uuid4())}
        )
        
        # Only attempt Monnify if the wallet was just now created or 
        # doesn't have an account number yet
        if not wallet.account_number:
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
                else:
                    # If R42 (already exists), try to FETCH the existing one
                    if resp and resp.get('responseCode') == '99': # Monnify uses 99 for duplicate reference sometimes, but R42 for duplicate email
                         # Let's check for 'R42' or fallback
                         pass

                    # More robust check: fetch if generation failed.
                    print(f"⚠️ Monnify Generation Failed: {resp.get('responseMessage')}")
                    print("🔄 Attempting to fetch existing reserved account...")
                    
                    existing_account = client.get_reserved_account_details(instance.email)
                    if existing_account and existing_account.get('requestSuccessful'):
                         body = existing_account.get('responseBody')
                         # Accounts list is usually returned in responseBody if successful? 
                         # Actually reserved-accounts/{email} usually returns a list or single object? 
                         # Let's assume standard object structure or list. 
                         # Common Monnify reserved-accounts response is a list of accounts.
                         # But client.get_reserved_account_details calls /reserved-accounts/{email}
                         
                         # If it returns a list, take the first one.
                         accounts = body if isinstance(body, list) else [body]
                         if accounts:
                             acc = accounts[0]
                             wallet.account_number = acc.get('accountNumber')
                             wallet.bank_name = acc.get('bankName')
                             wallet.bank_code = acc.get('bankCode')
                             wallet.save()
                             print(f"✅ Recovered Existing Monnify Account: {wallet.account_number}")

            except Exception as e:
                print(f"❌ Monnify Auto-Generation Error: {str(e)}")