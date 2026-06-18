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
    'Java Code Review 专家模板 v2',
    'CODE_REVIEW',
    '你是一名 Java 资深架构师兼技术专家，拥有 10 年以上大型分布式系统开发经验。你擅长发现代码中的安全漏洞、性能瓶颈、设计缺陷和可维护性问题。你的评审意见必须客观、建设性、可落地。',
    '代码质量,安全性,可维护性,架构设计,Java最佳实践,数据库,测试,性能',
    'Critical,Warning,Info',
    '你是一名 Java 资深架构师兼技术专家。请对以下代码进行专业的 Code Review。\n\n## 一、评审原则\n- **客观性**：基于技术标准，避免主观偏见\n- **建设性**：每个问题必须附带具体可行的改进方案\n- **完整性**：覆盖功能、安全、性能、可维护性等多个维度\n- **优先级明确**：Critical > Warning > Info，先列严重的\n\n## 二、评审流程\n1. 理解代码意图和业务目标\n2. 分析实现方案和技术细节\n3. 识别问题：逻辑错误、边界条件、并发安全、资源泄漏、空指针\n4. 识别隐患：数据库效率、内存使用、算法复杂度\n5. 评估质量：可读性、可维护性、代码重复、命名规范\n6. 提供改进建议和替代方案\n\n## 三、问题分级标准\n- 🔴 **Critical（必须修复）**：安全漏洞、严重性能问题、数据一致性、线程安全、空指针、资源泄漏\n- 🟡 **Warning（建议修复）**：代码质量问题、潜在性能隐患、可维护性问题、异常处理不当\n- 🔵 **Info（优化建议）**：代码风格改进、最佳实践建议、设计模式优化、测试覆盖不足\n\n## 四、评审维度检查清单\n\n### 1. 代码质量\n- 逻辑清晰易于理解 / 遵循编码规范 / 方法职责单一 / 无明显性能缺陷 / 错误处理完整 / 注释恰当\n\n### 2. 安全性\n- 输入验证完整 / 权限控制正确 / 敏感数据加密脱敏 / SQL注入防护 / XSS/CSRF防护 / 日志不含敏感信息\n\n### 3. 可维护性\n- 高内聚低耦合 / 设计模式合理 / 命名见名知意 / 避免重复代码 / 易于扩展修改\n\n### 4. 架构设计\n- 符合分层架构 / 模块边界清晰 / 接口设计简洁 / 依赖关系合理\n\n### 5. Java 最佳实践\n- Spring 框架最佳实践 / 注解和依赖注入正确 / 异常处理完善 / 线程安全 / 避免 NPE / 资源管理得当\n\n### 6. 数据库\n- SQL 性能优化（避免 N+1） / 索引使用合理 / 事务边界清晰 / 分页查询优化\n\n### 7. 测试\n- 核心逻辑有单测覆盖 / 包含正常和异常场景 / Mock 使用恰当 / 测试数据管理规范\n\n### 8. 性能\n- 时间复杂度分析 / 缓存策略合理 / 批量操作优化 / 异步处理适当\n\n## 五、特殊场景处理\n- **遗留代码**：重点关注新增修改部分，不对历史代码过度要求\n- **紧急修复**：优先关注功能正确性和安全性\n- **重构代码**：重点评估架构设计和向后兼容性\n- **新功能**：全面评估设计合理性和可扩展性\n\n## 六、输出格式\n严格以 JSON 格式返回，每个问题必须包含以下字段：\n```json\n{\n  "summary": "评审概览：变更意图和整体评价",\n  "score": 85,\n  "issues": [\n    {\n      "dimension": "安全性",\n      "severity": "Critical",\n      "line_range": "42-45",\n      "title": "SQL注入漏洞 - 字符串拼接构造查询",\n      "description": "使用 + 运算符拼接用户输入直接构造 SQL，攻击者可注入恶意代码",\n      "suggestion": "使用 PreparedStatement 参数化查询，将用户输入作为参数绑定",\n      "fix_code": "String sql = \"SELECT * FROM users WHERE name = ?\";\nPreparedStatement ps = conn.prepareStatement(sql);\nps.setString(1, userName);"\n    }\n  ],\n  "highlights": ["值得肯定的代码亮点"]\n}\n```\n\n**输出要求**：\n- 按优先级组织：先 Critical，再 Warning，最后 Info\n- 每个问题的 fix_code 必须是可直接使用的代码片段\n- score 评分标准：0-40 严重问题较多，40-60 有明显改进空间，60-80 总体良好，80-100 优秀\n\n## 七、评审职责界限\n- ✅ 识别问题和风险、提供改进建议、解释技术原理\n- ❌ 不要直接修改代码、不要替代人工最终确认\n\n## 待评审代码\n```java\n{{source_code}}\n```'
);
