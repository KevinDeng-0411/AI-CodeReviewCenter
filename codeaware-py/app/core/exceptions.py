"""稳定 API 错误语义与全局处理器。"""

import logging
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.response import Result

logger = logging.getLogger(__name__)


class BusinessException(Exception):
    """可安全暴露的稳定业务错误。"""

    def __init__(
        self,
        message: str,
        code: int = 0,
        *,
        status_code: int = 400,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


_VALIDATION_CODES = (
    ("/api/code-review", "CODE_REVIEW_REQUEST_INVALID"),
    ("/api/unit-test", "UNIT_TEST_REQUEST_INVALID"),
    ("/api/ai-readme", "AI_README_REQUEST_INVALID"),
    ("/api/chat", "CHAT_REQUEST_INVALID"),
    ("/api/knowledge", "KNOWLEDGE_REQUEST_INVALID"),
    ("/api/memory", "MEMORY_REQUEST_INVALID"),
    ("/api/prompts", "PROMPT_REQUEST_INVALID"),
)


def _validation_code(path: str) -> str:
    for prefix, code in _VALIDATION_CODES:
        if path.startswith(prefix):
            return code
    return "API_REQUEST_INVALID"


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，对应 Java GlobalExceptionHandler。"""

    @app.exception_handler(BusinessException)
    async def _business_exception_handler(_: Request, exc: BusinessException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=Result.error(exc.message, exc.code).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        if request.url.path.startswith("/api/"):
            # 不回显 Pydantic detail/raw input；其中可能含源码、Prompt 或宿主路径。
            return JSONResponse(
                status_code=422,
                content=Result.error(_validation_code(request.url.path)).model_dump(),
            )
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def _unhandled_api_exception(request: Request, exc: Exception) -> JSONResponse:
        if not request.url.path.startswith("/api/"):
            raise exc
        logger.exception(
            "unhandled API error code=API_INTERNAL_ERROR path=%s type=%s",
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=Result.error("API_INTERNAL_ERROR").model_dump(),
        )
