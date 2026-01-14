from django.urls import path
from .views import (
    CategoryListView, ProductListView, ProductDetailView,
    CreateStoreView, SellerProductListCreateView,BuyerOrderListView, 
    CreateOrderView,BuyerOrderListView, BuyerOrderDetailView,
)
from .views import (
    ProductListView, 
    ProductDetailView, 
    StoreCreateView, 
    SellerProductListView, 
    ProductCreateView,
    CartAPIView,ConfirmOrderReceiptView,
    SellerOrderListView,      # <--- Import
    SellerDashboardStatsView, # <--- Import
    SellerProductListView,    # <--- Import
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
    # --- SELLER ROUTES ---
    path('seller/stats/', SellerDashboardStatsView.as_view(), name='seller-stats'),
    path('seller/products/', SellerProductListView.as_view(), name='seller-products'),
    path('seller/products/add/', ProductCreateView.as_view(), name='seller-add-product'),
    path('seller/orders/', SellerOrderListView.as_view(), name='seller-orders'),
    

    # Buyer
    path('orders/', BuyerOrderListView.as_view(), name='buyer-orders'),
    path('buyer/orders/', BuyerOrderListView.as_view(), name='buyer-orders'), # <--- ADD THIS LINE
    path('buyer/orders/<int:pk>/', BuyerOrderDetailView.as_view(), name='buyer-order-detail'), # <--- Add this
    path('store/create/', StoreCreateView.as_view(), name='create-store'),

    path('cart/', CartAPIView.as_view(), name='cart'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),

    path('orders/<int:pk>/confirm/', ConfirmOrderReceiptView.as_view(), name='order-confirm'),

    path('cart/', CartAPIView.as_view(), name='cart-manage'),
    path('orders/create/', CreateOrderView.as_view(), name='create-order'),
]