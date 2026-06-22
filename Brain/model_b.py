from __future__ import annotations

import time

from django.db import transaction

from core.models import Alert, Command, ForensicLog, SensorState, WorkerSession
from core.realtime import push_dashboard_event
from .model_a import ModelA
from .sensors import SensorStateManager
from .token_client import TokenClient


class ModelB:
    """
    Network-facing command broker.
    """

    PERMITTED_COMMANDS = {"read", "write", "setpoint"}

    def __init__(self):
        self.model_a = ModelA()
        self.sensor_manager = SensorStateManager()
        self.token_client = TokenClient()

    def receive_command(self, session: WorkerSession, raw_command: dict) -> dict:
        self._validate(raw_command)
        sensor = SensorState.objects.get(sensor_id=raw_command["sensor_id"])
        timestamp = int(raw_command.get("timestamp") or int(time.time() * 1000))
        raw_command["timestamp"] = timestamp
        raw_command["command_hash"] = self.token_client.hash_command(
            session.worker_id,
            sensor.sensor_id,
            raw_command["command_type"],
            float(raw_command["parameter_value"]),
        )
        previous = session.commands.order_by("-timestamp").first()
        delta = abs(float(raw_command["parameter_value"]) - sensor.current_value)
        interval = (
            max((time.time() - previous.timestamp.timestamp()), 0.0) if previous else 0.0
        )
        result = self.model_a.evaluate_command(session, raw_command)

        with transaction.atomic():
            command = Command.objects.create(
                session=session,
                sensor_id=sensor.sensor_id,
                command_type=raw_command["command_type"],
                parameter_value=float(raw_command["parameter_value"]),
                delta=round(delta, 3),
                inter_command_interval=round(interval, 3),
                suspicion_score=result["score"],
                routing=result["routing"],
                token_issued=bool(result["token"]),
                token_value=result["token"] or "",
            )
            session.command_count = session.commands.count()
            session.suspicion_score = result["score"]
            session.mode = {
                "approve": WorkerSession.MODE_NORMAL,
                "honeypot": WorkerSession.MODE_HONEYPOT,
                "block": WorkerSession.MODE_LOCKDOWN,
            }[result["routing"]]
            session.save(update_fields=["command_count", "suspicion_score", "mode", "last_seen"])

            if result["routing"] == Command.ROUTE_APPROVE:
                self._execute_real_write(
                    session.worker_id,
                    sensor,
                    float(raw_command["parameter_value"]),
                    result["token"],
                    raw_command["command_hash"],
                    timestamp,
                )
            elif result["routing"] == Command.ROUTE_HONEYPOT:
                self._execute_honeypot_write(sensor, float(raw_command["parameter_value"]))
                ForensicLog.objects.create(
                    session=session,
                    command=command,
                    event_type="honeypot_entry",
                    evidence_json={"reason": result["reason"], "score": result["score"]},
                )
                from core.tasks import honeypot_evidence_aggregator

                honeypot_evidence_aggregator.delay(session.id)
            else:
                self._terminate_session(session, result["reason"])
                ForensicLog.objects.create(
                    session=session,
                    command=command,
                    event_type="block",
                    evidence_json={"reason": result["reason"], "score": result["score"]},
                )

        payload = {
            "routing": result["routing"],
            "score": result["score"],
            "reason": result["reason"],
            "token_issued": bool(result["token"]),
            "session_mode": session.mode,
            "sensor_id": sensor.sensor_id,
            "value": raw_command["parameter_value"],
        }
        push_dashboard_event(
            "score_update",
            {"session_id": session.id, "worker_id": session.worker_id, **payload},
        )
        return payload

    def _validate(self, raw_command: dict) -> None:
        required = {"sensor_id", "command_type", "parameter_value"}
        if missing := sorted(required - set(raw_command)):
            raise ValueError(f"Missing fields: {', '.join(missing)}")
        if raw_command["command_type"] not in self.PERMITTED_COMMANDS:
            raise ValueError("Unsupported command type")

    def _execute_real_write(
        self,
        worker_id: str,
        sensor: SensorState,
        value: float,
        token: str,
        command_hash: str,
        timestamp: int,
    ):
        if sensor.sensor_type and token:
            verified = self.token_client.verify_token(token, worker_id, command_hash, timestamp)
            if verified.get("valid"):
                self.sensor_manager.set_real_value(sensor, value)
                push_dashboard_event(
                    "sensor_update",
                    {"sensor_id": sensor.sensor_id, "current_value": sensor.current_value, "status": "approve"},
                )

    def _execute_honeypot_write(self, sensor: SensorState, value: float):
        self.sensor_manager.set_honeypot_value(sensor, value)
        push_dashboard_event(
            "sensor_update",
            {"sensor_id": sensor.sensor_id, "honeypot_value": sensor.honeypot_value, "status": "honeypot"},
        )

    def _terminate_session(self, session: WorkerSession, reason: str):
        session.is_active = False
        session.mode = WorkerSession.MODE_LOCKDOWN
        session.save(update_fields=["is_active", "mode", "last_seen"])
        Alert.objects.create(session=session, severity="critical", message=f"Session terminated: {reason}")
        push_dashboard_event(
            "alert_raised",
            {"session_id": session.id, "severity": "critical", "message": f"Session terminated: {reason}"},
        )
