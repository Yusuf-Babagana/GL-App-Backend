from rest_framework import serializers
from .models import Conversation, Message
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class MessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(source='sender.id', read_only=True)
    sender_name = serializers.SerializerMethodField()
    sender_image = serializers.SerializerMethodField()
    is_me = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'text', 'image_url',
            'sender_id', 'sender_name', 'sender_image',
            'recipient', 'is_read', 'is_me', 'created_at',
        ]
        read_only_fields = [
            'id', 'sender_id', 'sender_name', 'sender_image',
            'recipient', 'is_read', 'is_me', 'created_at', 'conversation',
        ]

    def get_sender_name(self, obj):
        return obj.sender.full_name or obj.sender.email

    def get_sender_image(self, obj):
        if obj.sender.profile_image:
            try:
                return obj.sender.profile_image.url
            except Exception:
                pass
        return None

    def get_is_me(self, obj):
        request = self.context.get('request')
        if request:
            return obj.sender == request.user
        return False


class MessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'recipient',
            'text', 'image_url', 'is_read', 'created_at',
        ]
        read_only_fields = [
            'id', 'sender', 'recipient', 'is_read', 'created_at',
        ]

    def validate(self, attrs):
        if not attrs.get('text') and not attrs.get('image_url'):
            raise serializers.ValidationError(
                'text or image_url is required'
            )
        return attrs


class ConversationListSerializer(serializers.ModelSerializer):
    other_user_name = serializers.SerializerMethodField()
    other_user_id = serializers.SerializerMethodField()
    other_user_image = serializers.SerializerMethodField()
    other_user_status = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_time = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    product_context_id = serializers.IntegerField(
        source='product_context_id', read_only=True
    )

    class Meta:
        model = Conversation
        fields = [
            'id', 'other_user_name', 'other_user_id', 'other_user_image',
            'other_user_status', 'last_message', 'last_message_time',
            'unread_count', 'product_context_id', 'updated_at',
        ]

    def _get_other_participant(self, obj):
        user = self.context['request'].user
        try:
            return obj.other_participant
        except AttributeError:
            for p in obj.participants.all():
                if p.id != user.id:
                    obj.other_participant = p
                    return p
        return None

    def get_other_user_name(self, obj):
        other = self._get_other_participant(obj)
        if other is None:
            return 'Unknown User'
        if hasattr(other, 'merchant_shop') and other.merchant_shop:
            return other.merchant_shop.name
        return other.full_name or other.email

    def get_other_user_id(self, obj):
        other = self._get_other_participant(obj)
        return other.id if other else None

    def get_other_user_image(self, obj):
        other = self._get_other_participant(obj)
        if other and other.profile_image:
            try:
                return other.profile_image.url
            except Exception:
                pass
        return None

    def get_other_user_status(self, obj):
        other = self._get_other_participant(obj)
        if other is None:
            return 'Offline'
        if other.is_online:
            return 'Active now'
        if other.last_seen:
            delta = timezone.now() - other.last_seen
            if delta.total_seconds() < 300:
                return 'Active now'
            if delta.total_seconds() < 86400:
                minutes = int(delta.total_seconds() // 60)
                return f'Active {minutes}m ago'
            return f"Last seen {other.last_seen.strftime('%d %b')}"
        return 'Offline'

    def get_last_message(self, obj):
        try:
            return obj.last_message_text
        except AttributeError:
            last = obj.messages.order_by('-created_at').first()
            return last.text if last else 'New Conversation'

    def get_last_message_time(self, obj):
        try:
            return obj.last_message_time_iso
        except AttributeError:
            last = obj.messages.order_by('-created_at').first()
            return last.created_at.isoformat() if last else None

    def get_unread_count(self, obj):
        user = self.context['request'].user
        try:
            return obj.unread_count_value
        except AttributeError:
            return obj.messages.filter(
                is_read=False
            ).exclude(sender=user).count()
