// API client - 解包统一响应包络，失败抛 ApiError；SSE 流式单独处理
import type {
  AiReadmeVO,
  ChatMessage,
  ChatResponseVO,
  CodeReviewVO,
  ConversationItem,
  Envelope,
  KnowledgeSearchHit,
  MemoryHit,
  PromptTemplateItem,
  UnitTestVO,
} from "./types";

export class ApiError extends Error {
  msg: string;
  constructor(msg: string) {
    super(msg);
    this.name = "ApiError";
    this.msg = msg;
  }
}

const BASE = ""; // 同源 / Vite 代理 /api

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(`HTTP ${res.status}: 响应非 JSON`);
  }
  if (body.code !== 1) throw new ApiError(body.msg || `HTTP ${res.status}`);
  return body.data;
}

// ---------- Code Review ----------
export const codeReview = {
  review: (p: { project_name: string; file_path: string; source_code: string }) =>
    call<CodeReviewVO>("/api/code-review/review", {
      method: "POST",
      body: JSON.stringify(p),
    }),
};

// ---------- Unit Test ----------
export const unitTest = {
  generate: (p: {
    project_name: string;
    file_path: string;
    source_code: string;
    test_framework: string;
  }) => call<UnitTestVO>("/api/unit-test/generate", { method: "POST", body: JSON.stringify(p) }),
};

// ---------- AI ReadMe ----------
export const aiReadme = {
  generate: (p: { project_name: string; project_path: string }) =>
    call<AiReadmeVO>("/api/ai-readme/generate", { method: "POST", body: JSON.stringify(p) }),
  get: (project_name: string) => call<AiReadmeVO | null>(`/api/ai-readme/${encodeURIComponent(project_name)}`),
};

// ---------- Chat ----------
export const chat = {
  send: (p: { conversation_id?: string; message: string }) =>
    call<ChatResponseVO>("/api/chat/send", { method: "POST", body: JSON.stringify(p) }),
  conversations: () => call<ConversationItem[]>("/api/chat/conversations"),
  messages: (cid: string) => call<ChatMessage[]>(`/api/chat/conversations/${cid}`),
  delete: (cid: string) =>
    call<null>(`/api/chat/conversations/${cid}`, { method: "DELETE" }),
};

/**
 * SSE 流式对话。后端逐行发 `data: <token>\n\n`，末尾 `data: [DONE]\n\n`。
 * 用 fetch + ReadableStream 解析（EventSource 不支持 POST）。
 * onToken 收到每个 token；返回完整回复。
 */
export async function chatStream(
  p: { conversation_id?: string; message: string },
  onToken: (token: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch(`${BASE}/api/chat/send/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const payload = trimmed.slice(5).trim();
      if (payload === "[DONE]") continue;
      if (payload) {
        full += payload;
        onToken(payload);
      }
    }
  }
  return full;
}

// ---------- Knowledge ----------
export const knowledge = {
  upload: (p: { title: string; content: string; source_type: string; project_name?: string }) =>
    call<{ id: number; title: string }>("/api/knowledge/upload", {
      method: "POST",
      body: JSON.stringify(p),
    }),
  uploadFile: async (file: File, project_name?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (project_name) fd.append("project_name", project_name);
    const res = await fetch(`${BASE}/api/knowledge/upload-file`, { method: "POST", body: fd });
    const body = (await res.json()) as Envelope<{ id: number; title: string }>;
    if (body.code !== 1) throw new ApiError(body.msg);
    return body.data;
  },
  search: (p: { query: string; top_k?: number }) =>
    call<KnowledgeSearchHit[]>("/api/knowledge/search", {
      method: "POST",
      body: JSON.stringify({ query: p.query, top_k: p.top_k ?? 5 }),
    }),
  remove: (id: number) => call<null>(`/api/knowledge/${id}`, { method: "DELETE" }),
};

// ---------- Memory ----------
export const memory = {
  save: (p: { content: string; memory_type?: string; conversation_id?: string; metadata?: object }) =>
    call<{ id: number; content: string }>("/api/memory/long-term", {
      method: "POST",
      body: JSON.stringify({ memory_type: "KNOWLEDGE", ...p }),
    }),
  search: (query: string, threshold = 0.3, topK = 5) =>
    call<MemoryHit[]>(
      `/api/memory/long-term/search?query=${encodeURIComponent(query)}&threshold=${threshold}&topK=${topK}`,
    ),
  remove: (id: number) => call<null>(`/api/memory/long-term/${id}`, { method: "DELETE" }),
};

// ---------- Prompt ----------
export const prompt = {
  list: (type?: string) =>
    call<PromptTemplateItem[]>(`/api/prompts${type ? `?type=${type}` : ""}`),
  preview: (id: number, sampleCode = "") =>
    call<{ rendered: string }>(
      `/api/prompts/${id}/preview?sampleCode=${encodeURIComponent(sampleCode)}`,
    ),
  activate: (id: number) =>
    call<{ id: number; version: number; is_active: boolean }>(`/api/prompts/${id}/activate`, {
      method: "POST",
    }),
};
