from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def push_dashboard_event(event_type: str, data: dict) -> None:
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "dashboard",
            {"type": event_type, "data": data},
        )
    except Exception:
        return
