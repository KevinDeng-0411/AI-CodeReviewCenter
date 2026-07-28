"""业务异常 + 全局处理器注册 - 对应 Java BusinessException + @RestControllerAdvice。"""

from fastapi import FastAPI, Request
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
