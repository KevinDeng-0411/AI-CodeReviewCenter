# AI Center — 工作室 AI 中心

> AI 驱动的研发效能平台，围绕「代码质量与团队知识管理」两大核心场景。
> 基于 LangChain4j + DeepSeek V4 + Ollama bge-m3 + MySQL + Redis。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 语言 | Java 17 | LTS |
| 框架 | Spring Boot 3.2.5 | 最新稳定版 |
| AI 框架 | LangChain4j 0.36.2 | Java 生态最成熟的 LLM 集成框架 |
| LLM | DeepSeek V4 Flash | 免费/超低成本、中文优秀、OpenAI 兼容 API |
| Embedding | Ollama + bge-m3 | 本地免费、1024 维、中文向量 SOTA |
| 向量存储 | 内存 / Pinecone(可选) | 内存降级方案 + Pinecone 云托管双模式 |
| 文档解析 | Apache Tika 3.1 | 支持 PDF/Word/HTML/Markdown 等多格式 |
| 数据库 | MySQL 8.0 | 关系数据存储 |
| 缓存 | Redis 7 | 短期记忆、会话管理 |
| ORM | MyBatis-Plus 3.5.5 | 简洁高效 |
| API 文档 | Knife4j (Swagger 3) | 可视化接口调试 |
| 构建 | Maven 多模块 | 分层清晰 |

## 模型选择说明

| 组件 | 选择 | 原因 |
|------|------|------|
| LLM | DeepSeek V4 Flash | 免费/超低成本，中文优秀，OpenAI 兼容 API |
| Embedding | Ollama bge-m3 | 本地免费无限制，1024-dim，中文向量 SOTA |
| 向量存储 | 内存 (默认) / Pinecone | 零配置即可运行，Pinecone 作为生产方案可选 |

## 项目结构

```
ai-center/
├── pom.xml
├── docker-compose.yml            # MySQL 8.0 + Redis 7 + Ollama
├── ai-center-common/             # 公共模块：Result、枚举、异常
├── ai-center-model/              # 模型模块：Entity、DTO、VO、Mapper
├── ai-center-ai/                 # AI 核心模块：LangChain4j + RAG + 记忆
│   ├── config/AIConfig.java      # LLM + Embedding + VectorStore Bean
│   ├── service/                  # CodeReview / UnitTest / AiReadme / Chat / Rag / DocumentParser
│   ├── memory/                   # 短期记忆(Redis) + 长期记忆(向量)
│   ├── prompt/                   # Prompt 模板管理器
│   └── rag/                      # 查询重写 + 语义分块 + BM25+向量混合检索
└── ai-center-server/             # Web 启动模块：Controller + 配置
```

---

## 快速启动

### 1. 启动基础设施

```bash
docker compose up -d
```

启动 MySQL 8.0 + Redis 7 + Ollama。

### 2. 拉取 Embedding 模型（仅首次）

```bash
docker exec ai-center-ollama ollama pull bge-m3
```

### 3. 配置 DeepSeek API Key

编辑 `ai-center-server/src/main/resources/application-dev.yml`：

```yaml
ai:
  llm:
    api-key: sk-your-deepseek-api-key
```

### 4. 启动应用

```bash
mvn clean package -pl ai-center-server -am -DskipTests
java -jar ai-center-server/target/ai-center-server-1.0.0-SNAPSHOT.jar
```

### 5. 访问 API 文档

http://localhost:8080/doc.html

---

## API 使用指南

### 1. AI Code Review — 结构化代码评审

**8 维度 + 3 级问题分类**：性能优化、安全性、代码质量、可维护性、异常处理、并发安全、资源管理、设计模式。
问题等级：Critical（必须修复）、Warning（建议修复）、Info（优化建议）。

```bash
# 提交代码评审
curl -X POST http://localhost:8080/api/code-review/review \
  -H "Content-Type: application/json" \
  -d '{
    "projectName": "my-project",
    "filePath": "src/main/java/com/example/UserService.java",
    "sourceCode": "public void save(String name) {\n  String sql = \"DELETE FROM users WHERE name=\" + name;\n  jdbc.execute(sql);\n}"
  }'
```

