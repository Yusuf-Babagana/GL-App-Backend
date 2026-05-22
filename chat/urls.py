from django.urls import path
from .views import ConversationListView, MessageView

urlpatterns = [
    path('conversations/', ConversationListView.as_view(), name='chat-conversations'),
    path('conversations/<int:conversation_id>/messages/', MessageView.as_view(), name='chat-messages'),
]
