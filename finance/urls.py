from django.urls import path
from .views import (
    WalletDetailView, 
    monnify_webhook, 
    VTPassPurchaseView, 
    VTPassVariationsView,
    VerifyBankAccountView,
    WithdrawalView,
    clubkonnect_deposit_webhook
)

urlpatterns = [
    # Wallet Info (This now handles account display)
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    
    # Automated Funding Webhooks
    path('monnify-webhook/', monnify_webhook, name='monnify-webhook'),
    path('webhook/deposit/', clubkonnect_deposit_webhook, name='deposit_webhook'),

    # Withdrawal Flow
    path('verify-bank/', VerifyBankAccountView.as_view(), name='verify-bank'),
    path('withdraw/', WithdrawalView.as_view(), name='withdraw'),
    
    # Bill Payments (Data/Airtime via Nellobyte)
    path('vtpass/variations/', VTPassVariationsView.as_view(), name='vtpass-variations'),
    path('vtpass/purchase/', VTPassPurchaseView.as_view(), name='vtpass-purchase'),
]