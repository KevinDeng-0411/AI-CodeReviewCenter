"""统一响应 - 对应 Java Result / PageResult。

成功 code=1，失败 code=0（与 Java 版 README 示例一致）。
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    code: int = 1
    msg: str = "success"
    data: T | None = None

    @classmethod
    def ok(cls, data: Any = None) -> "Result":
        return cls(code=1, msg="success", data=data)

    @classmethod
    def error(cls, msg: str, code: int = 0) -> "Result":
        return cls(code=code, msg=msg, data=None)


class PageResult(BaseModel, Generic[T]):
    total: int
    page: int
    size: int
    records: list[T]
