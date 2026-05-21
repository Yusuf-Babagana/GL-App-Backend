from django.urls import path
from .views import (
    StartOrGetConversationView,
    InboxListView,
    MessageListCreateView,
)
from market.views import ActivateSellerAccountView

urlpatterns = [
    path('start/', StartOrGetConversationView.as_view(), name='start-chat'),
    path('inbox/', InboxListView.as_view(), name='chat-inbox'),
    path(
        'conversations/<int:conversation_id>/messages/',
        MessageListCreateView.as_view(),
        name='chat-messages',
    ),
    path(
        'activate-seller/',
        ActivateSellerAccountView.as_view(),
        name='activate-seller',
    ),
]
