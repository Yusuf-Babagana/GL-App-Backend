from decimal import Decimal
from django.db import transaction
from .models import Wallet, Transaction

class WalletManager:
    @staticmethod
    def process_payment(user, amount, transaction_type, description, related_id=None):
        """
        A unified function to handle all outgoing payments (Market or Data).
        Returns (success_boolean, message)
        """
        amount = Decimal(str(amount))
        
        try:
            with transaction.atomic():
                # 1. Get and lock the wallet for this user (prevents double-spending)
                wallet = Wallet.objects.select_for_update().get(user=user)

                # 2. Check for sufficient funds
                if wallet.balance < amount:
                    return False, "Insufficient wallet balance."

                # 3. Create the ledger entry (Pending)
                ledger = Transaction.objects.create(
                    wallet=wallet,
                    amount=-amount,
                    transaction_type=transaction_type,
                    status=Transaction.Status.PENDING,
                    description=description,
                    related_order_id=related_id if transaction_type == 'escrow_lock' else None
                )

                # 4. Deduct the funds
                if transaction_type == Transaction.TransactionType.ESCROW_LOCK:
                    # For Marketplace: Move to Escrow
                    wallet.balance -= amount
                    wallet.escrow_balance += amount
                else:
                    # For Data/Bills: Immediate deduction
                    wallet.balance -= amount
                
                wallet.save()
                
                # Mark record as success now that local DB is updated
                ledger.status = Transaction.Status.SUCCESS
                ledger.save()

                return True, "Payment processed successfully."

        except Wallet.DoesNotExist:
            return False, "User wallet not found."
        except Exception as e:
            return False, f"Payment failed: {str(e)}"