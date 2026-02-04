from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import Conversation, Message
from market.models import Store
from django.contrib.auth import get_user_model

User = get_user_model()



from django.db.models import Max
from .serializers import ConversationSerializer, MessageSerializer

class InboxListView(generics.ListAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Return conversations where the user is a participant, 
        # ordered by the most recent message
        return Conversation.objects.filter(
            participants=self.request.user
        ).annotate(
            last_message_time=Max('messages__created_at')
        ).order_by('-last_message_time')


class StartOrGetConversationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        other_user_id = request.data.get('user_id') # Changed from seller_id to be generic
        product_id = request.data.get('product_id')
        other_user = get_object_or_404(User, id=other_user_id)
        
        if request.user == other_user:
            return Response({"error": "You cannot chat with yourself"}, status=400)

        conversation = Conversation.objects.filter(participants=request.user).filter(participants=other_user).first()

        if not conversation:
            conversation = Conversation.objects.create(product_context_id=product_id)
            conversation.participants.add(request.user, other_user)

        # Logic to determine display name
        if hasattr(other_user, 'store'):
            partner_name = other_user.store.name
        else:
            partner_name = other_user.full_name or other_user.email

        return Response({
            "conversation_id": conversation.id,
            "partner_name": partner_name,
            "messages": MessageSerializer(conversation.messages.all().order_by('created_at'), many=True, context={'request': request}).data
        })

class SendMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, conversation_id):
        conv = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
        text = request.data.get('text')
        
        message = Message.objects.create(
            conversation=conv,
            sender=request.user,
            text=text
        )
        
        # Trigger real-time notifications here later
        return Response({"status": "sent", "message_id": message.id})

class MessageListView(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        # Yusuf: We get the last_id from the URL query params
        last_id = self.request.query_params.get('last_id', 0)
        
        queryset = Message.objects.filter(
            conversation_id=conversation_id,
            conversation__participants=self.request.user
        )
        
        # If the app sends a last_id, only return messages newer than that
        if last_id:
            queryset = queryset.filter(id__gt=last_id)
            
        return queryset.order_by('created_at')