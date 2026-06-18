-- ============================================================
-- AI Center 数据库初始化脚本
-- PostgreSQL 16 + pgvector
-- ============================================================

-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. prompt_templates — AI Prompt 模板
-- ============================================================
CREATE TABLE IF NOT EXISTS prompt_templates (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(100)  NOT NULL,
    type            VARCHAR(30)   NOT NULL CHECK (type IN ('CODE_REVIEW', 'UNIT_TEST', 'AI_README', 'CHAT')),
    role_setting    TEXT          NOT NULL,
    review_dimensions TEXT[],     -- 评审维度数组（8项）
    severity_levels  TEXT[],      -- 问题等级：Critical/Warning/Info
    template_body   TEXT          NOT NULL,
    version         INT           NOT NULL DEFAULT 1,
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE prompt_templates IS 'Prompt 模板表';
COMMENT ON COLUMN prompt_templates.type IS '模板类型：CODE_REVIEW/UNIT_TEST/AI_README/CHAT';
COMMENT ON COLUMN prompt_templates.review_dimensions IS '评审维度数组';
COMMENT ON COLUMN prompt_templates.severity_levels IS '问题严重等级';

-- ============================================================
-- 2. code_review_records — AI Code Review 记录
-- ============================================================
CREATE TABLE IF NOT EXISTS code_review_records (
    id                  BIGSERIAL PRIMARY KEY,
    project_name        VARCHAR(100)  NOT NULL,
    file_path           VARCHAR(500)  NOT NULL,
    source_code         TEXT          NOT NULL,
    review_result       TEXT          NOT NULL DEFAULT '{}',
    issues_count        INT           NOT NULL DEFAULT 0,
    critical_count      INT           NOT NULL DEFAULT 0,
    warning_count       INT           NOT NULL DEFAULT 0,
    info_count          INT           NOT NULL DEFAULT 0,
    prompt_template_id  BIGINT        REFERENCES prompt_templates(id),
    ai_model            VARCHAR(50),
    created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE code_review_records IS 'AI Code Review 记录';
COMMENT ON COLUMN code_review_records.review_result IS '结构化评审结果 JSON';
COMMENT ON COLUMN code_review_records.source_code IS '原始待评审代码';

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
    prompt_template_id  BIGINT        REFERENCES prompt_templates(id),
    ai_model            VARCHAR(50),
    created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE unit_test_records IS 'AI 单元测试生成记录';

-- ============================================================
-- 4. chat_conversations — 会话
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_conversations (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(64)   NOT NULL UNIQUE,
    title       VARCHAR(200),
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_conversations_session ON chat_conversations(session_id);

COMMENT ON TABLE chat_conversations IS '会话表';

-- ============================================================
-- 5. chat_messages — 消息（短期记忆持久化）
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(64)   NOT NULL REFERENCES chat_conversations(session_id) ON DELETE CASCADE,
    role        VARCHAR(20)   NOT NULL CHECK (role IN ('USER', 'ASSISTANT', 'SYSTEM')),
    content     TEXT          NOT NULL,
    token_count INT           NOT NULL DEFAULT 0,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX idx_chat_messages_created ON chat_messages(session_id, created_at);

COMMENT ON TABLE chat_messages IS '消息表（短期记忆持久化）';

-- ============================================================
-- 6. long_term_memories — 长期记忆（向量存储）
-- ============================================================
CREATE TABLE IF NOT EXISTS long_term_memories (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(64),
    content     TEXT          NOT NULL,
    memory_type VARCHAR(30)   NOT NULL CHECK (memory_type IN ('FACT', 'PREFERENCE', 'KNOWLEDGE', 'EXPERIENCE')),
    embedding   TEXT,           -- bge-m3: 1024 维向量（逗号分隔）
    metadata    TEXT          NOT NULL DEFAULT '{}',
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 语义向量索引（TEXT 格式，余弦相似度在应用层计算）
-- 注意：如使用 pgvector 的 vector 类型，需 CREATE EXTENSION vector 并建 ivfflat 索引
CREATE INDEX IF NOT EXISTS idx_long_term_memories_type ON long_term_memories(memory_type);

COMMENT ON TABLE long_term_memories IS '长期记忆表（向量存储）';

-- ============================================================
-- 7. knowledge_documents — 知识文档（向量存储）
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id              BIGSERIAL PRIMARY KEY,
    title           VARCHAR(300)  NOT NULL,
    content         TEXT          NOT NULL,
    chunk_index     INT           NOT NULL DEFAULT 0,
    chunk_content   TEXT          NOT NULL,
    embedding       TEXT,         -- bge-m3: 1024 维向量（逗号分隔）
    source_type     VARCHAR(30)   NOT NULL CHECK (source_type IN ('AI_README', 'MANUAL', 'CODE', 'DOC')),
    project_name    VARCHAR(100),
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_project ON knowledge_documents(project_name);
CREATE INDEX idx_knowledge_documents_source ON knowledge_documents(source_type);

COMMENT ON TABLE knowledge_documents IS '知识文档表（向量存储）';

-- ============================================================
-- 8. ai_readme_documents — AIReadMe 文档
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_readme_documents (
    id            BIGSERIAL PRIMARY KEY,
    project_name  VARCHAR(100)  NOT NULL,
    section       VARCHAR(50)   NOT NULL CHECK (section IN (
                      'ARCHITECTURE', 'CORE_FLOW', 'DEV_GUIDE',
                      'STRUCTURE', 'BUSINESS', 'EXPERIENCE'
                  )),
    content       TEXT          NOT NULL,
    version       INT           NOT NULL DEFAULT 1,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_readme_project ON ai_readme_documents(project_name);

COMMENT ON TABLE ai_readme_documents IS 'AIReadMe 文档表';

-- ============================================================
-- 预置 CR Prompt 模板
-- ============================================================
INSERT INTO prompt_templates (name, type, role_setting, review_dimensions, severity_levels, template_body)
VALUES (
    'Java Code Review 标准模板',
    'CODE_REVIEW',
    '你是一名资深 Java 代码审查专家，拥有 10 年以上大型分布式系统开发经验。你擅长发现代码中的性能瓶颈、安全隐患、设计缺陷和可维护性问题。你的评审意见直接、专业、可操作。',
    ARRAY['性能优化', '安全性', '代码质量', '可维护性', '异常处理', '并发安全', '资源管理', '设计模式'],
    ARRAY['Critical', 'Warning', 'Info'],
    E'请对以下 Java 代码进行全面的 Code Review。\n\n## 评审要求\n严格按照以下 8 个维度进行审查：\n1. **性能优化**：是否有多余的对象创建、不必要的循环、可优化的算法\n2. **安全性**：是否存在 SQL 注入、XSS、敏感信息泄露等安全风险\n3. **代码质量**：命名是否规范、是否有重复代码、是否符合 SOLID 原则\n4. **可维护性**：代码是否易于理解、注释是否充分、模块划分是否合理\n5. **异常处理**：异常处理是否完善、是否存在吞异常的情况\n6. **并发安全**：是否存在线程安全问题、锁的使用是否合理\n7. **资源管理**：数据库连接、文件流等资源是否正确关闭\n8. **设计模式**：是否合理运用了设计模式，是否存在反模式\n\n## 问题等级定义\n- **Critical**：必须修复，可能导致系统故障、安全漏洞或数据丢失\n- **Warning**：建议修复，影响代码质量或存在潜在风险\n- **Info**：优化建议，可以提升代码优雅度或性能\n\n## 输出格式\n请以 JSON 格式返回评审结果，格式如下：\n```json\n{\n  "summary": "整体评审摘要",\n  "score": 85,\n  "issues": [\n    {\n      "dimension": "性能优化",\n      "severity": "Warning",\n      "line_range": "42-45",\n      "title": "问题标题",\n      "description": "问题详细描述",\n      "suggestion": "修复建议",\n      "fix_code": "建议的修复代码片段"\n    }\n  ],\n  "highlights": ["亮点1", "亮点2"]\n}\n```\n\n## 待评审代码\n```java\n{{source_code}}\n```'
);
