import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import DiscussionMessage, Notification, StudyGroup


class GroupChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_id = int(self.scope["url_route"]["kwargs"]["group_id"])
        self.room_name = f"study_group_{self.group_id}"
        if not self.scope["user"].is_authenticated or not await self.is_member():
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

    async def disconnect(self, _close_code):
        if hasattr(self, "room_name"):
            await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        payload = json.loads(text_data)
        body = payload.get("body", "").strip()
        if not body or len(body) > 2000:
            return
        message = await self.save_message(body)
        await self.channel_layer.group_send(self.room_name, {"type": "chat.message", "message": message})

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    async def chat_delete(self, event):
        await self.send(text_data=json.dumps({"action": "delete_message", "message_id": event["message_id"]}))

    @database_sync_to_async
    def is_member(self):
        from .models import GroupMembership
        from .services import GLOBAL_GC_NAME

        group = StudyGroup.objects.filter(pk=self.group_id).first()
        if not group:
            return False
        if group.name == GLOBAL_GC_NAME:
            GroupMembership.objects.get_or_create(group=group, user=self.scope["user"])
            return True
        return StudyGroup.objects.filter(pk=self.group_id, members=self.scope["user"]).exists()

    @database_sync_to_async
    def save_message(self, body):
        message = DiscussionMessage.objects.create(group_id=self.group_id, author=self.scope["user"], body=body)
        group = StudyGroup.objects.get(pk=self.group_id)
        Notification.objects.bulk_create([
            Notification(user=member, text=f"New message in {group.name} from {self.scope['user'].username}.", link=f"/groups/{group.pk}/")
            for member in group.members.exclude(pk=self.scope["user"].pk)
        ])
        return {
            "id": message.pk,
            "author": self.scope["user"].username,
            "is_admin": group.owner_id == self.scope["user"].pk,
            "body": message.body,
            "created_at": message.created_at.strftime("%I:%M %p").lstrip("0"),
        }
