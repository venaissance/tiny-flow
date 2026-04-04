"use client";

import type { SubagentTask } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  timed_out: "bg-orange-100 text-orange-800",
};

export function SubagentPanel({ tasks }: { tasks: SubagentTask[] }) {
  if (tasks.length === 0) {
    return <div className="p-4 text-sm text-gray-500">No subagent tasks</div>;
  }

  return (
    <div className="space-y-3 p-4">
      <h3 className="text-sm font-semibold">Subagent Tasks</h3>
      {tasks.map((task, index) => (
        <div key={task.taskId || `task-${index}`} className="rounded border p-3">
          <div className="mb-1 flex items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${STATUS_COLORS[task.status] || ""}`}
            >
              {task.status}
            </span>
            <span className="text-xs text-gray-500">{task.type}</span>
          </div>
          {task.output && (
            <div className="mt-2 max-h-32 overflow-y-auto text-xs text-gray-600">
              {task.output}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
