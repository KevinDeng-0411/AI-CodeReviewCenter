import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../api/types";
import {
  cancelledTurnMessages,
  ChatTurnController,
  optimisticTurnMessages,
  readCancelledTurnTruth,
} from "./chatTurnController";

const existingMessages: ChatMessage[] = [
  { role: "USER", content: "earlier question" },
  { role: "ASSISTANT", content: "earlier answer" },
];

describe("ChatTurnController", () => {
  it("首个 started 前取消会丢弃伪 USER 和空 ASSISTANT", () => {
    const controller = new ChatTurnController();
    const abortController = new AbortController();
    const turn = controller.start({
      controller: abortController,
      conversationId: null,
      baseMessages: existingMessages,
    });

    const optimistic = optimisticTurnMessages(existingMessages, "new question");
    expect(optimistic).toHaveLength(4);

    controller.cancelCurrent();

    expect(abortController.signal.aborted).toBe(true);
    expect(controller.acceptsEvents(turn)).toBe(false);
    expect(cancelledTurnMessages(turn.baseMessages)).toEqual(existingMessages);
  });

  it("多个 token 后取消仍以 PG 消息替换整个 optimistic turn", () => {
    const persisted: ChatMessage[] = [
      ...existingMessages,
      { role: "USER", content: "new question" },
    ];
    const optimistic = optimisticTurnMessages(existingMessages, "new question");
    optimistic[optimistic.length - 1] = {
      role: "ASSISTANT",
      content: "partial output that must disappear",
    };

    expect(cancelledTurnMessages(existingMessages, persisted)).toEqual(persisted);
    expect(cancelledTurnMessages(existingMessages, persisted)).not.toContainEqual(
      optimistic[optimistic.length - 1],
    );
  });

  it("旧请求的 callback 和 finally 不能影响新请求", () => {
    const controller = new ChatTurnController();
    const oldTurn = controller.start({
      controller: new AbortController(),
      conversationId: "old-cid",
      baseMessages: existingMessages,
    });
    controller.supersede();
    expect(oldTurn.controller.signal.aborted).toBe(true);

    const newTurn = controller.start({
      controller: new AbortController(),
      conversationId: "new-cid",
      baseMessages: [],
    });

    expect(controller.acceptsEvents(oldTurn)).toBe(false);
    expect(controller.rememberConversation(oldTurn, "stale-cid")).toBe(false);
    expect(controller.finish(oldTurn)).toBe(false);
    expect(controller.isCurrent(newTurn)).toBe(true);
    expect(controller.acceptsEvents(newTurn)).toBe(true);
  });

  it("started 事件只为当前请求记录真实 conversation_id", () => {
    const controller = new ChatTurnController();
    const turn = controller.start({
      controller: new AbortController(),
      conversationId: null,
      baseMessages: [],
    });

    expect(controller.rememberConversation(turn, "server-cid")).toBe(true);
    expect(turn.conversationId).toBe("server-cid");
  });

  it("已有 cid 的取消会并发回读消息与刷新会话列表", async () => {
    const controller = new ChatTurnController();
    const turn = controller.start({
      controller: new AbortController(),
      conversationId: "known-cid",
      baseMessages: existingMessages,
    });
    const calls: string[] = [];

    const truth = await readCancelledTurnTruth(turn, {
      messages: async (cid) => {
        calls.push(`messages:${cid}`);
        return existingMessages;
      },
      conversations: async () => {
        calls.push("conversations");
        return [];
      },
    });

    expect(calls).toContain("messages:known-cid");
    expect(calls).toContain("conversations");
    expect(truth.persistedMessages.status).toBe("fulfilled");
    expect(truth.conversations.status).toBe("fulfilled");
  });

  it("started 前无 cid 的取消不猜会话，但仍刷新列表", async () => {
    const controller = new ChatTurnController();
    const turn = controller.start({
      controller: new AbortController(),
      conversationId: null,
      baseMessages: existingMessages,
    });
    let messagesCalled = false;
    let conversationsCalled = false;

    const truth = await readCancelledTurnTruth(turn, {
      messages: async () => {
        messagesCalled = true;
        return [];
      },
      conversations: async () => {
        conversationsCalled = true;
        return [];
      },
    });

    expect(messagesCalled).toBe(false);
    expect(conversationsCalled).toBe(true);
    expect(truth.persistedMessages).toEqual({ status: "fulfilled", value: null });
  });
});
