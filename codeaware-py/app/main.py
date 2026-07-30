"""FastAPI 入口 - 对应 Java AiCenterApplication + Web 配置。

P0：/health 健康检查 + 全局异常注册。后续阶段挂载 api/v1 路由。
P5+：CORS（前端开发）+ 静态托管 frontend/dist（生产单进程）。
"""

import os
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.ai_health import router as ai_health_router
from app.api.v1.ai_readme import router as ai_readme_router
from app.api.v1.chat import router as chat_router
from app.api.v1.code_review import router as code_review_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.memory import router as memory_router
from app.api.v1.prompt import router as prompt_router
from app.api.v1.system_health import router as system_health_router
from app.api.v1.unit_test import router as unit_test_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.response import Result

app = FastAPI(
    title=settings.app_name,
    description="CodeAware - AI 驱动的研发效能平台 (Python 重构)",
    version="0.1.0",
)

# CORS：开发时 Vite 5173 跨域访问 8000；生产同源不需要（由静态托管提供）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(ai_health_router)
app.include_router(code_review_router)
app.include_router(unit_test_router)
app.include_router(ai_readme_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(memory_router)
app.include_router(prompt_router)
app.include_router(system_health_router)

if os.environ.get("CODEAWARE_BROWSER_E2E") == "1":
    stack_id = os.environ.get("CODEWARE_TEST_STACK_ID", "")
    auth = os.environ.get("CODEWARE_TEST_AUTH", "")
    project_root = os.environ.get("CODEAWARE_BROWSER_E2E_PROJECT_ROOT", "")
    if (
        os.environ.get("CODEAWARE_TESTING") != "1"
        or re.fullmatch(r"[0-9a-f]{16}", stack_id) is None
        or len(auth) < 16
        or not project_root
    ):
        raise RuntimeError("browser E2E adapter requires a disposable safe-runner stack")
    from app.testing.browser_e2e import install_browser_e2e_overrides

    install_browser_e2e_overrides(app)


@app.get("/health", tags=["系统"])
async def health() -> Result:
    """兼容入口：仅表示应用进程存活。"""
    return Result.ok({"status": "up"})


# 静态托管前端构建产物（生产单进程：访问 http://localhost:8000/ 即前端）
# dist 不存在（开发态未 build）或测试态（避免 Mount("/") 拦截运行时加的测试路由）则跳过。
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.is_dir() and not os.environ.get("CODEAWARE_TESTING"):
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
