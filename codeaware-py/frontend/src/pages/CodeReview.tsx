// Code Review - 七层结构化 Prompt。输入代码 -> 评分读数 + 按 severity 着色的问题卡
import { useState } from "react";
import { ScanSearch, FileCode2, Lightbulb } from "lucide-react";
import { codeReview } from "../api/client";
import type { CodeReviewVO, ReviewIssue } from "../api/types";
import {
  Button,
  EmptyState,
  Field,
  Input,
  SeverityBadge,
  SignalTrace,
  Textarea,
  ToastBar,
  useToast,
} from "../components/ui";

const SAMPLE = `public void save(String name) {
  String sql = "DELETE FROM users WHERE name=" + name;
  jdbc.execute(sql);
}`;

export default function CodeReviewPage() {
  const toast = useToast();
  const [project, setProject] = useState("demo");
  const [file, setFile] = useState("UserService.java");
  const [code, setCode] = useState(SAMPLE);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CodeReviewVO | null>(null);

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      setResult(await codeReview.review({ project_name: project, file_path: file, source_code: code }));
    } catch (e) {
      toast.show(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      {/* 输入控制板 */}
      <div className="w-80 shrink-0 border-r border-line bg-panel p-4 overflow-y-auto">
        <Header icon={ScanSearch} title="CODE REVIEW" sub="七层结构化 Prompt · 8 维度" />
        <div className="space-y-3 mt-4">
          <Field label="项目">
            <Input value={project} onChange={(e) => setProject(e.target.value)} />
          </Field>
          <Field label="文件路径">
            <Input value={file} onChange={(e) => setFile(e.target.value)} />
          </Field>
          <Field label="源代码" hint="粘贴待评审代码">
            <Textarea value={code} onChange={(e) => setCode(e.target.value)} rows={16} />
          </Field>
          <Button onClick={run} loading={loading} className="w-full justify-center">
            <ScanSearch className="w-4 h-4" /> 开始评审
          </Button>
        </div>
      </div>

      {/* 读数区 */}
      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <SignalTrace label="ANALYZING" />
            <p className="font-mono text-2xs text-mute tracking-techy">8 维度评审进行中…</p>
          </div>
        ) : !result ? (
          <EmptyState
            icon={<FileCode2 className="w-10 h-10" />}
            title="等待评审"
            hint="粘贴代码后点击「开始评审」，AI 将从 8 个维度输出结构化问题与评分。"
          />
        ) : (
          <ResultReadout r={result} />
        )}
      </div>
    </div>
  );
}

function ResultReadout({ r }: { r: CodeReviewVO }) {
  const total = r.issues_count || 1;
  return (
    <div className="max-w-4xl space-y-5">
      {/* 评分读数面板 - hero */}
      <div className="readout graph-paper p-5 flex items-center gap-6">
        <div>
          <div className="font-mono text-2xs uppercase tracking-techy text-mute">SCORE</div>
          <div
            className={`font-mono text-5xl font-semibold leading-none mt-1 ${
              r.score < 40 ? "text-oxblood" : r.score < 70 ? "text-amber" : "text-teal"
            }`}
          >
            {r.score}
          </div>
          <div className="font-mono text-2xs text-mute mt-1">/ 100</div>
        </div>
        <div className="flex-1">
          {/* severity 堆叠仪表 */}
          <div className="flex h-2 rounded overflow-hidden mb-2">
            <div className="bg-oxblood" style={{ width: `${(r.critical_count / total) * 100}%` }} />
            <div className="bg-amber" style={{ width: `${(r.warning_count / total) * 100}%` }} />
            <div className="bg-teal" style={{ width: `${(r.info_count / total) * 100}%` }} />
          </div>
          <div className="flex gap-4 font-mono text-2xs tracking-techy">
            <span className="text-oxblood">CRITICAL {r.critical_count}</span>
            <span className="text-amber">WARNING {r.warning_count}</span>
            <span className="text-teal">INFO {r.info_count}</span>
            <span className="text-mute">TOTAL {r.issues_count}</span>
          </div>
        </div>
      </div>

      <p className="text-sm text-ink leading-relaxed bg-panel border border-line rounded p-4">
        {r.summary}
      </p>

      {r.highlights.length > 0 && (
        <div className="flex items-start gap-2 flex-wrap">
          <Lightbulb className="w-4 h-4 text-teal mt-0.5" />
          {r.highlights.map((h, i) => (
            <span key={i} className="tag">
              {h}
            </span>
          ))}
        </div>
      )}

      {/* 问题卡 */}
      <div className="space-y-3">
        {r.issues.map((issue, i) => (
          <IssueCard key={i} issue={issue} />
        ))}
      </div>
    </div>
  );
}

function IssueCard({ issue }: { issue: ReviewIssue }) {
  return (
    <div className="bg-panel border border-line rounded p-4">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <SeverityBadge severity={issue.severity} />
        <span className="tag">{issue.dimension}</span>
        <span className="font-mono text-2xs text-mute tracking-techy">L{issue.line_range}</span>
      </div>
      <h4 className="text-sm font-semibold text-ink mb-1">{issue.title}</h4>
      <p className="text-xs text-mute mb-2">{issue.description}</p>
      <div className="text-xs text-ink">
        <span className="font-mono text-2xs uppercase tracking-techy text-teal">建议 · </span>
        {issue.suggestion}
      </div>
      {issue.fix_code && (
        <div className="mt-2 readout p-3 font-mono text-2xs text-ink whitespace-pre-wrap overflow-x-auto">
          {issue.fix_code}
        </div>
      )}
    </div>
  );
}

function Header({ icon: Icon, title, sub }: { icon: typeof ScanSearch; title: string; sub: string }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="w-4 h-4 text-oxblood" />
      <span className="font-mono text-sm font-semibold tracking-techy">{title}</span>
      <span className="font-mono text-2xs text-mute tracking-techy">· {sub}</span>
    </div>
  );
}
