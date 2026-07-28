"""枚举（对应 Java common/enums）。"""

from enum import Enum


class PromptType(str, Enum):
    """Prompt 模板类型 = 逻辑身份（ADR-0005）。"""

    CODE_REVIEW = "CODE_REVIEW"
    UNIT_TEST = "UNIT_TEST"
    AI_README = "AI_README"
    CHAT = "CHAT"


class AiOperationType(str, Enum):
    """AI 操作记录类型（ADR-0006 合并表）。"""

    CODE_REVIEW = "CODE_REVIEW"
    UNIT_TEST = "UNIT_TEST"
