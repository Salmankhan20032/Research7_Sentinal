import json

from channels.generic.websocket import AsyncWebsocketConsumer


class DashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("dashboard", self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected", "transport": "websocket"})

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("dashboard", self.channel_name)

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))

    async def sensor_update(self, event):
        await self.send_json({"event": "sensor_update", "data": event["data"]})

    async def score_update(self, event):
        await self.send_json({"event": "score_update", "data": event["data"]})

    async def alert_raised(self, event):
        await self.send_json({"event": "alert", "data": event["data"]})

    async def session_mode_change(self, event):
        await self.send_json({"event": "session_mode_change", "data": event["data"]})
