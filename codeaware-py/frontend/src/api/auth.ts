// 认证 API + token 管理（团队化升级阶段 C）
import type { Envelope } from "./types";

const TOKEN_KEY = "codeaware_token";

export interface AuthUser {
  id: number;
  username: string;
  role: string;
  display_name: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

// SSR/test 环境无 localStorage，安全降级
const hasStorage = typeof localStorage !== "undefined";

export function getToken(): string | null {
  return hasStorage ? localStorage.getItem(TOKEN_KEY) : null;
}

export function setToken(token: string): void {
  if (hasStorage) localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (hasStorage) localStorage.removeItem(TOKEN_KEY);
}

const BASE = "";

export async function login(username: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const body = (await res.json()) as Envelope<TokenResponse>;
  if (body.code !== 1) throw new Error(body.msg || "登录失败");
  return body.data;
}

export async function fetchMe(): Promise<AuthUser> {
  const res = await fetch(`${BASE}/api/auth/me`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (res.status === 401) throw new Error("AUTH_TOKEN_REQUIRED");
  const body = (await res.json()) as Envelope<AuthUser>;
  if (body.code !== 1) throw new Error(body.msg || "获取用户失败");
  return body.data;
}

/** 401 时清 token + 跳登录（由 call/chatStream 调用） */
export function onAuthFailure(): void {
  clearToken();
  if (typeof window !== "undefined") window.location.reload();
}
