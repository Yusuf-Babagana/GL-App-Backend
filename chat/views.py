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
            .order_by('-updated_at')
        )


class MessageView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return MessageSerializer

    def get_serializer_context(self):
        return {'request': self.request}

    def get(self, request, conversation_id):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if request.user not in (conversation.buyer, conversation.seller):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        qs = Message.objects.filter(conversation=conversation).select_related('sender')

        last_id = request.query_params.get('last_id')
        if last_id:
            try:
                qs = qs.filter(id__gt=int(last_id))
            except (ValueError, TypeError):
                pass

        qs = qs.order_by('created_at')

        Message.objects.filter(
            conversation=conversation, is_read=False
        ).exclude(sender=request.user).update(is_read=True)

        serializer = MessageSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, conversation_id):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if request.user not in (conversation.buyer, conversation.seller):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        serializer = MessageSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        message = serializer.save(
            conversation=conversation,
            sender=request.user,
        )

        conversation.save(update_fields=['updated_at'])

        return Response(
            MessageSerializer(message, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )
