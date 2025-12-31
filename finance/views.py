from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import Wallet, BankAccount, WithdrawalRequest
from .serializers import WalletSerializer, BankAccountSerializer, WithdrawalRequestSerializer

class WalletDetailView(generics.RetrieveAPIView):
    """
    Get my wallet balance and history.
    """
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet

class BankAccountListCreateView(generics.ListCreateAPIView):
    """
    Manage saved bank accounts for withdrawals.
    """
    serializer_class = BankAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return BankAccount.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class RequestWithdrawalView(APIView):
    """
    Move funds from Wallet -> Real Bank.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        bank_id = request.data.get('bank_account_id')
        
        wallet = Wallet.objects.get(user=request.user)
        
        if wallet.balance < float(amount):
            return Response({"error": "Insufficient funds"}, status=400)

        # Create Request
        WithdrawalRequest.objects.create(
            wallet=wallet,
            bank_account_id=bank_id,
            amount=amount
        )
        
        # Deduct from wallet immediately (prevent double spend)
        wallet.balance -= float(amount)
        wallet.save()

        return Response({"message": "Withdrawal request submitted."})