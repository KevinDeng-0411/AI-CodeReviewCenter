// C1-A: SSE 解析 - 空行边界组帧，只去 data: 后一个可选空格，不 trim delta。
// 纯函数 parseSseEvents 可单测；consumeChatStream 消费 ReadableStream 并按事件分派。

import type {
  ChatCompleted,
  ChatFailed,
  ChatStarted,
  ContextWarning,
  PostTurnWarning,
  TokenDelta,
} from "./chatEvents";

export interface RawSseEvent {
  id?: string;
  event?: string;
  data: string;
}

/**
 * 解析 SSE 缓冲：按空行(\n\n，兼容 \r\n\r\n)切分完整事件，返回事件列表与未完成剩余。
 * data: 行只去除一个可选前导空格；多 data 行用 \n 拼接。不 trim JSON 内的 delta。
 */
export function parseSseEvents(buffer: string): { events: RawSseEvent[]; rest: string } {
  const events: RawSseEvent[] = [];
  const parts = buffer.split(/\r?\n\r?\n/); // 兼容 CRLF
  const rest = parts.pop() ?? ""; // 最后一段可能不完整

  for (const block of parts) {
    if (!block.trim()) continue;
    const dataLines: string[] = [];
    const ev: RawSseEvent = { data: "" };
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("id:")) {
        ev.id = line.slice(3).trim();
      } else if (line.startsWith("event:")) {
        ev.event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        // 仅去一个可选空格，保留 delta 内的空格/换行
        dataLines.push(line.slice(5).replace(/^ /, ""));
      }
    }
    ev.data = dataLines.join("\n");
    if (ev.event) events.push(ev);
  }
  return { events, rest };
}

export interface ChatStreamHandlers {
  onStarted?: (e: ChatStarted) => void;
  onDelta?: (e: TokenDelta) => void;
  onContextWarning?: (e: ContextWarning) => void;
  onPostWarning?: (e: PostTurnWarning) => void;
  onCompleted?: (e: ChatCompleted) => void;
  onFailed?: (e: ChatFailed) => void;
  onUnknown?: (info: { event?: string; data: string }) => void;
}

function dispatch(ev: RawSseEvent, h: ChatStreamHandlers): void {
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(ev.data);
  } catch {
    h.onUnknown?.({ event: ev.event, data: ev.data });
    return;
  }
  if (parsed.protocol_version !== 1) {
    h.onUnknown?.({ event: ev.event, data: ev.data });
    return;
  }
  switch (ev.event) {
    case "chat.started":
      h.onStarted?.(parsed as unknown as ChatStarted);
      break;
    case "token.delta":
      h.onDelta?.(parsed as unknown as TokenDelta);
      break;
    case "context.warning":
      h.onContextWarning?.(parsed as unknown as ContextWarning);
      break;
    case "post_turn.warning":
      h.onPostWarning?.(parsed as unknown as PostTurnWarning);
      break;
    case "chat.completed":
      h.onCompleted?.(parsed as unknown as ChatCompleted);
      break;
    case "chat.failed":
      h.onFailed?.(parsed as unknown as ChatFailed);
      break;
    default:
      h.onUnknown?.({ event: ev.event, data: ev.data });
  }
}

/** 消费 ReadableStream，跨 chunk 边界组帧并分派 typed 事件。 */
export async function consumeChatStream(
  body: ReadableStream<Uint8Array>,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSseEvents(buffer);
      buffer = rest;
      for (const ev of events) dispatch(ev, handlers);
    }
    // 流末尾可能残留一个完整事件（无尾随 \n\n）
    if (buffer.trim()) {
      const { events } = parseSseEvents(buffer + "\n\n");
      for (const ev of events) dispatch(ev, handlers);
    }
  } finally {
    if (signal?.aborted) {
      await reader.cancel().catch(() => {});
    }
  }
}
