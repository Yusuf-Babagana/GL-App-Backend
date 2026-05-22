from rest_framework import serializers
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    created_at_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'sender_name', 'text',
            'image_url', 'is_read', 'created_at', 'created_at_formatted',
        ]
        read_only_fields = ['id', 'sender', 'sender_name', 'created_at', 'created_at_formatted']

    def get_sender_name(self, obj):
        return obj.sender.full_name or obj.sender.email

    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime('%Y-%m-%d %H:%M:%S')


class ConversationSerializer(serializers.ModelSerializer):
    other_user_name = serializers.SerializerMethodField()
    product_name = serializers.ReadOnlyField(source='product.name')
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'other_user_name', 'product', 'product_name',
            'last_message', 'unread_count', 'updated_at',
        ]

    def get_other_user_name(self, obj):
        request = self.context.get('request')
        if request and request.user == obj.buyer:
            return obj.seller.full_name or obj.seller.email
        return obj.buyer.full_name or obj.buyer.email

    def get_last_message(self, obj):
        msg = obj.messages.order_by('-created_at').first()
        return msg.text[:100] if msg else None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request:
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0
