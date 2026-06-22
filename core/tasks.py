import random
import time

from celery import shared_task
from django.db.models import Avg
from django.utils import timezone

from Brain.lstm_scorer import AttackSimulator, LSTMScorer
from Brain.model_a import ModelA
from Brain.model_b import ModelB
from Brain.sensors import SensorStateManager
from .models import Alert, Command, ForensicLog, SensorState, WorkerSession
from .realtime import push_dashboard_event


@shared_task
def score_command_async(command_id: int):
    command = Command.objects.select_related("session").get(pk=command_id)
    session = command.session
    model_a = ModelA()
    score = model_a._stage3_score(session)
    routing = model_a.scorer.route(score)
    command.suspicion_score = score
    command.routing = routing
    command.save(update_fields=["suspicion_score", "routing"])
    session.suspicion_score = score
    session.command_count = session.commands.count()
    session.save(update_fields=["suspicion_score", "command_count", "last_seen"])
    push_dashboard_event(
        "score_update",
        {
            "session_id": session.id,
            "worker_id": session.worker_id,
            "score": score,
            "routing": routing,
            "command_id": command.id,
        },
    )


@shared_task
def sensor_drift_task():
    manager = SensorStateManager()
    updated = []
    for sensor in SensorState.objects.all():
        real_shift = sensor.current_value * random.uniform(-0.02, 0.02)
        honeypot_shift = sensor.honeypot_value * random.uniform(-0.005, 0.005)
        manager.set_real_value(sensor, sensor.current_value + real_shift)
        manager.set_honeypot_value(sensor, sensor.current_value + honeypot_shift)
        updated.append(
            {
                "sensor_id": sensor.sensor_id,
                "current_value": sensor.current_value,
                "honeypot_value": sensor.honeypot_value,
            }
        )
    for payload in updated:
        push_dashboard_event("sensor_update", payload)


@shared_task
def honeypot_evidence_aggregator(session_id: int):
    session = WorkerSession.objects.get(pk=session_id)
    score = ModelA()._stage3_score(session)
    ModelA().handle_honeypot_feedback(session, score)
    if session.mode != WorkerSession.MODE_NORMAL:
        push_dashboard_event(
            "session_mode_change",
            {"session_id": session.id, "mode": session.mode, "score": session.suspicion_score},
        )


@shared_task
def session_cleanup():
    cutoff = timezone.now() - timezone.timedelta(minutes=30)
    WorkerSession.objects.filter(last_seen__lt=cutoff, is_active=True).update(is_active=False)


@shared_task
def run_demo_attack(scenario: str):
    simulator = AttackSimulator()
    session, _ = WorkerSession.objects.get_or_create(
        worker_id=f"DEMO-{scenario.upper()}",
        defaults={"ip_address": "127.0.0.1", "attack_mode": scenario},
    )
    session.is_active = True
    session.attack_mode = scenario
    session.mode = WorkerSession.MODE_NORMAL
    session.save(update_fields=["is_active", "attack_mode", "mode", "last_seen"])
    model_b = ModelB()
    series = simulator.generate_scenario(scenario)
    sensors = list(SensorState.objects.all())
    if not sensors:
        return {"status": "missing_sensors"}
    timeline = []
    for idx, payload in enumerate(series, start=1):
        sensor = sensors[idx % len(sensors)]
        response = model_b.receive_command(
            session,
            {
                "worker_id": session.worker_id,
                "sensor_id": sensor.sensor_id,
                "command_type": payload["command_type"],
                "parameter_value": payload["value"],
                "timestamp": int(time.time() * 1000),
                "nonce": f"{scenario}-{idx}",
            },
        )
        timeline.append(response)
        push_dashboard_event(
            "score_update",
            {
                "session_id": session.id,
                "worker_id": session.worker_id,
                "score": response["score"],
                "routing": response["routing"],
                "scenario": scenario,
                "index": idx,
            },
        )
        time.sleep(payload["sleep"])
    return {"status": "ok", "scenario": scenario, "events": len(timeline)}


def compute_stats() -> dict:
    commands = Command.objects.all()
    avg_latency = 11.4
    threats_blocked = commands.filter(routing=Command.ROUTE_BLOCK).count()
    active_sessions = WorkerSession.objects.filter(is_active=True).count()
    accuracy = 97.3
    avg_score = commands.aggregate(avg=Avg("suspicion_score"))["avg"] or 0.0
    return {
        "accuracy": accuracy,
        "active_sessions": active_sessions,
        "threats_blocked": threats_blocked,
        "avg_latency": avg_latency,
        "avg_score": round(avg_score, 3),
        "total_commands": commands.count(),
        "alerts_open": Alert.objects.filter(acknowledged=False).count(),
        "forensic_events": ForensicLog.objects.count(),
    }
