"use client";

import { useMemo } from "react";
import { PlusIcon, Trash2Icon, MessageSquareIcon, ZapIcon } from "lucide-react";
import type { Thread } from "@/lib/types";

// ---------------------------------------------------------------------------
// Relative time formatting
// ---------------------------------------------------------------------------
function formatRelativeTime(dateStr: string | undefined): string | null {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return null;

  const now = Date.now();
  const diffMs = now - date.getTime();
  if (diffMs < 0) return null;

  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return "刚刚";

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}分钟前`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;

  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;

  const months = Math.floor(days / 30);
  if (months < 12) return `${months}个月前`;

  return `${Math.floor(months / 12)}年前`;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface ThreadSidebarProps {
  threads: Thread[];
  activeThreadId: string | null;
  onSelect: (threadId: string) => void;
  onNew: () => void;
  onDelete: (threadId: string) => void;
}

// ---------------------------------------------------------------------------
// Thread Item
// ---------------------------------------------------------------------------
function ThreadItem({
  thread,
  isActive,
  onSelect,
  onDelete,
}: {
  thread: Thread;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const relativeTime = useMemo(
    () => formatRelativeTime(thread.updated_at),
    [thread.updated_at],
  );

  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        onClick={onSelect}
        onKeyDown={(e) => e.key === "Enter" && onSelect()}
        className={[
          "group relative flex w-full cursor-pointer items-start gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm",
          "transition-all duration-150 ease-in-out",
          isActive
            ? "border-l-2 border-l-blue-500 bg-blue-50/80 text-blue-700 dark:border-l-blue-400 dark:bg-blue-950/60 dark:text-blue-200"
            : "border-l-2 border-l-transparent text-gray-700 hover:bg-gray-100/80 dark:text-gray-300 dark:hover:bg-gray-800/60",
        ].join(" ")}
      >
        {/* Icon */}
        <MessageSquareIcon
          className={[
            "mt-0.5 h-4 w-4 flex-shrink-0 transition-colors duration-150",
            isActive
              ? "text-blue-500 dark:text-blue-400"
              : "text-gray-400 dark:text-gray-500",
          ].join(" ")}
        />

        {/* Content */}
        <div className="min-w-0 flex-1">
          <span className="block truncate font-medium leading-snug">
            {thread.title || "新对话"}
          </span>
          {relativeTime && (
            <span className="mt-0.5 block text-[11px] leading-none text-gray-400 dark:text-gray-500">
              {relativeTime}
            </span>
          )}
        </div>

        {/* Delete button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="mt-0.5 flex-shrink-0 rounded p-1 text-gray-300 opacity-0 transition-all duration-150 hover:bg-red-50 hover:text-red-500 group-hover:opacity-100 dark:text-gray-600 dark:hover:bg-red-950/40 dark:hover:text-red-400"
          title="删除"
        >
          <Trash2Icon className="h-3.5 w-3.5" />
        </button>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
export function ThreadSidebar({
  threads,
  activeThreadId,
  onSelect,
  onNew,
  onDelete,
}: ThreadSidebarProps) {
  return (
    <aside className="flex h-full w-full flex-col border-r border-gray-200/80 bg-gray-50/70 dark:border-gray-800 dark:bg-gray-950/80">
      {/* Header + New thread button */}
      <div className="p-3 pb-2">
        <button
          onClick={onNew}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:bg-blue-600 hover:shadow-md active:scale-[0.98] dark:bg-blue-600 dark:hover:bg-blue-500"
        >
          <PlusIcon className="h-4 w-4" />
          新对话
        </button>
      </div>

      {/* Thread list */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        {threads.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-3 py-8 text-center">
            <MessageSquareIcon className="mb-2 h-8 w-8 text-gray-300 dark:text-gray-600" />
            <p className="text-xs text-gray-400 dark:text-gray-500">暂无对话</p>
            <p className="mt-1 text-[11px] text-gray-300 dark:text-gray-600">
              点击上方按钮开始
            </p>
          </div>
        ) : (
          <ul className="space-y-0.5">
            {threads.map((thread) => (
              <ThreadItem
                key={thread.thread_id}
                thread={thread}
                isActive={thread.thread_id === activeThreadId}
                onSelect={() => onSelect(thread.thread_id)}
                onDelete={() => onDelete(thread.thread_id)}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-200/60 px-3 py-2.5 dark:border-gray-800/60">
        <div className="flex items-center gap-1.5">
          <ZapIcon className="h-3 w-3 text-blue-400 dark:text-blue-500" />
          <span className="text-[11px] font-medium text-gray-400 dark:text-gray-500">
            MdwFlow
          </span>
          <span className="text-[10px] text-gray-300 dark:text-gray-600">
            v0.1.0
          </span>
        </div>
      </div>
    </aside>
  );
}
