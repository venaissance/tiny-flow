import { CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TodoItem } from "@/lib/types";

interface TodoCardProps {
  todos: TodoItem[];
}

function StatusIcon({ status }: { status: TodoItem["status"] }) {
  switch (status) {
    case "pending":
      return (
        <span className="inline-flex h-4 w-4 items-center justify-center text-xs text-gray-400 dark:text-gray-500">
          &#9675;
        </span>
      );
    case "in_progress":
      return (
        <span className="inline-flex h-4 w-4 items-center justify-center text-xs text-blue-500 animate-pulse">
          &#9673;
        </span>
      );
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-500 dark:text-green-400" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-red-500 dark:text-red-400" />;
  }
}

export function TodoCard({ todos }: TodoCardProps) {
  if (todos.length === 0) return null;

  const completedCount = todos.filter(
    (t) => t.status === "completed",
  ).length;

  return (
    <div className="rounded-xl border border-gray-200 bg-white/80 shadow-sm backdrop-blur-sm dark:border-gray-700/60 dark:bg-gray-900/60">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-gray-100 px-3.5 py-2 dark:border-gray-800">
        <span className="text-sm">{"\uD83D\uDCCB"}</span>
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
          执行计划
        </span>
        <span className="text-[10px] tabular-nums text-gray-400 dark:text-gray-500">
          ({completedCount}/{todos.length})
        </span>
      </div>

      {/* Items */}
      <ul className="divide-y divide-gray-50 px-3.5 dark:divide-gray-800/50">
        {todos.map((todo) => (
          <li
            key={todo.id}
            className="flex items-start gap-2 py-2 first:pt-2.5 last:pb-2.5"
          >
            <span className="mt-0.5 flex-shrink-0">
              <StatusIcon status={todo.status} />
            </span>
            <span
              className={cn(
                "text-xs leading-relaxed",
                todo.status === "completed"
                  ? "text-gray-400 line-through dark:text-gray-500"
                  : todo.status === "failed"
                    ? "text-red-600 dark:text-red-400"
                    : "text-gray-700 dark:text-gray-300",
              )}
            >
              {todo.content}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
