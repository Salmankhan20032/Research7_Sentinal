from django.contrib import admin

from .models import Alert, Command, ForensicLog, SensorState, WorkerSession


@admin.register(WorkerSession)
class WorkerSessionAdmin(admin.ModelAdmin):
    list_display = ("worker_id", "mode", "suspicion_score", "command_count", "is_active", "last_seen")
    list_filter = ("mode", "is_active", "attack_mode")
    search_fields = ("worker_id", "ip_address")


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    list_display = ("session", "sensor_id", "command_type", "parameter_value", "suspicion_score", "routing", "timestamp")
    list_filter = ("routing", "command_type")
    search_fields = ("sensor_id", "session__worker_id")


@admin.register(SensorState)
class SensorStateAdmin(admin.ModelAdmin):
    list_display = ("sensor_id", "sensor_name", "sensor_type", "current_value", "honeypot_value", "last_updated")
    search_fields = ("sensor_id", "sensor_name")


@admin.register(ForensicLog)
class ForensicLogAdmin(admin.ModelAdmin):
    list_display = ("session", "command", "event_type", "timestamp")
    readonly_fields = ("session", "command", "timestamp", "event_type", "evidence_json")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("session", "severity", "acknowledged", "created_at")
    list_filter = ("severity", "acknowledged")
