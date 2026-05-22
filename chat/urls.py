from django.urls import path
from .views import (
    ConversationListView, MessageListView, SendMessageView,
    StartConversationView,
)

urlpatterns = [
    path('start/', StartConversationView.as_view(), name='chat-start'),
    path('inbox/', ConversationListView.as_view(), name='chat-inbox'),
    path('conversations/', ConversationListView.as_view(), name='chat-conversations'),
    path('conversations/<int:conversation_id>/messages/', MessageListView.as_view(), name='chat-messages'),
    path('conversations/<int:conversation_id>/messages/send/', SendMessageView.as_view(), name='chat-send-message'),
    path('conversations/<int:conversation_id>/messages/create/', SendMessageView.as_view(), name='chat-message-create'),
    path('conversations/<int:conversation_id>/send/', SendMessageView.as_view(), name='chat-send-alias'),
]
