// Prompt - 新建版本 + 模板列表 + 预览渲染 + 激活（ADR-0005 版本化）
import { useEffect, useState } from "react";
import { Settings2, Eye, Check, Plus, X } from "lucide-react";
import { prompt } from "../api/client";
import type { PromptCreateInput, PromptTemplateItem } from "../api/types";
import { Button, EmptyState, Field, Input, Textarea, ToastBar, useToast } from "../components/ui";
import PageHeader from "../components/PageHeader";

const TYPES = ["ALL", "CODE_REVIEW", "CHAT", "UNIT_TEST", "AI_README"];
const CREATE_TYPES: PromptCreateInput["type"][] = [
  "CODE_REVIEW",
  "CHAT",
  "UNIT_TEST",
  "AI_README",
];
const DEFAULT_BODIES: Record<PromptCreateInput["type"], string> = {
  CODE_REVIEW: "请评审以下代码：\n{{source_code}}",
  UNIT_TEST:
    "请为 {{file_path}} 生成 {{test_framework}} 测试：\n{{source_code}}",
  AI_README: "请为 {{project_name}}（{{project_path}}）生成项目说明。",
  CHAT:
    "长期记忆：\n{{long_term_memory}}\n\n知识：\n{{rag_context}}\n\n" +
    "历史：\n{{conversation_history}}\n\n用户：\n{{user_message}}",
};

function initialDraft(type: PromptCreateInput["type"] = "CODE_REVIEW"): PromptCreateInput {
  return {
    type,
    name: "",
    role_setting: "你是专业的软件研发助手。",
    template_body: DEFAULT_BODIES[type],
    review_dimensions: null,
    severity_levels: null,
  };
}

export default function PromptPage() {
  const toast = useToast();
  const [type, setType] = useState("ALL");
  const [items, setItems] = useState<PromptTemplateItem[]>([]);
  const [selected, setSelected] = useState<PromptTemplateItem | null>(null);
  const [sample, setSample] = useState("public class Test {}");
  const [preview, setPreview] = useState("");
  const [loadingPrev, setLoadingPrev] = useState(false);
  const [activating, setActivating] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<PromptCreateInput>(() => initialDraft());

  const refresh = async (): Promise<PromptTemplateItem[]> => {
    try {
      const next = await prompt.list(type === "ALL" ? undefined : type);
      setItems(next);
      return next;
    } catch (e) {
      toast.show(e);
      return [];
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
      const activated = await prompt.activate(t.id);
      setSelected(activated);
      await refresh();
    } catch (e) {
      toast.show(e);
    } finally {
      setActivating(false);
    }
  };

  const setDraftType = (nextType: PromptCreateInput["type"]) => {
    setDraft((current) => ({
      ...initialDraft(nextType),
      name: current.name,
      role_setting: current.role_setting,
    }));
  };

  const createVersion = async () => {
    setCreating(true);
    try {
      const created = await prompt.create({
        ...draft,
        review_dimensions: draft.review_dimensions || null,
        severity_levels: draft.severity_levels || null,
      });
      setType(created.type);
      setSelected(created);
      setShowCreate(false);
      setDraft(initialDraft(created.type));
      const rendered = await prompt.preview(created.id);
      setPreview(rendered.rendered);
      await refresh();
    } catch (e) {
      toast.show(e);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      {/* 列表 */}
      <div className="w-96 shrink-0 border-r border-line bg-panel flex flex-col">
        <div className="p-4 border-b border-line">
          <div className="flex items-start justify-between gap-2">
            <PageHeader icon={Settings2} title="PROMPT" sub="版本化 · 每 type 恰一激活" />
            <Button
              variant="ghost"
              onClick={() => setShowCreate((visible) => !visible)}
              aria-label={showCreate ? "关闭新建版本" : "新建 Prompt 版本"}
            >
              {showCreate ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            </Button>
          </div>
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
        {showCreate ? (
          <div className="max-w-3xl space-y-4">
            <div>
              <h3 className="text-base font-semibold text-ink">新建 Prompt 版本</h3>
              <p className="mt-1 text-xs text-mute">
                保存后创建并激活新版本；历史版本保持只读，可随时回滚激活。
              </p>
            </div>
            <Field label="类型">
              <select
                className="w-full px-3 py-2 bg-panel border border-line rounded text-sm text-ink"
                value={draft.type}
                onChange={(event) =>
                  setDraftType(event.target.value as PromptCreateInput["type"])
                }
              >
                {CREATE_TYPES.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="版本名称">
              <Input
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                placeholder="例如：review-security-v2"
              />
            </Field>
            <Field label="角色设定">
              <Textarea
                rows={3}
                value={draft.role_setting}
                onChange={(event) =>
                  setDraft({ ...draft, role_setting: event.target.value })
                }
              />
            </Field>
            <Field label="模板正文" hint="必须保留该类型要求的 {{placeholder}}">
              <Textarea
                rows={12}
                value={draft.template_body}
                onChange={(event) =>
                  setDraft({ ...draft, template_body: event.target.value })
                }
              />
            </Field>
            {draft.type === "CODE_REVIEW" && (
              <>
                <Field label="评审维度" hint="可选">
                  <Input
                    value={draft.review_dimensions ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, review_dimensions: event.target.value })
                    }
                  />
                </Field>
                <Field label="严重级别" hint="可选">
                  <Input
                    value={draft.severity_levels ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, severity_levels: event.target.value })
                    }
                  />
                </Field>
              </>
            )}
            <Button
              onClick={createVersion}
              loading={creating}
              disabled={!draft.name.trim() || !draft.role_setting.trim() || !draft.template_body.trim()}
            >
              <Plus className="w-4 h-4" /> 创建并激活
            </Button>
          </div>
        ) : !selected ? (
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
