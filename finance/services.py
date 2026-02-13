import hmac
import hashlib
import requests
import time
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from .models import Wallet, Transaction

class PaystackService:
    """
    Service layer for Paystack integration.
    Handles transaction initialization, verification, and wallet crediting.
    """
    BASE_URL = "https://api.paystack.co"
    SECRET_KEY = settings.PAYSTACK_SECRET_KEY

    @classmethod
    def _get_headers(cls):
        return {
            "Authorization": f"Bearer {cls.SECRET_KEY}",
            "Content-Type": "application/json",
        }

    @classmethod
    def initiate_deposit(cls, wallet, email, amount, reference):
        """
        Initializes a transaction with Paystack.
        Returns: {authorization_url, access_code, reference}
        """
        url = f"{cls.BASE_URL}/transaction/initialize"
        # Paystack expects amount in kobo
        payload = {
            "email": email,
            "amount": int(Decimal(str(amount)) * 100),
            "reference": reference,
            "callback_url": "https://standard.paystack.co/close" # Handled by Mobile SDK
        }

        response = requests.post(url, json=payload, headers=cls._get_headers())
        res_data = response.json()

        if response.status_code == 200 and res_data.get('status'):
            return res_data['data']
        raise Exception(f"Paystack Init Error: {res_data.get('message')}")

    @classmethod
    def verify_payment(cls, reference):
        """
        Checks Paystack API to verify the status of a transaction.
        """
        url = f"{cls.BASE_URL}/transaction/verify/{reference}"
        response = requests.get(url, headers=cls._get_headers())
        res_data = response.json()

        if response.status_code == 200 and res_data.get('status'):
            return res_data['data'] # Contains status, amount, etc.
        return None

    @classmethod
    @transaction.atomic
    def credit_wallet(cls, reference, amount_kobo=None):
        # Use select_for_update() to lock the transaction row immediately
        txn = Transaction.objects.select_for_update().get(reference=reference)

        if txn.status == 'success':
            return txn.wallet, False  # Already processed, do nothing

        # Lock the wallet row to prevent concurrent balance updates
        wallet = Wallet.objects.select_for_update().get(id=txn.wallet.id)
        
        # Standardize the amount logic
        if amount_kobo:
            actual_amount = Decimal(amount_kobo) / 100
            # If Paystack reports a different amount than we initiated, mark as failed for safety
            if actual_amount != txn.amount:
                txn.status = 'failed'
                txn.description = f"Fraud Alert: Expected {txn.amount}, got {actual_amount}"
                txn.save()
                return wallet, False

        wallet.balance += txn.amount
        wallet.save()

        txn.status = 'success'
        txn.save()
        return wallet, True

    @classmethod
    def resolve_bank_account(cls, account_number, bank_code):
        url = f"{cls.BASE_URL}/bank/resolve?account_number={account_number}&bank_code={bank_code}"
        response = requests.get(url, headers=cls._get_headers())
        res_data = response.json()
        
        print(f"DEBUG RESOLVE: {res_data}") 

        # We check for the BOOLEAN True or the STRING "true"
        status_val = res_data.get('status')
        if response.status_code == 200 and (status_val is True or str(status_val).lower() == 'true'):
            return res_data['data']['account_name']
        
        # Use the message from Paystack if it exists
        error_msg = res_data.get('message', 'Cannot resolve account')
        raise Exception(error_msg)

    @classmethod
    def create_transfer_recipient(cls, name, account_number, bank_code):
        """
        Step 2: Create a recipient on Paystack for the transfer.
        """
        url = f"{cls.BASE_URL}/transferrecipient"
        payload = {
            "type": "nuban",
            "name": name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN"
        }
        response = requests.post(url, json=payload, headers=cls._get_headers())
        res_data = response.json()

        if response.status_code in [200, 201] and res_data.get('status'):
            return res_data['data']['recipient_code']
        raise Exception(res_data.get('message', 'Could not create recipient'))

    @classmethod
    def initiate_transfer(cls, amount, recipient_code, reference):
        """
        Step 3: Send the money!
        """
        url = f"{cls.BASE_URL}/transfer"
        payload = {
            "source": "balance",
            "amount": int(Decimal(str(amount)) * 100), # Amount in kobo
            "recipient": recipient_code,
            "reference": reference,
            "reason": "Globalink Wallet Withdrawal"
        }
        response = requests.post(url, json=payload, headers=cls._get_headers())
        res_data = response.json()

        if response.status_code == 200 and res_data.get('status'):
            return res_data['data']
        raise Exception(res_data.get('message', 'Transfer initiation failed'))

    @classmethod
    def verify_webhook(cls, payload, signature):
        """
        Validates Paystack Webhook signature (HMAC SHA512).
        """
        computed_hash = hmac.new(
            cls.SECRET_KEY.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(computed_hash, signature)




class WalletService:
    """
    Service layer for internal wallet movements (Escrow, Payments, Refunds).
    Ensures all movements are atomic and recorded in the ledger.
    """

    @classmethod
    @transaction.atomic
    def lock_funds_for_order(cls, order):
        """
        Moves funds from Buyer's balance to Escrow balance.
        """
        buyer_wallet = Wallet.objects.select_for_update().get(user=order.buyer)
        
        if buyer_wallet.balance < order.total_price:
            raise Exception("Insufficient wallet balance.")

        # Atomic movement
        buyer_wallet.balance -= order.total_price
        buyer_wallet.escrow_balance += order.total_price
        buyer_wallet.save()

        # Update Order
        order.payment_status = 'escrow_held'
        order.save()

        # Ledger Entry
        Transaction.objects.create(
            wallet=buyer_wallet,
            amount=-order.total_price,
            transaction_type='escrow_lock',
            status='success',
            related_order_id=str(order.id),
            description=f"Escrow lock for Order #{order.id}"
        )
        return True

    @classmethod
    @transaction.atomic
    def release_escrow_to_seller_and_rider(cls, order):
        """
        Atomic release: 
        1. Debit Buyer Escrow.
        2. Credit Seller (90% of order total).
        3. Credit Rider (delivery_fee).
        4. Credit Platform (10% of order total).
        """
        if order.payment_status != 'escrow_held':
            raise Exception("No funds in escrow.")

        buyer_wallet = Wallet.objects.select_for_update().get(user=order.buyer)
        seller_wallet = Wallet.objects.select_for_update().get(user=order.store.owner)
        
        # 1. Buyer Side
        buyer_wallet.escrow_balance -= order.total_price
        buyer_wallet.save()

        # 2. Commission Calculation (3% capped at ₦15,000)
        # Cap applies from ₦500,000 and above (3% of 500k = 15k)
        commission = min(order.total_price * Decimal('0.03'), Decimal('15000'))
        
        # 3. Rider Side (Fixed Fee from order)
        rider_share = Decimal('0.00')
        if hasattr(order, 'rider') and order.rider:
            rider_share = order.delivery_fee
            rider_wallet = Wallet.objects.select_for_update().get(user=order.rider)
            rider_wallet.balance += rider_share
            rider_wallet.save()
            
            Transaction.objects.create(
                wallet=rider_wallet, amount=rider_share,
                transaction_type='payment', status='success',
                related_order_id=str(order.id), description=f"Delivery Fee: Order #{order.id}"
            )

        # 4. Seller Side (Total - Commission - Rider Fee)
        seller_share = order.total_price - commission - rider_share
        seller_wallet.balance += seller_share
        seller_wallet.save()

        # 5. Finalize Order
        order.payment_status = 'released'
        order.save()

        # Audit Trail
        Transaction.objects.create(
            wallet=buyer_wallet, amount=-order.total_price,
            transaction_type='escrow_release', status='success',
            related_order_id=str(order.id), description=f"Payment Released: Order #{order.id}"
        )
        Transaction.objects.create(
            wallet=seller_wallet, amount=seller_share,
            transaction_type='payment', status='success',
            related_order_id=str(order.id), description=f"Earnings: Order #{order.id}"
        )
        return True

    @classmethod
    @transaction.atomic
    def refund_escrow_to_buyer(cls, order):
        """
        Returns funds from Escrow to Buyer's balance.
        Called on order cancellation.
        """
        if order.payment_status != 'escrow_held':
            raise Exception("Cannot refund: Funds not in escrow.")

        buyer_wallet = Wallet.objects.select_for_update().get(user=order.buyer)

        # Move back to balance
        buyer_wallet.escrow_balance -= order.total_price
        buyer_wallet.balance += order.total_price
        buyer_wallet.save()

        # Update Order
        order.payment_status = 'refunded'
        order.save()

        # Ledger Entry
        Transaction.objects.create(
            wallet=buyer_wallet,
            amount=order.total_price,
            transaction_type='refund',
            status='success',
            related_order_id=str(order.id),
            description=f"Refund for Order #{order.id}"
        )
        return True

    @classmethod
    @transaction.atomic
    def initiate_withdrawal(cls, user, amount, account_number, bank_code):
        wallet = Wallet.objects.select_for_update().get(user=user)
        print(f"--- EMPEROR WITHDRAWAL START for {user.email} ---")

        if wallet.balance < amount:
            print("!!! ERROR: Insufficient Balance")
            raise Exception("Insufficient funds for withdrawal.")

        # 1. Resolve Account Name Inline to bypass method-check issues
        url = f"https://api.paystack.co/bank/resolve?account_number={account_number}&bank_code={bank_code}"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        
        resp = requests.get(url, headers=headers)
        res_data = resp.json()
        print(f"DEBUG RESOLVE INLINE: {res_data}")

        if resp.status_code != 200 or not res_data.get('status'):
            msg = res_data.get('message', 'Cannot resolve account')
            print(f"!!! ERROR RESOLVING: {msg}")
            raise Exception(msg)

        account_name = res_data['data']['account_name']

        # 2. Create Paystack Recipient
        # Using cls (PaystackService) to call the helper
        recipient_code = PaystackService.create_transfer_recipient(account_name, account_number, bank_code)
        print(f"DEBUG RECIPIENT: {recipient_code}")

        # 3. Reference and Debit
        reference = f"WTH-{user.id}-{int(time.time())}"
        wallet.balance -= amount
        wallet.save()

        # 4. Finalize Transfer
        try:
            PaystackService.initiate_transfer(amount, recipient_code, reference)
            Transaction.objects.create(
                wallet=wallet, amount=-amount, transaction_type='withdrawal',
                status='success', reference=reference,
                description=f"Withdrawal to {account_name} ({account_number})"
            )
            print("✅ WITHDRAWAL SUCCESSFUL")
            return True
        except Exception as e:
            wallet.balance += amount
            wallet.save()
            print(f"!!! TRANSFER ERROR: {str(e)}")
            raise Exception(f"Transfer Failed: {str(e)}")