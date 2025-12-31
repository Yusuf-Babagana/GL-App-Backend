from rest_framework import serializers
from .models import DeliveryJob, Vehicle
from market.serializers import OrderSerializer # To show order details to driver

class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ['vehicle_type', 'plate_number', 'color', 'is_verified']

class DeliveryJobSerializer(serializers.ModelSerializer):
    # Show full order details (address, items) to the driver
    order_details = OrderSerializer(source='order', read_only=True)
    driver_name = serializers.CharField(source='driver.full_name', read_only=True)

    class Meta:
        model = DeliveryJob
        fields = [
            'id', 'order', 'order_details', 'driver', 'driver_name',
            'status', 'delivery_fee', 'pickup_address_text', 'delivery_address_text',
            'proof_of_delivery_image', 'delivery_code', 'accepted_at', 'delivered_at'
        ]
        read_only_fields = ['order', 'driver', 'delivery_fee', 'pickup_address_text', 'delivery_address_text']

    def validate(self, data):
        # If marking as delivered, proof is required
        if data.get('status') == 'delivered' and not data.get('proof_of_delivery_image') and not data.get('delivery_code'):
            raise serializers.ValidationError("Proof of delivery (Image or Code) is required to complete the job.")
        return data