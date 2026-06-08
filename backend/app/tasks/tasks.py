"""
Task implementations for Celery workers.
"""
from datetime import datetime, timedelta
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.tasks.schedule_daily_calls", bind=True, max_retries=3)
def schedule_daily_calls(self):
    """
    Run at 5:30 AM IST daily.
    1. Gets all active users
    2. Selects top 5 news items per user (city + topics)
    3. Generates personalised script via OpenAI
    4. Creates CallLog entries for their preferred call time
    """
    from app.models.database import SessionLocal, User, NewsItem, CallLog
    from app.services.openai_service import generate_script
    from datetime import date

    db = SessionLocal()
    try:
        today = date.today()
        active_users = db.query(User).filter(User.status == "active").all()
        scheduled_count = 0

        for user in active_users:
            try:
                # Skip free users who've used weekly limit
                if user.subscription_tier == "free" and (user.calls_this_week or 0) >= 3:
                    continue

                # Parse call time
                h, m = map(int, (user.preferred_call_time or "07:00").split(":"))
                call_time = datetime.combine(today, datetime.min.time().replace(hour=h, minute=m))

                # Skip if already scheduled
                existing = db.query(CallLog).filter(
                    CallLog.user_id == user.id,
                    CallLog.scheduled_at == call_time,
                    CallLog.status.in_(["scheduled", "completed", "in_progress"]),
                ).first()
                if existing:
                    continue

                # Get relevant news
                news_items = (
                    db.query(NewsItem)
                    .filter(
                        NewsItem.is_active == True,
                        NewsItem.city.ilike(f"%{user.city}%"),
                    )
                    .order_by(NewsItem.importance_score.desc())
                    .limit(5)
                    .all()
                )

                if not news_items:
                    continue

                # Generate script
                script = generate_script(
                    news_items=news_items,
                    user_name=user.name,
                    city=user.city,
                    language=user.language,
                    topics=user.topics or [],
                )

                # Create call log
                call = CallLog(
                    user_id=user.id,
                    scheduled_at=call_time,
                    news_items_delivered=[item.id for item in news_items],
                    script_used=script,
                    status="scheduled",
                )
                db.add(call)
                scheduled_count += 1

            except Exception as e:
                print(f"[Task] Failed to schedule call for user {user.id}: {e}")
                continue

        db.commit()
        print(f"[Task] Scheduled {scheduled_count} calls for {today}")
        return {"scheduled": scheduled_count}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


@celery_app.task(name="app.tasks.tasks.process_pending_calls", bind=True)
def process_pending_calls(self):
    """
    Run every minute.
    Finds calls scheduled for the next 2 minutes and triggers them via VAPI.
    """
    from app.models.database import SessionLocal, CallLog, User
    from app.services.vapi_service import create_call

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=1)
        window_end = now + timedelta(minutes=2)

        pending_calls = (
            db.query(CallLog)
            .filter(
                CallLog.status == "scheduled",
                CallLog.scheduled_at.between(window_start, window_end),
            )
            .all()
        )

        triggered = 0
        for call in pending_calls:
            try:
                user = db.query(User).filter(User.id == call.user_id).first()
                if not user or user.status != "active":
                    call.status = "cancelled"
                    continue

                result = create_call(
                    phone_number=user.phone_number,
                    script=call.script_used or "",
                    user_name=user.name,
                    language=user.language,
                    call_log_id=call.id,
                )

                call.vapi_call_id = result.get("call_id")
                call.status = "in_progress"
                call.started_at = datetime.utcnow()
                triggered += 1

            except Exception as e:
                call.status = "failed"
                call.error_message = str(e)
                call.retry_count = (call.retry_count or 0) + 1
                print(f"[Task] Call {call.id} failed: {e}")
                # Schedule retry
                if call.retry_count < 2:
                    call.status = "scheduled"
                    call.scheduled_at = datetime.utcnow() + timedelta(minutes=5)

        db.commit()
        return {"triggered": triggered}
    finally:
        db.close()


