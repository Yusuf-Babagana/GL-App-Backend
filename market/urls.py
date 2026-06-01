from django.urls import path
from .views import (
    CategoryListView, ProductListView, ProductDetailView,
    ShopCreateView, ShopUpdateView, SellerProductListView, ProductCreateView,
    CartAPIView, CartSyncView, CreateOrderView, BuyerOrderListView,
    BuyerOrderDetailView, BuyerConfirmReceiptView,
    SellerOrderListView, MerchantDashboardView,
    SellerUpdateOrderStatusView, AdminDashboardStatsView,
    ProductDeleteView, ProductUpdateView, SellerOrderDetailView,
    ShopListView, ShopDetailView, ProductVideoFeedView,
    MarkOrderDispatchedView, MerchantOnboardingView, ShopStatusView,
    AdminOverviewView, AdminApproveShopView, AdminUpdateUserRoleView,
    MerchantGlobalOnboardingView, AdminOverviewTelemetryView,
    AdminReviewShopView, MerchantAnalyticsView, MyShopStatusView,
    InternalWalletCheckoutView, MerchantWithdrawalView
)
from chat.views import ConversationListView

urlpatterns = [
    # --- CART & CHECKOUT (The 404 Zone) ---
    # We add multiple paths to ensure the phone finds it regardless of the naming used
    path('orders/', CreateOrderView.as_view(), name='create-order'),
    path('orders/create/', CreateOrderView.as_view(), name='checkout-alias'),
    path('checkout/', CreateOrderView.as_view(), name='checkout'),
    path('orders/wallet-pay/', InternalWalletCheckoutView.as_view(), name='wallet-pay'),
    
    # --- SELLER / SHOP ---
    path('store/create/', ShopCreateView.as_view(), name='shop-create'),
    path('store/status/', ShopStatusView.as_view(), name='shop-status'),
    path('shop/my-status/', MyShopStatusView.as_view(), name='my-shop-status'),
    path('store/onboarding/', MerchantOnboardingView.as_view(), name='merchant-onboarding'),
    path('store/update/', ShopUpdateView.as_view(), name='shop-update'),
    path('store/global-onboard/', MerchantGlobalOnboardingView.as_view(), name='global-onboard'),
    path('seller/stats/', MerchantDashboardView.as_view(), name='seller-stats'),
    path('merchant/analytics/', MerchantAnalyticsView.as_view(), name='merchant-analytics'),
    path('seller/products/', SellerProductListView.as_view(), name='seller-products'),
    path('seller/products/add/', ProductCreateView.as_view(), name='product-add'),
    path('seller/products/create/', ProductCreateView.as_view(), name='seller-product-create'),
    path('products/create/', ProductCreateView.as_view(), name='product-create'),
    path('seller/products/<int:pk>/update/', ProductUpdateView.as_view(), name='product-update'),
    path('products/<int:pk>/update/', ProductUpdateView.as_view(), name='product-update-alias'),
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
    path('buyer/orders/<int:order_id>/confirm/', BuyerConfirmReceiptView.as_view(), name='buyer-confirm-receipt'),
    path('orders/<int:order_id>/confirm-receipt/', BuyerConfirmReceiptView.as_view(), name='confirm-receipt-alias'),
    path('cart/', CartAPIView.as_view(), name='cart'),
    path('cart/sync/', CartSyncView.as_view(), name='cart-sync'),

    # --- PUBLIC ---
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('stores/', ShopListView.as_view(), name='shop-list'),
    path('stores/<uuid:pk>/', ShopDetailView.as_view(), name='shop-detail'),
    path('video-ads/', ProductVideoFeedView.as_view(), name='video-ads-feed'),

    # --- ADMIN ---
    path('admin/stats/', AdminDashboardStatsView.as_view(), name='admin-stats'),
    path('admin/overview/', AdminOverviewTelemetryView.as_view(), name='admin-overview'),
    path('admin/approve-shop/<str:shop_id>/', AdminApproveShopView.as_view(), name='admin-approve-shop'),
    path('admin/review-shop/<uuid:shop_id>/', AdminReviewShopView.as_view(), name='admin-review-shop'),
    path('admin/update-user-role/<int:user_id>/', AdminUpdateUserRoleView.as_view(), name='admin-update-user-role'),

    # --- WITHDRAWAL ---
    path('merchant/withdraw/', MerchantWithdrawalView.as_view(), name='merchant-withdraw'),

    # --- CHAT (alias for frontend compatibility) ---
    path('conversations/', ConversationListView.as_view(), name='market-conversations'),
]