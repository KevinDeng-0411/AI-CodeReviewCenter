"""UnitTest schemas。"""

from pydantic import BaseModel


class UnitTestResult(BaseModel):
    """LLM 结构化输出契约。"""

    test_code: str
    test_framework: str


class UnitTestRequest(BaseModel):
    project_name: str
    file_path: str
    source_code: str
    test_framework: str = "JUnit5"


class UnitTestVO(BaseModel):
    id: int | None = None
    project_name: str | None = None
    file_path: str | None = None
    test_code: str
    test_framework: str = "JUnit5"
    ai_model: str = "deepseek-v4-flash"
