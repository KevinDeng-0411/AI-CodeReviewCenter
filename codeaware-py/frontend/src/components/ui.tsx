// 共享 UI 原语 - 工程仪表台风格
import { useEffect, useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { ApiError } from "../api/client";

// ---------- Button ----------
export function Button({
  children,
  variant = "primary",
  loading,
  ...props
}: {
  children: ReactNode;
  variant?: "primary" | "ghost";
  loading?: boolean;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const base =
    "inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const styles =
    variant === "primary"
      ? "bg-oxblood text-paper hover:bg-oxblood-soft"
      : "border border-line text-ink hover:bg-graph bg-panel";
  return (
    <button className={`${base} ${styles}`} disabled={loading || props.disabled} {...props}>
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  );
}

// ---------- Field ----------
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="font-mono text-2xs uppercase tracking-techy text-mute">{label}</span>
        {hint && <span className="text-2xs text-mute">{hint}</span>}
      </div>
      {children}
    </label>
  );
}

const inputCls =
  "w-full px-3 py-2 bg-panel border border-line rounded text-sm text-ink placeholder:text-mute/60 focus:outline-none focus:border-oxblood transition-colors";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${props.className ?? ""}`} />;
}
export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${inputCls} font-mono text-2xs ${props.className ?? ""}`} />;
}

// ---------- Severity badge ----------
export function severityColor(sev: string): string {
  const s = sev.trim().toLowerCase();
  if (s === "critical") return "oxblood";
  if (s === "warning") return "amber";
  return "teal";
}
export function SeverityBadge({ severity }: { severity: string }) {
  const c = severityColor(severity);
  const map: Record<string, string> = {
    oxblood: "bg-oxblood/10 text-oxblood border-oxblood/30",
    amber: "bg-amber/10 text-amber border-amber/30",
    teal: "bg-teal/10 text-teal border-teal/30",
  };
  return (
    <span
      className={`font-mono text-2xs uppercase tracking-techy px-1.5 py-0.5 rounded border ${map[c]}`}
    >
      {severity}
    </span>
  );
}

// ---------- Meter (VU 电平条 - 仪表式数据可视化) ----------
export function Meter({ value, max = 1 }: { value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = pct >= 66 ? "bg-teal" : pct >= 33 ? "bg-amber" : "bg-oxblood";
  return (
    <div className="h-1.5 w-full readout overflow-hidden">
      <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ---------- Empty state ----------
export function EmptyState({ icon, title, hint }: { icon: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-mute mb-3">{icon}</div>
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="text-xs text-mute mt-1 max-w-sm">{hint}</p>}
    </div>
  );
}

// ---------- Toast (错误条) ----------
export function useToast() {
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!err) return;
    const t = setTimeout(() => setErr(null), 5000);
    return () => clearTimeout(t);
  }, [err]);
  return {
    err,
    show: (e: unknown) => setErr(e instanceof ApiError ? e.msg : e instanceof Error ? e.message : "未知错误"),
    clear: () => setErr(null),
  };
}
export function ToastBar({ err, onClose }: { err: string | null; onClose: () => void }) {
  if (!err) return null;
  return (
    <div className="fixed bottom-5 right-5 z-50 flex items-start gap-2.5 max-w-md bg-ink text-paper px-4 py-3 rounded shadow-lg animate-rise">
      <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-amber-soft" />
      <div className="text-sm flex-1">{err}</div>
      <button onClick={onClose} className="text-paper/60 hover:text-paper text-xs">
        ✕
      </button>
    </div>
  );
}

// ---------- Signal trace (流式时的示波轨迹) ----------
export function SignalTrace({ label = "GENERATING" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-amber">
      <div className="signal-trace h-0.5 w-16 readout" />
      <span className="font-mono text-2xs uppercase tracking-techy animate-blink">{label}</span>
    </div>
  );
}

export function SuccessTick({ children }: { children: ReactNode }) {
  return (
    <div className="inline-flex items-center gap-1.5 text-teal text-xs">
      <CheckCircle2 className="w-3.5 h-3.5" />
      {children}
    </div>
  );
}
