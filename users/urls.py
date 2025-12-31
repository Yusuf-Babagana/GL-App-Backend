from django.urls import path
from .views import RegisterView, UserProfileView, AddRoleView, KYCSubmissionView
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
]