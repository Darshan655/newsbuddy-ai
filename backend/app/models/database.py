from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime,
    Float, Text, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func
import enum

from app.core.config import settings

Base = declarative_base()
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Enums ──────────────────────────────────────────────────────────────────────

class LanguageEnum(str, enum.Enum):
    hindi = "hi"
    nepali = "ne"
    english = "en"


class UserStatusEnum(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    blocked = "blocked"


class SubscriptionTierEnum(str, enum.Enum):
    free = "free"
    basic = "basic"
    premium = "premium"
    b2b = "b2b"


class CallStatusEnum(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    missed = "missed"
    cancelled = "cancelled"


class NewsCategory(str, enum.Enum):
    local = "local"
    crime = "crime"
    accident = "accident"
    market_prices = "market_prices"
    real_estate = "real_estate"
    government = "government"
    transport = "transport"
    weather = "weather"
    business = "business"
    national = "national"


# ── Models ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    whatsapp_number = Column(String(20), nullable=True)
    name = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=True)
    country = Column(String(10), default="IN")  # IN or NP
    language = Column(SAEnum(LanguageEnum), default=LanguageEnum.hindi)
    preferred_call_time = Column(String(5), default="07:00")  # HH:MM
    timezone = Column(String(50), default="Asia/Kolkata")
    topics = Column(JSON, default=list)  # ["market_prices", "crime", ...]
    status = Column(SAEnum(UserStatusEnum), default=UserStatusEnum.active)
    subscription_tier = Column(SAEnum(SubscriptionTierEnum), default=SubscriptionTierEnum.free)
    calls_this_week = Column(Integer, default=0)
    week_reset_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_call_at = Column(DateTime, nullable=True)

    # Relationships
    call_logs = relationship("CallLog", back_populates="user")
    reschedule_requests = relationship("RescheduleRequest", back_populates="user")

    def __repr__(self):
        return f"<User {self.name} ({self.phone_number}) - {self.city}>"


class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=False)
    full_content = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=True)
    source_name = Column(String(200), nullable=True)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=True)
    country = Column(String(10), default="IN")
    category = Column(SAEnum(NewsCategory), default=NewsCategory.local)
    language = Column(SAEnum(LanguageEnum), default=LanguageEnum.hindi)
    importance_score = Column(Integer, default=5)  # 1-10
    is_breaking = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    news_date = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<NewsItem {self.title[:50]} - {self.city}>"


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    call_sid = Column(String(100), nullable=True)       # Exotel / Twilio call ID
    vapi_call_id = Column(String(100), nullable=True)   # VAPI call ID (if used)
    status = Column(SAEnum(CallStatusEnum), default=CallStatusEnum.scheduled, index=True)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    news_items_delivered = Column(JSON, default=list)   # list of news item IDs
    script_used = Column(Text, nullable=True)
    questions_asked = Column(JSON, default=list)        # [{question, answer, timestamp}]
    user_feedback = Column(Integer, nullable=True)      # 1-5 rating
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    cost_inr = Column(Float, nullable=True)             # approximate call cost
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="call_logs")
    reschedule_request = relationship("RescheduleRequest", back_populates="original_call", uselist=False)

    def __repr__(self):
        return f"<CallLog user={self.user_id} status={self.status} at={self.scheduled_at}>"


class RescheduleRequest(Base):
    __tablename__ = "reschedule_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_call_id = Column(Integer, ForeignKey("call_logs.id"), nullable=True)
    requested_time = Column(DateTime, nullable=False)
    reason = Column(String(500), nullable=True)         # "call me in 15 minutes"
    raw_message = Column(String(500), nullable=True)    # original WhatsApp message
    is_processed = Column(Boolean, default=False)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="reschedule_requests")
    original_call = relationship("CallLog", back_populates="reschedule_request")

    def __repr__(self):
        return f"<RescheduleRequest user={self.user_id} at={self.requested_time}>"


class AdSponsor(Base):
    """Local business sponsors — 10-second ad read at end of calls."""
    __tablename__ = "ad_sponsors"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String(200), nullable=False)
    contact_phone = Column(String(20), nullable=True)
    city = Column(String(100), nullable=False, index=True)
    ad_script = Column(Text, nullable=False)            # 10-second read text
    language = Column(SAEnum(LanguageEnum), default=LanguageEnum.hindi)
    monthly_fee_inr = Column(Integer, default=5000)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<AdSponsor {self.business_name} - {self.city}>"


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_db():
    """FastAPI dependency to get a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
