// 后端 API 请求/响应类型 - 对齐 codeaware-py 的 Pydantic schemas + router 投影
// 统一响应包络：{ code: 1|0, msg, data }，code=1 成功
import type { WarningComponent } from "./chatEvents";

export interface Envelope<T> {
  code: number;
  msg: string;
  data: T;
}

// ---------- Code Review ----------
export interface ReviewIssue {
  dimension: string;
  severity: string; // Critical | Warning | Info
  line_range: string;
  title: string;
  description: string;
  suggestion: string;
  fix_code?: string | null;
}
export interface CodeReviewVO {
  id?: number;
  project_name?: string;
  file_path?: string;
  summary: string;
  score: number;
  issues: ReviewIssue[];
  highlights: string[];
  issues_count: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  ai_model?: string;
}

// ---------- Unit Test ----------
export interface UnitTestVO {
  id?: number;
  project_name?: string;
  file_path?: string;
  test_code: string;
  test_framework: string;
  ai_model?: string;
}

// ---------- AI ReadMe ----------
export interface AiReadmeVO {
  id?: number;
  project_name: string;
  title: string;
  content: string;
  version: number;
  snapshot_hash: string | null;
  snapshot_file_count: number | null;
  snapshot_generated_at: string | null;
  snapshot_truncated: boolean | null;
  ai_model?: string;
}

export interface AiReadmeCapability {
  enabled: boolean;
  reason: "available" | "disabled" | "roots_unavailable";
}

// ---------- Chat ----------
export interface ChatWarning {
  component: WarningComponent;
  code: string;
  message: string;
  retryable: boolean;
}

export interface ChatResponseVO {
  conversation_id: string;
  reply: string;
  memory_summary?: string | null;
  warnings: ChatWarning[];
}
export interface ConversationItem {
  id: number;
  conversation_id: string;
  title?: string | null;
  summary?: string | null;
}
export interface ChatMessage {
  role: string; // USER | ASSISTANT
  content: string;
}

// ---------- Knowledge ----------
export interface KnowledgeSearchHit {
  score: number;
  matchType: string; // vector | keyword | both
  document_id: number;
  chunk_content: string;
}

// ---------- Memory ----------
export interface MemoryHit {
  id: number;
  content: string;
  memory_type: string;
  conversation_id?: string | null;
  source?: string; // "conversation"（对话内生）| "manual"（手动录入）
  similarity: number;
}

// ---------- Prompt ----------
export interface PromptTemplateItem {
  id: number;
  type: "CODE_REVIEW" | "UNIT_TEST" | "AI_README" | "CHAT";
  version: number;
  name: string;
  role_setting: string;
  template_body: string;
  review_dimensions: string | null;
  severity_levels: string | null;
  is_active: boolean;
  created_at: string;
}

export interface PromptCreateInput {
  type: PromptTemplateItem["type"];
  name: string;
  role_setting: string;
  template_body: string;
  review_dimensions?: string | null;
  severity_levels?: string | null;
}
