from django.urls import path
from .views import PurchaseDataView

urlpatterns = [
    path('purchase-data/', PurchaseDataView.as_view(), name='purchase-data'),
]