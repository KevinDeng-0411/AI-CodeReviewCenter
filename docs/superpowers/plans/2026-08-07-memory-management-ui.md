# 长期记忆管理 UI 实施计划

## 背景

当前 Memory 页面只有手动录入 + 语义搜索，缺少"列出全部记忆"功能。用户无法查看自动抽取的 FACT 记忆，也无法批量管理。

## 改动范围

### 后端（2 文件）

#### 1. `app/schemas/memory.py` - 新增列表 VO

```python
class MemoryListItem(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    conversation_id: str | None = None
    source: str
    created_at: str = ""

class MemoryListVO(BaseModel):
    total: int
    page: int
    size: int
    records: list[MemoryListItem]
```

#### 2. `app/api/v1/memory.py` - 新增列表端点

```python
@router.get("/long-term", response_model=Result[MemoryListVO])
async def list_long_term(
    memory_type: str = Query("ALL", pattern="^(ALL|FACT|REFERENCE)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """列出全部长期记忆，支持按类型过滤 + 分页。"""
    from sqlalchemy import func

    base = select(LongTermMemory).order_by(LongTermMemory.id.desc())
    count_stmt = select(func.count()).select_from(LongTermMemory)
    if memory_type != "ALL":
        base = base.where(LongTermMemory.memory_type == memory_type)
        count_stmt = count_stmt.where(LongTermMemory.memory_type == memory_type)
    total = await db.scalar(count_stmt) or 0
    rows = (await db.execute(base.offset((page - 1) * size).limit(size))).scalars().all()
    return Result.ok(MemoryListVO(
        total=total, page=page, size=size,
        records=[
            MemoryListItem(
                id=r.id, content=r.content, memory_type=r.memory_type,
                conversation_id=r.conversation_id,
                source=(r.meta or {}).get("source", "manual"),
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rows
        ],
    ))
```

### 前端（2 文件）

#### 3. `frontend/src/api/client.ts` - 新增 list 方法

```typescript
export const memory = {
  // ... existing save, search, remove ...
  list: (params: { memory_type?: string; page?: number; size?: number }) =>
    call<MemoryListVO>(`/api/memory/long-term?${new URLSearchParams({
      memory_type: params.memory_type || "ALL",
      page: String(params.page || 1),
      size: String(params.size || 20),
    })}`),
};
```

在 `types.ts` 新增：
```typescript
export interface MemoryListItem {
  id: number; content: string; memory_type: string;
  conversation_id: string | null; source: string; created_at: string;
}
export interface MemoryListVO {
  total: number; page: number; size: number; records: MemoryListItem[];
}
```

#### 4. `frontend/src/pages/Memory.tsx` - 增强页面

在现有页面基础上加子标签切换：
- **召回** (existing): 语义搜索（保持不变）
- **全部** (new): 列出所有记忆，支持类型过滤 + 分页 + 删除

新增子标签切换逻辑：
```tsx
type Tab = "recall" | "all";
const [tab, setTab] = useState<Tab>("recall");
```

"全部" 子标签内容：
- 类型过滤按钮：全部 / FACT / REFERENCE
- 记忆列表（复用现有记忆卡片样式，去掉 Meter，加 created_at 时间）
- 分页（上一页/下一页）
- 删除按钮（复用现有 remove 逻辑）
- 加载后自动刷新列表