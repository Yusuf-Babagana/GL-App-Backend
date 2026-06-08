from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from .views import AdminDashboardView, MonnifyBatchCsvExportView, WithdrawalTicketUpdateStatusView, AdminShopVerificationView, AdminDataPricingView, AdminDataPlansView
from .admin_views import AdminOrderListView, AdminTransactionListView, AdminUserManageListView, AdminUserToggleActiveView, AdminUserChangeRoleView, AdminChartDataView

urlpatterns = [
    path('', AdminDashboardView.as_view(), name='admin-dashboard'),

    path(
        'admin-portal/login/',
        auth_views.LoginView.as_view(
            template_name='admin/login.html',
            redirect_authenticated_user=True,
            extra_context={'title': 'GLAPP Operational Hub'},
        ),
        name='admin_login',
    ),
    path(
        'admin-portal/logout/',
        auth_views.LogoutView.as_view(next_page='admin_login'),
        name='admin_logout',
    ),

    path('admin/', admin.site.urls),

    path('api/logistics/', include('logistics.urls')),
    path('api/chat/', include('chat.urls')),
    path('api/users/', include('users.urls')),
    path('api/finance/', include('finance.urls')),
    path('api/market/', include('market.urls')),

    path('api/finance/withdraw/csv/', MonnifyBatchCsvExportView.as_view(), name='monnify-csv'),
    path(
        'api/finance/withdraw/<int:ticket_id>/update-status/',
        WithdrawalTicketUpdateStatusView.as_view(),
        name='ticket-update-status',
    ),
    path(
        'api/merchant/verify-shop/<str:shop_id>/',
        AdminShopVerificationView.as_view(),
        name='verify-shop',
    ),
    path(
        'api/admin/data-pricing/',
        AdminDataPricingView.as_view(),
        name='admin-data-pricing',
    ),
    path(
        'api/admin/data-plans/',
        AdminDataPlansView.as_view(),
        name='admin-data-plans',
    ),
    path(
        'api/admin/orders/',
        AdminOrderListView.as_view(),
        name='admin-orders',
    ),
    path(
        'api/admin/transactions/',
        AdminTransactionListView.as_view(),
        name='admin-transactions',
    ),
    path(
        'api/admin/users/',
        AdminUserManageListView.as_view(),
        name='admin-users-manage',
    ),
    path(
        'api/admin/users/<int:user_id>/toggle-active/',
        AdminUserToggleActiveView.as_view(),
        name='admin-user-toggle-active',
    ),
    path(
        'api/admin/users/<int:user_id>/change-role/',
        AdminUserChangeRoleView.as_view(),
        name='admin-user-change-role',
    ),
    path(
        'api/admin/dashboard/charts/',
        AdminChartDataView.as_view(),
        name='admin-chart-data',
    ),
]

# Enable media handling in development (for Images/Videos)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


    