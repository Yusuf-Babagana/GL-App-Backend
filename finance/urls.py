from django.urls import path
from .views import WalletDetailView, InitiateDepositView, VerifyDepositView

urlpatterns = [
    path('wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('deposit/initiate/', InitiateDepositView.as_view(), name='deposit-initiate'),
    path('deposit/verify/', VerifyDepositView.as_view(), name='deposit-verify'),
]