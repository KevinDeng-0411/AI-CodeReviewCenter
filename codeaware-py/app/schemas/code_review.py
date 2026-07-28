"""Code Review schemas - 结构化输出契约 + VO（改进③，替代 Java extractJson）。

CodeReviewResult 作为 LangChain with_structured_output 的契约；
CodeReviewVO 为 API 响应视图（含计数）。字段 snake_case 对齐 Prompt 的 JSON 示例。
"""

from pydantic import BaseModel, ConfigDict


class ReviewIssue(BaseModel):
    dimension: str
    severity: str  # Critical / Warning / Info
    line_range: str
    title: str
    description: str
    suggestion: str
    fix_code: str | None = None


class CodeReviewResult(BaseModel):
    """LLM 结构化输出契约。"""

    summary: str
    score: int
    issues: list[ReviewIssue]
    highlights: list[str] = []


class CodeReviewVO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_name: str | None = None
    file_path: str | None = None
    summary: str = ""
    score: int = 0
    issues: list[ReviewIssue] = []
    highlights: list[str] = []
    issues_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    ai_model: str = "deepseek-v4-flash"
