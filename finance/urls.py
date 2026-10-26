# finance/urls.py
from django.urls import path
from .views import (
    WalletDetailView, 
    TransactionListView,
    MonnifyWebhookView, 
    DataPurchaseView, 
    DataHistoryView,
    DataVariationsView,
    WithdrawalView,
    BankListView,
    VerifyBankAccountView,
    AdminPendingWithdrawalListView,
    AdminConfirmPayoutView,
    clubkonnect_deposit_webhook,
    btdataplug_webhook,
)
from .bills import (
    AirtimePurchaseView,
    ElectricityDiscosView,
    VerifyMeterView,
    ElectricityPurchaseView,
    CablePlansView,
    VerifyCableView,
    CablePurchaseView,
)
from users.views import SetTransactionPINView

urlpatterns = [
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('transactions/', TransactionListView.as_view(), name='transaction-list'),
    path('monnify-webhook/', MonnifyWebhookView.as_view(), name='monnify-webhook'),
    path('webhook/deposit/', clubkonnect_deposit_webhook, name='deposit_webhook'),
    path('btdataplug-webhook/', btdataplug_webhook, name='btdataplug-webhook'),
    path('banks/', BankListView.as_view(), name='bank-list'),
    path('verify-bank/', VerifyBankAccountView.as_view(), name='verify-bank'),
    path('withdraw/', WithdrawalView.as_view(), name='withdraw'),
    path('data/plans/', DataVariationsView.as_view(), name='data-plans'),
    path('data/purchase/', DataPurchaseView.as_view(), name='data-purchase'),
    path('data/history/', DataHistoryView.as_view(), name='data-history'),
    path('airtime/purchase/', AirtimePurchaseView.as_view(), name='airtime-purchase'),
    path('electricity/discos/', ElectricityDiscosView.as_view(), name='electricity-discos'),
    path('electricity/verify/', VerifyMeterView.as_view(), name='electricity-verify'),
    path('electricity/purchase/', ElectricityPurchaseView.as_view(), name='electricity-purchase'),
    path('cable/plans/', CablePlansView.as_view(), name='cable-plans'),
    path('cable/verify/', VerifyCableView.as_view(), name='cable-verify'),
    path('cable/purchase/', CablePurchaseView.as_view(), name='cable-purchase'),
    path('pin/', SetTransactionPINView.as_view(), name='set-pin'),
    path('admin/withdrawals/pending/', AdminPendingWithdrawalListView.as_view(), name='admin-pending-withdrawals'),
    path('admin/withdrawals/<int:ticket_id>/confirm/', AdminConfirmPayoutView.as_view(), name='admin-confirm-payout'),
]