from rest_framework import serializers

from .models import Alert, Command, ForensicLog, SensorState, WorkerSession


class SensorStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorState
        fields = "__all__"


class CommandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Command
        fields = "__all__"


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = "__all__"


class ForensicLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ForensicLog
        fields = "__all__"


class WorkerSessionSerializer(serializers.ModelSerializer):
    commands = CommandSerializer(many=True, read_only=True)
    alerts = AlertSerializer(many=True, read_only=True)

    class Meta:
        model = WorkerSession
        fields = "__all__"


class CommandIntakeSerializer(serializers.Serializer):
    worker_id = serializers.CharField(max_length=64)
    sensor_id = serializers.CharField(max_length=32)
    command_type = serializers.ChoiceField(choices=["read", "write", "setpoint"])
    parameter_value = serializers.FloatField()
    attack_mode = serializers.ChoiceField(
        choices=["normal", "insider_threat", "credential_theft", "evasion", "model_b_compromise"],
        default="normal",
        required=False,
    )


class AttackScenarioSerializer(serializers.Serializer):
    scenario = serializers.ChoiceField(
        choices=["insider_threat", "credential_theft", "evasion", "model_b_compromise"]
    )
