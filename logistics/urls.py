from django.urls import path
from .views import (
    PurchaseDataView,
    nellobyte_callback,
)

urlpatterns = [
    path('purchase-data/', PurchaseDataView.as_view(), name='purchase-data'),
    path('nellobyte-callback/', nellobyte_callback, name='nellobyte-callback'),
]