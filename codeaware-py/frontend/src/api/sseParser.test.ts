import { describe, expect, it } from "vitest";
import {
  ChatStreamInterruptedError,
  ChatStreamProtocolError,
  consumeChatStream,
  parseSseEvents,
  type ChatStreamHandlers,
  type ChatStreamOutcome,
} from "./sseParser";

function base(sequence: number) {
  return {
    protocol_version: 1,
    conversation_id: "c1",
    turn_id: "t1",
    sequence,
  };
}

function sse(id: number, event: string, data: object): string {
  return `id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function started(sequence = 1): string {
  return sse(sequence, "chat.started", { ...base(sequence), created: true });
}

function delta(sequence: number, content: string): string {
  return sse(sequence, "token.delta", { ...base(sequence), delta: content });
}

function completed(sequence: number): string {
  return sse(sequence, "chat.completed", {
    ...base(sequence),
    assistant_message_id: 9,
    warning_count: 0,
  });
}

function failed(sequence: number): string {
  return sse(sequence, "chat.failed", {
    ...base(sequence),
    phase: "model",
    error: { code: "MODEL_STREAM_FAILED", message: "失败", retryable: true },
    partial_output_persisted: false,
  });
}

async function runStream(
  chunks: string[],
  handlers: ChatStreamHandlers = {},
  signal?: AbortSignal,
): Promise<ChatStreamOutcome> {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
      controller.close();
    },
  });
  return consumeChatStream(stream, handlers, signal);
}

async function expectProtocolReason(
  promise: Promise<unknown>,
  reason: ChatStreamProtocolError["reason"],
): Promise<void> {
  try {
    await promise;
    throw new Error("expected protocol error");
  } catch (error) {
    expect(error).toBeInstanceOf(ChatStreamProtocolError);
    expect((error as ChatStreamProtocolError).code).toBe("CHAT_SSE_PROTOCOL_ERROR");
    expect((error as ChatStreamProtocolError).reason).toBe(reason);
  }
}

describe("parseSseEvents", () => {
  it("解析单事件", () => {
    const { events, rest } = parseSseEvents(started());
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("chat.started");
    expect(events[0].id).toBe("1");
    expect(rest).toBe("");
  });

  it("兼容 CRLF 行尾", () => {
    const buffer = delta(2, " hi").replaceAll("\n", "\r\n");
    const { events } = parseSseEvents(buffer);
    expect(events[0].event).toBe("token.delta");
    expect(JSON.parse(events[0].data).delta).toBe(" hi");
  });

  it("保留 delta 前导空格且多 data 行仅按协议拼接换行", () => {
    const { events: deltaEvents } = parseSseEvents(delta(2, " world"));
    expect(JSON.parse(deltaEvents[0].data).delta).toBe(" world");

    const { events: multilineEvents } = parseSseEvents(
      "id: 1\nevent: token.delta\ndata: line1\ndata: line2\n\n",
    );
    expect(multilineEvents[0].data).toBe("line1\nline2");
  });

  it("未完成事件留在 rest 等待下一个网络 chunk", () => {
    const part1 = 'id: 1\nevent: token.delta\ndata: {"delta":"he';
    const first = parseSseEvents(part1);
    expect(first.events).toHaveLength(0);
    expect(first.rest).toBe(part1);

    const second = parseSseEvents(`${first.rest}llo"}\n\n`);
    expect(second.events).toHaveLength(1);
    expect(JSON.parse(second.events[0].data).delta).toBe("hello");
  });
});