@celery_app.task(name="app.tasks.tasks.dispatch_call_now")
def dispatch_call_now(call_id: int):
    """
    Claim a single scheduled call and start it through VAPI right now.

    This is the one code path that actually performs an outbound dispatch —
    used for on-demand triggers (POST /api/calls/trigger/{id}) as well as the
    ETA-scheduled job that POST /api/calls/schedule and POST /api/calls/reschedule
    enqueue for the moment a call falls due.

    The atomic UPDATE ... WHERE status='scheduled' below means whichever path
    gets here first — this task, a duplicate enqueue of it, or the minutely
    process_pending_calls sweep — wins the claim and everyone else quietly
    no-ops, so nobody ever gets dialled twice for the same CallLog.
    """
    from app.core.config import settings
    from app.models.database import SessionLocal, CallLog, User, NewsItem
    from app.services.openai_service import generate_script
    from app.services.vapi_service import create_call

    db = SessionLocal()
    try:
        claimed = (
            db.query(CallLog)
            .filter(CallLog.id == call_id, CallLog.status == "scheduled")
            .update({"status": "in_progress", "started_at": datetime.utcnow()}, synchronize_session=False)
        )
        db.commit()
        if not claimed:
            return {"status": "skipped", "call_id": call_id, "reason": "already claimed or not scheduled"}

        call = db.query(CallLog).filter(CallLog.id == call_id).first()
        user = db.query(User).filter(User.id == call.user_id).first()

        if not user or user.status != "active":
            call.status = "cancelled"
            call.error_message = "User inactive or missing at dispatch time"
            db.commit()
            return {"status": "cancelled", "call_id": call_id}

        # Daily calls already carry a script from schedule_daily_calls; build one
        # on the fly here for on-demand / rescheduled / "call me now" calls.
        if not call.script_used:
            news_items = (
                db.query(NewsItem)
                .filter(NewsItem.is_active == True, NewsItem.city.ilike(f"%{user.city}%"))
                .order_by(NewsItem.importance_score.desc(), NewsItem.created_at.desc())
                .limit(5)
                .all()
            )
            call.script_used = generate_script(
                news_items=news_items,
                user_name=user.name,
                city=user.city,
                language=user.language,
                topics=user.topics or [],
            )
            call.news_items_delivered = [item.id for item in news_items]
            db.commit()

        try:
            result = create_call(
                phone_number=user.phone_number,
                script=call.script_used or "",
                user_name=user.name,
                language=user.language,
                call_log_id=call.id,
            )
            call.vapi_call_id = result.get("call_id")
            db.commit()
            print(f"[Task] dispatch_call_now: call {call_id} dispatched to VAPI as {call.vapi_call_id}")
            return {"status": "dispatched", "call_id": call_id, "vapi_call_id": call.vapi_call_id}

        except Exception as e:
            call.retry_count = (call.retry_count or 0) + 1
            call.error_message = str(e)
            if call.retry_count <= settings.CALL_RETRY_ATTEMPTS:
                # Hand it back to "scheduled" — the next process_pending_calls
                # sweep (every minute) will retry the claim and dispatch.
                call.status = "scheduled"
                call.scheduled_at = datetime.utcnow() + timedelta(minutes=settings.CALL_RETRY_DELAY_MINUTES)
            else:
                call.status = "failed"
            db.commit()
            print(f"[Task] dispatch_call_now: VAPI dispatch failed for call {call_id}: {e}")
            return {"status": "failed", "call_id": call_id, "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="app.tasks.tasks.handle_missed_calls", bind=True)
def handle_missed_calls(self):
    """
    Run every 30 minutes.
    Finds calls that were scheduled but never started (missed).
    Sends WhatsApp notification and auto-retries if within retry window.
    """
    from app.models.database import SessionLocal, CallLog, User
    from app.services.whatsapp_service import send_missed_call_notification

    db = SessionLocal()
    try:
        # Calls scheduled >15 min ago still in 'scheduled' state = missed
        cutoff = datetime.utcnow() - timedelta(minutes=15)
        missed_calls = (
            db.query(CallLog)
            .filter(
                CallLog.status == "scheduled",
                CallLog.scheduled_at < cutoff,
            )
            .all()
        )

        notified = 0
        for call in missed_calls:
            user = db.query(User).filter(User.id == call.user_id).first()
            if not user:
                call.status = "failed"
                continue

            call.status = "missed"

            # Send WhatsApp notification
            send_missed_call_notification(
                to_number=user.whatsapp_number or user.phone_number,
                user_name=user.name,
                language=user.language,
            )
            notified += 1

        db.commit()
        return {"missed_calls_handled": notified}
    finally:
        db.close()


@celery_app.task(name="app.tasks.tasks.reset_weekly_call_counters")
def reset_weekly_call_counters():
    """Run every Monday. Resets free tier weekly call counter."""
    from app.models.database import SessionLocal, User

    db = SessionLocal()
    try:
        count = db.query(User).filter(User.subscription_tier == "free").update(
            {"calls_this_week": 0}
        )
        db.commit()
        print(f"[Task] Reset weekly counters for {count} free users")
        return {"reset_count": count}
    finally:
        db.close()


@celery_app.task(name="app.tasks.tasks.send_breaking_news_alert")
def send_breaking_news_alert_task(news_item_id: int):
    """
    Triggered when a news item is marked is_breaking=True.
    Sends WhatsApp alert to all Premium users in the same city.
    """
    from app.models.database import SessionLocal, NewsItem, User
    from app.services.whatsapp_service import send_breaking_news_alert

    db = SessionLocal()
    try:
        item = db.query(NewsItem).filter(NewsItem.id == news_item_id).first()
        if not item:
            return

        premium_users = (
            db.query(User)
            .filter(
                User.city.ilike(f"%{item.city}%"),
                User.subscription_tier == "premium",
                User.status == "active",
            )
            .all()
        )

        sent = 0
        for user in premium_users:
            send_breaking_news_alert(
                to_number=user.whatsapp_number or user.phone_number,
                user_name=user.name,
                headline=item.title,
                city=item.city,
                language=user.language,
            )
            sent += 1

        print(f"[Task] Breaking news alerts sent to {sent} premium users in {item.city}")
        return {"alerts_sent": sent}
    finally:
        db.close()
