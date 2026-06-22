from django.core.exceptions import ValidationError
from django.db import models


class WorkerSession(models.Model):
    MODE_NORMAL = "normal"
    MODE_HONEYPOT = "honeypot"
    MODE_LOCKDOWN = "lockdown"
    MODE_CHOICES = [
        (MODE_NORMAL, "Normal"),
        (MODE_HONEYPOT, "Honeypot"),
        (MODE_LOCKDOWN, "Lockdown"),
    ]

    worker_id = models.CharField(max_length=64, db_index=True)
    ip_address = models.GenericIPAddressField()
    attack_mode = models.CharField(max_length=32, blank=True, default="normal")
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_NORMAL)
    suspicion_score = models.FloatField(default=0.0)
    command_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.worker_id} ({self.mode})"


class SensorState(models.Model):
    sensor_id = models.CharField(max_length=32, unique=True)
    sensor_name = models.CharField(max_length=64)
    sensor_type = models.CharField(max_length=32)
    unit = models.CharField(max_length=16)
    current_value = models.FloatField()
    honeypot_value = models.FloatField()
    min_safe = models.FloatField()
    max_safe = models.FloatField()
    last_updated = models.DateTimeField(auto_now=True)

    def clean(self) -> None:
        if self.min_safe >= self.max_safe:
            raise ValidationError("min_safe must be less than max_safe")

    @property
    def safe_range(self) -> float:
        return self.max_safe - self.min_safe

    def __str__(self) -> str:
        return self.sensor_id


class Command(models.Model):
    ROUTE_APPROVE = "approve"
    ROUTE_HONEYPOT = "honeypot"
    ROUTE_BLOCK = "block"
    ROUTING_CHOICES = [
        (ROUTE_APPROVE, "Approve"),
        (ROUTE_HONEYPOT, "Honeypot"),
        (ROUTE_BLOCK, "Block"),
    ]

    session = models.ForeignKey(WorkerSession, on_delete=models.CASCADE, related_name="commands")
    timestamp = models.DateTimeField(auto_now_add=True)
    sensor_id = models.CharField(max_length=32)
    command_type = models.CharField(max_length=16)
    parameter_value = models.FloatField()
    delta = models.FloatField(default=0.0)
    inter_command_interval = models.FloatField(default=0.0)
    suspicion_score = models.FloatField(default=0.0)
    routing = models.CharField(max_length=16, choices=ROUTING_CHOICES)
    token_issued = models.BooleanField(default=False)
    token_value = models.CharField(max_length=256, blank=True)

    class Meta:
        ordering = ["-timestamp"]


class ForensicLog(models.Model):
    session = models.ForeignKey(WorkerSession, on_delete=models.CASCADE, related_name="forensic_logs")
    command = models.ForeignKey(Command, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=32)
    evidence_json = models.JSONField()

    class Meta:
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("ForensicLog is append-only")
        super().save(*args, **kwargs)


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    session = models.ForeignKey(WorkerSession, on_delete=models.CASCADE, related_name="alerts")
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
