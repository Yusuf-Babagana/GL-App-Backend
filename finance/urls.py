from django.urls import path
from .views import (
    WalletDetailView, InitiateDepositView, VerifyDepositView, 
    VerifyBankAccountView, WithdrawalView, MonnifyWebhookView
)

urlpatterns = [
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('deposit/initiate/', InitiateDepositView.as_view(), name='deposit-initiate'),
    path('deposit/verify/', VerifyDepositView.as_view(), name='deposit-verify'),
    
    # Monnify Flows
    path('verify-bank/', VerifyBankAccountView.as_view(), name='verify-bank'),
    path('withdraw/', WithdrawalView.as_view(), name='withdraw'),
    path('webhook/monnify/', MonnifyWebhookView.as_view(), name='monnify-webhook'),
]