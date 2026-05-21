import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "globalink_core.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

try:
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter
    import chat.routing

    application = ProtocolTypeRouter(
        {
            "http": django_asgi_app,
            "websocket": AuthMiddlewareStack(
                URLRouter(chat.routing.websocket_urlpatterns)
            ),
        }
    )
except ImportError:
    application = django_asgi_app
