from pydantic import BaseModel, field_validator, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


# ── Enums (mirrors database enums) ────────────────────────────────────────────

class Language(str, Enum):
    hindi = "hi"
    nepali = "ne"
    english = "en"


class UserStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    blocked = "blocked"


class SubscriptionTier(str, Enum):
    free = "free"
    basic = "basic"
    premium = "premium"
    b2b = "b2b"


class CallStatus(str, Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    missed = "missed"
    cancelled = "cancelled"


class NewsCategory(str, Enum):
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


# ── User Schemas ───────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    phone_number: str
    name: str
    city: str
    state: Optional[str] = None
    country: str = "IN"
    language: Language = Language.hindi
    preferred_call_time: str = "07:00"
    topics: List[str] = []
    whatsapp_number: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v):
        v = v.strip()
        if not v.startswith("+"):
            raise ValueError("Phone number must start with country code, e.g. +91...")
        if len(v) < 10:
            raise ValueError("Phone number too short")
        return v

    @field_validator("preferred_call_time")
    @classmethod
    def validate_time(cls, v):
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Invalid time")
        return v

    model_config = {"json_schema_extra": {"example": {
        "phone_number": "+919876543210",
        "name": "Rajesh Kumar",
        "city": "Gorakhpur",
        "state": "Uttar Pradesh",
        "language": "hi",
        "preferred_call_time": "07:00",
        "topics": ["market_prices", "crime", "local"],
    }}}


class UserUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    language: Optional[Language] = None
    preferred_call_time: Optional[str] = None
    topics: Optional[List[str]] = None
    status: Optional[UserStatus] = None
    subscription_tier: Optional[SubscriptionTier] = None


class UserResponse(BaseModel):
    id: int
    phone_number: str
    name: str
    city: str
    country: str
    language: str
    preferred_call_time: str
    topics: List[Any]
    status: str
    subscription_tier: str
    created_at: datetime
    last_call_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── News Schemas ───────────────────────────────────────────────────────────────

class NewsCreate(BaseModel):
    title: str
    summary: str
    full_content: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    city: str
    state: Optional[str] = None
    country: str = "IN"
    category: NewsCategory = NewsCategory.local
    language: Language = Language.hindi
    importance_score: int = Field(default=5, ge=1, le=10)
    is_breaking: bool = False

    model_config = {"json_schema_extra": {"example": {
        "title": "गोलघर मंडी में आलू के भाव 20% बढ़े",
        "summary": "गोरखपुर की गोलघर मंडी में आलू की कीमतें 20 रुपये प्रति किलो से बढ़कर 24 रुपये हो गई हैं।",
        "city": "Gorakhpur",
        "category": "market_prices",
        "language": "hi",
        "importance_score": 7,
    }}}


class NewsUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    full_content: Optional[str] = None
    importance_score: Optional[int] = Field(default=None, ge=1, le=10)
    is_breaking: Optional[bool] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None


class NewsResponse(BaseModel):
    id: int
    title: str
    summary: str
    city: str
    category: str
    language: str
    importance_score: int
    is_breaking: bool
    is_verified: bool
    source_name: Optional[str]
    news_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Call Schemas ───────────────────────────────────────────────────────────────

class CallScheduleRequest(BaseModel):
    user_id: int
    scheduled_at: datetime
    news_item_ids: Optional[List[int]] = None  # if None, auto-select

    model_config = {"json_schema_extra": {"example": {
        "user_id": 1,
        "scheduled_at": "2026-05-27T07:00:00",
    }}}


class RescheduleRequest(BaseModel):
    user_id: int
    original_call_id: Optional[int] = None
    requested_time: datetime
    raw_message: Optional[str] = None  # "call me in 15 minutes"


class CallLogResponse(BaseModel):
    id: int
    user_id: int
    status: str
    scheduled_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    retry_count: int
    questions_asked: List[Any]
    cost_inr: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── WhatsApp / Webhook Schemas ─────────────────────────────────────────────────

class WhatsAppMessage(BaseModel):
    """Incoming message from Twilio WhatsApp webhook."""
    From: str           # whatsapp:+919876543210
    Body: str           # message text
    To: str             # our WhatsApp number
    MessageSid: Optional[str] = None
    ProfileName: Optional[str] = None


class VAPICallEvent(BaseModel):
    """Incoming event from VAPI webhook."""
    call_id: Optional[str] = None
    type: str           # call-started, call-ended, transcript, etc.
    status: Optional[str] = None
    transcript: Optional[str] = None
    duration: Optional[int] = None
    ended_reason: Optional[str] = None


# ── Admin Schemas ──────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_users: int
    active_users: int
    calls_today: int
    calls_completed_today: int
    calls_failed_today: int
    free_users: int
    basic_users: int
    premium_users: int
    total_news_items: int
    breaking_news_count: int
    estimated_revenue_inr: float
    estimated_costs_inr: float
