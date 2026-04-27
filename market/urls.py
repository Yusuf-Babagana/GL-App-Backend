from django.urls import path, re_path
from .views import (
    CategoryListView, ProductListView, ProductDetailView,
    ShopCreateView, SellerProductListView, ProductCreateView,
    CartAPIView, CreateOrderView, BuyerOrderListView,
    BuyerOrderDetailView, ConfirmOrderReceiptView,
    SellerOrderListView, SellerDashboardStatsView,
    SellerUpdateOrderStatusView, AvailableDeliveriesView,
    RiderMyDeliveriesView, AcceptDeliveryView,
    RiderUpdateStatusView, AdminDashboardStatsView,
    StartChatView, SendMessageView, ConversationListView,
    ProductDeleteView, ProductUpdateView, SellerOrderDetailView,
    ShopListView, ShopDetailView, ProductVideoFeedView,
    MarkOrderDispatchedView
)

urlpatterns = [
    # --- CART & CHECKOUT (The 404 Zone) ---
    # We add multiple paths to ensure the phone finds it regardless of the naming used
    path('orders/create/', CreateOrderView.as_view(), name='checkout-alias'),
    path('checkout/', CreateOrderView.as_view(), name='checkout'),
    
    # --- SELLER / SHOP ---
    path('store/create/', ShopCreateView.as_view(), name='shop-create'),
    path('seller/stats/', SellerDashboardStatsView.as_view(), name='seller-stats'),
    path('seller/products/', SellerProductListView.as_view(), name='seller-products'),
    path('seller/products/add/', ProductCreateView.as_view(), name='product-add'),
    path('seller/products/create/', ProductCreateView.as_view(), name='seller-product-create'),
    path('seller/products/<int:pk>/update/', ProductUpdateView.as_view(), name='product-update'),
    path('seller/products/<int:pk>/delete/', ProductDeleteView.as_view(), name='product-delete'),
    
    # --- SELLER ORDERS ---
    path('seller/orders/', SellerOrderListView.as_view(), name='seller-orders'),
    path('seller/orders/<int:pk>/', SellerOrderDetailView.as_view(), name='seller-order-detail'),
    path('seller/orders/status-change/<int:pk>/', SellerUpdateOrderStatusView.as_view(), name='seller-order-status-change'),
    path('seller/orders/<int:order_id>/dispatch/', MarkOrderDispatchedView.as_view(), name='seller-order-dispatch'),
    path('orders/<int:order_id>/dispatch/', MarkOrderDispatchedView.as_view(), name='order-dispatch-alias'),

    # --- BUYER ---
    path('buyer/orders/', BuyerOrderListView.as_view(), name='buyer-orders'),
    path('buyer/orders/<int:pk>/', BuyerOrderDetailView.as_view(), name='buyer-order-detail'),
    path('buyer/orders/<int:order_id>/confirm/', ConfirmOrderReceiptView.as_view(), name='buyer-confirm-receipt'),
    path('orders/<int:order_id>/confirm-receipt/', ConfirmOrderReceiptView.as_view(), name='confirm-receipt-alias'),
    path('cart/', CartAPIView.as_view(), name='cart'),

    # --- PUBLIC ---
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('stores/', ShopListView.as_view(), name='shop-list'),
    path('stores/<int:pk>/', ShopDetailView.as_view(), name='shop-detail'),
    path('video-ads/', ProductVideoFeedView.as_view(), name='video-ads-feed'),

    # --- RIDER ---
    path('rider/orders/available/', AvailableDeliveriesView.as_view(), name='rider-available'),
    path('rider/orders/active/', RiderMyDeliveriesView.as_view(), name='rider-active'),
    path('rider/orders/<int:pk>/accept/', AcceptDeliveryView.as_view(), name='rider-accept'),
    path('rider/orders/<int:pk>/update/', RiderUpdateStatusView.as_view(), name='rider-update'),

    # --- CHAT ---
    path('conversations/', ConversationListView.as_view(), name='my-conversations'),
    path('chat/start/<int:userId>/', StartChatView.as_view(), name='start-chat'),
    path('chat/<int:conversationId>/send/', SendMessageView.as_view(), name='send-message'),

    # --- ADMIN ---
    path('admin/stats/', AdminDashboardStatsView.as_view(), name='admin-stats'),
]