import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

try:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False

from .models import Conversation, Message
from .serializers import (
    ConversationDetailSerializer,
    ConversationListSerializer,
    MessageSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def send_expo_push_notification(token, title, body, data=None):
    if not token:
        return False
    import requests
    try:
        payload = {
            "to": token,
            "sound": "default",
            "title": title,
            "body": body,
            "priority": "high",
        }
        if data:
            payload["data"] = data
        resp = requests.post(
            "https://exp.host/--/api/v2/push/send",
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException as exc:
        logger.error(f"Expo push notification failed: {exc}")
        return False


def broadcast_message(message):
    if not CHANNELS_AVAILABLE:
        return
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        conv_id = message.conversation_id
        group_name = f"chat_{conv_id}"
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "new_message",
                "payload": {
                    "id": message.id,
                    "conversation": conv_id,
                    "text": message.text,
                    "attachment": message.attachment,
                    "sender": message.sender_id,
                    "sender_id": message.sender_id,
                    "sender_name": message.sender.full_name or message.sender.email,
                    "sender_image": (
                        message.sender.profile_image.url
                        if message.sender.profile_image
                        else None
                    ),
                    "recipient": message.recipient_id,
                    "is_read": message.is_read,
                    "created_at": message.created_at.isoformat(),
                },
            },
        )
    except Exception as exc:
        logger.warning(f"WebSocket broadcast failed: {exc}")


class InboxListView(generics.ListAPIView):
    serializer_class = ConversationListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return (
            Conversation.objects.filter(participants=user)
            .prefetch_related(
                Prefetch(
                    "messages",
                    queryset=Message.objects.order_by("-created_at"),
                    to_attr="latest_messages",
                ),
                "participants",
            )
            .annotate(
                last_message_text=Message.objects.filter(
                    conversation=OuterRef("pk")
                )
                .order_by("-created_at")
                .values("text")[:1],
                last_message_time_iso=Message.objects.filter(
                    conversation=OuterRef("pk")
                )
                .order_by("-created_at")
                .values("created_at")[:1],
                unread_count_value=Message.objects.filter(
                    conversation=OuterRef("pk"), is_read=False
                )
                .exclude(sender=user)
                .order_by()
                .annotate(cnt=Count("id"))
                .values("cnt"),
            )
            .order_by("-updated_at")
        )


class StartOrGetConversationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        other_user_id = request.data.get("user_id")
        product_id = request.data.get("product_id")
        other_user = get_object_or_404(User, id=other_user_id)

        if request.user == other_user:
            return Response(
                {"error": "You cannot chat with yourself"}, status=400
            )

        conversation = (
            Conversation.objects.filter(participants=request.user)
            .filter(participants=other_user)
            .prefetch_related("participants")
            .first()
        )

        if not conversation:
            conversation = Conversation.objects.create(
                product_context_id=product_id
            )
            conversation.participants.add(request.user, other_user)

        if hasattr(other_user, "merchant_shop") and other_user.merchant_shop:
            partner_name = other_user.merchant_shop.name
        else:
            partner_name = other_user.full_name or other_user.email

        messages = conversation.messages.select_related(
            "sender", "recipient"
        ).all()
        serializer = MessageSerializer(
            messages,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "conversation_id": conversation.id,
                "partner_name": partner_name,
                "messages": serializer.data,
            }
        )


class SendMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, conversation_id):
        conv = get_object_or_404(
            Conversation, id=conversation_id, participants=request.user
        )
        text = request.data.get("text", "")
        attachment = request.data.get("attachment")

        if not text and not attachment:
            return Response(
                {"error": "Text or attachment is required"}, status=400
            )

        recipient = conv.participants.exclude(id=request.user.id).first()

        message = Message.objects.create(
            conversation=conv,
            sender=request.user,
            recipient=recipient,
            text=text,
            attachment=attachment,
        )

        conv.save(update_fields=["updated_at"])
        message.refresh_from_db()

        broadcast_message(message)

        if recipient and not recipient.is_online:
            sender_name = request.user.full_name or request.user.email
            product_name = ""
            if conv.product_context_id:
                try:
                    from market.models import Product
                    product = Product.objects.get(id=conv.product_context_id)
                    product_name = product.name
                except Exception:
                    pass

            push_data = {
                "type": "new_message",
                "conversation_id": conv.id,
                "sender_id": request.user.id,
            }

            notification_title = f"New message from {sender_name}"
            if product_name:
                notification_body = f"Regarding: {product_name}"
            else:
                notification_body = text[:100] if text else "Sent an attachment"

            if recipient.push_token:
                send_expo_push_notification(
                    token=recipient.push_token,
                    title=notification_title,
                    body=notification_body,
                    data=push_data,
                )

        return Response(
            {
                "status": "sent",
                "message_id": message.id,
                "created_at": message.created_at.isoformat(),
            }
        )


class MessageListView(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs["conversation_id"]
        last_id = self.request.query_params.get("last_id", 0)
        user = self.request.user

        queryset = (
            Message.objects.filter(
                conversation_id=conversation_id,
                conversation__participants=user,
            )
            .select_related("sender", "recipient")
            .order_by("created_at")
        )

        if last_id:
            try:
                queryset = queryset.filter(id__gt=int(last_id))
            except (ValueError, TypeError):
                pass

        unread = queryset.filter(is_read=False).exclude(sender=user)
        unread.update(is_read=True)

        return queryset
