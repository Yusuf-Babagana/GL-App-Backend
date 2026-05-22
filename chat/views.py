import logging

from django.contrib.auth import get_user_model
from django.db.models import OuterRef, Prefetch, Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Conversation, Message
from .serializers import (
    ConversationListSerializer,
    MessageSerializer,
    MessageCreateSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def send_expo_push_notification(token, title, body, data=None):
    if not token:
        return False
    import requests
    try:
        payload = {
            'to': token,
            'sound': 'default',
            'title': title,
            'body': body,
            'priority': 'high',
        }
        if data:
            payload['data'] = data
        resp = requests.post(
            'https://exp.host/--/api/v2/push/send',
            json=payload,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException as exc:
        logger.error(f'Expo push notification failed: {exc}')
        return False


class InboxListView(generics.ListAPIView):
    serializer_class = ConversationListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return (
            Conversation.objects.filter(participants=user)
            .prefetch_related(
                Prefetch(
                    'messages',
                    queryset=Message.objects.order_by('-created_at'),
                    to_attr='latest_messages',
                ),
                'participants',
            )
            .annotate(
                last_message_text=Message.objects.filter(
                    conversation=OuterRef('pk')
                )
                .order_by('-created_at')
                .values('text')[:1],
                last_message_time_iso=Message.objects.filter(
                    conversation=OuterRef('pk')
                )
                .order_by('-created_at')
                .values('created_at')[:1],
                unread_count_value=Message.objects.filter(
                    conversation=OuterRef('pk'), is_read=False
                )
                .exclude(sender=user)
                .order_by()
                .annotate(cnt=Count('id'))
                .values('cnt'),
            )
            .order_by('-updated_at')
        )


class StartOrGetConversationView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        other_user_id = request.data.get('user_id')
        product_id = request.data.get('product_id')
        other_user = get_object_or_404(User, id=other_user_id)

        if request.user == other_user:
            return Response(
                {'error': 'You cannot chat with yourself'}, status=400
            )

        conversation = (
            Conversation.objects.filter(participants=request.user)
            .filter(participants=other_user)
            .prefetch_related('participants')
            .first()
        )

        if not conversation:
            conversation = Conversation.objects.create(
                product_context_id=product_id
            )
            conversation.participants.add(request.user, other_user)

        if hasattr(other_user, 'merchant_shop') and other_user.merchant_shop:
            partner_name = other_user.merchant_shop.name
        else:
            partner_name = other_user.full_name or other_user.email

        messages = conversation.messages.select_related('sender').all()
        serializer = MessageSerializer(
            messages, many=True, context={'request': request},
        )

        return Response({
            'conversation_id': conversation.id,
            'partner_name': partner_name,
            'messages': serializer.data,
        })


class MessageListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MessageCreateSerializer
        return MessageSerializer

    def get_serializer_context(self):
        return {'request': self.request}

    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        last_id = self.request.query_params.get('last_id')
        user = self.request.user

        qs = (
            Message.objects.filter(
                conversation_id=conversation_id,
                conversation__participants=user,
            )
            .select_related('sender')
            .order_by('created_at')
        )

        if last_id:
            try:
                qs = qs.filter(id__gt=int(last_id))
            except (ValueError, TypeError):
                pass

        Message.objects.filter(
            conversation_id=conversation_id,
            is_read=False,
        ).exclude(sender=user).update(is_read=True)

        return qs

    def perform_create(self, serializer):
        conversation_id = self.kwargs['conversation_id']
        conv = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=self.request.user,
        )
        recipient = conv.participants.exclude(
            id=self.request.user.id
        ).first()

        message = serializer.save(
            conversation=conv,
            sender=self.request.user,
            recipient=recipient,
        )

        conv.save(update_fields=['updated_at'])

        if recipient and not recipient.is_online:
            sender_name = (
                self.request.user.full_name or self.request.user.email
            )
            product_name = ''
            if conv.product_context_id:
                try:
                    from market.models import Product
                    product = Product.objects.get(id=conv.product_context_id)
                    product_name = product.name
                except Exception:
                    pass

            push_data = {
                'type': 'new_message',
                'conversation_id': conv.id,
                'sender_id': self.request.user.id,
            }

            notification_title = f'New message from {sender_name}'
            if product_name:
                notification_body = f'Regarding: {product_name}'
            else:
                text = message.text or ''
                notification_body = text[:100] or 'Sent an image'

            if recipient.push_token:
                send_expo_push_notification(
                    token=recipient.push_token,
                    title=notification_title,
                    body=notification_body,
                    data=push_data,
                )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            MessageSerializer(
                serializer.instance, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )
