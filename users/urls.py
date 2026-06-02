from django.urls import path
from .views import AdminDashboardStatsView, CustomRegisterView, AdminKYCListView, AdminKYCActionView, UserProfileView, AddRoleView, KYCSubmissionView, SetTransactionPINView, UpdateBVNView, CustomLoginView, RequestAccountDeletionView, CancelAccountDeletionView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Auth
    path('register/', CustomRegisterView.as_view(), name='register'),
    path('login/', CustomLoginView.as_view(), name='login'), # Custom login returning user metadata
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Profile & Roles
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('roles/add/', AddRoleView.as_view(), name='add_role'), # POST { "role": "seller" }
    path('set-pin/', SetTransactionPINView.as_view(), name='set-pin'),

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