from django.contrib import admin
from .models import Product, Order, OrderItem, Category, Shop

admin.site.register(Product)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Category)
@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'id_type', 'is_active', 'created_at')
    list_filter = ('is_active',) # Quickly filter by "Unapproved"
    search_fields = ('name', 'owner__email')
    
    actions = ['approve_shops']

    def approve_shops(self, request, queryset):
        queryset.update(is_active=True)
        # 📧 Optional: Trigger an email to the user here
    approve_shops.short_description = "Approve selected merchant shops"
