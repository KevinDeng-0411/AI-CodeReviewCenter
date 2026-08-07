// Memory - 长期记忆管理 + 语义相似度召回（VU 电平条）
import { useEffect, useState } from "react";
import { Brain, Save, Search, Trash2, List, ChevronLeft, ChevronRight } from "lucide-react";
import { memory } from "../api/client";
import type { MemoryHit, MemoryListItem } from "../api/types";
import {
  Button,
  EmptyState,
  Field,
  Input,
  Meter,
  Textarea,
  ToastBar,
  useToast,
} from "../components/ui";
import PageHeader from "../components/PageHeader";

type Tab = "recall" | "all";
type MemTypeFilter = "ALL" | "FACT" | "REFERENCE";

export default function MemoryPage() {
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("recall");

  // ---- 录入 + 召回（原有逻辑）----
  const [content, setContent] = useState("");
  const memType = "REFERENCE";
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [threshold, setThreshold] = useState(0.3);
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<MemoryHit[]>([]);

  const save = async () => {
    if (!content.trim()) {
      toast.show(new Error("记忆内容不能为空"));
      return;
    }
    setSaving(true);
    try {
      await memory.save({ content, memory_type: memType });
      setContent("");
    } catch (e) {
      toast.show(e);
    } finally {
      setSaving(false);
    }
  };

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      setHits(await memory.search(query, threshold, 5));
    } catch (e) {
      toast.show(e);
    } finally {
      setSearching(false);
    }
  };

  const removeHit = async (id: number) => {
    try {
      await memory.remove(id);
      setHits((h) => h.filter((x) => x.id !== id));
    } catch (e) {
      toast.show(e);
    }
  };

  // ---- 全部记忆列表（新增）----
  const [memTypeFilter, setMemTypeFilter] = useState<MemTypeFilter>("ALL");
  const [memRecords, setMemRecords] = useState<MemoryListItem[]>([]);
  const [memTotal, setMemTotal] = useState(0);
  const [memPage, setMemPage] = useState(1);
  const [memSize] = useState(20);
  const [loadingList, setLoadingList] = useState(false);

  const loadList = async (filter: MemTypeFilter, page: number) => {
    setLoadingList(true);
    try {
      const data = await memory.list({ memory_type: filter, page, size: memSize });
      setMemRecords(data.records);
      setMemTotal(data.total);
      setMemPage(data.page);
    } catch (e) {
      toast.show(e);
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => {
    if (tab === "all") {
      loadList(memTypeFilter, 1);
    }
  }, [tab, memTypeFilter]);

  const removeListItem = async (id: number) => {
    try {
      await memory.remove(id);
      setMemRecords((r) => r.filter((x) => x.id !== id));
      setMemTotal((t) => t - 1);
    } catch (e) {
      toast.show(e);
    }
  };

  const totalPages = Math.ceil(memTotal / memSize);

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      {/* 左侧面板：录入 */}
      <div className="w-80 shrink-0 border-r border-line bg-panel p-4 overflow-y-auto">
        <PageHeader icon={Brain} title="MEMORY" sub="bge-m3 向量语义召回" />
        <div className="space-y-3 mt-4">
          <Field label="记忆类型">
            <Input value={memType} disabled />
            <p className="mt-1 font-mono text-2xs text-mute">
              手动录入固定为 REFERENCE；FACT 仅由 Chat 自动抽取。
            </p>
          </Field>
          <Field label="内容" hint="原子事实，不分块">
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={8}
              placeholder="团队使用 SQLAlchemy 2.0 作为 ORM 框架"
            />
          </Field>
          <Button onClick={save} loading={saving} className="w-full justify-center">
            <Save className="w-4 h-4" /> 录入记忆
          </Button>
          <div className="pt-2 border-t border-line text-2xs text-mute font-mono leading-relaxed">
            对话内生：Chat 达 2 轮后自动抽取原子事实落库（FACT，带 conversation_id）。
            vs 知识库 Knowledge = 外部上传文档-分块。同为向量召回，起源与结构不同（ADR-0001）。
          </div>
        </div>
      </div>

      {/* 右侧：子标签切换 */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="max-w-4xl">
          {/* 子标签 */}
          <div className="flex gap-1 mb-4 border-b border-line">
            <button
              onClick={() => setTab("recall")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase tracking-techy border-b-2 transition-colors ${
                tab === "recall"
                  ? "border-oxblood text-oxblood"
                  : "border-transparent text-mute hover:text-ink"
              }`}
            >
              <Search className="w-3.5 h-3.5" /> 语义召回
            </button>
            <button
              onClick={() => setTab("all")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase tracking-techy border-b-2 transition-colors ${
                tab === "all"
                  ? "border-oxblood text-oxblood"
                  : "border-transparent text-mute hover:text-ink"
              }`}
            >
              <List className="w-3.5 h-3.5" /> 全部记忆
            </button>
          </div>

          {/* 召回子标签 */}
          {tab === "recall" && (
            <>
              <div className="flex gap-2 mb-3">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && search()}
                  placeholder="自然语言查询，如「后端 ORM 框架」"
                />
                <Button onClick={search} loading={searching}>
                  <Search className="w-4 h-4" /> 召回
                </Button>
              </div>
              <div className="flex items-center gap-3 mb-5">
                <span className="font-mono text-2xs uppercase tracking-techy text-mute">
                  阈值 {threshold.toFixed(2)}
                </span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  className="flex-1 accent-oxblood"
                />
              </div>

              {hits.length === 0 && !searching ? (
                <EmptyState
                  icon={<Brain className="w-10 h-10" />}
                  title="语义召回"
                  hint="录入记忆后用自然语言查询，按向量相似度召回相关记忆。"
                />
              ) : searching ? (
                <p className="font-mono text-2xs text-mute tracking-techy animate-blink">RECALLING…</p>
              ) : (
                <div className="space-y-3">
                  {hits.map((h) => (
                    <div key={h.id} className="bg-panel border border-line rounded p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="tag">{h.memory_type}</span>
                          {h.source === "conversation" ? (
                            <span
                              className="font-mono text-2xs tracking-techy px-1.5 py-0.5 rounded border border-amber/30 text-amber bg-amber/10"
                              title={h.conversation_id || ""}
                            >
                              对话内生 · {(h.conversation_id || "").slice(0, 8)}…
                            </span>
                          ) : (
                            <span className="tag">手动录入</span>
                          )}
                        </div>
                        <button
                          onClick={() => removeHit(h.id)}
                          className="text-mute hover:text-oxblood"
                          title="删除记忆"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <div className="flex items-center gap-3 mb-2">
                        <Meter value={h.similarity} max={1} />
                        <span className="font-mono text-2xs text-mute w-10 text-right">
                          {h.similarity.toFixed(3)}
                        </span>
                      </div>
                      <p className="text-sm text-ink">{h.content}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* 全部记忆子标签 */}
          {tab === "all" && (
            <>
              {/* 类型过滤 */}
              <div className="flex items-center gap-2 mb-4">
                {(["ALL", "FACT", "REFERENCE"] as MemTypeFilter[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => setMemTypeFilter(t)}
                    className={`px-2.5 py-1 text-xs font-mono uppercase tracking-techy rounded border transition-colors ${
                      memTypeFilter === t
                        ? "border-oxblood text-oxblood bg-oxblood/5"
                        : "border-line text-mute hover:text-ink"
                    }`}
                  >
                    {t === "ALL" ? "全部" : t}
                  </button>
                ))}
                <span className="ml-auto font-mono text-2xs text-mute">
                  共 {memTotal} 条
                </span>
              </div>

              {/* 列表 */}
              {loadingList ? (
                <p className="font-mono text-2xs text-mute tracking-techy animate-blink">LOADING…</p>
              ) : memRecords.length === 0 ? (
                <EmptyState
                  icon={<Brain className="w-10 h-10" />}
                  title="暂无记忆"
                  hint="对话达 4 轮后自动抽取 FACT，或手动录入 REFERENCE。"
                />
              ) : (
                <div className="space-y-3">
                  {memRecords.map((m) => (
                    <div key={m.id} className="bg-panel border border-line rounded p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="tag">{m.memory_type}</span>
                          {m.source === "conversation" ? (
                            <span
                              className="font-mono text-2xs tracking-techy px-1.5 py-0.5 rounded border border-amber/30 text-amber bg-amber/10"
                              title={m.conversation_id || ""}
                            >
                              对话内生 · {(m.conversation_id || "").slice(0, 8)}…
                            </span>
                          ) : (
                            <span className="tag">手动录入</span>
                          )}
                          {m.created_at && (
                            <span className="font-mono text-2xs text-mute">
                              {m.created_at.slice(0, 19).replace("T", " ")}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => removeListItem(m.id)}
                          className="text-mute hover:text-oxblood"
                          title="删除记忆"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <p className="text-sm text-ink">{m.content}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* 分页 */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-4">
                  <button
                    onClick={() => loadList(memTypeFilter, memPage - 1)}
                    disabled={memPage <= 1}
                    className="p-1.5 rounded border border-line text-mute hover:text-ink disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span className="font-mono text-2xs text-mute">
                    {memPage} / {totalPages}
                  </span>
                  <button
                    onClick={() => loadList(memTypeFilter, memPage + 1)}
                    disabled={memPage >= totalPages}
                    className="p-1.5 rounded border border-line text-mute hover:text-ink disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}