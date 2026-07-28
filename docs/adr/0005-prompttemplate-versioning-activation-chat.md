# ADR-0005: PromptTemplate 版本化模型 + 激活不变量 + CHAT 纳入模板

- **状态**: Accepted
- **日期**: 2026-07-28
- **关联术语**: Prompt Template

## 背景

- **Q10**:PromptTemplate 是领域实体(产品 IP,有生命周期),非配置。
- **Q11 激活模型坏了**:[PromptTemplateManager.java:43](../ai-center-ai/src/main/java/com/aicenter/ai/prompt/PromptTemplateManager.java#L43) `refreshCache` 对同 type 多激活模板 `put(type,t)` 后者覆盖前者,查询无 `ORDER BY` -> **非确定性**;`init.sql` 无 `(type) WHERE is_active` 部分唯一索引;[CodeReviewService.java:57](../ai-center-ai/src/main/java/com/aicenter/ai/service/CodeReviewService.java#L57) `getActiveTemplateByName(type, null)` -> `name = null` 永不命中 -> **死分支**。
- **Q12**:`version` 列([entity:46](../ai-center-model/src/main/java/com/aicenter/model/entity/PromptTemplate.java#L46))被存但全代码无任何读取/比较/回滚 -> **幽灵列**。决定真做版本化(Prompt 是迭代资产,区别于 Document 一次性资料,见 ADR-0002)。
- **Q13**:CHAT 类型枚举存在但 [ChatService.buildContextPrompt](../ai-center-ai/src/main/java/com/aicenter/ai/service/ChatService.java#L136) 系统 prompt 硬编码,CHAT 模板是空壳。

## 决策

1. **PromptTemplate 是领域实体**,有完整生命周期。
2. **逻辑身份 = `type`**(CODE_REVIEW / UNIT_TEST / AI_README / CHAT)。一 type 一逻辑 prompt,**不支持命名变体**。
3. **版本化模型**:每行 = 一个版本。列:`(id, type, version, name[标签], role_setting, template_body, review_dimensions, severity_levels, is_active, created_at)`。
   - **编辑 = 新增版本**:`version = max+1`,激活新行,旧行保留供回滚/对比。不覆盖。
   - **`name` 降级为版本标签**(如 "v2-七层结构化"),不再当身份,不再塞版本号。
   - **回滚**:把某旧 version 置 active(自动 deactivate 同 type 其他)。
4. **激活不变量**:每个 `type` 恰好一行 `is_active=true`。落实:
   - DB 部分唯一索引 `(type) WHERE is_active = true`;
   - 激活操作 = 事务内 deactivate 同 type 其他 + activate 目标;
   - 缓存按 type 取,**确定性**(消除 last-wins 非确定性);
   - 删除 `getActiveTemplateByName(type, null)` 死分支,激活一律走 type 维度。
5. **CHAT 纳入模板**:`buildContextPrompt` 改为加载激活的 CHAT 模板并渲染。模板存**静态外壳 + 占位符**(`{{long_term_memory}}` / `{{rag_context}}` / `{{conversation_history}}` / `{{user_message}}`);**拼装逻辑(拉记忆/RAG/历史)留在代码**。CHAT 类型不再是空壳。

## 结果

- `version` 列从装饰品变为真版本号(历史/回滚可用)。
- CHAT prompt 与 CR/unittest/readme 统一为运行时可管理(改 prompt 不再重部署)。
- `name` 与版本解耦。
- 初始数据:4 个 type 各 seed 一个 active v1(CR 的七层 Prompt 即 CR active v1;另 seed CHAT/UNIT_TEST/AI_README v1)。
- **与 ADR-0002 的不对称已论证**:Prompt 迭代资产(留历史可回滚) vs Document 一次性资料(upsert 替换)。

## 遗留

- `review_dimensions` / `severity_levels` 仅 CODE_REVIEW 有意义,其余 type 为空--可接受(版本行的可选元数据),或未来按 type 约束。