describe("consumeChatStream protocol state", () => {
  it("仅在 started → delta* → completed 后返回成功终态", async () => {
    const deltas: string[] = [];
    const outcome = await runStream(
      [started(), delta(2, " he"), delta(3, "llo"), completed(4)],
      { onDelta: (event) => deltas.push(event.delta) },
    );

    expect(outcome.status).toBe("completed");
    expect(deltas.join("")).toBe(" hello");
  });

  it("返回显式 failed 终态而不当作 completed", async () => {
    let completedCalled = false;
    let failedCalled = false;
    const outcome = await runStream(
      [started(), delta(2, "partial"), failed(3)],
      {
        onCompleted: () => (completedCalled = true),
        onFailed: () => (failedCalled = true),
      },
    );

    expect(outcome.status).toBe("failed");
    expect(completedCalled).toBe(false);
    expect(failedCalled).toBe(true);
    if (outcome.status === "failed") {
      expect(outcome.event.error.code).toBe("MODEL_STREAM_FAILED");
    }
  });

  it("分派 context/post-turn warning 并保留 component", async () => {
    const warnings: string[] = [];
    const outcome = await runStream(
      [
        started(),
        sse(2, "context.warning", {
          ...base(2),
          component: "rag_retrieval",
          code: "RAG_FAILED",
          message: "检索降级",
          retryable: true,
        }),
        sse(3, "post_turn.warning", {
          ...base(3),
          component: "summary_cache",
          code: "REDIS_UNAVAILABLE",
          message: "摘要缓存不可用",
          retryable: true,
        }),
        sse(4, "post_turn.warning", {
          ...base(4),
          component: "memory_extraction",
          code: "MEMORY_EXTRACTION_FAILED",
          message: "记忆提取降级",
          retryable: true,
        }),
        completed(5),
      ],
      {
        onContextWarning: (event) => warnings.push(event.component),
        onPostWarning: (event) => warnings.push(event.component),
      },
    );

    expect(outcome.status).toBe("completed");
    expect(warnings).toEqual([
      "rag_retrieval",
      "summary_cache",
      "memory_extraction",
    ]);
  });

  it("按任意字节边界还原前导换行和多字节中文", async () => {
    const full = started() + delta(2, "\n你好") + completed(3);
    const bytes = new TextEncoder().encode(full);
    const pieces = Array.from(bytes, (byte) => new Uint8Array([byte]));
    const values: string[] = [];
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const piece of pieces) controller.enqueue(piece);
        controller.close();
      },
    });

    const outcome = await consumeChatStream(stream, {
      onDelta: (event) => values.push(event.delta),
    });

    expect(outcome.status).toBe("completed");
    expect(values.join("")).toBe("\n你好");
  });

  it("JSON 损坏时立即停止且不消费后续合法事件", async () => {
    let completedCalled = false;
    const malformed =
      'id: 2\nevent: token.delta\ndata: {"protocol_version":1,\n\n';

    await expectProtocolReason(
      runStream(
        [started() + malformed + completed(3)],
        { onCompleted: () => (completedCalled = true) },
      ),
      "MALFORMED_JSON",
    );
    expect(completedCalled).toBe(false);
  });

  it("未知 protocol_version 是可识别的协议错误", async () => {
    await expectProtocolReason(
      runStream([
        sse(1, "chat.started", {
          ...base(1),
          protocol_version: 2,
          created: true,
        }),
      ]),
      "UNSUPPORTED_PROTOCOL_VERSION",
    );
  });

  it("未知事件立即失败且不静默当作 token", async () => {
    let deltaCalled = false;
    await expectProtocolReason(
      runStream(
        [
          started(),
          sse(2, "future.event", base(2)),
          delta(3, "must not be consumed"),
          completed(4),
        ],
        { onDelta: () => (deltaCalled = true) },
      ),
      "UNKNOWN_EVENT",
    );
    expect(deltaCalled).toBe(false);
  });

  it("缺少 event 字段的数据帧按未知事件拒绝", async () => {
    await expectProtocolReason(
      runStream([started(), `id: 2\ndata: ${JSON.stringify(base(2))}\n\n`]),
      "UNKNOWN_EVENT",
    );
  });

  it("拒绝缺少 started、重复 started 和不连续 sequence", async () => {
    await expectProtocolReason(
      runStream([delta(1, "bad"), completed(2)]),
      "EVENT_ORDER",
    );
    await expectProtocolReason(
      runStream([started(), started(2), completed(3)]),
      "EVENT_ORDER",
    );
    await expectProtocolReason(
      runStream([started(), delta(3, "gap"), completed(4)]),
      "SEQUENCE_MISMATCH",
    );
  });

  it("拒绝 SSE id 不匹配以及流中 cid/turn 身份漂移", async () => {
    await expectProtocolReason(
      runStream([
        started(),
        sse(7, "token.delta", { ...base(2), delta: "wrong id" }),
      ]),
      "SEQUENCE_MISMATCH",
    );
    await expectProtocolReason(
      runStream([
        started(),
        sse(2, "token.delta", {
          ...base(2),
          conversation_id: "other-cid",
          delta: "wrong stream",
        }),
      ]),
      "STREAM_IDENTITY_MISMATCH",
    );
  });

  it("拒绝契约外的 warning component、failed phase 和 partial 持久化标记", async () => {
    await expectProtocolReason(
      runStream([
        started(),
        sse(2, "context.warning", {
          ...base(2),
          component: "unknown_component",
          code: "UNKNOWN",
          message: "bad component",
          retryable: false,
        }),
      ]),
      "INVALID_EVENT",
    );
    await expectProtocolReason(
      runStream([
        started(),
        sse(2, "chat.failed", {
          ...base(2),
          phase: "unknown_phase",
          error: { code: "UNKNOWN", message: "bad phase", retryable: false },
          partial_output_persisted: false,
        }),
      ]),
      "INVALID_EVENT",
    );
    await expectProtocolReason(
      runStream([
        started(),
        sse(2, "chat.failed", {
          ...base(2),
          phase: "model",
          error: { code: "UNKNOWN", message: "partial persisted", retryable: false },
          partial_output_persisted: true,
        }),
      ]),
      "INVALID_EVENT",
    );
  });

  it("进入 post-turn 阶段后不能回到模型或上下文阶段", async () => {
    const postTurn = sse(2, "post_turn.warning", {
      ...base(2),
      component: "summary_cache",
      code: "REDIS_UNAVAILABLE",
      message: "摘要缓存不可用",
      retryable: true,
    });

    await expectProtocolReason(
      runStream([started(), postTurn, delta(3, "late token")]),
      "EVENT_ORDER",
    );
    await expectProtocolReason(
      runStream([
        started(),
        postTurn,
        sse(3, "context.warning", {
          ...base(3),
          component: "rag_retrieval",
          code: "RAG_FAILED",
          message: "late context warning",
          retryable: true,
        }),
      ]),
      "EVENT_ORDER",
    );
  });

  it("终态后出现任何事件都是协议错误", async () => {
    let completedCalled = false;
    await expectProtocolReason(
      runStream(
        [started(), completed(2), delta(3, "late")],
        { onCompleted: () => (completedCalled = true) },
      ),
      "EVENT_AFTER_TERMINAL",
    );
    expect(completedCalled).toBe(false);
  });

  it("没有 completed/failed 的 EOF 是中断错误而非成功", async () => {
    await expect(runStream([started(), delta(2, "partial")])).rejects.toMatchObject({
      name: "ChatStreamInterruptedError",
      code: "CHAT_SSE_UNEXPECTED_EOF",
    });
    await expect(runStream([])).rejects.toBeInstanceOf(ChatStreamInterruptedError);
  });

  it("Abort 取消 reader 并返回 aborted，不误报协议或 EOF", async () => {
    let readerCancelled = false;
    const stream = new ReadableStream<Uint8Array>({
      cancel() {
        readerCancelled = true;
      },
    });
    const abortController = new AbortController();
    const consuming = consumeChatStream(stream, {}, abortController.signal);

    abortController.abort();
    const outcome = await consuming;

    expect(outcome).toEqual({ status: "aborted" });
    expect(readerCancelled).toBe(true);
  });

  it("terminal 已解析但仍等待 EOF 时 Abort 优先返回 aborted", async () => {
    let readerCancelled = false;
    const abortController = new AbortController();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(started() + completed(2)));
      },
      cancel() {
        readerCancelled = true;
      },
    });

    const outcome = await consumeChatStream(
      stream,
      {
        onStarted: () => {
          // 当前 chunk 中的 terminal 会先完成解析；microtask 随后在等待
          // 下一次 read/EOF 时触发 Abort，精确覆盖 Stop/terminal 竞态。
          queueMicrotask(() => abortController.abort());
        },
      },
      abortController.signal,
    );

    expect(outcome).toEqual({ status: "aborted" });
    expect(readerCancelled).toBe(true);
  });
});

