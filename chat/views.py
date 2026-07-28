from django.contrib.auth import get_user_model
from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer

User = get_user_model()


def _real_user(request):
    return request.user.is_authenticated


def _resolve_conversation(request, conversation_id):
    try:
        return Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist:
        conv = Conversation.objects.filter(
            models.Q(buyer=request.user, seller_id=conversation_id)
            | models.Q(buyer_id=conversation_id, seller=request.user)
        ).first()
        if conv:
            return conv
    return get_object_or_404(Conversation, id=conversation_id)


class ConversationListView(generics.ListAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user = self.request.user
        if not _real_user(self.request):
            return Conversation.objects.none()
        return (
            Conversation.objects.filter(
                models.Q(buyer=user) | models.Q(seller=user)
            )
            .select_related('buyer', 'seller', 'product')
            .order_by('-created_at')
        )


class MessageListView(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        return {'request': self.request}

    def get_queryset(self):
        if not _real_user(self.request):
            return Message.objects.none()
        conversation_id = self.kwargs['conversation_id']
        conversation = _resolve_conversation(self.request, conversation_id)
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
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        return {'request': self.request}

    def perform_create(self, serializer):
        if not _real_user(self.request):
            self.permission_denied(self.request)
        conversation_id = self.kwargs['conversation_id']
        conversation = _resolve_conversation(self.request, conversation_id)
        if self.request.user not in (conversation.buyer, conversation.seller):
            self.permission_denied(self.request)

        serializer.save(
            conversation=conversation,
            sender=self.request.user,
        )


class StartConversationView(generics.GenericAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        return {'request': self.request}

    def post(self, request):
        if not _real_user(request):
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # The app has shipped this call under a few different key names over time.
        receiver_id = (
            request.data.get('user_id')
            or request.data.get('receiver_id')
            or request.data.get('seller_id')
        )

        if not receiver_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if int(receiver_id) == request.user.id:
            return Response(
                {'error': 'You cannot chat with yourself'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        receiver = get_object_or_404(User, id=receiver_id)

        conversation = Conversation.objects.filter(
            models.Q(buyer=request.user, seller=receiver)
            | models.Q(buyer=receiver, seller=request.user)
        ).first()

        if not conversation:
            product_id = request.data.get('product_id')
            conversation = Conversation.objects.create(
                buyer=request.user,
                seller=receiver,
                product_id=product_id or None,
            )

        other_user = conversation.seller if conversation.buyer == request.user else conversation.buyer

        Message.objects.filter(
            conversation=conversation, is_read=False
        ).exclude(sender=request.user).update(is_read=True)

        messages = [
            {
                'id': m.id,
                'text': m.text,
                'sender__id': m.sender_id,
                'created_at': m.created_at.isoformat(),
            }
            for m in conversation.messages.order_by('created_at')
        ]

        return Response({
            'conversation_id': conversation.id,
            'partner_name': other_user.full_name or other_user.email,
            'other_user_name': other_user.full_name or other_user.email,
            'messages': messages,
        }, status=status.HTTP_200_OK)
