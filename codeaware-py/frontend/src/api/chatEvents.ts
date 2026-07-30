// C1-A: typed Chat SSE 事件类型（对齐后端 app/schemas/chat_events.py）

export interface ChatEventBase {
  protocol_version: 1;
  conversation_id: string;
  turn_id: string;
  sequence: number;
}

export interface ChatStarted extends ChatEventBase {
  created: boolean;
}
export interface ContextWarning extends ChatEventBase {
  component: string;
  code: string;
  message: string;
  retryable: boolean;
}
export interface TokenDelta extends ChatEventBase {
  delta: string;
}
export interface PostTurnWarning extends ChatEventBase {
  component: string;
  code: string;
  message: string;
  retryable: boolean;
}
export interface ChatCompleted extends ChatEventBase {
  assistant_message_id: number;
  warning_count: number;
}
export interface ErrorInfo {
  code: string;
  message: string;
  retryable: boolean;
}
export interface ChatFailed extends ChatEventBase {
  phase: string;
  error: ErrorInfo;
  partial_output_persisted: boolean;
}

export type ChatEvent =
  | ChatStarted
  | ContextWarning
  | TokenDelta
  | PostTurnWarning
  | ChatCompleted
  | ChatFailed;

export const EVENT_NAMES = [
  "chat.started",
  "context.warning",
  "token.delta",
  "post_turn.warning",
  "chat.completed",
  "chat.failed",
] as const;

export type EventName = (typeof EVENT_NAMES)[number];
