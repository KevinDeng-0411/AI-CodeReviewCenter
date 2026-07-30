"""业务异常 + 全局处理器注册 - 对应 Java BusinessException + @RestControllerAdvice。"""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.response import Result


class BusinessException(Exception):
    """业务异常。code=0 表示常规业务错误。"""

    def __init__(self, message: str, code: int = 0) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，对应 Java GlobalExceptionHandler。"""

    @app.exception_handler(BusinessException)
    async def _business_exception_handler(_: Request, exc: BusinessException) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=Result.error(exc.message, exc.code).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        if request.url.path == "/api/ai-readme/generate":
            # project_path 属于宿主路径；默认 422 detail 会回显 raw input。
            return JSONResponse(
                status_code=422,
                content=Result.error("AI_README_REQUEST_INVALID").model_dump(),
            )
        if request.url.path not in {"/api/chat/send", "/api/chat/send/stream"}:
            return await request_validation_exception_handler(request, exc)
        # Chat 不回显 raw input 或 Pydantic detail，统一为稳定、可冻结的错误 envelope。
        return JSONResponse(
            status_code=422,
            content=Result.error("CHAT_REQUEST_INVALID").model_dump(),
        )
