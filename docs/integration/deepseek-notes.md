# DeepSeek API 集成约定

> 适用：DeepSeek thinking 模型（deepseek-v4-flash / deepseek-v4-pro），OpenAI 兼容 API。
> 来源：官方「思考模式工具调用」文档 + P3-1 实测（思考/非思考均真实验证）。

## 模型与模式

- 当前默认：`deepseek-v4-flash`（thinking 模型，config `llm_model`）。
- thinking 由请求体 `extra_body={"thinking":{"type":"enabled" | "disabled"}}` 控制。
  - `enabled`：思考模式（默认行为）。
  - `disabled`：非思考模式。

---

## 1. 结构化输出（CodeReview 等单次返回 schema）

实测两模式（✅=可用，❌=400）：

| `with_structured_output` method | thinking 模式 | 非思考模式 |
|--------|:---:|:---:|
| `json_schema`（response_format） | ❌ | ❌ |
| `function_calling`（强制 tool_choice） | ❌ | ✅ |
| **`json_mode`** | ✅ | ✅ |

> **根因（实测）**：
> - `json_schema` response_format 是 **DeepSeek 通用限制**（两模式均 `response_format type unavailable`），非 thinking 专属。
> - `function_calling` 失败是 thinking 模式**拒绝强制 `tool_choice`**（langchain 内部强制 tool_choice 保证结构化）；非思考模式解除此限制，故可用。

**约定（当前 thinking 模式）**：

```python
self.chat_model.with_structured_output(Schema, method="json_mode")
```

配 `ainvoke` + Pydantic `model_validate` 回退（见 `../../codeaware-py/app/ai/services/code_review.py:_invoke_structured`、`_extract_json`）。

---

## 2. thinking 模式 agentic 多轮工具调用（未来 ChatService / LangGraph）

thinking 模式**支持**工具调用，但须遵守三条，否则 400：

1. `extra_body={"thinking":{"type":"enabled"}}` + `reasoning_effort`。
2. **每轮把 `response.choices[0].message`（含 `reasoning_content`）完整 append 回 messages**。不回传 `reasoning_content` -> 400。后续所有请求都要带上本 turn 产生的 reasoning_content。
3. **不强制 `tool_choice`**（用 auto）；强制 -> 400。

手动管理 tool_call 循环：

```python
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

## 3. 非思考模式工具调用方法（已实测）

`extra_body={"thinking":{"type":"disabled"}}` 关闭思考。实测结论：

| 能力 | 非思考模式 | 备注 |
|------|:---:|------|
| 强制 `tool_choice` | ✅ | thinking 模式会 400，非思考解除 |
| auto `tool_choice` | ✅ | 标准工具调用 |
| `json_schema` response_format | ❌ | DeepSeek 通用限制，非 thinking 专属 |
| `reasoning_content` 回传 | 不需要 | 无思考，无 reasoning_content |

### 3.1 结构化输出（比 json_mode 更严格）

非思考模式下 `function_calling` 可用，schema 由 function signature 强制（比 json_mode 靠 LLM 自觉返回 JSON 更稳）：

```python
# langchain：非思考模式 + function_calling 结构化输出
from langchain_openai import ChatOpenAI
model = ChatOpenAI(
    api_key=..., base_url="https://api.deepseek.com/v1", model="deepseek-v4-flash",
    model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
)
structured = model.with_structured_output(Schema, method="function_calling")  # ✅ 非思考下可用
result = await structured.ainvoke(prompt)
```

### 3.2 agentic 多轮工具调用（标准 OpenAI 模式，无 reasoning_content）

非思考模式即标准 OpenAI 工具调用，**无需 reasoning_content 回传**，比 §2 简单：

```python
resp = client.chat.completions.create(
    model="deepseek-v4-flash", messages=msgs, tools=tools,
    tool_choice="auto",  # 也可强制 {"type":"function","function":{"name":"..."}}
    extra_body={"thinking": {"type": "disabled"}},
)
msg = resp.choices[0].message
if msg.tool_calls:
    for tc in msg.tool_calls:
        result = TOOL_MAP[tc.function.name](**json.loads(tc.function.arguments))
        msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    # 继续下一轮 create（无需回传 reasoning_content）
```

---

## 决策

- **当前（P3-1+）**：保持 **thinking 模式 + `json_mode`** 结构化输出 + ainvoke 回退。已真实验证。thinking 提升评审/回答深度，质量优先。
- **非思考模式**：暂不切换，但方法已实测记录（§3）。触发时机：
  - 速度/成本成瓶颈（省推理 token 与延迟）；
  - 需更强 schema 强制（`function_calling` 比 `json_mode` 稳）。
  - 切换代价：`model_kwargs={"extra_body":{"thinking":{"type":"disabled"}}}` + method 改 `function_calling`，并权衡失去思考深度。
- **agentic 工具调用**：P3-4 / LangGraph 演进时实现。若需思考深度用 §2（reasoning_content 回传）；若需速度用 §3.2（标准循环）。
- **json_schema 永不可用**：DeepSeek 通用限制，任何模式都别用。

## 是否需要非思考模式的工具调用方法？

**结论：当前不切换，但方法已记录备选（§3，已实测）。**

- 现有任务（CodeReview/Chat/单测）在 thinking + `json_mode` 下工作且质量更好，无需切非思考。
- 非思考模式两个价值：① 速度/成本（省推理 token）；② 严格 schema 强制（`function_calling`，§3.1 已验证可用）。
- 出现「响应慢成瓶颈」或「json_mode 偶发 schema 不符需更强约束」时，按 §3 启用（代价：失去思考深度）。
