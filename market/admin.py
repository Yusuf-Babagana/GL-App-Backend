# market/admin.py
from django.contrib import admin
from market.models import Shop, Product, Category, Order, OrderItem

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    # Displays clean, readable information columns inside the Admin list directory view
    list_display = ('name', 'owner_email', 'shop_type', 'state', 'is_active', 'date_applied')
    
    # Adds a functional sidebar filter module for fast approval pipeline tracking
    list_filter = ('is_active', 'shop_type', 'state', 'is_registered')
    
    # Enables global keyword lookup matching across critical indexing fields
    search_fields = ('name', 'owner_full_name', 'owner_email', 'cac_number')
    
    # Groups form inputs cleanly inside the individual edit workspace page
    fieldsets = (
        ('Platform Status Control', {
            'fields': ('is_active', 'owner')
        }),
        ('Merchant Identification Info (Step 1)', {
            'fields': ('owner_full_name', 'owner_email', 'owner_phone', 'id_type', 'id_number', 'id_image')
        }),
        ('Store Architecture Metrics (Step 2)', {
            'fields': ('name', 'shop_type', 'business_phone', 'address', 'country', 'state', 'logo')
        }),
        ('Corporate Registry Legal Data', {
            'fields': ('is_registered', 'cac_number')
        }),
    )

    actions = ['approve_shops']

    def approve_shops(self, request, queryset):
        queryset.update(is_active=True)
    approve_shops.short_description = "Approve selected merchant shops"

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'owner') or not obj.owner:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

# Safely register the remaining core e-commerce models with standard layout views
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'price', 'stock')
    search_fields = ('name', 'shop__name')

admin.site.register(Category)
admin.site.register(Order)
admin.site.register(OrderItem)
