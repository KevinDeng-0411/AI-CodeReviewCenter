"""Memory schemas - 长期记忆抽取契约。"""

from pydantic import BaseModel, Field


class ExtractedFacts(BaseModel):
    """LLM 从对话中抽取的原子事实契约（json_mode 结构化输出）。"""

    facts: list[str] = Field(default_factory=list)
