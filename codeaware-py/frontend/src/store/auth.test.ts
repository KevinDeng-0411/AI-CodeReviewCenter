// 认证状态测试（团队化升级阶段 C）
import { describe, it, expect, vi, beforeEach } from "vitest";

// mock auth API
vi.mock("../api/auth", () => ({
  login: vi.fn(),
  fetchMe: vi.fn(),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  getToken: vi.fn(() => null),
  onAuthFailure: vi.fn(),
}));

import { useAuth } from "./auth";
import { login as apiLogin, fetchMe } from "../api/auth";

describe("auth store", () => {
  beforeEach(() => {
    useAuth.setState({ user: null, status: "loading" });
    vi.clearAllMocks();
  });

  it("login 成功后进入 authed 状态", async () => {
    const mockUser = { id: 1, username: "alice", role: "member", display_name: "Alice" };
    (apiLogin as ReturnType<typeof vi.fn>).mockResolvedValue({
      access_token: "tok",
      token_type: "bearer",
      user: mockUser,
    });

    await useAuth.getState().login("alice", "pw");

    expect(useAuth.getState().status).toBe("authed");
    expect(useAuth.getState().user).toEqual(mockUser);
  });

  it("bootstrap 无 token 时进入 unauthed", async () => {
    (fetchMe as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("AUTH_TOKEN_REQUIRED"));

    await useAuth.getState().bootstrap();

    expect(useAuth.getState().status).toBe("unauthed");
    expect(useAuth.getState().user).toBeNull();
  });

  it("logout 清空状态", async () => {
    useAuth.setState({ user: { id: 1, username: "x", role: "member", display_name: null }, status: "authed" });

    useAuth.getState().logout();

    expect(useAuth.getState().status).toBe("unauthed");
    expect(useAuth.getState().user).toBeNull();
  });
});
