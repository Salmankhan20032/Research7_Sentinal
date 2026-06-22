from dataclasses import dataclass

from core.models import SensorState

DEFAULT_SENSORS = [
    {"sensor_id": "TEMP_01", "sensor_name": "Reactor Temperature", "sensor_type": "temperature", "unit": "°C", "min_safe": 20.0, "max_safe": 280.0},
    {"sensor_id": "TEMP_02", "sensor_name": "Coolant Temperature", "sensor_type": "temperature", "unit": "°C", "min_safe": 5.0, "max_safe": 45.0},
    {"sensor_id": "PRES_01", "sensor_name": "System Pressure", "sensor_type": "pressure", "unit": "bar", "min_safe": 1.0, "max_safe": 8.5},
    {"sensor_id": "PRES_02", "sensor_name": "Injection Pressure", "sensor_type": "pressure", "unit": "bar", "min_safe": 0.5, "max_safe": 12.0},
    {"sensor_id": "FLOW_01", "sensor_name": "Coolant Flow Rate", "sensor_type": "flow", "unit": "L/min", "min_safe": 10.0, "max_safe": 250.0},
    {"sensor_id": "FLOW_02", "sensor_name": "Exhaust Flow Rate", "sensor_type": "flow", "unit": "L/min", "min_safe": 5.0, "max_safe": 180.0},
]


@dataclass
class SensorStateManager:
    def set_real_value(self, sensor: SensorState, value: float) -> SensorState:
        sensor.current_value = round(value, 2)
        sensor.save(update_fields=["current_value", "last_updated"])
        return sensor

    def set_honeypot_value(self, sensor: SensorState, value: float) -> SensorState:
        sensor.honeypot_value = round(value, 2)
        sensor.save(update_fields=["honeypot_value", "last_updated"])
        return sensor

    def get_sensor(self, sensor_id: str) -> SensorState:
        return SensorState.objects.get(sensor_id=sensor_id)
