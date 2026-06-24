"""
Celery tasks — background job queue for call scheduling, script generation, and retries.
Workers run separately from the FastAPI server.
"""
from celery import Celery
from celery.schedules import crontab
from datetime import datetime, timedelta

from app.core.config import settings

celery_app = Celery(
    "newsbuddy",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                # Retry on worker crash
    worker_prefetch_multiplier=1,       # Don't grab more tasks than needed
    task_soft_time_limit=120,           # 2 min soft limit per task
    task_time_limit=180,                # 3 min hard limit
)

# ── Periodic schedule (Celery Beat) ───────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Deliver daily news voice notes over WhatsApp at 5:30 AM IST
    "schedule-daily-calls": {
        "task": "app.tasks.tasks.schedule_daily_calls",
        "schedule": crontab(hour=5, minute=30),
    },
    # Reset weekly free tier call counters every Monday midnight
    "reset-weekly-counters": {
        "task": "app.tasks.tasks.reset_weekly_call_counters",
        "schedule": crontab(day_of_week=1, hour=0, minute=0),
    },
    # Check for missed calls and notify via WhatsApp every 30 min
    "handle-missed-calls": {
        "task": "app.tasks.tasks.handle_missed_calls",
        "schedule": crontab(minute="*/30"),
    },
}