返回示例：
```json
{
  "code": 1,
  "data": {
    "score": 15,
    "summary": "该代码存在严重的安全漏洞...",
    "issuesCount": 6,
    "criticalCount": 1,
    "warningCount": 2,
    "infoCount": 3,
    "issues": [
      {
        "dimension": "安全性",
        "severity": "Critical",
        "lineRange": "1-3",
        "title": "SQL注入漏洞",
        "description": "使用字符串拼接构造SQL...",
        "suggestion": "使用PreparedStatement参数化查询",
        "fixCode": "String sql = \"DELETE FROM users WHERE name = ?\";\nPreparedStatement ps = conn.prepareStatement(sql);\nps.setString(1, name);"
      }
    ]
  }
}
```

```bash
# 查询评审记录
curl "http://localhost:8080/api/code-review/records?page=1&size=10&projectName=my-project"

# 查询评审详情
curl "http://localhost:8080/api/code-review/records/1"
```

### 2. AI 单元测试生成

提交源代码，自动生成 JUnit 5 + Mockito 单元测试。

```bash
curl -X POST http://localhost:8080/api/unit-test/generate \
  -H "Content-Type: application/json" \
  -d '{
    "projectName": "my-project",
    "filePath": "src/main/java/com/example/UserService.java",
    "sourceCode": "public class UserService {\n  public User findById(Long id) {\n    return userMapper.selectById(id);\n  }\n}",
    "testFramework": "JUnit5"
  }'
```

```bash
# 查询生成记录
curl "http://localhost:8080/api/unit-test/records?page=1&size=10"
```

### 3. AIReadMe 文档生成

扫描项目信息，自动生成 6 章节文档：技术架构、核心流程、开发指南、项目结构、业务知识、历史经验。

```bash
curl -X POST http://localhost:8080/api/ai-readme/generate \
  -H "Content-Type: application/json" \
  -d '{
    "projectName": "ai-center",
    "projectPath": "/home/projects/ai-center"
  }'

# 获取已生成的文档
curl "http://localhost:8080/api/ai-readme/ai-center"
```

### 4. 智能问答 — 多轮对话

整合短期记忆（Redis 滑动窗口 + LLM 摘要）+ 长期记忆（Ollama 向量语义召回）+ RAG 知识库检索。

```bash
# 发送消息（首次无 sessionId，自动创建）
curl -X POST http://localhost:8080/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "什么是Spring Boot的自动配置原理？"}'
```

返回示例：
```json
{
  "code": 1,
  "data": {
    "sessionId": "a7f5239e459647f3...",
    "reply": "Spring Boot的自动配置基于@EnableAutoConfiguration注解...",
    "memorySummary": null
  }
}
```

```bash
# 多轮对话 — 使用返回的 sessionId 保持上下文
curl -X POST http://localhost:8080/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "a7f5239e459647f3...",
    "message": "给我一个具体的例子"
  }'

# 查看会话列表
curl "http://localhost:8080/api/chat/conversations"

# 查看会话消息历史（含短期记忆）
curl "http://localhost:8080/api/chat/conversations/a7f5239e459647f3..."

# 删除会话
curl -X DELETE "http://localhost:8080/api/chat/conversations/a7f5239e459647f3..."
```

### 5. 知识库 + RAG 混合检索

上传知识文档 → 语义分块 → bge-m3 向量化 → 混合检索（BM25 关键词 + 向量语义）。

```bash
# 上传知识文档（文本）
curl -X POST http://localhost:8080/api/knowledge/upload \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Redis缓存最佳实践",
    "content": "## 缓存穿透\n查询不存在的数据。方案：布隆过滤器、缓存空值。\n\n## 缓存击穿\n热点Key失效瞬间大量请求打DB。方案：互斥锁、逻辑过期。\n\n## 缓存雪崩\n大量Key同时失效。方案：过期时间加随机值、多级缓存。",
    "sourceType": "MANUAL",
    "projectName": "ai-center"
  }'
```

```bash
# RAG 混合检索 (BM25 + 向量)
curl -X POST http://localhost:8080/api/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "缓存击穿如何解决", "topK": 3}'
```

返回示例：
```json
{
  "code": 1,
  "data": [
    {
      "fusionScore": 0.565,
      "bm25Score": 0.0,
      "vectorScore": 0.807,
      "document": {
        "title": "Redis缓存最佳实践",
        "chunkIndex": 2,
        "chunkContent": "## 缓存击穿\n热点Key失效瞬间大量请求打DB。方案：互斥锁、逻辑过期。"
      }
    }
  ]
}
```

```bash
# 上传文档文件（支持 PDF/Word/HTML/Markdown 等）
curl -X POST http://localhost:8080/api/knowledge/upload-file \
  -F "file=@/path/to/document.pdf" \
  -F "projectName=ai-center" \
  -F "sourceType=DOC"

# 删除知识文档
curl -X DELETE "http://localhost:8080/api/knowledge/1"
```

