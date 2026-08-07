"""Application liveness and dependency readiness endpoints."""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.response import Result
from app.db.redis import redis_client
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["系统"])
_READINESS_TIMEOUT_SECONDS = 2.0


async def _check_postgres() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _check_redis() -> None:
    await redis_client.ping()


async def _check_ollama() -> None:
    async with httpx.AsyncClient(timeout=_READINESS_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
        response.raise_for_status()


async def _check_deepseek() -> None:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY not configured")
    async with httpx.AsyncClient(timeout=_READINESS_TIMEOUT_SECONDS) as client:
        response = await client.get(
            f"{settings.llm_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        )
        response.raise_for_status()


async def _bounded(check) -> str:
    try:
        async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
            await check()
        return "up"
    except Exception:  # noqa: BLE001 - readiness must return a sanitized aggregate
        return "down"


@router.get("/live")
async def liveness() -> Result:
    """Process-only liveness; does not contact dependencies."""
    return Result.ok({"status": "up"})


@router.get("/ready")
async def readiness():
    """Strict PG/Redis/Ollama readiness without exposing dependency errors."""
    postgres, redis, ollama, deepseek = await asyncio.gather(
        _bounded(_check_postgres),
        _bounded(_check_redis),
        _bounded(_check_ollama),
        _bounded(_check_deepseek),
    )
    checks = {"postgres": postgres, "redis": redis, "ollama": ollama, "deepseek": deepseek}
    ready = all(value == "up" for value in checks.values())
    payload = Result(
        code=1 if ready else 0,
        msg="success" if ready else "not ready",
        data={"status": "ready" if ready else "not_ready", "checks": checks},
    )
    if ready:
        return payload
    return JSONResponse(status_code=503, content=payload.model_dump())
