-- ============================================================
-- AI Center 数据库初始化脚本
-- MySQL 8.0
-- 向量数据由 Pinecone 管理，此处仅存储关系数据
-- ============================================================

-- ============================================================
-- 1. prompt_templates — AI Prompt 模板
-- ============================================================
CREATE TABLE IF NOT EXISTS prompt_templates (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100)  NOT NULL,
    type            VARCHAR(30)   NOT NULL,
    role_setting    TEXT          NOT NULL,
    review_dimensions TEXT,        -- 逗号分隔的评审维度
    severity_levels  TEXT,         -- 逗号分隔的问题等级
    template_body   TEXT          NOT NULL,
    version         INT           NOT NULL DEFAULT 1,
    is_active       TINYINT(1)    NOT NULL DEFAULT 1,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 2. code_review_records — AI Code Review 记录
-- ============================================================
CREATE TABLE IF NOT EXISTS code_review_records (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
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
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
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
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id  VARCHAR(64)   NOT NULL UNIQUE,
    title       VARCHAR(200),
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id)
);

-- ============================================================
-- 5. chat_messages — 消息（短期记忆持久化）
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id  VARCHAR(64)   NOT NULL,
    role        VARCHAR(20)   NOT NULL,
    content     TEXT          NOT NULL,
    token_count INT           NOT NULL DEFAULT 0,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_msg_session (session_id),
    INDEX idx_msg_created (session_id, created_at)
);

-- ============================================================
-- 6. long_term_memories — 长期记忆
-- 向量数据已迁移至 Pinecone，embedding 列保留用于兼容
-- ============================================================
CREATE TABLE IF NOT EXISTS long_term_memories (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id  VARCHAR(64),
    content     TEXT          NOT NULL,
    memory_type VARCHAR(30)   NOT NULL,
    embedding   TEXT,           -- 向量数据已迁至 Pinecone，此列保留
    metadata    TEXT,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_memory_type (memory_type)
);

-- ============================================================
-- 7. knowledge_documents — 知识文档
-- 向量数据已迁移至 Pinecone，embedding 列保留用于兼容
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    title           VARCHAR(300)  NOT NULL,
    content         TEXT          NOT NULL,
    chunk_index     INT           NOT NULL DEFAULT 0,
    chunk_content   TEXT          NOT NULL,
    embedding       TEXT,           -- 向量数据已迁至 Pinecone，此列保留
    source_type     VARCHAR(30)   NOT NULL,
    project_name    VARCHAR(100),
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_knowledge_project (project_name),
    INDEX idx_knowledge_source (source_type)
);

-- ============================================================
-- 8. ai_readme_documents — AIReadMe 文档
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_readme_documents (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    project_name  VARCHAR(100)  NOT NULL,
    section       VARCHAR(50)   NOT NULL,
    content       TEXT          NOT NULL,
    version       INT           NOT NULL DEFAULT 1,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ai_readme_project (project_name)
);

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
