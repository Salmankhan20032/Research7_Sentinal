from django.db.models import Prefetch
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from Brain.model_b import ModelB
from .models import Alert, Command, ForensicLog, SensorState, WorkerSession
from .serializers import (
    AlertSerializer,
    AttackScenarioSerializer,
    CommandIntakeSerializer,
    ForensicLogSerializer,
    SensorStateSerializer,
    WorkerSessionSerializer,
)
from .tasks import compute_stats, honeypot_evidence_aggregator, run_demo_attack


def global_template_context(request: HttpRequest) -> dict:
    return {
        "unacked_alert_count": Alert.objects.filter(acknowledged=False).count(),
        "system_status": "alert" if Alert.objects.filter(acknowledged=False).exists() else "operational",
    }


@require_GET
def dashboard(request: HttpRequest):
    sensors = SensorState.objects.all().order_by("sensor_id")
    sessions = WorkerSession.objects.filter(is_active=True).order_by("-last_seen")[:10]
    commands = Command.objects.select_related("session").all()[:20]
    alerts = Alert.objects.filter(acknowledged=False)[:10]
    context = {
        "stats": compute_stats(),
        "sensors": sensors,
        "sessions": sessions,
        "commands": commands,
        "alerts": alerts,
        "chart_labels": [f"C{i}" for i in range(1, 51)],
        "chart_points": [0] * 50,
    }
    return render(request, "dashboard/index.html", context)


@require_GET
def sessions_page(request: HttpRequest):
    sessions = WorkerSession.objects.prefetch_related("alerts").order_by("-last_seen")
    return render(request, "dashboard/sessions.html", {"sessions": sessions})


@require_GET
def forensic_page(request: HttpRequest):
    session_id = request.GET.get("session")
    session = WorkerSession.objects.filter(pk=session_id).first() if session_id else WorkerSession.objects.first()
    logs = session.forensic_logs.all() if session else []
    return render(request, "dashboard/forensic.html", {"session": session, "logs": logs})


@require_GET
def command_page(request: HttpRequest):
    return render(
        request,
        "command/send.html",
        {"sensors": SensorState.objects.all().order_by("sensor_id"), "workers": [f"W00{i}" for i in range(1, 6)]},
    )


@require_GET
def sensors_partial(request: HttpRequest):
    sensors = SensorState.objects.all().order_by("sensor_id")
    return render(request, "partials/sensor_grid.html", {"sensors": sensors})


@require_GET
def commands_partial(request: HttpRequest):
    commands = Command.objects.select_related("session").all()[:20]
    return render(request, "partials/command_table.html", {"commands": commands})


@require_GET
def alerts_partial(request: HttpRequest):
    alerts = Alert.objects.filter(acknowledged=False)[:10]
    return render(request, "partials/alerts_list.html", {"alerts": alerts})


@api_view(["POST"])
def command_intake(request):
    serializer = CommandIntakeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data
    session, _ = WorkerSession.objects.get_or_create(
        worker_id=payload["worker_id"],
        defaults={"ip_address": request.META.get("REMOTE_ADDR", "127.0.0.1"), "attack_mode": payload.get("attack_mode", "normal")},
    )
    if payload.get("attack_mode"):
        session.attack_mode = payload["attack_mode"]
        session.save(update_fields=["attack_mode", "last_seen"])
    response = ModelB().receive_command(
        session,
        {
            **payload,
            "timestamp": request.data.get("timestamp"),
            "nonce": request.data.get("nonce", "api"),
        },
    )
    if request.headers.get("HX-Request") == "true":
        html = render_to_string("partials/command_result.html", {"result": response})
        return Response(html)
    return Response(response)


@api_view(["GET"])
def sessions_api(request):
    sessions = WorkerSession.objects.filter(is_active=True).order_by("-last_seen")
    return Response(WorkerSessionSerializer(sessions, many=True).data)


@api_view(["GET"])
def session_detail_api(request, session_id: int):
    session = get_object_or_404(
        WorkerSession.objects.prefetch_related(
            Prefetch("commands", queryset=Command.objects.all()),
            "alerts",
            "forensic_logs",
        ),
        pk=session_id,
    )
    return Response(WorkerSessionSerializer(session).data)


@api_view(["GET"])
def sensors_api(request):
    return Response(SensorStateSerializer(SensorState.objects.all().order_by("sensor_id"), many=True).data)


@api_view(["GET"])
def sensor_detail_api(request, sensor_id: int):
    sensor = get_object_or_404(SensorState, pk=sensor_id)
    return Response(SensorStateSerializer(sensor).data)


@api_view(["GET"])
def alerts_api(request):
    return Response(AlertSerializer(Alert.objects.filter(acknowledged=False), many=True).data)


@api_view(["POST"])
def alert_ack_api(request, alert_id: int):
    alert = get_object_or_404(Alert, pk=alert_id)
    alert.acknowledged = True
    alert.save(update_fields=["acknowledged"])
    return Response({"status": "acknowledged"})


@api_view(["GET"])
def forensic_api(request, session_id: int):
    logs = ForensicLog.objects.filter(session_id=session_id)
    return Response(ForensicLogSerializer(logs, many=True).data)


@api_view(["POST"])
def demo_attack_api(request):
    serializer = AttackScenarioSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    scenario = serializer.validated_data["scenario"]
    run_demo_attack.delay(scenario)
    return Response({"status": "queued", "scenario": scenario}, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
def stats_api(request):
    return Response(compute_stats())


@api_view(["GET"])
def dashboard_state_api(request):
    data = {
        "stats": compute_stats(),
        "sensors": SensorStateSerializer(SensorState.objects.all().order_by("sensor_id"), many=True).data,
        "alerts": AlertSerializer(Alert.objects.filter(acknowledged=False), many=True).data,
    }
    return Response(data)
