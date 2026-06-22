import random

from django.core.management.base import BaseCommand

from Brain.sensors import DEFAULT_SENSORS
from core.models import SensorState


class Command(BaseCommand):
    help = "Initialize the six simulated SENTINEL sensors."

    def handle(self, *args, **options):
        created = 0
        for payload in DEFAULT_SENSORS:
            lower = payload["min_safe"]
            upper = payload["max_safe"]
            initial = lower + (upper - lower) * random.uniform(0.3, 0.7)
            _, was_created = SensorState.objects.get_or_create(
                sensor_id=payload["sensor_id"],
                defaults={
                    "sensor_name": payload["sensor_name"],
                    "sensor_type": payload["sensor_type"],
                    "unit": payload["unit"],
                    "current_value": round(initial, 2),
                    "honeypot_value": round(initial, 2),
                    "min_safe": lower,
                    "max_safe": upper,
                },
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Sensors initialized. New records: {created}"))
