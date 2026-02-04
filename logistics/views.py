from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from market.models import Order
from market.serializers import OrderSerializer
from django.db import transaction

class AvailableJobsView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Look for orders that are ready for pickup and have no rider assigned
        return Order.objects.filter(delivery_status='ready_for_pickup', rider__isnull=True)


class AcceptDeliveryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        if order.rider:
            return Response({"error": "Already taken"}, status=400)
        
        order.rider = request.user
        order.delivery_status = 'picked_up'
        order.save()
        return Response({"message": "Delivery accepted"})

class VerifyDeliveryPINView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        pin = request.data.get('pin')

        if pin == order.delivery_code:
            with transaction.atomic():
                order.delivery_status = 'delivered'
                order.payment_status = 'released'
                order.save()
                # Trigger finance logic here to move money from Escrow to Seller Wallet
            return Response({"message": "Delivery Successful"})
        return Response({"error": "Invalid PIN"}, status=400)