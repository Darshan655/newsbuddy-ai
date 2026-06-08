from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date

from app.models.database import get_db, User, NewsItem, CallLog
from app.models.schemas import DashboardStats
from app.core.config import settings

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Admin dashboard overview.
    Returns user counts, call stats for today, and revenue estimate.
    """
    today_start = datetime.combine(date.today(), datetime.min.time())

    # User stats
    total_users = db.query(func.count(User.id)).scalar()
    active_users = db.query(func.count(User.id)).filter(User.status == "active").scalar()
    free_users = db.query(func.count(User.id)).filter(User.subscription_tier == "free").scalar()
    basic_users = db.query(func.count(User.id)).filter(User.subscription_tier == "basic").scalar()
    premium_users = db.query(func.count(User.id)).filter(User.subscription_tier == "premium").scalar()

    # Call stats today
    calls_today = db.query(func.count(CallLog.id)).filter(CallLog.scheduled_at >= today_start).scalar()
    calls_completed = db.query(func.count(CallLog.id)).filter(
        CallLog.scheduled_at >= today_start, CallLog.status == "completed"
    ).scalar()
    calls_failed = db.query(func.count(CallLog.id)).filter(
        CallLog.scheduled_at >= today_start, CallLog.status == "failed"
    ).scalar()

    # News stats
    total_news = db.query(func.count(NewsItem.id)).filter(NewsItem.is_active == True).scalar()
    breaking_news = db.query(func.count(NewsItem.id)).filter(
        NewsItem.is_active == True, NewsItem.is_breaking == True
    ).scalar()

    # Revenue estimate (monthly)
    estimated_revenue = (
        basic_users * settings.BASIC_PLAN_PRICE
        + premium_users * settings.PREMIUM_PLAN_PRICE
    )
    # Cost: ₹112/user/month (from business report)
    estimated_costs = active_users * 112

    return DashboardStats(
        total_users=total_users or 0,
        active_users=active_users or 0,
        calls_today=calls_today or 0,
        calls_completed_today=calls_completed or 0,
        calls_failed_today=calls_failed or 0,
        free_users=free_users or 0,
        basic_users=basic_users or 0,
        premium_users=premium_users or 0,
        total_news_items=total_news or 0,
        breaking_news_count=breaking_news or 0,
        estimated_revenue_inr=float(estimated_revenue or 0),
        estimated_costs_inr=float(estimated_costs or 0),
    )


@router.get("/users-by-city")
def users_by_city(db: Session = Depends(get_db)):
    """Breakdown of active users per city. Useful for ad sponsor targeting."""
    results = (
        db.query(User.city, func.count(User.id).label("count"))
        .filter(User.status == "active")
        .group_by(User.city)
        .order_by(func.count(User.id).desc())
        .all()
    )
    return [{"city": r.city, "users": r.count} for r in results]


@router.get("/call-success-rate")
def call_success_rate(db: Session = Depends(get_db)):
    """7-day call success rate breakdown."""
    from datetime import timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)

    total = db.query(func.count(CallLog.id)).filter(CallLog.scheduled_at >= week_ago).scalar() or 1
    completed = db.query(func.count(CallLog.id)).filter(
        CallLog.scheduled_at >= week_ago, CallLog.status == "completed"
    ).scalar() or 0
    failed = db.query(func.count(CallLog.id)).filter(
        CallLog.scheduled_at >= week_ago, CallLog.status == "failed"
    ).scalar() or 0
    missed = db.query(func.count(CallLog.id)).filter(
        CallLog.scheduled_at >= week_ago, CallLog.status == "missed"
    ).scalar() or 0

    return {
        "period": "last_7_days",
        "total_calls": total,
        "completed": completed,
        "failed": failed,
        "missed": missed,
        "success_rate_pct": round(completed / total * 100, 1),
    }
