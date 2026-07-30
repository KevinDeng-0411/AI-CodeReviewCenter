import { afterEach, describe, expect, it, vi } from "vitest";
import { aiReadme, ApiError, knowledge, readApiErrorMessage } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
});

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

describe("knowledge.uploadFile", () => {
  it("使用 FormData 且不手工设置 multipart Content-Type", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        code: 1,
        msg: "success",
        data: { id: 7, title: "README.md" },
      }),
    } as Response);
    const file = new File(["# Upload"], "README.md", { type: "text/markdown" });

    await expect(knowledge.uploadFile(file, "demo-project")).resolves.toEqual({
      id: 7,
      title: "README.md",
    });

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/knowledge/upload-file");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toBeUndefined();
    expect(init?.body).toBeInstanceOf(FormData);
    const form = init?.body as FormData;
    expect(form.get("project_name")).toBe("demo-project");
    const uploaded = form.get("file") as File;
    expect(uploaded.name).toBe("README.md");
    expect(uploaded.type).toBe("text/markdown");
  });

  it("保留后端稳定文件上传错误码", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        code: 0,
        msg: "KNOWLEDGE_FILE_TYPE_UNSUPPORTED",
        data: null,
      }),
    } as Response);
    const file = new File(["bad"], "bad.exe", { type: "application/octet-stream" });

    await expect(knowledge.uploadFile(file)).rejects.toEqual(
      new ApiError("KNOWLEDGE_FILE_TYPE_UNSUPPORTED"),
    );
  });
});

describe("aiReadme.capabilities", () => {
  it("读取最小 capability 契约且不发送项目路径", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        code: 1,
        msg: "success",
        data: { enabled: false, reason: "roots_unavailable" },
      }),
    } as Response);

    await expect(aiReadme.capabilities()).resolves.toEqual({
      enabled: false,
      reason: "roots_unavailable",
    });

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/ai-readme/capabilities");
    expect(init?.method).toBeUndefined();
    expect(init?.body).toBeUndefined();
  });
});
