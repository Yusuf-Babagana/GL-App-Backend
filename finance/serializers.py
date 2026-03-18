from rest_framework import serializers
from .models import Wallet, Transaction, BankAccount, WithdrawalRequest

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'transaction_type', 'status', 'description', 'reference', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    user_has_bvn = serializers.SerializerMethodField()
    user_has_pin = serializers.SerializerMethodField()
    funding_accounts = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = [
            'balance', 'pending_balance', 'account_number', 'bank_name', 
            'account_reference', 'user_has_bvn', 'user_has_pin', 'funding_accounts'
        ]

    def get_user_has_bvn(self, obj):
        return bool(obj.user.bvn)

    def get_user_has_pin(self, obj):
        # Returns true only if the pin is set and not empty
        return bool(obj.user.transaction_pin and obj.user.transaction_pin.strip() != "")

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