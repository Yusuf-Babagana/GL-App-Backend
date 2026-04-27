from django.contrib import admin
from .models import Product, Order, OrderItem, Category, Shop

admin.site.register(Product)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Category)
admin.site.register(Shop)
