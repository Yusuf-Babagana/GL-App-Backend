# finance/urls.py
from django.urls import path
from .views import (
    WalletDetailView, 
    TransactionListView,
    monnify_webhook, 
    DataPurchaseView, 
    DataVariationsView,
    WithdrawalView,
    clubkonnect_deposit_webhook
)

urlpatterns = [
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('transactions/', TransactionListView.as_view(), name='transaction-list'),
    path('monnify-webhook/', monnify_webhook, name='monnify-webhook'),
    path('webhook/deposit/', clubkonnect_deposit_webhook, name='deposit_webhook'),
    path('withdraw/', WithdrawalView.as_view(), name='withdraw'),
    path('data/plans/', DataVariationsView.as_view(), name='data-plans'),
    path('data/purchase/', DataPurchaseView.as_view(), name='data-purchase'),
]