describe("C6 context.references + reasoning.delta", () => {
  function references(sequence: number): string {
    return sse(sequence, "context.references", {
      ...base(sequence),
      knowledge_refs: [
        {
          document_id: 1,
          title: "缓存最佳实践",
          snippet: "热点Key失效瞬间大量请求打DB。方案：互斥锁、逻辑过期。",
          match_type: "both",
          score: 0.85,
        },
      ],
      memory_refs: [
        { content: "团队使用 SQLAlchemy 2.0", memory_type: "REFERENCE", similarity: 0.72 },
      ],
    });
  }

  function reasoning(sequence: number, content: string): string {
    return sse(sequence, "reasoning.delta", { ...base(sequence), delta: content });
  }

  it("started -> references -> reasoning -> token -> completed 顺序解析", async () => {
    const received: string[] = [];
    const outcome = await consumeChatStream(
      new ReadableStream({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode(
              started(1) +
                references(2) +
                reasoning(3, "analyzing…") +
                delta(4, "答案") +
                completed(5),
            ),
          );
          controller.close();
        },
      }),
      {
        onReferences: (e) => received.push(`refs:${e.knowledge_refs[0].match_type}`),
        onReasoning: (e) => received.push(`reasoning:${e.delta}`),
        onDelta: (e) => received.push(`delta:${e.delta}`),
      },
    );

    expect(outcome).toEqual({
      status: "completed",
      event: expect.objectContaining({ assistant_message_id: 9 }),
    });
    expect(received).toEqual([
      "refs:both",
      "reasoning:analyzing…",
      "delta:答案",
    ]);
  });

  it("context.references 校验失败时 fail closed", async () => {
    await expect(
      consumeChatStream(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              new TextEncoder().encode(
                started(1) +
                  sse(2, "context.references", {
                    ...base(2),
                    knowledge_refs: [{ document_id: "not-number", title: 1 }],
                    memory_refs: [],
                  }),
              ),
            );
            controller.close();
          },
        }),
        {},
      ),
    ).rejects.toThrow(ChatStreamProtocolError);
  });
});
