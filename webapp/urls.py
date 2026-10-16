from django.urls import path

from . import views

app_name = 'webapp'

urlpatterns = [
    # Single-page web client. Client-side routing uses the URL hash
    # (#/market, #/wallet, ...) so no catch-all route is needed.
    path('', views.index, name='index'),
    path('assets/<str:name>', views.asset, name='asset'),
]
