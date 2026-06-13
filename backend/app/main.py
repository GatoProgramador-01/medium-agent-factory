import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_client, create_indexes
from app.routers import analytics, pipeline, posts, series

if settings.langchain_tracing_v2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project

app = FastAPI(
    title="Medium Agent Factory",
    description="Multi-agent pipeline for automated Medium post generation",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    return {"status": "ok", "environment": settings.environment}
