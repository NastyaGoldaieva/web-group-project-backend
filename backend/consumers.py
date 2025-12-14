import json
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        qs = parse_qs(self.scope.get('query_string', b'').decode())
        user_ids = qs.get('user_id', [])
        if not user_ids:
            await self.close()
            return
        self.group_name = f"user_{user_ids[0]}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify(self, event):
        await self.send(text_data=json.dumps({
            "event": event.get("event"),
            "data": event.get("data")
        }))