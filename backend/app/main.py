import sys

# Windows consoles default to a legacy code page (e.g. cp1252) that can't encode
# the emoji in our startup/shutdown log lines, which crashes the whole app with
# UnicodeEncodeError before it can bind to a port. Force UTF-8 on stdout/stderr
# so `print()` behaves the same here as it does on Linux/Docker/CI.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.models.database import create_tables
from app.api import users, news, calls, admin, webhooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 NewsBuddy AI starting up...")
    create_tables()
    print("✅ Database tables ready")
    yield
    # Shutdown
    print("👋 NewsBuddy AI shutting down...")


app = FastAPI(
    title="NewsBuddy AI",
    description="AI-Powered Hyperlocal Voice News Assistant for India & Nepal",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(news.router, prefix="/api/news", tags=["News"])
app.include_router(calls.router, prefix="/api/calls", tags=["Calls"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])


@app.get("/")
def root():
    return {"service": "NewsBuddy AI", "status": "running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "database": "connected",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }
