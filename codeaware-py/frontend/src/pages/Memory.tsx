// Memory - 长期记忆录入 + 语义相似度召回（VU 电平条）
import { useState } from "react";
import { Brain, Save, Search, Trash2 } from "lucide-react";
import { memory } from "../api/client";
import type { MemoryHit } from "../api/types";
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

export default function MemoryPage() {
  const toast = useToast();
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

  const remove = async (id: number) => {
    try {
      await memory.remove(id);
      setHits((h) => h.filter((x) => x.id !== id));
    } catch (e) {
      toast.show(e);
    }
  };

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      {/* 录入面板 */}
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

      {/* 召回区 */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="max-w-4xl">
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
                      onClick={() => remove(h.id)}
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
        </div>
      </div>
    </div>
  );
}
