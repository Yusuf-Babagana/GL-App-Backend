from rest_framework import serializers
from .models import Conversation, Message

class MessageSerializer(serializers.ModelSerializer):
    is_me = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'text', 'sender', 'is_me', 'created_at']

    def get_is_me(self, obj):
        return obj.sender == self.context['request'].user

class ConversationSerializer(serializers.ModelSerializer):
    other_user_name = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'other_user_name', 'last_message', 'updated_at']

    def get_other_user_name(self, obj):
        # Logic to find the participant who IS NOT the current user
        user = self.context['request'].user
        other = obj.participants.exclude(id=user.id).first()
        # If the other person has a store, show Store Name, else show Full Name
        if hasattr(other, 'store'):
            return other.store.name
        return other.full_name or other.email

    def get_last_message(self, obj):
        last = obj.messages.last()
        return last.text if last else "No messages yet"