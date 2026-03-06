from rest_framework import serializers
from .models import Wallet, Transaction, BankAccount, WithdrawalRequest, UserVirtualAccount

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'transaction_type', 'status', 'description', 'created_at']

class VirtualAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserVirtualAccount
        fields = ['bank_name', 'account_number', 'account_name']

class WalletSerializer(serializers.ModelSerializer):
    # Include the virtual account details in the wallet response
    virtual_account = VirtualAccountSerializer(read_only=True)
    transactions = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = [
            'currency', 'balance', 'escrow_balance', 'total_assets', 
            'transactions', 'virtual_account'
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