// Knowledge - 上传知识文档(文本/文件) + RAG 混合检索(pg_trgm + 向量)
import { useRef, useState } from "react";
import { Library, Upload, Search, Trash2, FileUp } from "lucide-react";
import { knowledge } from "../api/client";
import type { KnowledgeSearchHit } from "../api/types";
import {
  Button,
  EmptyState,
  Field,
  Input,
  Meter,
  SuccessTick,
  Textarea,
  ToastBar,
  useToast,
} from "../components/ui";
import PageHeader from "../components/PageHeader";

export default function KnowledgePage() {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const showOk = (m: string) => {
    setOkMsg(m);
    setTimeout(() => setOkMsg(null), 2000);
  };
  // 上传表单
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [project, setProject] = useState("demo");
  const [uploading, setUploading] = useState(false);
  // 检索
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<KnowledgeSearchHit[]>([]);

  const upload = async () => {
    if (!title.trim() || !content.trim()) {
      toast.show(new Error("标题与内容不能为空"));
      return;
    }
    setUploading(true);
    try {
      await knowledge.upload({ title, content, source_type: "MANUAL", project_name: project });
      showOk("已上传");
      setTitle("");
      setContent("");
    } catch (e) {
      toast.show(e);
    } finally {
      setUploading(false);
    }
  };

  const uploadFile = async (f: File) => {
    setUploading(true);
    try {
      await knowledge.uploadFile(f, project);
      showOk(`已上传 ${f.name}`);
    } catch (e) {
      toast.show(e);
    } finally {
      setUploading(false);
    }
  };

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      setHits(await knowledge.search({ query, top_k: 5 }));
    } catch (e) {
      toast.show(e);
    } finally {
      setSearching(false);
    }
  };

  const remove = async (docId: number) => {
    try {
      await knowledge.remove(docId);
      setHits((h) => h.filter((x) => x.document_id !== docId));
    } catch (e) {
      toast.show(e);
    }
  };

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      {/* 上传面板 */}
      <div className="w-80 shrink-0 border-r border-line bg-panel p-4 overflow-y-auto">
        <PageHeader icon={Library} title="KNOWLEDGE" sub="RAG · pg_trgm + 向量" />
        <div className="space-y-3 mt-4">
          <Field label="标题">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Redis 缓存最佳实践" />
          </Field>
          <Field label="项目">
            <Input value={project} onChange={(e) => setProject(e.target.value)} />
          </Field>
          <Field label="文档内容" hint="Markdown 可用">
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={10}
              placeholder={"## 缓存击穿\n热点 Key 失效方案…"}
            />
          </Field>
          <Button onClick={upload} loading={uploading} className="w-full justify-center">
            <Upload className="w-4 h-4" /> 上传文本
          </Button>
          {okMsg && (
            <div className="flex justify-center">
              <SuccessTick>{okMsg}</SuccessTick>
            </div>
          )}
          <div className="relative">
            <div className="my-2 border-t border-line" />
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.html,.htm,.md,.markdown,.txt"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0])}
            />
            <Button variant="ghost" onClick={() => fileRef.current?.click()} className="w-full justify-center">
              <FileUp className="w-4 h-4" /> 上传文件 (PDF/DOCX/HTML/MD/TXT · 最大 5 MiB)
            </Button>
          </div>
        </div>
      </div>

      {/* 检索区 */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="max-w-4xl">
          <div className="flex gap-2 mb-5">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="检索知识库，如「缓存击穿如何解决」"
            />
            <Button onClick={search} loading={searching}>
              <Search className="w-4 h-4" /> 检索
            </Button>
          </div>

          {hits.length === 0 && !searching ? (
            <EmptyState
              icon={<Library className="w-10 h-10" />}
              title="知识库检索"
              hint="上传文档后输入查询，混合检索（关键词 pg_trgm + 向量语义）返回相关分块。"
            />
          ) : searching ? (
            <p className="font-mono text-2xs text-mute tracking-techy animate-blink">SEARCHING…</p>
          ) : (
            <div className="space-y-3">
              <p className="font-mono text-2xs uppercase tracking-techy text-mute">
                {hits.length} 条命中 · RRF 融合
              </p>
              {hits.map((h, i) => (
                <div key={i} className="bg-panel border border-line rounded p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="tag">{h.match_type}</span>
                      <span className="font-mono text-2xs text-mute tracking-techy">
                        DOC #{h.document_id}
                      </span>
                    </div>
                    <button
                      onClick={() => remove(h.document_id)}
                      className="text-mute hover:text-oxblood"
                      title="删除该文档"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="flex items-center gap-3 mb-2">
                    <Meter value={h.score} max={1} />
                    <span className="font-mono text-2xs text-mute w-10 text-right">
                      {h.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="font-mono text-2xs text-ink whitespace-pre-wrap leading-relaxed">
                    {h.chunk_content}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
