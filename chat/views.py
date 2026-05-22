from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer


class ConversationListView(generics.ListAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return (
            Conversation.objects.filter(
                models.Q(buyer=user) | models.Q(seller=user)
            )
            .select_related('buyer', 'seller', 'product')
            .order_by('-created_at')
        )


class MessageListView(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        return {'request': self.request}

    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if self.request.user not in (conversation.buyer, conversation.seller):
            return Message.objects.none()

        qs = Message.objects.filter(conversation=conversation).select_related('sender')

        last_id = self.request.query_params.get('last_id')
        if last_id:
            try:
                qs = qs.filter(id__gt=int(last_id))
            except (ValueError, TypeError):
                pass

        qs = qs.order_by('created_at')

        Message.objects.filter(
            conversation=conversation, is_read=False
        ).exclude(sender=self.request.user).update(is_read=True)

        return qs


class SendMessageView(generics.CreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        return {'request': self.request}

    def perform_create(self, serializer):
        conversation_id = self.kwargs['conversation_id']
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if self.request.user not in (conversation.buyer, conversation.seller):
            self.permission_denied(self.request)

        serializer.save(
            conversation=conversation,
            sender=self.request.user,
        )
