# finance/urls.py
from django.urls import path
from .views import (
    WalletDetailView, 
    monnify_webhook, 
    VTPassPurchaseView, 
    VTPassVariationsView,
    WithdrawalView,
    clubkonnect_deposit_webhook
)

urlpatterns = [
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('monnify-webhook/', monnify_webhook, name='monnify-webhook'),
    path('webhook/deposit/', clubkonnect_deposit_webhook, name='deposit_webhook'),
    path('withdraw/', WithdrawalView.as_view(), name='withdraw'),
    path('vtpass/variations/', VTPassVariationsView.as_view(), name='vtpass-variations'),
    path('vtpass/purchase/', VTPassPurchaseView.as_view(), name='vtpass-purchase'),
]