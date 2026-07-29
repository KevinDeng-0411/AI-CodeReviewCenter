// Prompt - 模板列表 + 预览渲染 + 激活（ADR-0005 版本化）
import { useEffect, useState } from "react";
import { Settings2, Eye, Check } from "lucide-react";
import { prompt } from "../api/client";
import type { PromptTemplateItem } from "../api/types";
import { Button, EmptyState, Input, ToastBar, useToast } from "../components/ui";
import PageHeader from "../components/PageHeader";

const TYPES = ["ALL", "CODE_REVIEW", "CHAT", "UNIT_TEST", "AI_README"];

export default function PromptPage() {
  const toast = useToast();
  const [type, setType] = useState("ALL");
  const [items, setItems] = useState<PromptTemplateItem[]>([]);
  const [selected, setSelected] = useState<PromptTemplateItem | null>(null);
  const [sample, setSample] = useState("public class Test {}");
  const [preview, setPreview] = useState("");
  const [loadingPrev, setLoadingPrev] = useState(false);
  const [activating, setActivating] = useState(false);

  const refresh = async () => {
    try {
      setItems(await prompt.list(type === "ALL" ? undefined : type));
    } catch (e) {
      toast.show(e);
    }
  };
  useEffect(() => {
    refresh();
  }, [type]);

  const doPreview = async (t: PromptTemplateItem) => {
    setSelected(t);
    setLoadingPrev(true);
    setPreview("");
    try {
      const r = await prompt.preview(t.id, t.type === "CODE_REVIEW" ? sample : "");
      setPreview(r.rendered);
    } catch (e) {
      toast.show(e);
    } finally {
      setLoadingPrev(false);
    }
  };

  const activate = async (t: PromptTemplateItem) => {
    setActivating(true);
    try {
      await prompt.activate(t.id);
      await refresh();
    } catch (e) {
      toast.show(e);
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      {/* 列表 */}
      <div className="w-96 shrink-0 border-r border-line bg-panel flex flex-col">
        <div className="p-4 border-b border-line">
          <PageHeader icon={Settings2} title="PROMPT" sub="版本化 · 每 type 恰一激活" />
          <div className="flex flex-wrap gap-1 mt-3">
            {TYPES.map((t) => (
              <button
                key={t}
                onClick={() => setType(t)}
                className={`font-mono text-2xs uppercase tracking-techy px-2 py-1 rounded border transition-colors ${
                  type === t
                    ? "bg-oxblood text-paper border-oxblood"
                    : "border-line text-mute hover:text-ink"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {items.length === 0 ? (
            <EmptyState icon={<Settings2 className="w-8 h-8" />} title="无模板" />
          ) : (
            items.map((t) => (
              <button
                key={t.id}
                onClick={() => doPreview(t)}
                className={`w-full text-left px-3 py-2.5 rounded mb-1 border transition-colors ${
                  selected?.id === t.id ? "bg-graph border-line" : "border-transparent hover:bg-graph/60"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-ink">{t.name}</span>
                  {t.is_active && <Check className="w-3.5 h-3.5 text-teal" />}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="font-mono text-2xs text-mute tracking-techy">v{t.version}</span>
                  <span className="font-mono text-2xs text-mute tracking-techy">#{t.id}</span>
                  <span
                    className={`font-mono text-2xs tracking-techy ${t.is_active ? "text-teal" : "text-mute/50"}`}
                  >
                    {t.is_active ? "ACTIVE" : "INACTIVE"}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* 预览 */}
      <div className="flex-1 overflow-y-auto p-5">
        {!selected ? (
          <EmptyState
            icon={<Eye className="w-10 h-10" />}
            title="选择模板预览"
            hint="点击左侧模板查看渲染效果；CODE_REVIEW 模板可用示例代码渲染占位符。"
          />
        ) : (
          <div className="max-w-4xl space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-ink">{selected.name}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className="tag">{selected.type}</span>
                  <span className="font-mono text-2xs text-mute tracking-techy">v{selected.version}</span>
                  {selected.is_active && <span className="tag text-teal border-teal/30">ACTIVE</span>}
                </div>
              </div>
              {!selected.is_active && (
                <Button onClick={() => activate(selected)} loading={activating}>
                  <Check className="w-4 h-4" /> 激活此版本
                </Button>
              )}
            </div>

            {selected.type === "CODE_REVIEW" && (
              <Input value={sample} onChange={(e) => setSample(e.target.value)} placeholder="示例代码" />
            )}

            <div>
              <div className="font-mono text-2xs uppercase tracking-techy text-mute mb-2">
                渲染结果
              </div>
              {loadingPrev ? (
                <p className="font-mono text-2xs text-mute tracking-techy animate-blink">RENDERING…</p>
              ) : (
                <pre className="readout graph-paper p-4 font-mono text-2xs text-ink whitespace-pre-wrap leading-relaxed overflow-x-auto">
                  {preview || "（空）"}
                </pre>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
