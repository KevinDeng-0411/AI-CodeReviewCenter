// 后端 API 请求/响应类型 - 对齐 codeaware-py 的 Pydantic schemas + router 投影
// 统一响应包络：{ code: 1|0, msg, data }，code=1 成功

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
  ai_model?: string;
}

// ---------- Chat ----------
export interface ChatResponseVO {
  conversation_id: string;
  reply: string;
  memory_summary?: string | null;
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
  similarity: number;
}

// ---------- Prompt ----------
export interface PromptTemplateItem {
  id: number;
  type: string;
  version: number;
  name: string;
  is_active: boolean;
}
