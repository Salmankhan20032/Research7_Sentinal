# SENTINEL

SENTINEL is a deployable prototype of a Secure and Evasion-aware Neural Trust Engine for industrial IoT environments. The system combines a Django control plane, a deterministic trust-scoring engine, a Go HMAC write-gate, simulated sensors, real-time dashboard updates, and demo attack scenarios.

## Prerequisites

- Python 3.11+
- Go 1.21+
- Docker (for Redis) OR Redis installed locally
- Git

## Local Setup (Step by Step)

```bash
# 1. Clone and enter project
git clone <repo>
cd sentinel-project

# 2. Start Redis (Docker)
docker-compose up -d redis

# 3. Set up Python environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY and SENTINEL_HMAC_SECRET to any random strings

# 5. Run Django migrations
python manage.py migrate

# 6. Initialize sensors
python manage.py init_sensors

# 7. Create superuser (optional, for /admin)
python manage.py createsuperuser

# 8. Build and start Go write-gate service (separate terminal)
cd sentinel-engine
go build -o sentinel-engine .
./sentinel-engine
# Go service now running on http://localhost:8081

# 9. Start Celery worker (separate terminal, back in project root)
source venv/bin/activate
celery -A sentinel worker -l info

# 10. Start Celery beat scheduler (separate terminal)
source venv/bin/activate
celery -A sentinel beat -l info

# 11. Start Django (main terminal)
python manage.py runserver

# Open http://localhost:8000
```

## Demo Usage

1. Open dashboard at `http://localhost:8000`
2. Go to "Demo Mode" in sidebar
3. Select attack scenario and click "Launch Attack"
4. Watch the dashboard live-update as the attack unfolds
5. Check "Forensic Log" after an attack for evidence trail
