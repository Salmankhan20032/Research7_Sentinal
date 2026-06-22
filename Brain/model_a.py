from __future__ import annotations

import time

from django.utils import timezone

from core.models import Alert, Command, ForensicLog, SensorState, WorkerSession
from .lstm_scorer import LSTMScorer
from .token_client import TokenClient


class ModelA:
    """Trust & Verification Engine. Never network-exposed."""

    def __init__(self):
        self.scorer = LSTMScorer()
        self.token_client = TokenClient()

    def evaluate_command(self, session: WorkerSession, raw_command: dict) -> dict:
        if not self._stage1_auth(session, raw_command):
            return self._blocked_payload(1, "auth_binding_failed")

        sensor = SensorState.objects.filter(sensor_id=raw_command["sensor_id"]).first()
        if not sensor:
            return self._blocked_payload(2, "unknown_sensor")

        if not self._stage2_range(raw_command, sensor):
            return self._blocked_payload(2, "unsafe_range")

        score = self._stage3_score(session)
        routing = self.scorer.route(score)
        token = None
        reason = "approved"

        if routing == Command.ROUTE_APPROVE and raw_command["command_type"] in {"write", "setpoint"}:
            token = self._stage4_token(
                session.worker_id,
                raw_command["command_hash"],
                raw_command["timestamp"],
            )
            if not token:
                routing = Command.ROUTE_BLOCK
                reason = "write_gate_unavailable"
        elif routing == Command.ROUTE_HONEYPOT:
            reason = "behavioral_anomaly_detected"
        elif routing == Command.ROUTE_BLOCK:
            reason = "threat_threshold_exceeded"

        return {
            "routing": routing,
            "score": score,
            "token": token,
            "stage_blocked": 4 if routing == Command.ROUTE_BLOCK and reason == "write_gate_unavailable" else None,
            "reason": reason,
        }

    def _blocked_payload(self, stage: int, reason: str) -> dict:
        return {"routing": "block", "score": 1.0 if stage == 1 else 0.85, "token": None, "stage_blocked": stage, "reason": reason}

    def _stage1_auth(self, session, command) -> bool:
        timestamp = command.get("timestamp") or int(time.time() * 1000)
        now_ms = int(time.time() * 1000)
        return abs(now_ms - int(timestamp)) <= 5_000 and bool(command.get("nonce")) and session.is_active

    def _stage2_range(self, command, sensor: SensorState) -> bool:
        if command["command_type"] == "read":
            return True
        value = float(command["parameter_value"])
        return sensor.min_safe <= value <= sensor.max_safe

    def _stage3_score(self, session) -> float:
        recent = list(
            session.commands.order_by("-timestamp")
            .values("sensor_id", "parameter_value", "delta", "inter_command_interval")[: self.scorer.WINDOW]
        )
        recent.reverse()
        attack_mode = session.attack_mode or "normal"
        for row in recent:
            sensor = SensorState.objects.filter(sensor_id=row["sensor_id"]).first()
            row["safe_range"] = sensor.safe_range if sensor else 1.0
            row["attack_mode"] = attack_mode
        return self.scorer.score(recent)

    def _stage4_token(self, worker_id, command_hash, timestamp) -> str | None:
        response = self.token_client.issue_token(worker_id, command_hash, int(timestamp))
        if response.get("valid"):
            return response.get("token")
        return None

    def handle_honeypot_feedback(self, session: WorkerSession, new_score: float):
        if new_score >= self.scorer.TAU_BLOCK:
            session.mode = WorkerSession.MODE_LOCKDOWN
            severity = "critical"
            message = "Session escalated to lockdown after honeypot evidence aggregation."
        elif new_score > self.scorer.TAU_CLEAR:
            session.mode = WorkerSession.MODE_HONEYPOT
            severity = "high"
            message = "Session redirected to honeypot after anomaly review."
        else:
            session.mode = WorkerSession.MODE_NORMAL
            severity = "low"
            message = "Session returned to normal supervision."
        session.suspicion_score = new_score
        session.save(update_fields=["mode", "suspicion_score", "last_seen"])
        Alert.objects.create(session=session, severity=severity, message=message)
        latest_command = session.commands.first()
        if latest_command:
            ForensicLog.objects.create(
                session=session,
                command=latest_command,
                event_type="score_escalation",
                evidence_json={
                    "score": new_score,
                    "mode": session.mode,
                    "reviewed_at": timezone.now().isoformat(),
                },
            )
