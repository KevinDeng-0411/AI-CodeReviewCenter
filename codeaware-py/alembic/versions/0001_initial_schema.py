"""initial schema - 8 tables

Revision ID: 0001
Revises:
Create Date: 2026-07-28

遵循 ADR-0001~0007：
- 内联 pgvector Vector(1024)（消除 UUID 反查）
- Knowledge 拆 documents + knowledge_chunks 父子（ADR-0002）
- CR/UT 合并 ai_operation_records（ADR-0006）
- conversation_id 命名 + conversations.summary（ADR-0003/0004）
- prompt_templates 版本化 + 每 type 恰一激活 partial unique（ADR-0005）
- pg_trgm + HNSW 索引（ADR-0001 改进②）
- seed 七层 CR Prompt 为 CODE_REVIEW active v1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === 扩展 ===
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # === 1. prompt_templates（ADR-0005）===
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role_setting", sa.Text, nullable=False),
        sa.Column("template_body", sa.Text, nullable=False),
        sa.Column("review_dimensions", sa.String(255), nullable=True),
        sa.Column("severity_levels", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "uq_prompt_templates_type_active",
        "prompt_templates",
        ["type"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    # === 2. conversations（ADR-0004 + ADR-0003 summary）===
    op.create_table(
        "conversations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # === 3. messages（FK -> conversations.conversation_id, CASCADE）===
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    # === 4. documents（父，ADR-0002）===
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("project_name", sa.String(100), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # === 5. knowledge_chunks（子，FK -> documents.id CASCADE，内联 Vector）===
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            sa.BigInteger,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_kc_document_id", "knowledge_chunks", ["document_id"])
    op.create_index(
        "ix_kc_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_kc_chunk_content_trgm",
        "knowledge_chunks",
        ["chunk_content"],
        postgresql_using="gin",
        postgresql_ops={"chunk_content": "gin_trgm_ops"},
    )

    # === 6. long_term_memories（内联 Vector，ADR-0001）===
    op.create_table(
        "long_term_memories",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(64), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("memory_type", sa.String(30), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ltm_conversation_id", "long_term_memories", ["conversation_id"])
    op.create_index(
        "ix_ltm_embedding_hnsw",
        "long_term_memories",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # === 7. ai_operation_records（合并 CR/UT，ADR-0006）===
    op.create_table(
        "ai_operation_records",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("project_name", sa.String(100), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("source_code", sa.Text, nullable=False),
        sa.Column("result", sa.Text, nullable=False),
        sa.Column("prompt_template_id", sa.BigInteger, sa.ForeignKey("prompt_templates.id"), nullable=True),
        sa.Column("ai_model", sa.String(50), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # === 8. ai_readme_documents（不变）===
    op.create_table(
        "ai_readme_documents",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_name", sa.String(100), nullable=False),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ard_project_name", "ai_readme_documents", ["project_name"])

    # === seed：七层 CR Prompt = CODE_REVIEW active v1（init.sql:129-137 原样）===
    op.get_bind().execute(
        sa.text(
            "INSERT INTO prompt_templates "
            "(type, version, name, role_setting, template_body, review_dimensions, severity_levels, is_active) "
            "VALUES (:type, :version, :name, :role_setting, :template_body, :review_dimensions, :severity_levels, :is_active)"
        ),
        {
            "type": "CODE_REVIEW",
            "version": 1,
            "name": "Java Code Review 专家模板 v2",
            "role_setting": "你是一名 Java 资深架构师兼技术专家，拥有 10 年以上大型分布式系统开发经验。"
            "你擅长发现代码中的安全漏洞、性能瓶颈、设计缺陷和可维护性问题。"
            "你的评审意见必须客观、建设性、可落地。",
            "review_dimensions": "代码质量,安全性,可维护性,架构设计,Java最佳实践,数据库,测试,性能",
            "severity_levels": "Critical,Warning,Info",
            "is_active": True,
            "template_body": CR_PROMPT_BODY,
        },
    )


def downgrade() -> None:
    op.drop_table("ai_readme_documents")
    op.drop_table("ai_operation_records")
    op.drop_table("long_term_memories")
    op.drop_table("knowledge_chunks")
    op.drop_table("documents")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("prompt_templates")
    # 扩展保留（可能被其他库使用）


CR_PROMPT_BODY = '''你是一名 Java 资深架构师兼技术专家。请对以下代码进行专业的 Code Review。

## 一、评审原则
- **客观性**：基于技术标准，避免主观偏见
- **建设性**：每个问题必须附带具体可行的改进方案
- **完整性**：覆盖功能、安全、性能、可维护性等多个维度
- **优先级明确**：Critical > Warning > Info，先列严重的

## 二、评审流程
1. 理解代码意图和业务目标
2. 分析实现方案和技术细节
3. 识别问题：逻辑错误、边界条件、并发安全、资源泄漏、空指针
4. 识别隐患：数据库效率、内存使用、算法复杂度
5. 评估质量：可读性、可维护性、代码重复、命名规范
6. 提供改进建议和替代方案

## 三、问题分级标准
- 🔴 **Critical（必须修复）**：安全漏洞、严重性能问题、数据一致性、线程安全、空指针、资源泄漏
- 🟡 **Warning（建议修复）**：代码质量问题、潜在性能隐患、可维护性问题、异常处理不当
- 🔵 **Info（优化建议）**：代码风格改进、最佳实践建议、设计模式优化、测试覆盖不足

## 四、评审维度检查清单

### 1. 代码质量
- 逻辑清晰易于理解 / 遵循编码规范 / 方法职责单一 / 无明显性能缺陷 / 错误处理完整 / 注释恰当

### 2. 安全性
- 输入验证完整 / 权限控制正确 / 敏感数据加密脱敏 / SQL注入防护 / XSS/CSRF防护 / 日志不含敏感信息

### 3. 可维护性
- 高内聚低耦合 / 设计模式合理 / 命名见名知意 / 避免重复代码 / 易于扩展修改

### 4. 架构设计
- 符合分层架构 / 模块边界清晰 / 接口设计简洁 / 依赖关系合理

### 5. Java 最佳实践
- Spring 框架最佳实践 / 注解和依赖注入正确 / 异常处理完善 / 线程安全 / 避免 NPE / 资源管理得当

### 6. 数据库
- SQL 性能优化（避免 N+1） / 索引使用合理 / 事务边界清晰 / 分页查询优化

### 7. 测试
- 核心逻辑有单测覆盖 / 包含正常和异常场景 / Mock 使用恰当 / 测试数据管理规范

### 8. 性能
- 时间复杂度分析 / 缓存策略合理 / 批量操作优化 / 异步处理适当

## 五、特殊场景处理
- **遗留代码**：重点关注新增修改部分，不对历史代码过度要求
- **紧急修复**：优先关注功能正确性和安全性
- **重构代码**：重点评估架构设计和向后兼容性
- **新功能**：全面评估设计合理性和可扩展性

## 六、输出格式
严格以 JSON 格式返回，每个问题必须包含以下字段：
```json
{
  "summary": "评审概览：变更意图和整体评价",
  "score": 85,
  "issues": [
    {
      "dimension": "安全性",
      "severity": "Critical",
      "line_range": "42-45",
      "title": "SQL注入漏洞 - 字符串拼接构造查询",
      "description": "使用 + 运算符拼接用户输入直接构造 SQL，攻击者可注入恶意代码",
      "suggestion": "使用 PreparedStatement 参数化查询，将用户输入作为参数绑定",
      "fix_code": "String sql = \\"SELECT * FROM users WHERE name = ?\\";\\nPreparedStatement ps = conn.prepareStatement(sql);\\nps.setString(1, userName);"
    }
  ],
  "highlights": ["值得肯定的代码亮点"]
}
```

**输出要求**：
- 按优先级组织：先 Critical，再 Warning，最后 Info
- 每个问题的 fix_code 必须是可直接使用的代码片段
- score 评分标准：0-40 严重问题较多，40-60 有明显改进空间，60-80 总体良好，80-100 优秀

## 七、评审职责界限
- ✅ 识别问题和风险、提供改进建议、解释技术原理
- ❌ 不要直接修改代码、不要替代人工最终确认

## 待评审代码
```java
{{source_code}}
```'''
