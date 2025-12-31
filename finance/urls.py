from django.urls import path
from .views import WalletDetailView, BankAccountListCreateView, RequestWithdrawalView

urlpatterns = [
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('bank-accounts/', BankAccountListCreateView.as_view(), name='bank-accounts'),
    path('withdraw/', RequestWithdrawalView.as_view(), name='withdraw-request'),
]