// Unit Test - 粘贴代码 + 选框架 -> 生成测试代码（高亮 + 复制）
import { useState } from "react";
import { FlaskConical, FileCode2, Copy, Check } from "lucide-react";
import { unitTest } from "../api/client";
import type { UnitTestVO } from "../api/types";
import {
  Button,
  EmptyState,
  Field,
  Input,
  Textarea,
  SignalTrace,
  ToastBar,
  useToast,
} from "../components/ui";
import PageHeader from "../components/PageHeader";
import Markdown from "../components/Markdown";

const SAMPLE = `public class Calc {
  public int add(int a, int b) { return a + b; }
}`;

export default function UnitTestPage() {
  const toast = useToast();
  const [project, setProject] = useState("demo");
  const [file, setFile] = useState("Calc.java");
  const [code, setCode] = useState(SAMPLE);
  const [framework, setFramework] = useState("JUnit5");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<UnitTestVO | null>(null);
  const [copied, setCopied] = useState(false);

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      setResult(
        await unitTest.generate({ project_name: project, file_path: file, source_code: code, test_framework: framework }),
      );
    } catch (e) {
      toast.show(e);
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    if (result) {
      navigator.clipboard.writeText(result.test_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      <div className="w-80 shrink-0 border-r border-line bg-panel p-4 overflow-y-auto">
        <PageHeader icon={FlaskConical} title="UNIT TEST" sub="AAA 模式 · 三场景覆盖" />
        <div className="space-y-3 mt-4">
          <Field label="项目">
            <Input value={project} onChange={(e) => setProject(e.target.value)} />
          </Field>
          <Field label="文件路径">
            <Input value={file} onChange={(e) => setFile(e.target.value)} />
          </Field>
          <Field label="测试框架">
            <Input value={framework} onChange={(e) => setFramework(e.target.value)} />
          </Field>
          <Field label="源代码">
            <Textarea value={code} onChange={(e) => setCode(e.target.value)} rows={14} />
          </Field>
          <Button onClick={run} loading={loading} className="w-full justify-center">
            <FlaskConical className="w-4 h-4" /> 生成单测
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <SignalTrace label="GENERATING" />
            <p className="font-mono text-2xs text-mute tracking-techy">生成测试用例中…</p>
          </div>
        ) : !result ? (
          <EmptyState
            icon={<FileCode2 className="w-10 h-10" />}
            title="等待生成"
            hint="粘贴源码后生成覆盖正常/边界/异常场景的单元测试。"
          />
        ) : (
          <div className="max-w-4xl">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="tag">{result.test_framework}</span>
                <span className="font-mono text-2xs text-mute tracking-techy">
                  {result.test_code.split("\n").length} 行
                </span>
              </div>
              <Button variant="ghost" onClick={copy}>
                {copied ? <Check className="w-3.5 h-3.5 text-teal" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? "已复制" : "复制"}
              </Button>
            </div>
            <Markdown>{`\`\`\`java\n${result.test_code}\n\`\`\``}</Markdown>
          </div>
        )}
      </div>
    </div>
  );
}
