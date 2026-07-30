// C1-A: SSE parser 单测 - 覆盖 chunk 边界、CRLF、多 data 行、空白保真、未知版本/事件。
import { describe, expect, it } from "vitest";
import { consumeChatStream, parseSseEvents } from "../api/sseParser";
import type { ChatStreamHandlers } from "../api/sseParser";

function sse(id: number, event: string, data: object): string {
  return `id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

describe("parseSseEvents", () => {
  it("解析单事件", () => {
    const { events, rest } = parseSseEvents(sse(1, "chat.started", { protocol_version: 1, conversation_id: "c1", turn_id: "t1", sequence: 1, created: true }));
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("chat.started");
    expect(events[0].id).toBe("1");
    expect(rest).toBe("");
  });

  it("CRLF 行尾兼容", () => {
    const buf = "id: 2\nevent: token.delta\r\ndata: " + JSON.stringify({ protocol_version: 1, conversation_id: "c", turn_id: "t", sequence: 2, delta: " hi" }) + "\r\n\r\n";
    const { events } = parseSseEvents(buf);
    expect(events[0].event).toBe("token.delta");
    expect(events[0].data).toContain('" hi"');
  });

  it("delta 前导空格保真（不 trim）", () => {
    const buf = sse(3, "token.delta", { protocol_version: 1, conversation_id: "c", turn_id: "t", sequence: 3, delta: " world" });
    const { events } = parseSseEvents(buf);
    const parsed = JSON.parse(events[0].data);
    expect(parsed.delta).toBe(" world");
  });

  it("多 data 行用 \\n 拼接", () => {
    const buf = "id: 1\nevent: token.delta\ndata: line1\ndata: line2\n\n";
    const { events } = parseSseEvents(buf);
    expect(events[0].data).toBe("line1\nline2");
  });

  it("未完成事件留在 rest（跨 chunk 边界）", () => {
    const part1 = "id: 1\nevent: token.delta\ndata: {\"delta\":\"he";
    const { events, rest } = parseSseEvents(part1);
    expect(events).toHaveLength(0);
    expect(rest).toBe(part1);
    // 第二 chunk 补全
    const part2 = 'llo"}\n\n';
    const { events: ev2 } = parseSseEvents(rest + part2);
    expect(ev2).toHaveLength(1);
    expect(JSON.parse(ev2[0].data).delta).toBe("hello");
  });
});

describe("consumeChatStream dispatch", () => {
  async function runStream(chunks: string[], handlers: ChatStreamHandlers): Promise<void> {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const c of chunks) controller.enqueue(new TextEncoder().encode(c));
        controller.close();
      },
    });
    await consumeChatStream(stream, handlers);
  }

  it("按事件分派 started/delta/completed", async () => {
    const deltas: string[] = [];
    let started = false;
    let completed = false;
    await runStream(
      [
        sse(1, "chat.started", { protocol_version: 1, conversation_id: "c1", turn_id: "t", sequence: 1, created: true }),
        sse(2, "token.delta", { protocol_version: 1, conversation_id: "c1", turn_id: "t", sequence: 2, delta: " he" }),
        sse(3, "token.delta", { protocol_version: 1, conversation_id: "c1", turn_id: "t", sequence: 3, delta: "llo" }),
        sse(4, "chat.completed", { protocol_version: 1, conversation_id: "c1", turn_id: "t", sequence: 4, assistant_message_id: 9, warning_count: 0 }),
      ],
      {
        onStarted: () => (started = true),
        onDelta: (e) => deltas.push(e.delta),
        onCompleted: () => (completed = true),
      },
    );
    expect(started).toBe(true);
    expect(completed).toBe(true);
    expect(deltas.join("")).toBe(" hello");
  });

  it("delta 跨 chunk 拆分仍完整还原", async () => {
    const deltas: string[] = [];
    // 完整事件从 data JSON 中间拆到两个 chunk
    const full = sse(1, "token.delta", { protocol_version: 1, conversation_id: "c", turn_id: "t", sequence: 1, delta: "hello" });
    const mid = full.indexOf('"delta":"hel') + '"delta":"hel'.length;
    await runStream([full.slice(0, mid), full.slice(mid)], { onDelta: (e) => deltas.push(e.delta) });
    expect(deltas.join("")).toBe("hello");
  });

  it("未知 protocol_version -> onUnknown", async () => {
    let unknown = false;
    await runStream(["id: 1\nevent: chat.started\ndata: " + JSON.stringify({ protocol_version: 2, conversation_id: "c", turn_id: "t", sequence: 1, created: true }) + "\n\n"], {
      onUnknown: () => (unknown = true),
    });
    expect(unknown).toBe(true);
  });

  it("未知 event 名 -> onUnknown", async () => {
    let unknown = false;
    await runStream(["id: 1\nevent: foo.bar\ndata: {}\n\n"], { onUnknown: () => (unknown = true) });
    expect(unknown).toBe(true);
  });

  it("warning 与 failed 事件分派", async () => {
    let ctxWarn = false;
    let failed = false;
    await runStream(
      [
        sse(1, "chat.started", { protocol_version: 1, conversation_id: "c", turn_id: "t", sequence: 1, created: true }),
        sse(2, "context.warning", { protocol_version: 1, conversation_id: "c", turn_id: "t", sequence: 2, component: "rag_retrieval", code: "RAG_FAILED", message: "检索降级", retryable: true }),
        sse(3, "chat.failed", { protocol_version: 1, conversation_id: "c", turn_id: "t", sequence: 3, phase: "model", error: { code: "MODEL_STREAM_FAILED", message: "失败", retryable: true }, partial_output_persisted: false }),
      ],
      {
        onContextWarning: () => (ctxWarn = true),
        onFailed: () => (failed = true),
      },
    );
    expect(ctxWarn).toBe(true);
    expect(failed).toBe(true);
  });
});
