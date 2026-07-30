import type { ChatMessage, ConversationItem } from "../api/types";

export interface ChatTurn {
  readonly id: number;
  readonly controller: AbortController;
  readonly baseMessages: ChatMessage[];
  conversationId: string | null;
  cancelRequested: boolean;
}

interface StartChatTurn {
  controller: AbortController;
  conversationId: string | null;
  baseMessages: ChatMessage[];
}

interface ChatTruthReader {
  messages: (conversationId: string) => Promise<ChatMessage[]>;
  conversations: () => Promise<ConversationItem[]>;
}

export interface CancelledTurnTruth {
  persistedMessages: PromiseSettledResult<ChatMessage[] | null>;
  conversations: PromiseSettledResult<ConversationItem[]>;
}

/**
 * Tracks the one UI-owned Chat turn.
 *
 * Identity checks keep callbacks and finally blocks from an older request from
 * mutating a newer request after navigation or an Abort.
 */
export class ChatTurnController {
  private active: ChatTurn | null = null;
  private nextId = 1;

  hasActive(): boolean {
    return this.active !== null;
  }

  start(input: StartChatTurn): ChatTurn {
    if (this.active) throw new Error("A Chat turn is already active");
    const turn: ChatTurn = {
      id: this.nextId++,
      controller: input.controller,
      baseMessages: [...input.baseMessages],
      conversationId: input.conversationId,
      cancelRequested: false,
    };
    this.active = turn;
    return turn;
  }

  isCurrent(turn: ChatTurn): boolean {
    return this.active === turn;
  }

  acceptsEvents(turn: ChatTurn): boolean {
    return (
      this.isCurrent(turn) &&
      !turn.cancelRequested &&
      !turn.controller.signal.aborted
    );
  }

  rememberConversation(turn: ChatTurn, conversationId: string): boolean {
    if (!this.acceptsEvents(turn)) return false;
    turn.conversationId = conversationId;
    return true;
  }

  cancelCurrent(): ChatTurn | null {
    const turn = this.active;
    if (!turn || turn.cancelRequested) return turn;
    turn.cancelRequested = true;
    turn.controller.abort();
    return turn;
  }

  /**
   * Invalidates the current turn before aborting it. Synchronous abort
   * callbacks therefore already see the turn as stale.
   */
  supersede(): void {
    const turn = this.active;
    this.active = null;
    if (!turn) return;
    turn.cancelRequested = true;
    turn.controller.abort();
  }

  /**
   * Returns true only when this turn still owns UI cleanup.
   */
  finish(turn: ChatTurn): boolean {
    if (!this.isCurrent(turn)) return false;
    this.active = null;
    return true;
  }
}

export function optimisticTurnMessages(
  baseMessages: ChatMessage[],
  userContent: string,
): ChatMessage[] {
  return [
    ...baseMessages,
    { role: "USER", content: userContent },
    { role: "ASSISTANT", content: "" },
  ];
}

/**
 * Cancellation never keeps optimistic USER/ASSISTANT content. Prefer a fresh
 * PostgreSQL-backed response; otherwise fall back to the pre-turn snapshot.
 */
export function cancelledTurnMessages(
  baseMessages: ChatMessage[],
  persistedMessages?: ChatMessage[] | null,
): ChatMessage[] {
  return persistedMessages ? [...persistedMessages] : [...baseMessages];
}

/**
 * Refreshes both views of PG truth after cancellation. A new conversation
 * cancelled before chat.started has no safe cid to guess, so it refreshes only
 * the list and keeps the pre-turn message snapshot.
 */
export async function readCancelledTurnTruth(
  turn: ChatTurn,
  reader: ChatTruthReader,
): Promise<CancelledTurnTruth> {
  const persistedRequest = turn.conversationId
    ? reader.messages(turn.conversationId)
    : Promise.resolve<ChatMessage[] | null>(null);
  const [persistedMessages, conversations] = await Promise.allSettled([
    persistedRequest,
    reader.conversations(),
  ]);
  return { persistedMessages, conversations };
}
