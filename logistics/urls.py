from django.urls import path
from .views import (
    PurchaseDataView,
    btdataplug_callback,
)

urlpatterns = [
    path('purchase-data/', PurchaseDataView.as_view(), name='purchase-data'),
    path('nellobyte-callback/', btdataplug_callback, name='nellobyte-callback'),
]