"""Code Review schemas - 结构化输出契约 + VO（改进③，替代 Java extractJson）。

CodeReviewResult 作为 LangChain with_structured_output 的契约；
CodeReviewVO 为 API 响应视图（含计数）。字段 snake_case 对齐 Prompt 的 JSON 示例。
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CodeReviewRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=100)
    file_path: str = Field(min_length=1, max_length=500)
    source_code: str = Field(min_length=1, max_length=100_000)
    prompt_template_id: int | None = Field(default=None, gt=0)

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


class ReviewIssue(BaseModel):
    dimension: str = Field(min_length=1)
    severity: str = Field(min_length=1)  # Critical / Warning / Info
    line_range: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)
    fix_code: str | None = None


class CodeReviewResult(BaseModel):
    """LLM 结构化输出契约。"""

    summary: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    issues: list[ReviewIssue]
    highlights: list[str] = Field(default_factory=list)


class CodeReviewVO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_name: str | None = None
    file_path: str | None = None
    summary: str = ""
    score: int = 0
    issues: list[ReviewIssue] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    issues_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    ai_model: str = "deepseek-v4-flash"


def _extract_json(text: str) -> str:
    """从 LLM 文本中提取 JSON（兼容 ```json 代码块 / 裸 JSON）。"""
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text.strip()
