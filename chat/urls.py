from django.urls import path
from .views import (
    StartOrGetConversationView, 
    InboxListView, 
    MessageListView, 
    SendMessageView
)

urlpatterns = [
    # 1. Start or find a chat (POST /api/chat/start/)
    path('start/', StartOrGetConversationView.as_view(), name='start-chat'),
    
    # 2. View the list of all chats (GET /api/chat/inbox/)
    path('inbox/', InboxListView.as_view(), name='chat-inbox'),
    
    # 3. Get messages for one chat (GET /api/chat/conversations/<id>/messages/)
    path('conversations/<int:conversation_id>/messages/', MessageListView.as_view(), name='chat-messages'),
    
    # 4. Send a message (POST /api/chat/conversations/<id>/send/)
    path('conversations/<int:conversation_id>/send/', SendMessageView.as_view(), name='send-message'),
]