### 6. 长期记忆管理

手动录入团队知识 → bge-m3 向量化存储 → 语义相似度召回。

```bash
# 保存长期记忆
curl -X POST http://localhost:8080/api/memory/long-term \
  -H "Content-Type: application/json" \
  -d '{
    "content": "团队使用 MyBatis-Plus 3.5.5 作为 ORM 框架，配合 MySQL 8.0",
    "memoryType": "KNOWLEDGE",
    "sessionId": "a7f5239e...",
    "metadata": "{\"source\": \"team-wiki\"}"
  }'
```

```bash
# 语义搜索（自然语言查询，自动转向量比对）
curl --get "http://localhost:8080/api/memory/long-term/search" \
  --data-urlencode "query=ORM框架数据库" \
  --data-urlencode "threshold=0.3" \
  --data-urlencode "topK=5"
```

返回示例：
```json
{
  "code": 1,
  "data": [
    {
      "id": 2,
      "content": "团队使用 MyBatis-Plus 3.5.5 作为 ORM 框架，配合 MySQL 8.0",
      "memoryType": "KNOWLEDGE",
      "similarity": 0.6349
    }
  ]
}
```

```bash
# 删除记忆
curl -X DELETE "http://localhost:8080/api/memory/long-term/2"
```

### 7. Prompt 模板管理

```bash
# 查询模板列表
curl "http://localhost:8080/api/prompts?type=CODE_REVIEW"

# 预览模板效果
curl "http://localhost:8080/api/prompts/1/preview?sampleCode=public class Test {}"

# 激活指定模板
curl -X POST "http://localhost:8080/api/prompts/1/activate"
```

---

## 架构设计要点

### 短期记忆 (Short-Term Memory)

```
用户消息 → Redis List (滑动窗口, 最近 20 轮)
         → 超过 10 轮触发 LLM 摘要 → Redis String
         → 冷数据异步持久化到 MySQL
```

### 长期记忆 (Long-Term Memory)

```
手动录入/自动捕获 → Ollama bge-m3 向量化 → EmbeddingStore
用户查询 → 向量化 → 余弦相似度 Top-K 召回 → 注入对话上下文
```

### RAG 混合检索

```
用户查询 → QueryRewriter (改写+生成变体)
         → HybridRetriever:
              BM25: MySQL 关键词匹配 (权重 0.3)
              向量: EmbeddingStore 语义检索 (权重 0.7)
         → 融合排序 → Top-K 结果
```

### 向量存储双模式

```
默认: SimpleInMemoryEmbeddingStore (零配置，内存存储)
生产: PineconeEmbeddingStore (配置 ai.pinecone.api-key 自动切换)
```

---

## Docker Compose 服务

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| mysql | `mysql:8.0` | 3307→3306 | 关系数据 |
| redis | `redis:7-alpine` | 6380→6379 | 缓存 + 短期记忆 |
| ollama | `ollama/ollama:latest` | 11434→11434 | 本地 Embedding |

---

## API 端点汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/code-review/review` | AI 代码评审 |
| GET | `/api/code-review/records` | 评审记录列表 |
| GET | `/api/code-review/records/{id}` | 评审详情 |
| POST | `/api/unit-test/generate` | 生成单元测试 |
| GET | `/api/unit-test/records` | 生成记录列表 |
| GET | `/api/unit-test/records/{id}` | 生成详情 |
| POST | `/api/ai-readme/generate` | 生成 AIReadMe |
| GET | `/api/ai-readme/{projectName}` | 获取文档 |
| POST | `/api/chat/send` | 发送消息（多轮对话） |
| GET | `/api/chat/conversations` | 会话列表 |
| GET | `/api/chat/conversations/{sessionId}` | 会话消息历史 |
| DELETE | `/api/chat/conversations/{sessionId}` | 删除会话 |
| POST | `/api/memory/long-term` | 录入长期记忆 |
| GET | `/api/memory/long-term/search` | 语义搜索记忆 |
| DELETE | `/api/memory/long-term/{id}` | 删除记忆 |
| POST | `/api/knowledge/upload` | 上传知识文档（文本） |
| POST | `/api/knowledge/upload-file` | 上传知识文档（文件） |
| POST | `/api/knowledge/search` | RAG 混合检索 |
| DELETE | `/api/knowledge/{id}` | 删除知识文档 |
| GET/POST/PUT | `/api/prompts` | Prompt 模板管理 |
