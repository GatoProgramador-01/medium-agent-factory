import os
from collections.abc import Callable
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import close_client, create_indexes
from app.limiter import limiter
from app.routers import analytics, pipeline, posts, series

if settings.langchain_tracing_v2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response


app = FastAPI(
    title="Medium Agent Factory",
    description="Multi-agent pipeline for automated Medium post generation",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    cast(Any, _rate_limit_exceeded_handler),
)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.allowed_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)

app.include_router(pipeline.router)
app.include_router(posts.router)
app.include_router(analytics.router)
app.include_router(series.router)


@app.on_event("startup")
async def startup() -> None:
    await create_indexes()


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_client()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
