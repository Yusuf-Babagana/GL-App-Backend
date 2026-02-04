from rest_framework import serializers
from .models import Wallet, Transaction, BankAccount, WithdrawalRequest

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'transaction_type', 'status', 'description', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    # This will now automatically pull the latest transactions linked to the wallet
    transactions = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = [
            'currency', 'balance', 'escrow_balance', 'total_assets', 
            'transactions', 'account_number', 'bank_name'
        ]

    def get_transactions(self, obj):
        # Return the 10 most recent transactions
        query = obj.transactions.all().order_by('-created_at')[:10]
        return TransactionSerializer(query, many=True).data

class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ['id', 'bank_name', 'account_number', 'account_name', 'is_primary']
        read_only_fields = ['is_verified']

class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = ['amount', 'bank_account', 'status', 'created_at']
        read_only_fields = ['status']