-- ============================================================
-- AI Center 数据库初始化脚本
-- PostgreSQL 16 + pgvector
-- 向量存储由 PgVectorEmbeddingStore 管理
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. prompt_templates — AI Prompt 模板
-- ============================================================
CREATE TABLE IF NOT EXISTS prompt_templates (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(100)  NOT NULL,
    type            VARCHAR(30)   NOT NULL,
    role_setting    TEXT          NOT NULL,
    review_dimensions TEXT,        -- 逗号分隔
    severity_levels  TEXT,         -- 逗号分隔
    template_body   TEXT          NOT NULL,
    version         INT           NOT NULL DEFAULT 1,
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 2. code_review_records — AI Code Review 记录
-- ============================================================
CREATE TABLE IF NOT EXISTS code_review_records (
    id                  BIGSERIAL PRIMARY KEY,
    project_name        VARCHAR(100)  NOT NULL,
    file_path           VARCHAR(500)  NOT NULL,
    source_code         TEXT          NOT NULL,
    review_result       TEXT          NOT NULL,
    issues_count        INT           NOT NULL DEFAULT 0,
    critical_count      INT           NOT NULL DEFAULT 0,
    warning_count       INT           NOT NULL DEFAULT 0,
    info_count          INT           NOT NULL DEFAULT 0,
    prompt_template_id  BIGINT,
    ai_model            VARCHAR(50),
    created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 3. unit_test_records — AI 单元测试生成记录
-- ============================================================
CREATE TABLE IF NOT EXISTS unit_test_records (
    id                  BIGSERIAL PRIMARY KEY,
    project_name        VARCHAR(100)  NOT NULL,
    file_path           VARCHAR(500)  NOT NULL,
    source_code         TEXT          NOT NULL,
    test_code           TEXT          NOT NULL,
    test_framework      VARCHAR(30)   NOT NULL DEFAULT 'JUnit5',
    prompt_template_id  BIGINT,
    ai_model            VARCHAR(50),
    created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. chat_conversations — 会话
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_conversations (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(64)   NOT NULL UNIQUE,
    title       VARCHAR(200),
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_session ON chat_conversations(session_id);

-- ============================================================
-- 5. chat_messages — 消息（短期记忆持久化）
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(64)   NOT NULL,
    role        VARCHAR(20)   NOT NULL,
    content     TEXT          NOT NULL,
    token_count INT           NOT NULL DEFAULT 0,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON chat_messages(session_id);

-- ============================================================
-- 6. long_term_memories — 长期记忆（元数据）
-- 向量由 PgVectorEmbeddingStore 管理，embedding 列存 UUID 反向索引
-- ============================================================
CREATE TABLE IF NOT EXISTS long_term_memories (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(64),
    content     TEXT          NOT NULL,
    memory_type VARCHAR(30)   NOT NULL,
    embedding   VARCHAR(64),   -- PGVector 嵌入的 UUID 反向索引
    metadata    TEXT,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 7. knowledge_documents — 知识文档（元数据）
-- 向量由 PgVectorEmbeddingStore 管理，embedding 列存 UUID 反向索引
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id              BIGSERIAL PRIMARY KEY,
    title           VARCHAR(300)  NOT NULL,
    content         TEXT          NOT NULL,
    chunk_index     INT           NOT NULL DEFAULT 0,
    chunk_content   TEXT          NOT NULL,
    embedding       VARCHAR(64),   -- PGVector 嵌入的 UUID 反向索引
    source_type     VARCHAR(30)   NOT NULL,
    project_name    VARCHAR(100),
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_kd_project ON knowledge_documents(project_name);

-- ============================================================
-- 8. ai_readme_documents — AIReadMe 文档
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_readme_documents (
    id            BIGSERIAL PRIMARY KEY,
    project_name  VARCHAR(100)  NOT NULL,
    section       VARCHAR(50)   NOT NULL,
    content       TEXT          NOT NULL,
    version       INT           NOT NULL DEFAULT 1,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ar_project ON ai_readme_documents(project_name);

-- ============================================================
-- 预置 CR Prompt 模板
-- ============================================================
INSERT INTO prompt_templates (name, type, role_setting, review_dimensions, severity_levels, template_body)
VALUES (
    'Java Code Review 标准模板',
    'CODE_REVIEW',
    '你是一名资深 Java 代码审查专家，拥有 10 年以上大型分布式系统开发经验。',
    '性能优化,安全性,代码质量,可维护性,异常处理,并发安全,资源管理,设计模式',
    'Critical,Warning,Info',
    '请对以下 Java 代码进行全面的 Code Review。\n\n## 评审要求\n严格按照以下 8 个维度进行审查：\n1. **性能优化**\n2. **安全性**\n3. **代码质量**\n4. **可维护性**\n5. **异常处理**\n6. **并发安全**\n7. **资源管理**\n8. **设计模式**\n\n## 问题等级\n- **Critical**：必须修复，可能导致系统故障、安全漏洞或数据丢失\n- **Warning**：建议修复，影响代码质量或存在潜在风险\n- **Info**：优化建议\n\n## 输出格式\n请以 JSON 格式返回评审结果：\n```json\n{\n  "summary": "整体评审摘要",\n  "score": 85,\n  "issues": [\n    {\n      "dimension": "性能优化",\n      "severity": "Warning",\n      "line_range": "42-45",\n      "title": "问题标题",\n      "description": "问题详细描述",\n      "suggestion": "修复建议",\n      "fix_code": "建议的修复代码片段"\n    }\n  ],\n  "highlights": ["亮点1"]\n}\n```\n\n## 待评审代码\n```java\n{{source_code}}\n```'
);
