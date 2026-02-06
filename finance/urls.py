from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import (
    WalletDetailView, InitiateDepositView, VerifyDepositView, 
    VerifyBankAccountView, WithdrawalView, MonnifyWebhookView,
    VTPassPurchaseView, VTPassVariationsView
)

urlpatterns = [
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('deposit/initiate/', InitiateDepositView.as_view(), name='deposit-initiate'),
    path('deposit/verify/', VerifyDepositView.as_view(), name='deposit-verify'),
    
    # Monnify Flows
    path('verify-bank/', VerifyBankAccountView.as_view(), name='verify-bank'),
    path('withdraw/', WithdrawalView.as_view(), name='withdraw'),
    path('webhook/monnify/', csrf_exempt(MonnifyWebhookView.as_view()), name='monnify-webhook'),
    
    # VTpass Flows
    path('vtpass/variations/', VTPassVariationsView.as_view(), name='vtpass-variations'),
    path('vtpass/purchase/', VTPassPurchaseView.as_view(), name='vtpass-purchase'),
]