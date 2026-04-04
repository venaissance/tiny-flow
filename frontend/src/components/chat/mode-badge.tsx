import { cn } from "@/lib/utils";
import type { ExecutionMode } from "@/lib/types";

interface ModeBadgeProps {
  mode: ExecutionMode | null;
  reason?: string;
}

const modeConfig: Record<
  ExecutionMode,
  { icon: string; label: string; bg: string; text: string; ring: string }
> = {
  flash: {
    icon: "\u26A1",
    label: "Flash",
    bg: "bg-gray-100 dark:bg-gray-800",
    text: "text-gray-700 dark:text-gray-300",
    ring: "ring-gray-200 dark:ring-gray-700",
  },
  thinking: {
    icon: "\uD83E\uDDE0",
    label: "Thinking",
    bg: "bg-purple-50 dark:bg-purple-950/40",
    text: "text-purple-700 dark:text-purple-300",
    ring: "ring-purple-200 dark:ring-purple-800",
  },
  pro: {
    icon: "\uD83D\uDCCB",
    label: "Pro",
    bg: "bg-blue-50 dark:bg-blue-950/40",
    text: "text-blue-700 dark:text-blue-300",
    ring: "ring-blue-200 dark:ring-blue-800",
  },
  ultra: {
    icon: "\uD83D\uDE80",
    label: "Ultra",
    bg: "bg-orange-50 dark:bg-orange-950/40",
    text: "text-orange-700 dark:text-orange-300",
    ring: "ring-orange-200 dark:ring-orange-800",
  },
};

export function ModeBadge({ mode, reason }: ModeBadgeProps) {
  if (!mode) return null;

  const config = modeConfig[mode];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset",
        "animate-in fade-in duration-300",
        config.bg,
        config.text,
        config.ring,
      )}
      title={reason}
    >
      <span className="text-sm leading-none">{config.icon}</span>
      <span>{config.label}</span>
      {reason && (
        <span
          className={cn(
            "ml-0.5 max-w-[120px] truncate text-[10px] font-normal opacity-70",
          )}
        >
          · {reason}
        </span>
      )}
    </span>
  );
}
