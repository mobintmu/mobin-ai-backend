import ipaddress
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.routes import router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.metrics import ACTIVE_KNOWLEDGE, API_DURATION, API_REQUESTS
from app.core.security import client_ip
from app.persistence.database import engine, session_factory
from app.persistence.models import KnowledgeRelease, SecurityEvent
from app.providers.embeddings import EmbeddingGateway
from app.providers.gateway import FakeGateway, HttpGateway
from app.providers.turnstile import FakeTurnstile, HttpTurnstile
from app.rag.retrieval import GraphIndex, Retriever
from app.rag.service import RagService

settings = get_settings()
logger = logging.getLogger("mobin_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        app.state.settings = settings
        app.state.turnstile = (
            FakeTurnstile()
            if settings.app_env in ("local", "test")
            else HttpTurnstile(settings, client)
        )
        app.state.gateway = (
            FakeGateway()
            if settings.app_env in ("local", "test")
            else HttpGateway(settings, client)
        )
        app.state.rag_service = None
        try:
            async with session_factory() as session:
                release = await session.scalar(
                    select(KnowledgeRelease).where(KnowledgeRelease.active.is_(True))
                )
            if release:
                graph = GraphIndex.load(
                    settings.knowledge_root / release.version / "graph.json", release.version
                )
                embeddings = (
                    EmbeddingGateway(settings, client)
                    if settings.embedding_base_url
                    and settings.embedding_api_key
                    and settings.embedding_model
                    else None
                )
                app.state.rag_service = RagService(
                    session_factory, settings, Retriever(graph, embeddings), app.state.gateway
                )
                ACTIVE_KNOWLEDGE.labels(version=release.version).set(1)
        except Exception as exc:
            logger.error(
                json.dumps({"event": "knowledge_startup_failed", "error_class": type(exc).__name__})
            )
        yield
    await engine.dispose()


app = FastAPI(
    title="Mobin AI API",
    version="1.0.0",
    description=(
        "Scoped 100-question GraphRAG API. Register, exchange the one-time grant, "
        "then authorize with the returned bearer token."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.include_router(router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4()
    peer = request.client.host if request.client else "127.0.0.1"
    try:
        request.state.client_ip, request.state.ip_source = client_ip(
            peer, request.headers.get("X-Forwarded-For"), settings
        )
    except ValueError:
        request.state.client_ip, request.state.ip_source = str(ipaddress.ip_address(peer)), "socket"
    started = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    route_name = route.path if route else "unmatched"
    duration = time.perf_counter() - started
    API_REQUESTS.labels(request.method, route_name, str(response.status_code)).inc()
    API_DURATION.labels(request.method, route_name).observe(duration)
    if response.status_code >= 400 and request.url.path.startswith("/api/v1/"):
        try:
            async with session_factory() as session:
                session.add(
                    SecurityEvent(
                        id=uuid.uuid4(),
                        request_id=request.state.request_id,
                        client_ip=request.state.client_ip,
                        ip_source=request.state.ip_source,
                        status_code=response.status_code,
                        reason=f"http_{response.status_code}",
                    )
                )
                await session.commit()
        except Exception:
            logger.error(
                json.dumps(
                    {
                        "request_id": str(request.state.request_id),
                        "event": "security_event_write_failed",
                    }
                )
            )
    logger.info(
        json.dumps(
            {
                "request_id": str(request.state.request_id),
                "method": request.method,
                "route": route_name,
                "status": response.status_code,
                "duration_ms": round(duration * 1000),
            }
        )
    )
    response.headers["X-Request-ID"] = str(request.state.request_id)
    return response


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": str(request.state.request_id),
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "Request validation failed",
            "request_id": str(request.state.request_id),
            "details": [
                {"field": ".".join(map(str, item["loc"])), "message": item["msg"]}
                for item in exc.errors()
            ],
        },
    )


@app.get("/health/live", tags=["Health"])
async def live():
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
async def ready(request: Request):
    if not request.app.state.rag_service:
        raise AppError(503, "knowledge_unavailable", "No valid active knowledge release")
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
            active = await session.scalar(
                select(KnowledgeRelease.version).where(KnowledgeRelease.active.is_(True))
            )
    except SQLAlchemyError as exc:
        raise AppError(503, "database_unavailable", "Database is not ready") from exc
    loaded = request.app.state.rag_service.retriever.graph.version
    if active != loaded:
        raise AppError(503, "knowledge_stale", "API must reload the active knowledge release")
    return {"status": "ready", "knowledge_version": loaded}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception):
    logger.error(
        json.dumps({"request_id": str(request.state.request_id), "error_class": type(exc).__name__})
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "An internal error occurred",
            "request_id": str(request.state.request_id),
        },
    )
