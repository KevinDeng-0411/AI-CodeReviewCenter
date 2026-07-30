// AI ReadMe - 项目信息 -> 6 章节 Markdown 文档（渲染 / 源码切换）
import { useEffect, useState } from "react";
import { BookOpen, FileText, Eye, Code2 } from "lucide-react";
import { aiReadme } from "../api/client";
import type { AiReadmeCapability, AiReadmeVO } from "../api/types";
import { Button, EmptyState, Field, Input, SignalTrace, ToastBar, useToast } from "../components/ui";
import PageHeader from "../components/PageHeader";
import Markdown from "../components/Markdown";

function formatGeneratedAt(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default function AiReadmePage() {
  const toast = useToast();
  const [project, setProject] = useState("demo");
  const [path, setPath] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiReadmeVO | null>(null);
  const [view, setView] = useState<"render" | "source">("render");
  const [capability, setCapability] = useState<AiReadmeCapability | null>(null);
  const [capabilityLoading, setCapabilityLoading] = useState(true);
  const [capabilityError, setCapabilityError] = useState(false);

  useEffect(() => {
    let active = true;
    aiReadme
      .capabilities()
      .then((value) => {
        if (active) setCapability(value);
      })
      .catch(() => {
        if (active) setCapabilityError(true);
      })
      .finally(() => {
        if (active) setCapabilityLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const snapshotAvailable =
    capability?.enabled === true && capability.reason === "available" && !capabilityError;

  const run = async () => {
    if (!snapshotAvailable) return;
    setLoading(true);
    setResult(null);
    try {
      setResult(await aiReadme.generate({ project_name: project, project_path: path }));
    } catch (e) {
      toast.show(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      <div className="w-80 shrink-0 border-r border-line bg-panel p-4 overflow-y-auto">
        <PageHeader icon={BookOpen} title="AI README" sub="6 章节 · AI 友好文档" />
        <div className="space-y-3 mt-4">
          <Field label="项目名">
            <Input value={project} onChange={(e) => setProject(e.target.value)} />
          </Field>
          <Field label="项目路径">
            <Input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/absolute/path/to/project"
              disabled={!snapshotAvailable || loading}
            />
          </Field>
          <Button
            onClick={run}
            loading={loading}
            disabled={!snapshotAvailable || !project.trim() || !path.trim()}
            className="w-full justify-center"
          >
            <BookOpen className="w-4 h-4" /> 生成文档
          </Button>
          {capabilityLoading ? (
            <p className="text-2xs text-mute">正在检查本地项目快照能力…</p>
          ) : !snapshotAvailable ? (
            <p className="text-2xs text-amber">
              仅支持服务端允许的本地项目目录
              {capabilityError ? "（能力检查失败）" : ""}
            </p>
          ) : (
            <p className="text-2xs text-teal">本地项目快照能力可用</p>
          )}
          <div className="pt-2 border-t border-line mt-4">
            <p className="font-mono text-2xs uppercase tracking-techy text-mute mb-1.5">
              章节
            </p>
            <ul className="text-2xs text-mute space-y-0.5 font-mono">
              <li>01 技术架构</li>
              <li>02 核心流程</li>
              <li>03 开发指南</li>
              <li>04 项目结构</li>
              <li>05 业务知识</li>
              <li>06 历史经验</li>
            </ul>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <SignalTrace label="DRAFTING" />
            <p className="font-mono text-2xs text-mute tracking-techy">生成项目文档中…</p>
          </div>
        ) : !result ? (
          <EmptyState
            icon={<FileText className="w-10 h-10" />}
            title="等待生成"
            hint="填写项目信息，生成给 AI 编码助手作上下文的 README 文档。"
          />
        ) : (
          <div className="max-w-4xl">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 mb-4 rounded border border-line bg-panel p-3 font-mono text-2xs sm:grid-cols-5">
              <div>
                <dt className="text-mute">版本</dt>
                <dd className="text-ink">v{result.version}</dd>
              </div>
              <div>
                <dt className="text-mute">快照 Hash</dt>
                <dd className="text-ink" title={result.snapshot_hash ?? undefined}>
                  {result.snapshot_hash ? `${result.snapshot_hash.slice(0, 12)}…` : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-mute">文件数</dt>
                <dd className="text-ink">{result.snapshot_file_count ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-mute">生成时间</dt>
                <dd className="text-ink">{formatGeneratedAt(result.snapshot_generated_at)}</dd>
              </div>
              <div>
                <dt className="text-mute">截断</dt>
                <dd className="text-ink">
                  {result.snapshot_truncated == null
                    ? "—"
                    : result.snapshot_truncated
                      ? "是"
                      : "否"}
                </dd>
              </div>
            </dl>
            <div className="flex items-center gap-1 mb-4 border-b border-line pb-2">
              <button
                onClick={() => setView("render")}
                className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded ${
                  view === "render" ? "bg-graph text-ink" : "text-mute hover:text-ink"
                }`}
              >
                <Eye className="w-3.5 h-3.5" /> 渲染
              </button>
              <button
                onClick={() => setView("source")}
                className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded ${
                  view === "source" ? "bg-graph text-ink" : "text-mute hover:text-ink"
                }`}
              >
                <Code2 className="w-3.5 h-3.5" /> 源码
              </button>
            </div>
            {view === "render" ? (
              <Markdown>{result.content}</Markdown>
            ) : (
              <pre className="readout p-4 font-mono text-2xs text-ink whitespace-pre-wrap overflow-x-auto">
                {result.content}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
