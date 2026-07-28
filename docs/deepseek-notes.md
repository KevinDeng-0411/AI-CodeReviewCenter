# DeepSeek API 集成约定

> 适用：DeepSeek thinking 模型（deepseek-v4-flash / deepseek-v4-pro），OpenAI 兼容 API。
> 来源：官方「思考模式工具调用」文档 + P3-1 实测。

## 模型与模式

- 当前默认：`deepseek-v4-flash`（thinking 模型，config `llm_model`）。
- thinking 由请求体 `extra_body={"thinking":{"type":"enabled" | "disabled"}}` 控制。

---

## 1. 结构化输出（CodeReview 等单次返回 schema）

**thinking 模式下**实测：

| `with_structured_output` method | 结果 |
|--------|------|
| `json_schema`（langchain 默认 response_format） | ❌ 400 `response_format type unavailable` |
| `function_calling`（强制 tool_choice） | ❌ 400 `Thinking mode does not support this tool_choice` |
| **`json_mode`** | ✅ 可用（真实七层 Prompt 验证：score=10, 7 issues） |

> 根因：thinking 模式**支持工具调用，但不支持被强制 `tool_choice`**；而 langchain `function_calling` 内部强制 tool_choice 来保证结构化输出，故被拒。`json_schema` response_format 则被 DeepSeek 直接拒。

**约定**：thinking 模式结构化输出用

```python
self.chat_model.with_structured_output(Schema, method="json_mode")
```

并配 `ainvoke` + Pydantic `model_validate` 回退（见 `codeaware-py/app/ai/services/code_review.py:_invoke_structured`、`_extract_json`）。回退为迁移文档 §10 风险缓解。

---

## 2. agentic 多轮工具调用（未来 ChatService / LangGraph）

thinking 模式**支持**工具调用，但须遵守三条，否则 400：

1. `extra_body={"thinking":{"type":"enabled"}}` + `reasoning_effort`。
2. **每轮把 `response.choices[0].message`（含 `reasoning_content`）完整 append 回 messages**。不回传 `reasoning_content` → 400。后续所有请求都要带上本 turn 产生的 reasoning_content。
3. **不强制 `tool_choice`**（用 auto）；强制 → 400。

手动管理 tool_call 循环（调工具 → 回 tool 结果 → 继续）：

```python
# 伪代码：thinking 模式工具调用循环
resp = client.chat.completions.create(
    model="deepseek-v4-flash", messages=msgs, tools=tools,
    reasoning_effort="high", extra_body={"thinking": {"type": "enabled"}},
)
msgs.append(resp.choices[0].message)   # 含 reasoning_content，必须回传
if resp.choices[0].message.tool_calls:
    for tc in resp.choices[0].message.tool_calls:
        result = TOOL_MAP[tc.function.name](**json.loads(tc.function.arguments))
        msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    # 继续下一轮 create...
```

---

## 3. 非思考模式（可选，速度优先）

`extra_body={"thinking":{"type":"disabled"}}` 关闭思考：

- thinking 模式的上述限制**应解除**：强制 `tool_choice` 可用、`json_schema` response_format 可用 → `with_structured_output(method="function_calling")` 直接工作，schema 约束更严（function signature 强制）。
- 适用：简单/快速任务（省去推理 token 与延迟），或需严格 schema 强制时。
- **当前未启用**；首次使用时实测验证（thinking disabled 后 function_calling/json_schema 是否真能用）。

---

## 决策

- **当前（P3-1+）**：保持 thinking 模式 + `json_mode` 结构化输出 + ainvoke 回退。已真实验证。
- **非思考模式**：暂不需要；留作未来「速度优先 / 严格 schema」场景的备选，届时按 §3 启用并验证。
- **agentic 工具调用**：P3-4 / LangGraph 演进时按 §2 实现（`reasoning_content` 回传是关键坑）。

## 是否需要非思考模式的工具调用方法？

**结论：当前不需要，但记录备选。**

- 现有任务（CodeReview / Chat / 单测生成）在 thinking + `json_mode` 下已工作且质量更好（thinking 提升评审深度），无需切非思考。
- 非思考模式的价值在两点：① 速度/成本（省推理 token）；② 严格 schema 强制（function_calling 强制 tool_choice，比 json_mode 的「LLM 自觉返回 JSON」更稳）。
- 触发时机：出现「响应慢成为瓶颈」或「json_mode 偶发 schema 不符需要更强约束」时，再按 §3 启用并实测。届时 `with_structured_output(method="function_calling")` 可直接用（非思考模式不拒 tool_choice）。
