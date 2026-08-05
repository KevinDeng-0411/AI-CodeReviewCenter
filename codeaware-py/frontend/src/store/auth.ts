// 认证状态（团队化升级阶段 C）- zustand
import { create } from "zustand";
import { clearToken, fetchMe, login as apiLogin, setToken, type AuthUser } from "../api/auth";

interface AuthState {
  user: AuthUser | null;
  status: "loading" | "authed" | "unauthed";
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  bootstrap: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  status: "loading",

  login: async (username, password) => {
    const res = await apiLogin(username, password);
    setToken(res.access_token);
    set({ user: res.user, status: "authed" });
  },

  logout: () => {
    clearToken();
    set({ user: null, status: "unauthed" });
  },

  bootstrap: async () => {
    try {
      const user = await fetchMe();
      set({ user, status: "authed" });
    } catch {
      clearToken();
      set({ user: null, status: "unauthed" });
    }
  },
}));
