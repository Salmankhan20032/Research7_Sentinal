import hashlib
from collections import Counter

import numpy as np


class LSTMScorer:
    """
    Deterministic behavioral scorer that simulates a Bi-LSTM classifier.
    """

    WINDOW = 32
    TAU_CLEAR = 0.25
    TAU_BLOCK = 0.72

    def _noise(self, command_window: list[dict]) -> float:
        if not command_window:
            return 0.02
        basis = "|".join(
            f"{row.get('sensor_id')}:{row.get('parameter_value')}:{row.get('inter_command_interval')}"
            for row in command_window[-self.WINDOW :]
        )
        seed = int(hashlib.sha256(basis.encode()).hexdigest()[:8], 16)
        return 0.02 + (seed % 31) / 1000

    def score(self, command_window: list[dict]) -> float:
        if not command_window:
            return 0.02
        window = command_window[-self.WINDOW :]
        deltas = np.array([abs(item.get("delta", 0.0)) for item in window], dtype=float)
        intervals = np.array([max(item.get("inter_command_interval", 0.0), 0.001) for item in window], dtype=float)
        safe_ranges = np.array([max(item.get("safe_range", 1.0), 1.0) for item in window], dtype=float)
        sensor_ids = [item.get("sensor_id", "unknown") for item in window]

        delta_factor = min(1.0, float(deltas.sum() / np.maximum(safe_ranges.mean() * 0.40, 1.0)))
        avg_interval = float(intervals.mean())
        low_interval_fraction = float(np.mean(intervals < max(avg_interval * 0.2, 0.05)))
        cadence_factor = min(1.0, low_interval_fraction * 2.4)
        dominant_sensor_fraction = Counter(sensor_ids).most_common(1)[0][1] / len(sensor_ids)
        pattern_factor = min(1.0, max(dominant_sensor_fraction - 0.60, 0.0) / 0.40)

        attack_mode = window[-1].get("attack_mode", "normal")
        progression = min(len(window) / self.WINDOW, 1.0)
        attack_bias = {
            "normal": 0.0,
            "insider_threat": 0.22 * progression,
            "credential_theft": 0.35 if len(window) >= 3 else 0.18,
            "evasion": 0.18 * progression,
            "model_b_compromise": -0.04,
        }.get(attack_mode, 0.0)

        weighted = (
            delta_factor * 0.4
            + cadence_factor * 0.3
            + pattern_factor * 0.2
            + self._noise(window) * 0.1
            + attack_bias
        )
        if attack_mode == "credential_theft" and len(window) >= 6:
            weighted += 0.18
        if attack_mode == "evasion" and len(window) >= 28:
            weighted += 0.15
        if attack_mode == "insider_threat" and len(window) >= 31:
            weighted += 0.12
        if attack_mode == "model_b_compromise":
            weighted = min(weighted, 0.02)
        return float(min(max(weighted, 0.0), 1.0))

    def route(self, score: float) -> str:
        if score <= self.TAU_CLEAR:
            return "approve"
        if score < self.TAU_BLOCK:
            return "honeypot"
        return "block"


class AttackSimulator:
    def generate_scenario(self, mode: str) -> list[dict]:
        if mode == "credential_theft":
            return [
                {"command_type": "write", "value": 120 + index * 5, "sleep": 0.15}
                for index in range(8)
            ]
        if mode == "evasion":
            return [
                {"command_type": "setpoint", "value": 90 + index * 1.8, "sleep": 0.25}
                for index in range(35)
            ]
        if mode == "model_b_compromise":
            return [
                {"command_type": "write", "value": 200 + index * 2, "sleep": 0.1}
                for index in range(10)
            ]
        return [
            {"command_type": "write", "value": 110 + index * 3.5, "sleep": 0.2}
            for index in range(50)
        ]
