from rest_framework import serializers
from .models import Conversation, Message
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class MessageSerializer(serializers.ModelSerializer):
    is_me = serializers.SerializerMethodField()
    # Adding sender_id explicitly helps the frontend logic
    sender_id = serializers.ReadOnlyField(source='sender.id')

    class Meta:
        model = Message
        # Include sender_id for the frontend 'isMe' check
        fields = ['id', 'text', 'sender', 'sender_id', 'is_me', 'created_at']

    def get_is_me(self, obj):
        return obj.sender == self.context['request'].user

class ConversationSerializer(serializers.ModelSerializer):
    other_user_name = serializers.SerializerMethodField()
    other_user_id = serializers.SerializerMethodField() # Added for navigation
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField() # Added for badges
    other_user_status = serializers.SerializerMethodField() # Added for online status

    class Meta:
        model = Conversation
        fields = ['id', 'other_user_name', 'other_user_id', 'other_user_status', 'last_message', 'unread_count', 'updated_at']

    def get_other_user_name(self, obj):
        user = self.context['request'].user
        other = obj.participants.exclude(id=user.id).first()
        if other:
            if hasattr(other, 'store'):
                return other.store.name
            return other.full_name or other.email
        return "Unknown User"

    def get_other_user_id(self, obj):
        user = self.context['request'].user
        other = obj.participants.exclude(id=user.id).first()
        return other.id if other else None

    def get_last_message(self, obj):
        last = obj.messages.order_by('-created_at').first()
        return last.text if last else "New Conversation"

    def get_unread_count(self, obj):
        user = self.context['request'].user
        # Count messages not sent by me that are still 'is_read=False'
        return obj.messages.filter(is_read=False).exclude(sender=user).count()

    def get_other_user_status(self, obj):
        user = self.context['request'].user
        other = obj.participants.exclude(id=user.id).first()
        if other:
            # If the user logged in within the last 5 minutes, consider them "Active Now"
            if other.last_login and (timezone.now() - other.last_login).total_seconds() < 300:
                return "Active now"
            elif other.last_login:
                return f"Last seen {other.last_login.strftime('%H:%M')}"
        return "Offline"
        user = self.context['request'].user
        # Count messages not sent by me that are still 'is_read=False'
        return obj.messages.filter(is_read=False).exclude(sender=user).count()