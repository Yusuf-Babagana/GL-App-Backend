import hmac
import hashlib
import requests
import time
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from .models import Wallet, Transaction






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

        # Removed Paystack logic. TODO: Implement Monnify Disbursement logic
        raise Exception("Withdrawals are currently being migrated to Monnify. Please try again later.")