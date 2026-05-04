from django.contrib import admin
from .models import Product, Order, OrderItem, Category, Shop

admin.site.register(Product)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Category)
@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    # 1. This makes the list easy to read and approve
    list_display = ('name', 'owner', 'shop_type', 'is_active', 'id_type')
    list_editable = ('is_active',) # Quick approve from the list!
    list_filter = ('is_active',)
    search_fields = ('name', 'owner__email')
    
    actions = ['approve_shops']

    def approve_shops(self, request, queryset):
        queryset.update(is_active=True)
    approve_shops.short_description = "Approve selected merchant shops"

    # 2. This prevents the "Owner is required" error if you create a shop manually
    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'owner') or not obj.owner:
            obj.owner = request.user
        super().save_model(request, obj, form, change)
