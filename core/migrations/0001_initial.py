from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SensorState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sensor_id", models.CharField(max_length=32, unique=True)),
                ("sensor_name", models.CharField(max_length=64)),
                ("sensor_type", models.CharField(max_length=32)),
                ("unit", models.CharField(max_length=16)),
                ("current_value", models.FloatField()),
                ("honeypot_value", models.FloatField()),
                ("min_safe", models.FloatField()),
                ("max_safe", models.FloatField()),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="WorkerSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("worker_id", models.CharField(db_index=True, max_length=64)),
                ("ip_address", models.GenericIPAddressField()),
                ("attack_mode", models.CharField(blank=True, default="normal", max_length=32)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
                ("mode", models.CharField(choices=[("normal", "Normal"), ("honeypot", "Honeypot"), ("lockdown", "Lockdown")], default="normal", max_length=16)),
                ("suspicion_score", models.FloatField(default=0.0)),
                ("command_count", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="Command",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("sensor_id", models.CharField(max_length=32)),
                ("command_type", models.CharField(max_length=16)),
                ("parameter_value", models.FloatField()),
                ("delta", models.FloatField(default=0.0)),
                ("inter_command_interval", models.FloatField(default=0.0)),
                ("suspicion_score", models.FloatField(default=0.0)),
                ("routing", models.CharField(choices=[("approve", "Approve"), ("honeypot", "Honeypot"), ("block", "Block")], max_length=16)),
                ("token_issued", models.BooleanField(default=False)),
                ("token_value", models.CharField(blank=True, max_length=256)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commands", to="core.workersession")),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.CreateModel(
            name="ForensicLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("event_type", models.CharField(max_length=32)),
                ("evidence_json", models.JSONField()),
                ("command", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.command")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="forensic_logs", to="core.workersession")),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.CreateModel(
            name="Alert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("severity", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], max_length=16)),
                ("message", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("acknowledged", models.BooleanField(default=False)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="core.workersession")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.RunSQL(
            sql="""
            CREATE TRIGGER IF NOT EXISTS forensic_log_append_only
            BEFORE UPDATE ON core_forensiclog
            BEGIN
                SELECT RAISE(FAIL, 'ForensicLog is append-only');
            END;
            """,
            reverse_sql="DROP TRIGGER IF EXISTS forensic_log_append_only;",
        ),
        migrations.RunSQL(
            sql="""
            CREATE TRIGGER IF NOT EXISTS forensic_log_delete_block
            BEFORE DELETE ON core_forensiclog
            BEGIN
                SELECT RAISE(FAIL, 'ForensicLog delete is disabled');
            END;
            """,
            reverse_sql="DROP TRIGGER IF EXISTS forensic_log_delete_block;",
        ),
    ]
