// Markdown 渲染器 - Chat 回复 / AIReadMe 文档，含代码高亮
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useState } from "react";
import { Check, Copy } from "lucide-react";

function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="group relative my-3 rounded overflow-hidden border border-line">
      <div className="flex items-center justify-between px-3 py-1.5 bg-graph border-b border-line">
        <span className="font-mono text-2xs uppercase tracking-techy text-mute">
          {language || "code"}
        </span>
        <button
          onClick={copy}
          className="text-mute hover:text-ink transition-colors"
          aria-label="复制代码"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-teal" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={vscDarkPlus}
        customStyle={{ margin: 0, fontSize: "12.5px", padding: "12px 14px" }}
      >
        {value}
      </SyntaxHighlighter>
    </div>
  );
}

export default function Markdown({ children }: { children: string }) {
  return (
    <div className="prose-code:text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // react-markdown v9 不再传 inline；按 language class / 换行判断行内代码
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const value = String(children).replace(/\n$/, "");
            const isInline = !match && !value.includes("\n");
            if (isInline) {
              return (
                <code
                  className="font-mono text-2xs px-1 py-0.5 bg-graph rounded text-ink"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return <CodeBlock language={match?.[1] ?? ""} value={value} />;
          },
          p: ({ children }) => <p className="my-2 text-sm text-ink">{children}</p>,
          h1: ({ children }) => <h1 className="text-lg font-semibold mt-4 mb-2 text-ink">{children}</h1>,
          h2: ({ children }) => <h2 className="text-base font-semibold mt-3 mb-2 text-ink">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1 text-ink">{children}</h3>,
          ul: ({ children }) => <ul className="list-disc pl-5 my-2 text-sm text-ink space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 my-2 text-sm text-ink space-y-0.5">{children}</ol>,
          strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-oxblood underline">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <table className="my-2 w-full text-xs border-collapse">{children}</table>
          ),
          th: ({ children }) => (
            <th className="border border-line bg-graph px-2 py-1 text-left font-mono uppercase tracking-techy text-mute">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-line px-2 py-1 text-ink">{children}</td>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-oxblood/40 pl-3 my-2 text-mute italic text-sm">
              {children}
            </blockquote>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
