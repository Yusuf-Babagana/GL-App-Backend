from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')), 
    path('api/finance/', include('finance.urls')),
    path('api/market/', include('market.urls')), # Has came, Coming soon
    # path('api/jobs/', include('jobs.urls')),     # Coming soon
]

# Enable media handling in development (for Images/Videos)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


    