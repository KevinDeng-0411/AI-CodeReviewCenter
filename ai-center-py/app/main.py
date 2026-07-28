"""FastAPI 入口 - 对应 Java AiCenterApplication + Web 配置。

P0：/health 健康检查 + 全局异常注册。后续阶段挂载 api/v1 路由。
"""

from fastapi import FastAPI

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.response import Result

app = FastAPI(
    title=settings.app_name,
    description="AI Center - AI 驱动的研发效能平台 (Python 重构)",
    version="0.1.0",
)

register_exception_handlers(app)


@app.get("/health", tags=["系统"])
async def health() -> Result:
    """健康检查。"""
    return Result.ok({"status": "up"})
