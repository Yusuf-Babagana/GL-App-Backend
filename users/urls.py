from django.urls import path
from .views import AdminDashboardStatsView, RegisterView, AdminKYCListView, AdminKYCActionView, UserProfileView, AddRoleView, KYCSubmissionView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Auth
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'), # Returns JWT Access/Refresh tokens
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Profile & Roles
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('roles/add/', AddRoleView.as_view(), name='add_role'), # POST { "role": "seller" }

    # KYC
    path('kyc/upload/', KYCSubmissionView.as_view(), name='kyc_upload'),
    path('admin/kyc/pending/', AdminKYCListView.as_view(), name='admin-kyc-list'),
    path('admin/kyc/<int:pk>/action/', AdminKYCActionView.as_view(), name='admin-kyc-action'),
    path('admin/dashboard/stats/', AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),
]