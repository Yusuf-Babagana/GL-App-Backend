from django.contrib import admin
from .models import DataTransaction, DeliveryJob, Vehicle

@admin.register(DataTransaction)
class DataTransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'service_id', 'data_plan', 'phone', 'amount', 'status', 'created_at']
    list_filter = ['status', 'service_id']
    search_fields = ['phone', 'user__email', 'request_id']
    readonly_fields = ['request_id', 'created_at', 'updated_at']

@admin.register(DeliveryJob)
class DeliveryJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'driver', 'status', 'delivery_fee', 'created_at']
    list_filter = ['status']
    search_fields = ['order__id', 'driver__email']

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['driver', 'vehicle_type', 'plate_number', 'is_verified']
    list_filter = ['vehicle_type', 'is_verified']
