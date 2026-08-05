// 登录页（团队化升级阶段 C）
import { useState } from "react";
import { LogIn } from "lucide-react";
import { useAuth } from "../store/auth";

export default function LoginPage() {
  const login = useAuth((s) => s.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center h-screen bg-ink text-paper">
      <div className="w-80 rounded-lg border border-paper/10 bg-ink/80 p-8">
        <div className="flex items-center gap-2 mb-6">
          <LogIn className="w-5 h-5 text-oxblood" />
          <h1 className="font-mono text-sm font-semibold tracking-techy">CODEAWARE</h1>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="用户名"
            autoFocus
            className="w-full px-3 py-2 bg-paper/5 border border-paper/10 rounded text-sm text-paper placeholder:text-paper/40 focus:outline-none focus:border-oxblood"
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="密码"
            className="w-full px-3 py-2 bg-paper/5 border border-paper/10 rounded text-sm text-paper placeholder:text-paper/40 focus:outline-none focus:border-oxblood"
          />
          {error && <p className="font-mono text-2xs text-oxblood">{error}</p>}
          <button
            type="submit"
            disabled={loading || !username || !password}
            className="w-full px-3 py-2 text-sm font-medium rounded bg-oxblood text-paper hover:bg-oxblood/80 transition-colors disabled:opacity-40"
          >
            {loading ? "登录中…" : "登录"}
          </button>
        </form>
      </div>
    </div>
  );
}
