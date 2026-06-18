# AI Center — 工作室 AI 中心

> AI 驱动的研发效能平台，围绕「代码质量与团队知识管理」两大核心场景，构建 AI Code Review、AI 单元测试生成、AIReadMe 文档生成和智能问答知识库四大功能模块。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 语言 | Java 17 | LTS，稳定可靠 |
| 框架 | Spring Boot 3.2.5 | 最新稳定版 |
| AI 框架 | LangChain4j 0.36.2 | Java 生态最成熟的 LLM 集成框架 |
| LLM (对话) | DeepSeek (OpenAI 兼容) | 便宜、中文优秀 |
| Embedding | Ollama + bge-m3 | 本地免费，1024 维中文向量 |
| 向量存储 | pgvector (PostgreSQL 扩展) | 向量与业务数据合二为一 |
| 数据库 | PostgreSQL 16 + pgvector | 现代化关系型数据库 |
| 缓存 | Redis 7 | 短期记忆、会话管理 |
| ORM | MyBatis-Plus 3.5.5 | 简洁高效 |
| API 文档 | Knife4j (Swagger 3) | 可视化接口调试 |
| 构建 | Maven 多模块 | 分层清晰 |

## 项目结构

```
ai-center/
├── pom.xml                     # 父 POM，版本管理
├── docker-compose.yml          # PostgreSQL + Redis + Ollama
├── ai-center-common/           # 公共模块：Result、枚举、异常
├── ai-center-model/            # 模型模块：Entity、DTO、VO、Mapper
├── ai-center-ai/               # AI 核心模块：LangChain4j + RAG + 记忆
│   ├── config/                 # LLM / Embedding Bean 配置
│   ├── service/                # CodeReview / UnitTest / AiReadme / Chat
│   ├── memory/                 # 短期记忆 + 长期记忆管理
│   ├── prompt/                 # Prompt 模板管理器
│   └── rag/                    # 查询重写 + 语义分块 + 混合检索
└── ai-center-server/           # Web 启动模块：Controller + Spring 配置
    └── resources/db/init.sql   # 数据库初始化脚本（含预置数据）
```

## 快速启动

### 1. 启动基础设施

```bash
docker-compose up -d
```

启动 PostgreSQL (pgvector)、Redis、Ollama 三个服务。

### 2. 拉取 Embedding 模型（仅首次）

```bash
docker exec ai-center-ollama ollama pull bge-m3
```

### 3. 配置 API Key

编辑 `ai-center-server/src/main/resources/application-dev.yml`，或设置环境变量：

```bash
export DEEPSEEK_API_KEY=your-deepseek-api-key
```

### 4. 启动应用

```bash
mvn clean package -pl ai-center-server -am -DskipTests
java -jar ai-center-server/target/ai-center-server-1.0.0-SNAPSHOT.jar
```

### 5. 访问 API 文档

http://localhost:8080/doc.html

## 四大核心功能

### 1. AI Code Review — 结构化代码评审

基于「角色设定 + 8 维度 + 3 级问题分类 + JSON Schema 约束输出」的结构化 Prompt：

- **8 个评审维度**：性能优化、安全性、代码质量、可维护性、异常处理、并发安全、资源管理、设计模式
- **3 级问题分类**：Critical（必须修复）、Warning（建议修复）、Info（优化建议）
- **模板化输出**：JSON 格式，含评分、问题列表、修复代码、亮点

```
POST /api/code-review/review    # 提交代码评审
GET  /api/code-review/records   # 评审记录列表
```

### 2. AI 单元测试生成

提交源代码 → AI 自动生成 JUnit 5 + Mockito 单元测试，覆盖正常/边界/异常场景。

```
POST /api/unit-test/generate    # 生成单元测试
GET  /api/unit-test/records     # 生成记录列表
```

### 3. AIReadMe 文档生成

扫描项目信息 → AI 按 6 个章节依次生成：
1. 技术架构 2. 核心流程 3. 开发指南 4. 项目结构 5. 业务知识 6. 历史经验

```
POST /api/ai-readme/generate    # 生成 AIReadMe
GET  /api/ai-readme/{project}   # 获取项目文档
```

### 4. 智能问答知识库 — 三层记忆 + RAG

**短期记忆**：滑动窗口（最近 20 轮）+ LLM 摘要 + Redis 存储

**长期记忆**：主动录入 + bge-m3 向量化 + pgvector 语义召回

**RAG 检索增强**：
查询重写 → 语义分块 → BM25 + 向量混合检索（权重 0.3:0.7）

```
POST /api/chat/send             # 智能对话
POST /api/memory/long-term      # 录入长期记忆
GET  /api/memory/long-term/search  # 语义搜索记忆
POST /api/knowledge/upload      # 上传知识文档
POST /api/knowledge/search      # RAG 检索
```

## API 概览

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| CR | POST | `/api/code-review/review` | 提交代码评审 |
| CR | GET | `/api/code-review/records` | 评审记录列表 |
| CR | GET | `/api/code-review/records/{id}` | 评审详情 |
| 单测 | POST | `/api/unit-test/generate` | 生成单元测试 |
| 单测 | GET | `/api/unit-test/records` | 生成记录列表 |
| 单测 | GET | `/api/unit-test/records/{id}` | 生成详情 |
| 文档 | POST | `/api/ai-readme/generate` | 生成 AIReadMe |
| 文档 | GET | `/api/ai-readme/{projectName}` | 获取文档 |
| 对话 | POST | `/api/chat/send` | 发送消息 |
| 对话 | GET | `/api/chat/conversations` | 会话列表 |
| 对话 | DELETE | `/api/chat/conversations/{id}` | 删除会话 |
| 记忆 | POST | `/api/memory/long-term` | 录入长期记忆 |
| 记忆 | GET | `/api/memory/long-term/search` | 语义搜索 |
| 记忆 | DELETE | `/api/memory/long-term/{id}` | 删除记忆 |
| 知识 | POST | `/api/knowledge/upload` | 上传知识文档 |
| 知识 | POST | `/api/knowledge/search` | RAG 检索 |
| Prompt | GET/POST/PUT | `/api/prompts` | 模板管理 |
| Prompt | POST | `/api/prompts/{id}/activate` | 激活模板 |

## Docker Compose 服务

| 服务 | 镜像 | 端口 |
|------|------|------|
| postgres | `pgvector/pgvector:pg16` | 5433→5432 |
| redis | `redis:7-alpine` | 6380→6379 |
| ollama | `ollama/ollama:latest` | 11434→11434 |
