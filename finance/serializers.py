from rest_framework import serializers
from .models import Wallet, Transaction, BankAccount, WithdrawalRequest

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'transaction_type', 'status', 'description', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    # We rename this to funding_accounts to match a professional Monnify response
    funding_accounts = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ['balance', 'funding_accounts']

    def get_funding_accounts(self, obj):
        # If the user has a Monnify account in the DB, show it.
        if obj.account_number:
            return [{
                "bank_name": obj.bank_name,
                "account_number": obj.account_number,
                "account_name": obj.user.full_name or obj.user.username
            }]
        # Fallback to null so the frontend knows to show "Generating..."
        return None

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