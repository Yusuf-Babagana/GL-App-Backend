import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from chat.models import Conversation, Message

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self.conversation_id = self.scope["url_route"]["kwargs"][
            "conversation_id"
        ]
        self.room_group_name = f"chat_{self.conversation_id}"

        if not await self._is_participant():
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(
            self.room_group_name, self.channel_name
        )
        await self.accept()

        await self._update_online_status(True)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_status",
                "payload": {
                    "user_id": self.user.id,
                    "is_online": True,
                },
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )
        await self._update_online_status(False)
        if hasattr(self, "room_group_name") and hasattr(self, "user"):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_status",
                    "payload": {
                        "user_id": self.user.id,
                        "is_online": False,
                    },
                },
            )

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = data.get("action")

        if action == "mark_read":
            message_ids = data.get("message_ids", [])
            if message_ids:
                await self._mark_messages_read(message_ids)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "messages_read",
                        "payload": {
                            "message_ids": message_ids,
                            "read_by": self.user.id,
                        },
                    },
                )

        elif action == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_typing",
                    "payload": {
                        "user_id": self.user.id,
                        "conversation_id": int(self.conversation_id),
                        "is_typing": data.get("is_typing", True),
                    },
                },
            )

    async def new_message(self, event):
        payload = event["payload"]
        payload["is_me"] = payload.get("sender") == self.user.id
        await self.send(text_data=json.dumps(payload))

    async def user_status(self, event):
        payload = event["payload"]
        await self.send(
            text_data=json.dumps({"type": "user_status", **payload})
        )

    async def messages_read(self, event):
        payload = event["payload"]
        await self.send(
            text_data=json.dumps({"type": "messages_read", **payload})
        )

    async def user_typing(self, event):
        payload = event["payload"]
        if payload.get("user_id") != self.user.id:
            await self.send(
                text_data=json.dumps({"type": "user_typing", **payload})
            )

    @database_sync_to_async
    def _is_participant(self):
        return Conversation.objects.filter(
            id=self.conversation_id, participants=self.user
        ).exists()

    @database_sync_to_async
    def _update_online_status(self, is_online):
        from django.utils import timezone
        user = self.user.__class__.objects.get(id=self.user.id)
        user.is_online = is_online
        if not is_online:
            user.last_seen = timezone.now()
        user.save(update_fields=["is_online", "last_seen"])

    @database_sync_to_async
    def _mark_messages_read(self, message_ids):
        Message.objects.filter(
            id__in=message_ids,
            conversation_id=self.conversation_id,
            recipient=self.user,
        ).update(is_read=True)
