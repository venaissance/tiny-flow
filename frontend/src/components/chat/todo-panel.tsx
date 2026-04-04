import { CheckCircle2, XCircle, Loader2, ListTodo } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TodoItem } from "@/lib/types";

interface TodoPanelProps {
  todos: TodoItem[];
}

function StatusIcon({ status }: { status: TodoItem["status"] }) {
  switch (status) {
    case "pending":
      return (
        <span className="inline-flex h-5 w-5 items-center justify-center text-sm text-gray-400 dark:text-gray-500">
          &#9675;
        </span>
      );
    case "in_progress":
      return <Loader2 className="h-5 w-5 animate-spin text-blue-500" />;
    case "completed":
      return <CheckCircle2 className="h-5 w-5 text-green-500 dark:text-green-400" />;
    case "failed":
      return <XCircle className="h-5 w-5 text-red-500 dark:text-red-400" />;
  }
}

function statusLabel(status: TodoItem["status"]): string {
  switch (status) {
    case "pending":
      return "待执行";
    case "in_progress":
      return "执行中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
  }
}

export function TodoPanel({ todos }: TodoPanelProps) {
  if (todos.length === 0) return null;

  const completedCount = todos.filter(
    (t) => t.status === "completed",
  ).length;
  const progress =
    todos.length > 0 ? Math.round((completedCount / todos.length) * 100) : 0;

  return (
    <div className="flex h-full flex-col bg-white dark:bg-gray-950">
      {/* Header */}
      <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <ListTodo className="h-4 w-4 text-gray-500 dark:text-gray-400" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            执行计划
          </span>
          <span className="ml-auto text-xs tabular-nums text-gray-400 dark:text-gray-500">
            {completedCount}/{todos.length}
          </span>
        </div>

        {/* Progress bar */}
        <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500 ease-out",
              progress === 100
                ? "bg-green-500"
                : "bg-blue-500",
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="mt-1 text-[10px] tabular-nums text-gray-400 dark:text-gray-500">
          {progress}% 完成
        </p>
      </div>

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto">
        <ul className="divide-y divide-gray-100 dark:divide-gray-800/60">
          {todos.map((todo) => (
            <li key={todo.id} className="px-4 py-3">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex-shrink-0">
                  <StatusIcon status={todo.status} />
                </span>
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-sm leading-relaxed",
                      todo.status === "completed"
                        ? "text-gray-400 line-through dark:text-gray-500"
                        : todo.status === "failed"
                          ? "text-gray-700 dark:text-gray-300"
                          : "text-gray-700 dark:text-gray-300",
                    )}
                  >
                    {todo.content}
                  </p>
                  <span
                    className={cn(
                      "mt-1 inline-block text-[10px] font-medium",
                      todo.status === "pending" && "text-gray-400 dark:text-gray-500",
                      todo.status === "in_progress" && "text-blue-500",
                      todo.status === "completed" && "text-green-500 dark:text-green-400",
                      todo.status === "failed" && "text-red-500 dark:text-red-400",
                    )}
                  >
                    {statusLabel(todo.status)}
                  </span>
                  {todo.status === "failed" && todo.error && (
                    <p className="mt-1 rounded bg-red-50 px-2 py-1 text-xs text-red-600 dark:bg-red-950/30 dark:text-red-400">
                      {todo.error}
                    </p>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
