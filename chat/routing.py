from django.urls import re_path

from chat.authentication import TokenAuthMiddlewareStack
from chat.consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(
        r"ws/chat/(?P<conversation_id>\d+)/$",
        TokenAuthMiddlewareStack(ChatConsumer.as_asgi()),
    ),
]
