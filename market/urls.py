from django.urls import path
from .views import (
    CategoryListView, ProductListView, ProductDetailView,
    CreateStoreView, SellerProductListCreateView, CreateOrderView
)
from .views import (
    ProductListView, 
    ProductDetailView, 
    StoreCreateView, 
    SellerProductListView, 
    ProductCreateView
)



urlpatterns = [

    # Public Market
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    
    # Seller Routes
    path('store/create/', StoreCreateView.as_view(), name='create-store'),
    path('seller/products/', SellerProductListView.as_view(), name='seller-products'),
    path('seller/products/create/', ProductCreateView.as_view(), name='create-product'),

    
    # Public
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),

    # Seller
    path('store/create/', CreateStoreView.as_view(), name='store-create'),
    path('seller/products/', SellerProductListCreateView.as_view(), name='seller-products'),

    # Buyer
    path('orders/create/', CreateOrderView.as_view(), name='order-create'),


    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),

]