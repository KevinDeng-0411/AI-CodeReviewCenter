"""FastAPI 入口 - 对应 Java AiCenterApplication + Web 配置。

P0：/health 健康检查 + 全局异常注册。后续阶段挂载 api/v1 路由。
"""

from fastapi import FastAPI

from app.api.v1.ai_health import router as ai_health_router
from app.api.v1.chat import router as chat_router
from app.api.v1.code_review import router as code_review_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.memory import router as memory_router
from app.api.v1.prompt import router as prompt_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.response import Result

app = FastAPI(
    title=settings.app_name,
    description="CodeAware - AI 驱动的研发效能平台 (Python 重构)",
    version="0.1.0",
)

register_exception_handlers(app)
app.include_router(ai_health_router)
app.include_router(code_review_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(memory_router)
app.include_router(prompt_router)


@app.get("/health", tags=["系统"])
async def health() -> Result:
    """健康检查。"""
    return Result.ok({"status": "up"})
