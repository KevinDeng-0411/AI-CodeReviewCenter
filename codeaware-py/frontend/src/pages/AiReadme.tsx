// AI ReadMe - 项目信息 -> 6 章节 Markdown 文档（渲染 / 源码切换）
import { useState } from "react";
import { BookOpen, FileText, Eye, Code2 } from "lucide-react";
import { aiReadme } from "../api/client";
import type { AiReadmeVO } from "../api/types";
import { Button, EmptyState, Field, Input, SignalTrace, ToastBar, useToast } from "../components/ui";
import PageHeader from "../components/PageHeader";
import Markdown from "../components/Markdown";

export default function AiReadmePage() {
  const toast = useToast();
  const [project, setProject] = useState("demo");
  const [path, setPath] = useState("/home/demo");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiReadmeVO | null>(null);
  const [view, setView] = useState<"render" | "source">("render");

  const run = async () => {
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
            <Input value={path} onChange={(e) => setPath(e.target.value)} />
          </Field>
          <Button onClick={run} loading={loading} className="w-full justify-center">
            <BookOpen className="w-4 h-4" /> 生成文档
          </Button>
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
