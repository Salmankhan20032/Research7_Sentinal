from __future__ import annotations

import hashlib
from typing import Any

import httpx
from django.conf import settings


class TokenClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.SENTINEL_ENGINE_URL).rstrip("/")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=1.5) as client:
            response = client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()

    def issue_token(self, worker_id: str, command_hash: str, timestamp: int) -> dict[str, Any]:
        try:
            return self._post(
                "/token/issue",
                {"worker_id": worker_id, "command_hash": command_hash, "timestamp": timestamp},
            )
        except Exception as exc:
            return {"valid": False, "token": None, "reason": f"engine_unreachable: {exc}"}

    def verify_token(self, token: str, worker_id: str, command_hash: str, timestamp: int) -> dict[str, Any]:
        try:
            return self._post(
                "/token/verify",
                {
                    "token": token,
                    "worker_id": worker_id,
                    "command_hash": command_hash,
                    "timestamp": timestamp,
                },
            )
        except Exception as exc:
            return {"valid": False, "reason": f"engine_unreachable: {exc}"}

    @staticmethod
    def hash_command(worker_id: str, sensor_id: str, command_type: str, parameter_value: float) -> str:
        material = f"{worker_id}:{sensor_id}:{command_type}:{parameter_value:.4f}"
        return hashlib.sha256(material.encode()).hexdigest()
