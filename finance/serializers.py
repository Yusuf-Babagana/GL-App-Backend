from rest_framework import serializers
from .models import Wallet, Transaction, BankAccount, WithdrawalRequest

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'transaction_type', 'status', 'description', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    virtual_account = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ['balance', 'virtual_account']

    def get_virtual_account(self, obj):
        # We return your official business account details here as a fallback/default
        return {
            "bank_name": "Moniepoint MFB",
            "account_number": "6649014083",
            "account_name": f"GLAPP FUNDING ({obj.user.username})"
        }

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