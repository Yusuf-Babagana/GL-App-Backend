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
    virtual_account = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ['balance', 'virtual_account']

    def get_virtual_account(self, obj):
        try:
            acc = obj.virtual_account # This is the related_name from models.py
            return {
                "bank_name": acc.bank_name,
                "account_number": acc.account_number,
                "account_name": acc.account_name
            }
        except:
            # RETURN DEFAULT: Show your business account if theirs isn't ready
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