from django.urls import path
from .views import (
    WalletDetailView, 
    InitiateDepositView, 
    VerifyDepositView, 
    PaystackWebhookView,
    VTPassPurchaseView, 
    VTPassVariationsView,
    VerifyBankAccountView,
    WithdrawalView
)

urlpatterns = [
    # Wallet Info
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    
    # Paystack Funding Flow
    path('deposit/initiate/', InitiateDepositView.as_view(), name='deposit-initiate'),
    path('deposit/verify/', VerifyDepositView.as_view(), name='deposit-verify'),
    path('paystack/webhook/', PaystackWebhookView.as_view(), name='paystack-webhook'),

    # Withdrawal Flow
    path('verify-bank/', VerifyBankAccountView.as_view(), name='verify-bank'),
    path('withdraw/', WithdrawalView.as_view(), name='withdraw'),
    
    # VTpass Bill Payments (Data/Airtime)
    path('vtpass/variations/', VTPassVariationsView.as_view(), name='vtpass-variations'),
    path('vtpass/purchase/', VTPassPurchaseView.as_view(), name='vtpass-purchase'),
]