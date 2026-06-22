from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sessions/", views.sessions_page, name="sessions-page"),
    path("forensic/", views.forensic_page, name="forensic-page"),
    path("demo/", views.command_page, name="command-page"),
    path("partials/sensors/", views.sensors_partial, name="sensors-partial"),
    path("partials/commands/", views.commands_partial, name="commands-partial"),
    path("partials/alerts/", views.alerts_partial, name="alerts-partial"),
    path("api/v1/command/", views.command_intake, name="command-intake"),
    path("api/v1/sessions/", views.sessions_api, name="sessions-api"),
    path("api/v1/sessions/<int:session_id>/", views.session_detail_api, name="session-detail-api"),
    path("api/v1/sensors/", views.sensors_api, name="sensors-api"),
    path("api/v1/sensors/<int:sensor_id>/", views.sensor_detail_api, name="sensor-detail-api"),
    path("api/v1/alerts/", views.alerts_api, name="alerts-api"),
    path("api/v1/alerts/<int:alert_id>/ack/", views.alert_ack_api, name="alert-ack-api"),
    path("api/v1/forensic/<int:session_id>/", views.forensic_api, name="forensic-api"),
    path("api/v1/demo/attack/", views.demo_attack_api, name="demo-attack-api"),
    path("api/v1/stats/", views.stats_api, name="stats-api"),
    path("api/v1/dashboard-state/", views.dashboard_state_api, name="dashboard-state-api"),
]
