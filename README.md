# AI Center — 工作室 AI 中心

> AI 驱动的研发效能平台，围绕「代码质量与团队知识管理」两大核心场景。
> 基于 LangChain4j + DeepSeek + text-embedding-v3 + Pinecone + MySQL + Redis。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 语言 | Java 17 | LTS |
| 框架 | Spring Boot 3.2.5 | 最新稳定版 |
| AI 框架 | LangChain4j 0.36.2 | Java 生态最成熟的 LLM 集成框架 |
| LLM | DeepSeek | 免费/超低成本、中文优秀、OpenAI 兼容 API |
| Embedding | text-embedding-v3 | SOTA 质量、1024 维、OpenAI 兼容 API |
| 向量数据库 | Pinecone | 全托管、零运维、LangChain4j 原生集成 |
| 文档解析 | Apache Tika 3.1 | 支持 PDF/Word/HTML/Markdown 等多格式 |
| 数据库 | MySQL 8.0 | 关系数据存储 |
| 缓存 | Redis 7 | 短期记忆、会话管理 |
| ORM | MyBatis-Plus 3.5.5 | 简洁高效 |
| API 文档 | Knife4j (Swagger 3) | 可视化接口调试 |
| 构建 | Maven 多模块 | 分层清晰 |

## 模型选择说明

| 组件 | 选择 | 原因 |
|------|------|------|
| LLM | DeepSeek | 免费/超低成本，中文优秀，OpenAI 兼容 API |
| Embedding | text-embedding-3-large | SOTA embedding 质量，1024-dim，中文支持好 |
| 向量数据库 | Pinecone | 全托管无需运维，LangChain4j 原生 PineconeEmbeddingStore |
| 文档解析 | Apache Tika | 自动检测 20+ 文件格式，一行代码提取文本 |

## 项目结构

```
ai-center/
├── pom.xml
├── docker-compose.yml            # MySQL 8.0 + Redis 7
├── ai-center-common/             # 公共模块：Result、枚举、异常
├── ai-center-model/              # 模型模块：Entity、DTO、VO、Mapper
├── ai-center-ai/                 # AI 核心模块：LangChain4j + RAG + 记忆
│   ├── config/AIConfig.java      # LLM + Embedding + Pinecone Bean
│   ├── service/                  # CodeReview / UnitTest / AiReadme / Chat / Rag / DocumentParser
│   ├── memory/                   # 短期记忆(Redis) + 长期记忆(Pinecone)
│   ├── prompt/                   # Prompt 模板管理器
│   └── rag/                      # 查询重写 + 语义分块 + BM25+向量混合检索
└── ai-center-server/             # Web 启动模块：Controller + 配置
```

## 快速启动

### 1. 启动基础设施

```bash
docker-compose up -d
```

启动 MySQL 8.0 + Redis 7。

### 2. 配置 API Key

编辑 `ai-center-server/src/main/resources/application-dev.yml`：

```yaml
ai:
  llm:
    api-key: sk-your-deepseek-key      # DeepSeek API Key
  embedding:
    api-key: sk-your-openai-key        # text-embedding-v3 的 API Key
  pinecone:
    api-key: your-pinecone-api-key     # Pinecone API Key
    index: ai-center                    # Pinecone index 名称
```

### 3. 创建 Pinecone Index

在 https://app.pinecone.io 创建 index：
- Name: `ai-center`
- Dimensions: `1024`
- Metric: `cosine`

### 4. 启动应用

```bash
mvn clean package -pl ai-center-server -am -DskipTests
java -jar ai-center-server/target/ai-center-server-1.0.0-SNAPSHOT.jar
```

### 5. 访问 API 文档

http://localhost:8080/doc.html

## 四大核心功能

### 1. AI Code Review — 结构化代码评审

8 维度 + 3 级问题分类 + JSON Schema 约束输出

```
POST /api/code-review/review    # 提交代码评审
GET  /api/code-review/records   # 评审记录列表
```

### 2. AI 单元测试生成

提交代码 → JUnit 5 + Mockito 自动生成

```
POST /api/unit-test/generate    # 生成单元测试
GET  /api/unit-test/records     # 生成记录列表
```

### 3. AIReadMe 文档生成

6 章节自动生成：架构、流程、开发指南、结构、业务、经验

```
POST /api/ai-readme/generate    # 生成 AIReadMe
GET  /api/ai-readme/{project}   # 获取项目文档
```

### 4. 智能问答知识库 — 三层记忆 + RAG

- 短期记忆：滑动窗口 + 摘要 + Redis
- 长期记忆：Pinecone 向量存储 + 语义召回
- RAG：查询重写 + 语义分块 + BM25(MySQL) + 向量(Pinecone) 混合检索
- 文档解析：Apache Tika 多格式文本提取

```
POST /api/chat/send             # 智能对话
POST /api/memory/long-term      # 录入长期记忆 → Pinecone
GET  /api/memory/long-term/search  # 语义搜索 → Pinecone
POST /api/knowledge/upload      # 上传知识文档 → 分块 → Pinecone
POST /api/knowledge/upload-file # 上传 PDF/Word → Tika → Pinecone
POST /api/knowledge/search      # RAG 混合检索
```

## API 概览 (22 个端点)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/code-review/review` | 提交代码评审 |
| GET | `/api/code-review/records` | 评审记录列表 |
| GET | `/api/code-review/records/{id}` | 评审详情 |
| POST | `/api/unit-test/generate` | 生成单元测试 |
| GET | `/api/unit-test/records` | 生成记录列表 |
| GET | `/api/unit-test/records/{id}` | 生成详情 |
| POST | `/api/ai-readme/generate` | 生成 AIReadMe |
| GET | `/api/ai-readme/{projectName}` | 获取文档 |
| POST | `/api/chat/send` | 发送消息 |
| GET | `/api/chat/conversations` | 会话列表 |
| DELETE | `/api/chat/conversations/{id}` | 删除会话 |
| POST | `/api/memory/long-term` | 录入长期记忆 |
| GET | `/api/memory/long-term/search` | 语义搜索 |
| DELETE | `/api/memory/long-term/{id}` | 删除记忆 |
| POST | `/api/knowledge/upload` | 上传文本知识 |
| POST | `/api/knowledge/upload-file` | 上传文件(Tika) |
| POST | `/api/knowledge/search` | RAG 混合检索 |
| DELETE | `/api/knowledge/{id}` | 删除知识文档 |
| GET/POST/PUT | `/api/prompts` | Prompt 模板管理 |

## Docker Compose

| 服务 | 镜像 | 端口 |
|------|------|------|
| mysql | `mysql:8.0` | 3307→3306 |
| redis | `redis:7-alpine` | 6380→6379 |
