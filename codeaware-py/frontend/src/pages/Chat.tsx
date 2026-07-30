// Chat - 核心域。SSE 流式 + 多轮 + 会话侧栏 + 信号轨迹
import { useEffect, useRef, useState } from "react";
import { MessageSquare, Plus, Send, Trash2, User, Cpu } from "lucide-react";
import { chat, chatStream, ApiError } from "../api/client";
import type { ChatMessage, ConversationItem } from "../api/types";
import { Button, EmptyState, SignalTrace, ToastBar, useToast } from "../components/ui";
import Markdown from "../components/Markdown";

export default function ChatPage() {
  const toast = useToast();
  const [convs, setConvs] = useState<ConversationItem[]>([]);
  const [activeCid, setActiveCid] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [loadingConv, setLoadingConv] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const refreshConvs = async () => {
    try {
      setConvs(await chat.conversations());
    } catch (e) {
      toast.show(e);
    }
  };
  useEffect(() => {
    refreshConvs();
  }, []);

  // 自动滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const newChat = () => {
    abortRef.current?.abort();
    setActiveCid(null);
    setMessages([]);
    setInput("");
    setStreaming(false);
  };

  const selectConv = async (cid: string) => {
    if (streaming) return;
    setActiveCid(cid);
    setLoadingConv(true);
    try {
      setMessages(await chat.messages(cid));
    } catch (e) {
      toast.show(e);
    } finally {
      setLoadingConv(false);
    }
  };

  const deleteConv = async (cid: string) => {
    try {
      await chat.delete(cid);
      if (activeCid === cid) newChat();
      refreshConvs();
    } catch (e) {
      toast.show(e);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setStreaming(true);
    setWarnings([]);
    const userMsg: ChatMessage = { role: "USER", content: text };
    const aiMsg: ChatMessage = { role: "ASSISTANT", content: "" };
    setMessages((m) => [...m, userMsg, aiMsg]);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let cid = activeCid;
    try {
      await chatStream(
        { conversation_id: cid ?? undefined, message: text },
        {
          onStarted: (e) => {
            cid = e.conversation_id;
            setActiveCid(e.conversation_id); // 立即拿到 cid，不猜最新
          },
          onDelta: (e) => {
            setMessages((m) => {
              const next = [...m];
              next[next.length - 1] = {
                role: "ASSISTANT",
                content: next[next.length - 1].content + e.delta,
              };
              return next;
            });
          },
          onContextWarning: (e) => setWarnings((w) => [...w, e.message]),
          onPostWarning: (e) => setWarnings((w) => [...w, e.message]),
          onFailed: (e) => {
            setMessages((m) => {
              const next = [...m];
              next[next.length - 1] = {
                role: "ASSISTANT",
                content: `（生成失败：${e.error.message}）`,
              };
              return next;
            });
          },
          onUnknown: () => {
            setMessages((m) => {
              const next = [...m];
              next[next.length - 1] = {
                role: "ASSISTANT",
                content: "（协议版本不兼容，请升级前端）",
              };
              return next;
            });
          },
        },
        ctrl.signal,
      );
      setConvs(await chat.conversations());
    } catch (e) {
      if (e instanceof ApiError || (e instanceof Error && e.name !== "AbortError")) toast.show(e);
      const cancelled = e instanceof Error && e.name === "AbortError";
      setMessages((m) => {
        const next = [...m];
        const last = next[next.length - 1];
        if (last && last.role === "ASSISTANT" && !last.content) {
          next[next.length - 1] = {
            role: "ASSISTANT",
            content: cancelled ? "（生成已取消）" : "（生成中断）",
          };
        }
        return next;
      });
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  return (
    <div className="flex h-full">
      <ToastBar err={toast.err} onClose={toast.clear} />
      {/* 会话侧栏 */}
      <div className="w-56 shrink-0 border-r border-line bg-panel flex flex-col">
        <div className="p-3 border-b border-line">
          <Button variant="ghost" onClick={newChat} className="w-full justify-center">
            <Plus className="w-4 h-4" /> 新对话
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto py-1">
          {convs.length === 0 ? (
            <p className="text-2xs text-mute text-center mt-4 font-mono">NO CONVERSATIONS</p>
          ) : (
            convs.map((c) => (
              <div
                key={c.conversation_id}
                onClick={() => selectConv(c.conversation_id)}
                className={`group mx-2 my-0.5 px-2.5 py-2 rounded cursor-pointer border transition-colors ${
                  activeCid === c.conversation_id
                    ? "bg-graph border-line"
                    : "border-transparent hover:bg-graph/60"
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="text-xs font-medium text-ink truncate flex-1">
                    {c.title || "新对话"}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteConv(c.conversation_id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-mute hover:text-oxblood transition-opacity"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="font-mono text-2xs text-mute tracking-techy mt-0.5 truncate">
                  {c.conversation_id.slice(0, 12)}…
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 消息流 */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="px-5 py-3 border-b border-line flex items-center gap-2 bg-panel">
          <MessageSquare className="w-4 h-4 text-oxblood" />
          <span className="font-mono text-sm font-semibold tracking-techy">CHAT</span>
          <span className="font-mono text-2xs text-mute tracking-techy">
            · 两级记忆 + RAG 整合
          </span>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5">
          {messages.length === 0 && !loadingConv ? (
            <EmptyState
              icon={<MessageSquare className="w-10 h-10" />}
              title="开始一段对话"
              hint="AI 会整合长期记忆、知识库 RAG 与对话历史作答。支持多轮上下文与流式输出。"
            />
          ) : (
            <div className="max-w-3xl mx-auto space-y-5">
              {messages.map((m, i) => (
                <MessageBubble key={i} msg={m} streaming={streaming && i === messages.length - 1} />
              ))}
            </div>
          )}
        </div>

        {/* 降级提示（非阻塞） */}
        {warnings.length > 0 && (
          <div className="px-5 py-2 border-t border-amber/20 bg-amber/5 flex flex-wrap gap-x-4 gap-y-1">
            {warnings.map((w, i) => (
              <span key={i} className="font-mono text-2xs text-amber tracking-techy">
                ⚠ {w}
              </span>
            ))}
          </div>
        )}

        {/* 输入器 */}
        <div className="px-5 py-3 border-t border-line bg-panel">
          <div className="max-w-3xl mx-auto flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="输入消息，Enter 发送，Shift+Enter 换行"
              rows={1}
              className="flex-1 resize-none px-3 py-2 bg-paper border border-line rounded text-sm text-ink placeholder:text-mute/60 focus:outline-none focus:border-oxblood max-h-32"
            />
            <Button onClick={send} loading={streaming}>
              {!streaming && <Send className="w-4 h-4" />}
              {streaming ? "生成中" : "发送"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg, streaming }: { msg: ChatMessage; streaming: boolean }) {
  const isUser = msg.role === "USER";
  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`w-7 h-7 shrink-0 rounded flex items-center justify-center ${
          isUser ? "bg-oxblood text-paper" : "bg-ink text-paper"
        }`}
      >
        {isUser ? <User className="w-3.5 h-3.5" /> : <Cpu className="w-3.5 h-3.5" />}
      </div>
      <div className={`flex-1 min-w-0 ${isUser ? "text-right" : ""}`}>
        <div
          className={`font-mono text-2xs uppercase tracking-techy mb-1 ${
            isUser ? "text-oxblood" : "text-mute"
          }`}
        >
          {isUser ? "YOU" : "AI"}
        </div>
        <div
          className={`inline-block text-left rounded px-3.5 py-2.5 ${
            isUser ? "bg-oxblood/8 border border-oxblood/20" : "bg-panel border border-line"
          }`}
        >
          {isUser ? (
            <p className="text-sm text-ink whitespace-pre-wrap">{msg.content}</p>
          ) : msg.content ? (
            <Markdown>{msg.content}</Markdown>
          ) : (
            <SignalTrace />
          )}
          {streaming && msg.content && <SignalTrace label="STREAMING" />}
        </div>
      </div>
    </div>
  );
}
