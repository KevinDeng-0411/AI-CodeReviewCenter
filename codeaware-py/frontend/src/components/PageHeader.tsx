// 共享页头 - 图标 + 标题 + 副标
import type { LucideIcon } from "lucide-react";

export default function PageHeader({
  icon: Icon,
  title,
  sub,
}: {
  icon: LucideIcon;
  title: string;
  sub: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="w-4 h-4 text-oxblood" />
      <span className="font-mono text-sm font-semibold tracking-techy">{title}</span>
      <span className="font-mono text-2xs text-mute tracking-techy">· {sub}</span>
    </div>
  );
}
