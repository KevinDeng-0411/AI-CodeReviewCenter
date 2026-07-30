"""UnitTest request/result/response schemas。"""

from pydantic import BaseModel, Field, field_validator

from app.core.enums import TestFramework


class UnitTestResult(BaseModel):
    """LLM 结构化输出契约。"""

    test_code: str = Field(min_length=1)
    test_framework: TestFramework


class UnitTestRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=100)
    file_path: str = Field(min_length=1, max_length=500)
    source_code: str = Field(min_length=1, max_length=100_000)
    test_framework: TestFramework = TestFramework.JUNIT5

    @field_validator("project_name", "file_path")
    @classmethod
    def strip_nonblank_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("source_code")
    @classmethod
    def source_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_code must not be blank")
        return value


class UnitTestVO(BaseModel):
    id: int | None = None
    project_name: str | None = None
    file_path: str | None = None
    test_code: str
    test_framework: TestFramework = TestFramework.JUNIT5
    ai_model: str = "deepseek-v4-flash"
