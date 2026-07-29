# CodeAware 前端 - 工程仪表台

React + Vite + TypeScript + Tailwind。7 模块 SPA，Chat 为核心域。

## 设计

工程仪表台（Engineering Instrument）：冷调技术纸 + oxblood 权威信号色 + 磷光琥珀实时信号。
字体 IBM Plex Mono（标题/数据）+ IBM Plex Sans（正文）。签名元素：流式生成时的琥珀示波轨迹、
相似度 VU 电平条、severity 堆叠仪表。

## 开发

```bash
cd frontend
npm install                # 首次
npm run dev                # http://localhost:5173，代理 /api -> :8000
```

需后端同跑：`uv run uvicorn app.main:app --reload --port 8000`（CORS 已放行 5173）。

## 构建（生产单进程）

```bash
npm run build              # -> dist/
# 由 FastAPI 静态托管：访问 http://localhost:8000/ 即前端
```

## 结构

```
src/
├── api/            # typed fetch client + SSE 流式解析 + 类型（对齐后端 schemas）
├── components/      # Layout 侧栏 / Markdown 渲染 / UI 原语（Meter/Severity/SignalTrace）
├── pages/           # Chat(核心) / CodeReview / UnitTest / AiReadme / Knowledge / Memory / Prompt
├── App.tsx          # 状态切换视图（无 router）
└── index.css        # Tailwind + 设计 token（绘图纸网格 / 信号轨迹）
```

API 契约对齐后端：`conversation_id`（非 sessionId）、统一响应 `{code,data}`、SSE `data:<token>` + `data:[DONE]`。
