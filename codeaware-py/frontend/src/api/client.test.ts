import { describe, expect, it } from "vitest";
import { readApiErrorMessage } from "./client";

describe("readApiErrorMessage", () => {
  it("保留统一错误 envelope 的稳定业务消息", async () => {
    const message = await readApiErrorMessage({
      status: 409,
      json: async () => ({
        code: 0,
        msg: "CHAT_TURN_IN_PROGRESS",
        data: null,
      }),
    });

    expect(message).toBe("CHAT_TURN_IN_PROGRESS");
  });

  it("非 JSON、空 msg 或异常 envelope 回退 HTTP 状态", async () => {
    await expect(
      readApiErrorMessage({
        status: 502,
        json: async () => {
          throw new SyntaxError("not json");
        },
      }),
    ).resolves.toBe("HTTP 502");

    await expect(
      readApiErrorMessage({
        status: 503,
        json: async () => ({ code: 0, msg: "   ", data: null }),
      }),
    ).resolves.toBe("HTTP 503");

    await expect(
      readApiErrorMessage({
        status: 500,
        json: async () => ({ detail: "not the unified envelope" }),
      }),
    ).resolves.toBe("HTTP 500");
  });
});
