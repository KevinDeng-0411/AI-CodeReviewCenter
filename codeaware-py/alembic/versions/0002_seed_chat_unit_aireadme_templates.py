"""seed CHAT / UNIT_TEST / AI_README prompt templates

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29

0001 仅 seed 了 CODE_REVIEW（七层 Prompt）。本迁移补齐其余 3 类 active v1 模板，
使 4 类 PromptType 均有激活模板可用（ADR-0005：每 type 恰一激活；CHAT 纳入模板）。
否则 UNIT_TEST / AI_README 服务因 get_active 返回 None 抛 BusinessException；CHAT 退化为硬编码 fallback。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insert_sql = sa.text(
        "INSERT INTO prompt_templates "
        "(type, version, name, role_setting, template_body, review_dimensions, severity_levels, is_active) "
        "VALUES (:type, :version, :name, :role_setting, :template_body, :review_dimensions, :severity_levels, :is_active)"
    )

    bind.execute(
        insert_sql,
        {
            "type": "CHAT",
            "version": 1,
            "name": "Chat 系统提示词 v1",
            "role_setting": "你是一个知识渊博的技术助手，服务于一个开发团队。",
            "review_dimensions": None,
            "severity_levels": None,
            "is_active": True,
            "template_body": CHAT_PROMPT_BODY,
        },
    )
    bind.execute(
        insert_sql,
        {
            "type": "UNIT_TEST",
            "version": 1,
            "name": "单元测试生成模板 v1",
            "role_setting": "你是一名资深测试工程师，擅长编写高质量单元测试。",
            "review_dimensions": None,
            "severity_levels": None,
            "is_active": True,
            "template_body": UNIT_TEST_PROMPT_BODY,
        },
    )
    bind.execute(
        insert_sql,
        {
            "type": "AI_README",
            "version": 1,
            "name": "AIReadMe 生成模板 v1",
            "role_setting": "你是一名资深技术架构师，负责为项目生成 AI 友好的 README 文档。",
            "review_dimensions": None,
            "severity_levels": None,
            "is_active": True,
            "template_body": AI_README_PROMPT_BODY,
        },
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM prompt_templates WHERE type IN ('CHAT', 'UNIT_TEST', 'AI_README') AND version = 1"
    )


CHAT_PROMPT_BODY = """你是一个知识渊博的技术助手，服务于一个开发团队。请基于以下上下文回答用户的最新问题。

## 长期记忆
{{long_term_memory}}

## 相关知识库文档
{{rag_context}}

## 对话历史
{{conversation_history}}

## 用户问题
{{user_message}}

如果问题超出上下文范围，请基于你的专业知识回答。"""


UNIT_TEST_PROMPT_BODY = """你是一名资深测试工程师，擅长编写高质量单元测试。请为以下代码生成单元测试。

## 要求
1. 使用 {{test_framework}} 框架
2. 使用 Mockito 对外部依赖进行 Mock
3. 必须覆盖：正常路径、边界条件、异常场景
4. 遵循 AAA 模式（Arrange-Act-Assert）
5. 测试方法命名清晰，包含场景描述
6. 目标覆盖率 > 80%

## 源代码文件
{{file_path}}

## 源代码
{{source_code}}

## 输出格式
严格以 JSON 返回，不要输出多余解释：
```json
{
  "test_code": "完整的单元测试代码（含 import）",
  "test_framework": "实际使用的测试框架名称"
}
```"""


AI_README_PROMPT_BODY = """你是一名资深技术架构师，负责为项目生成 AI 友好的 README 文档（给 AI 编码助手作为项目上下文）。

## 项目信息
- 项目名：{{project_name}}
- 项目路径：{{project_path}}

## 要求
生成一份完整的开发文档，包含以下章节：
1. 技术架构：技术栈选型、分层设计、关键决策
2. 核心流程：业务流程序列、数据流转
3. 开发指南：环境搭建、启动命令、开发规范
4. 项目结构：模块划分、包结构、关键目录
5. 业务知识：领域术语、业务规则、实体关系
6. 历史经验：已知陷阱、调优经验、最佳实践

## 输出格式
严格以 JSON 返回，不要输出多余解释：
```json
{
  "content": "Markdown 格式的完整 README 文档"
}
```"""
