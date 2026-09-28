from rest_framework import serializers
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'sender_name', 'text',
            'is_read', 'created_at',
        ]
        read_only_fields = ['id', 'sender', 'sender_name', 'conversation', 'created_at']

    def get_sender_name(self, obj):
        return obj.sender.full_name or obj.sender.email


class ConversationSerializer(serializers.ModelSerializer):
    other_user_id = serializers.SerializerMethodField()
    other_user_name = serializers.SerializerMethodField()
    other_user_avatar = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'other_user_id', 'other_user_name', 'other_user_avatar',
            'product', 'product_name', 'last_message', 'unread_count',
            'created_at', 'updated_at',
        ]

    def _other_user(self, obj):
        request = self.context.get('request')
        if request and request.user == obj.buyer:
            return obj.seller
        return obj.buyer

    def get_product_name(self, obj):
        return obj.product.name if obj.product else None

    def get_other_user_id(self, obj):
        return self._other_user(obj).id

    def get_other_user_name(self, obj):
        other_user = self._other_user(obj)
        return other_user.full_name or other_user.email

    def get_other_user_avatar(self, obj):
        other_user = self._other_user(obj)
        if not other_user.profile_image:
            return None
        request = self.context.get('request')
        url = other_user.profile_image.url
        return request.build_absolute_uri(url) if request else url

    def _last_message_obj(self, obj):
        # Cached per-instance so get_last_message/get_updated_at (called for the
        # same conversation within one serialization pass) don't each fire their
        # own query.
        if not hasattr(obj, '_cached_last_message'):
            obj._cached_last_message = obj.messages.order_by('-created_at').first()
        return obj._cached_last_message

    def get_last_message(self, obj):
        msg = self._last_message_obj(obj)
        return msg.text[:100] if msg else None

    def get_updated_at(self, obj):
        msg = self._last_message_obj(obj)
        return (msg.created_at if msg else obj.created_at).isoformat()

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request:
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0
