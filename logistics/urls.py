from django.urls import path
from .views import AcceptDeliveryView, VerifyDeliveryPINView

urlpatterns = [
    path('accept/<int:order_id>/', AcceptDeliveryView.as_view()),
    path('verify-pin/<int:order_id>/', VerifyDeliveryPINView.as_view()),
]