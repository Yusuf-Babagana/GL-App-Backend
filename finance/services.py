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
    Refactored Service layer: Removed Escrow.
    Handles immediate wallet settlements and withdrawals.
    """

    @classmethod
    @transaction.atomic
    def settle_order_payment(cls, order):
        """
        Directly distributes funds from Buyer to Seller, Rider, and Platform.
        No escrow involved.
        """
        buyer_wallet = Wallet.objects.select_for_update().get(user=order.buyer)
        seller_wallet = Wallet.objects.select_for_update().get(user=order.shop.owner)

        if buyer_wallet.balance < order.total_price:
            raise Exception("Insufficient wallet balance.")

        # 1. Calculate Splits
        # Commission: 3% capped at ₦15,000
        commission = min(order.total_price * Decimal('0.03'), Decimal('15000'))
        
        rider_share = Decimal('0.00')
        if hasattr(order, 'rider') and order.rider:
            rider_share = order.delivery_fee
            rider_wallet = Wallet.objects.select_for_update().get(user=order.rider)
            
            # Credit Rider
            rider_wallet.balance += rider_share
            rider_wallet.save()
            
            Transaction.objects.create(
                wallet=rider_wallet, amount=rider_share,
                transaction_type=Transaction.TransactionType.PAYMENT, status=Transaction.Status.SUCCESS,
                related_order_id=str(order.id), description=f"Delivery Fee: Order #{order.id}"
            )

        seller_share = order.total_price - commission - rider_share

        # 2. Atomic Movement
        buyer_wallet.balance -= order.total_price
        buyer_wallet.save()

        seller_wallet.balance += seller_share
        seller_wallet.save()

        # 3. Finalize Order Status
        order.payment_status = 'paid'
        order.save()

        # 4. Audit Trail for Buyer and Seller
        Transaction.objects.create(
            wallet=buyer_wallet, amount=-order.total_price,
            transaction_type=Transaction.TransactionType.PAYMENT, status=Transaction.Status.SUCCESS,
            related_order_id=str(order.id), description=f"Order Payment: #{order.id}"
        )
        Transaction.objects.create(
            wallet=seller_wallet, amount=seller_share,
            transaction_type=Transaction.TransactionType.PAYMENT, status=Transaction.Status.SUCCESS,
            related_order_id=str(order.id), description=f"Sales Earning: Order #{order.id}"
        )
        return True

    @classmethod
    @transaction.atomic
    def process_direct_refund(cls, order):
        """
        Directly refunds the Buyer's balance from the platform/seller.
        """
        buyer_wallet = Wallet.objects.select_for_update().get(user=order.buyer)
        
        buyer_wallet.balance += order.total_price
        buyer_wallet.save()

        order.payment_status = 'refunded'
        order.save()

        Transaction.objects.create(
            wallet=buyer_wallet, amount=order.total_price,
            transaction_type=Transaction.TransactionType.REFUND, status=Transaction.Status.SUCCESS,
            related_order_id=str(order.id), description=f"Refund for Order #{order.id}"
        )
        return True

class WithdrawalService:
    @staticmethod
    def initiate_payout(user, amount, bank_code, account_number):
        import uuid
        from .utils import MonnifyAPI
        
        amount = Decimal(str(amount))
        reference = f"WITHDRAW-{uuid.uuid4().hex[:8]}"

        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=user)

                if wallet.balance < amount:
                    return False, "Insufficient balance."

                # 1. Deduct immediately (Pre-debit)
                wallet.balance -= amount
                wallet.save()

                # 2. Call Monnify Disbursement API
                # This moves real money from your Monnify account to the user
                response = MonnifyAPI.disburse_funds(
                    amount=amount,
                    reference=reference,
                    bank_code=bank_code,
                    account_number=account_number,
                    narration=f"Withdrawal for {user.username}"
                )

                if response.get("requestSuccessful"):
                    Transaction.objects.create(
                        wallet=wallet,
                        amount=-amount,
                        transaction_type=Transaction.TransactionType.WITHDRAWAL,
                        status=Transaction.Status.SUCCESS,
                        reference=reference,
                        description=f"Withdrawal to {account_number}"
                    )
                    return True, {"message": "Withdrawal processed successfully."}
                else:
                    # 3. Rollback
                    error_msg = response.get("responseMessage", "Transaction rejected by provider")
                    error_code = response.get("responseCode", "UNKNOWN")
                    # Raising exception to trigger rollback
                    raise ValueError(f"{error_code}|{error_msg}")

        except ValueError as ve:
            # We catch our custom ValueError to parse the code and message securely
            parts = str(ve).split('|', 1)
            code = parts[0] if len(parts) > 1 else "UNKNOWN"
            msg = parts[1] if len(parts) > 1 else str(ve)
            return False, {"error": msg, "code": code}
        except Exception as e:
            return False, {"error": f"Withdrawal failed: {str(e)}", "code": "SYS_ERR"}