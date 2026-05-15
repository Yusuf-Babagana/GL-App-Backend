# finance/urls.py
from django.urls import path
from .views import (
    WalletDetailView, 
    TransactionListView,
    MonnifyWebhookView, 
    DataPurchaseView, 
    DataVariationsView,
    WithdrawalView,
    BankListView,
    VerifyBankAccountView,
    clubkonnect_deposit_webhook
)

urlpatterns = [
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('transactions/', TransactionListView.as_view(), name='transaction-list'),
    path('monnify-webhook/', MonnifyWebhookView.as_view(), name='monnify-webhook'),
    path('webhook/deposit/', clubkonnect_deposit_webhook, name='deposit_webhook'),
    path('banks/', BankListView.as_view(), name='bank-list'),
    path('verify-bank/', VerifyBankAccountView.as_view(), name='verify-bank'),
    path('withdraw/', WithdrawalView.as_view(), name='withdraw'),
    path('data/plans/', DataVariationsView.as_view(), name='data-plans'),
    path('data/purchase/', DataPurchaseView.as_view(), name='data-purchase'),
]