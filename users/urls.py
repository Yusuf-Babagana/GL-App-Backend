from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import AdminDashboardStatsView, CustomRegisterView, AdminKYCListView, AdminKYCActionView, UserProfileView, AddRoleView, KYCSubmissionView, SetTransactionPINView, UpdateBVNView, CustomLoginView, RequestAccountDeletionView, CancelAccountDeletionView, RequestPasswordResetView, ConfirmPasswordResetView, AddressListCreateView, AddressDetailView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from market.views import WishlistView, WishlistItemDetailView

urlpatterns = [
    # Auth
    path('register/', csrf_exempt(CustomRegisterView.as_view()), name='register'),
    path('login/', csrf_exempt(CustomLoginView.as_view()), name='login'), # Custom login returning user metadata
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('password-reset/request/', csrf_exempt(RequestPasswordResetView.as_view()), name='password-reset-request'),
    path('password-reset/confirm/', csrf_exempt(ConfirmPasswordResetView.as_view()), name='password-reset-confirm'),
    
    # Profile & Roles
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('roles/add/', AddRoleView.as_view(), name='add_role'), # POST { "role": "seller" }
    path('set-pin/', SetTransactionPINView.as_view(), name='set-pin'),

    # Address book (hooks/useAddressess.ts calls these WITHOUT a trailing
    # slash — matched exactly here rather than relying on APPEND_SLASH,
    # which doesn't reliably redirect POST/PUT/DELETE).
    path('addresses', AddressListCreateView.as_view(), name='address-list-create'),
    path('addresses/<int:pk>', AddressDetailView.as_view(), name='address-detail'),

    # Wishlist (hooks/useWishlist.ts calls these WITHOUT a trailing slash)
    path('wishlist', WishlistView.as_view(), name='wishlist-list-create'),
    path('wishlist/<int:product_id>', WishlistItemDetailView.as_view(), name='wishlist-detail'),

    # KYC
    path('kyc/upload/', KYCSubmissionView.as_view(), name='kyc_upload'),
    path('admin/kyc/pending/', AdminKYCListView.as_view(), name='admin-kyc-list'),
    path('admin/kyc/<int:pk>/action/', AdminKYCActionView.as_view(), name='admin-kyc-action'),
    path('admin/dashboard/stats/', AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),

    # Financial KYC
    path('update-bvn/', UpdateBVNView.as_view(), name='update-bvn'),

    # Account Deletion
    path('request-deletion/', RequestAccountDeletionView.as_view(), name='request-deletion'),
    path('cancel-deletion/', CancelAccountDeletionView.as_view(), name='cancel-deletion'),
]