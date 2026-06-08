from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.models.database import get_db, User, CallLog, RescheduleRequest as RescheduleModel
from app.models.schemas import CallScheduleRequest, RescheduleRequest, CallLogResponse
from app.tasks.tasks import dispatch_call_now

router = APIRouter()


@router.post("/schedule", response_model=CallLogResponse, status_code=201)
def schedule_call(
    req: CallScheduleRequest,
    db: Session = Depends(get_db),
):
    """Schedule a call for a user at a specific time."""
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != "active":
        raise HTTPException(status_code=400, detail="User account is not active")

    # Check free tier weekly limit
    if user.subscription_tier == "free":
        from app.core.config import settings
        if user.calls_this_week >= settings.FREE_TIER_CALLS_PER_WEEK:
            raise HTTPException(
                status_code=429,
                detail=f"Free tier limit reached ({settings.FREE_TIER_CALLS_PER_WEEK} calls/week). Upgrade to continue."
            )

    call = CallLog(
        user_id=req.user_id,
        scheduled_at=req.scheduled_at,
        news_items_delivered=req.news_item_ids or [],
        status="scheduled",
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    # Hand off to Celery: dispatch_call_now will fire at scheduled_at, claim the
    # call, build its script if it doesn't have one yet, and start it via VAPI.
    # If the broker is briefly unreachable we don't fail the request — the
    # minutely process_pending_calls beat job acts as a fallback sweep.
    try:
        dispatch_call_now.apply_async(args=[call.id], eta=req.scheduled_at)
    except Exception as e:
        print(f"[Calls] Failed to enqueue dispatch for call {call.id}, "
              f"relying on process_pending_calls fallback: {e}")

    return call


@router.post("/reschedule", status_code=201)
def reschedule_call(req: RescheduleRequest, db: Session = Depends(get_db)):
    """
    Handle 'call me in 15 minutes' requests from WhatsApp.
    Creates a new CallLog at the requested time.
    """
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Save reschedule request
    reschedule = RescheduleModel(
        user_id=req.user_id,
        original_call_id=req.original_call_id,
        requested_time=req.requested_time,
        raw_message=req.raw_message,
    )
    db.add(reschedule)

    # Create new call log for the rescheduled time
    new_call = CallLog(
        user_id=req.user_id,
        scheduled_at=req.requested_time,
        status="scheduled",
    )
    db.add(new_call)
    db.commit()
    db.refresh(new_call)

    reschedule.is_processed = True
    reschedule.processed_at = datetime.utcnow()
    db.commit()

    # Same hand-off as /schedule — dispatch_call_now will claim and run this
    # call through VAPI at the newly requested time.
    try:
        dispatch_call_now.apply_async(args=[new_call.id], eta=req.requested_time)
    except Exception as e:
        print(f"[Calls] Failed to enqueue dispatch for rescheduled call {new_call.id}: {e}")

    return {
        "message": "Call rescheduled",
        "new_call_id": new_call.id,
        "scheduled_at": new_call.scheduled_at.isoformat(),
    }


@router.get("/logs", response_model=List[CallLogResponse])
def get_call_logs(
    user_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get call history. Filter by user, status, or date range."""
    q = db.query(CallLog)
    if user_id:
        q = q.filter(CallLog.user_id == user_id)
    if status:
        q = q.filter(CallLog.status == status)
    if date_from:
        q = q.filter(CallLog.scheduled_at >= date_from)
    return q.order_by(CallLog.scheduled_at.desc()).offset(skip).limit(limit).all()


@router.get("/logs/{call_id}", response_model=CallLogResponse)
def get_call_log(call_id: int, db: Session = Depends(get_db)):
    call = db.query(CallLog).filter(CallLog.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call log not found")
    return call


@router.post("/trigger/{call_id}")
def trigger_call_now(call_id: int, db: Session = Depends(get_db)):
    """
    Manually trigger a scheduled call immediately — dispatches to Celery, which
    claims the call, builds its script if needed, and starts it via VAPI.
    """
    call = db.query(CallLog).filter(CallLog.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if call.status not in ("scheduled",):
        raise HTTPException(status_code=400, detail=f"Cannot trigger call with status: {call.status}")

    try:
        dispatch_call_now.delay(call.id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not reach the task queue: {e}")

    # Status stays "scheduled" here — dispatch_call_now claims it and flips it
    # to "in_progress" the moment the worker picks it up (usually within seconds).
    return {"message": "Call dispatch queued — it will start within moments", "call_id": call_id, "status": call.status}


@router.post("/schedule-daily")
def schedule_daily_calls(db: Session = Depends(get_db)):
    """
    Bulk-schedule today's calls for all active users.
    Called by Celery beat at ~5:30 AM daily.
    """
    from datetime import date
    today = date.today()
    active_users = db.query(User).filter(User.status == "active").all()

    scheduled = 0
    skipped = 0

    for user in active_users:
        # Skip free users who've hit weekly limit
        if user.subscription_tier == "free" and user.calls_this_week >= 3:
            skipped += 1
            continue

        # Parse preferred time
        try:
            h, m = map(int, user.preferred_call_time.split(":"))
        except Exception:
            h, m = 7, 0

        call_time = datetime.combine(today, datetime.min.time().replace(hour=h, minute=m))

        # Avoid duplicate scheduling
        existing = db.query(CallLog).filter(
            CallLog.user_id == user.id,
            CallLog.scheduled_at == call_time,
        ).first()
        if existing:
            skipped += 1
            continue

        call = CallLog(user_id=user.id, scheduled_at=call_time, status="scheduled")
        db.add(call)
        scheduled += 1

    db.commit()
    return {"scheduled": scheduled, "skipped": skipped, "total_users": len(active_users)}
