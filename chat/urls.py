from django.urls import path
from .views import ConversationListView, MessageListView, SendMessageView

urlpatterns = [
    path('conversations/', ConversationListView.as_view(), name='chat-conversations'),
    path('conversations/<int:conversation_id>/messages/', MessageListView.as_view(), name='chat-messages'),
    path('conversations/<int:conversation_id>/messages/send/', SendMessageView.as_view(), name='chat-send-message'),
]
