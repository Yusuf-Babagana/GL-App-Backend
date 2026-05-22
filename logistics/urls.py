from django.urls import path
from .views import (
    PurchaseDataView,
    nellobyte_callback,
    AvailableDeliveriesView,
    RiderMyDeliveriesView,
    AcceptDeliveryView,
    RiderUpdateStatusView,
)

urlpatterns = [
    path('purchase-data/', PurchaseDataView.as_view(), name='purchase-data'),
    path('nellobyte-callback/', nellobyte_callback, name='nellobyte-callback'),
    # Rider Delivery Management
    path('rider/orders/available/', AvailableDeliveriesView.as_view(), name='rider-available'),
    path('rider/orders/active/', RiderMyDeliveriesView.as_view(), name='rider-active'),
    path('rider/orders/<int:pk>/accept/', AcceptDeliveryView.as_view(), name='rider-accept'),
    path('rider/orders/<int:pk>/update/', RiderUpdateStatusView.as_view(), name='rider-update'),
]