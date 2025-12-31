from django.urls import path
from .views import AvailableJobsView, AcceptJobView, UpdateDeliveryStatusView

urlpatterns = [
    path('available/', AvailableJobsView.as_view(), name='delivery-available'),
    path('job/<int:pk>/accept/', AcceptJobView.as_view(), name='delivery-accept'),
    path('job/<int:pk>/update/', UpdateDeliveryStatusView.as_view(), name='delivery-update'),
]