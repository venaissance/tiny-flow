"use client";

import { useMemo, useState } from "react";
import {
  PlusIcon,
  Trash2Icon,
  MessageSquareIcon,
  ZapIcon,
  PencilIcon,
  CheckIcon,
  XIcon,
} from "lucide-react";
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
export interface MemoryFact {
  id: string;
  content: string;
  category: string;
  confidence: number;
  access_count?: number;
  score_breakdown?: {
    explicitness?: number;
    repetition?: number;
    consistency?: number;
  };
  source_thread?: string;
  created_at?: string;
}

interface ThreadSidebarProps {
  threads: Thread[];
  activeThreadId: string | null;
  onSelect: (threadId: string) => void;
  onNew: () => void;
  onDelete: (threadId: string) => void;
  userMemory?: MemoryFact[];
  onMemoryDelete?: (id: string) => void;
  onMemoryUpdate?: (
    id: string,
    patch: { content?: string; category?: string; confidence?: number },
  ) => void;
  onMemoryClear?: () => void;
}

// Public weights shown in the UI — kept in sync with backend core.memory.scorer.WEIGHTS.
const SCORE_WEIGHTS = { explicitness: 0.3, repetition: 0.4, consistency: 0.3 };
const COMPONENT_LABELS: Record<string, { label: string; hint: string; color: string }> = {
  explicitness: {
    label: "具体度",
    hint: "事实越具体/越长 → 越可信（>20字=0.9，否则=0.5）",
    color: "bg-sky-500",
  },
  repetition: {
    label: "重复度",
    hint: "多次提到相似信息 → 越可信（每次相似度>0.5 +0.3，上限1.0）",
    color: "bg-emerald-500",
  },
  consistency: {
    label: "一致性",
    hint: "与已有同类记忆不冲突 → 越可信（无冲突=1.0，疑似冲突=0.5）",
    color: "bg-violet-500",
  },
};

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
const DEFAULT_META = { emoji: "📌", label: "背景" } as const;
const CATEGORY_META: Record<string, { emoji: string; label: string }> = {
  preference: { emoji: "❤️", label: "偏好" },
  context: { emoji: "📌", label: "背景" },
  behavior: { emoji: "🧭", label: "习惯" },
  knowledge: { emoji: "📚", label: "知识" },
};

export function ThreadSidebar({
  threads,
  activeThreadId,
  onSelect,
  onNew,
  onDelete,
  userMemory = [],
  onMemoryDelete,
  onMemoryUpdate,
  onMemoryClear,
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

      {/* Durable user memory — persists across threads and restarts. */}
      {userMemory.length > 0 && (
        <div className="border-t border-gray-200/60 bg-gradient-to-b from-blue-50/80 to-purple-50/60 px-3 py-2.5 dark:border-gray-700 dark:from-blue-950/30 dark:to-purple-950/20">
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="text-xs">🧠</span>
              <span className="text-[11px] font-semibold text-gray-600 dark:text-gray-300">
                用户记忆
              </span>
              <span className="text-[10px] text-gray-400 dark:text-gray-500">
                {userMemory.length} 条
              </span>
            </div>
            {onMemoryClear && (
              <button
                type="button"
                onClick={() => {
                  if (confirm(`清空全部 ${userMemory.length} 条用户记忆？此操作不可撤销。`)) {
                    onMemoryClear();
                  }
                }}
                className="rounded px-1.5 py-0.5 text-[10px] text-gray-400 transition hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                title="清空全部记忆"
              >
                清空
              </button>
            )}
          </div>
          <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
            {userMemory.map((fact) => (
              <MemoryFactCard
                key={fact.id}
                fact={fact}
                onDelete={onMemoryDelete}
                onUpdate={onMemoryUpdate}
              />
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-gray-200/60 px-3 py-2.5 dark:border-gray-800/60">
        <div className="flex items-center gap-1.5">
          <ZapIcon className="h-3 w-3 text-blue-400 dark:text-blue-500" />
          <span className="text-[11px] font-medium text-gray-400 dark:text-gray-500">
            TinyFlow
          </span>
          <span className="text-[10px] text-gray-300 dark:text-gray-600">
            v0.1.0
          </span>
        </div>
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// MemoryFactCard — one fact with click-to-expand confidence breakdown.
// ---------------------------------------------------------------------------
function MemoryFactCard({
  fact,
  onDelete,
  onUpdate,
}: {
  fact: MemoryFact;
  onDelete?: (id: string) => void;
  onUpdate?: (
    id: string,
    patch: { content?: string; category?: string; confidence?: number },
  ) => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(fact.content);
  const [draftCat, setDraftCat] = useState(fact.category);
  const meta = CATEGORY_META[fact.category] ?? DEFAULT_META;

  // Clamp bar fill to [0..100] for visual; support missing breakdown gracefully.
  const breakdown = fact.score_breakdown ?? {};
  const E = breakdown.explicitness ?? 0;
  const R = breakdown.repetition ?? 0;
  const C = breakdown.consistency ?? 0;
  const contrib = {
    explicitness: SCORE_WEIGHTS.explicitness * E,
    repetition: SCORE_WEIGHTS.repetition * R,
    consistency: SCORE_WEIGHTS.consistency * C,
  };
  const conf = fact.confidence;
  const confColor =
    conf >= 0.7 ? "text-emerald-600 dark:text-emerald-400" :
    conf >= 0.5 ? "text-sky-600 dark:text-sky-400" :
    conf >= 0.3 ? "text-amber-600 dark:text-amber-400" :
                  "text-gray-400 dark:text-gray-500";
  const confBar =
    conf >= 0.7 ? "bg-emerald-500" :
    conf >= 0.5 ? "bg-sky-500" :
    conf >= 0.3 ? "bg-amber-500" :
                  "bg-gray-400";

  const handleSaveEdit = () => {
    if (!onUpdate) return;
    const trimmed = draft.trim();
    if (!trimmed) return;
    const patch: { content?: string; category?: string } = {};
    if (trimmed !== fact.content) patch.content = trimmed;
    if (draftCat !== fact.category) patch.category = draftCat;
    if (Object.keys(patch).length) onUpdate(fact.id, patch);
    setEditing(false);
  };

  const handleCancelEdit = () => {
    setDraft(fact.content);
    setDraftCat(fact.category);
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="rounded-md border border-blue-300 bg-white p-2 shadow-sm dark:border-blue-700 dark:bg-gray-800">
        <div className="flex items-start gap-1.5">
          <select
            value={draftCat}
            onChange={(e) => setDraftCat(e.target.value)}
            className="flex-shrink-0 rounded border border-gray-200 bg-white px-1 py-0.5 text-[10px] text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
          >
            {(["preference", "context", "behavior", "knowledge"] as const).map((c) => {
              const m = CATEGORY_META[c] ?? DEFAULT_META;
              return (
                <option key={c} value={c}>
                  {m.emoji} {m.label}
                </option>
              );
            })}
          </select>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            className="flex-1 resize-none rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[11px] leading-relaxed text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                handleSaveEdit();
              } else if (e.key === "Escape") {
                e.preventDefault();
                handleCancelEdit();
              }
            }}
          />
        </div>
        <div className="mt-1.5 flex justify-end gap-1">
          <button
            type="button"
            onClick={handleCancelEdit}
            className="rounded px-1.5 py-0.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
            title="取消 (Esc)"
          >
            <XIcon className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={handleSaveEdit}
            className="rounded bg-blue-500 px-1.5 py-0.5 text-white hover:bg-blue-600"
            title="保存 (⌘/Ctrl+Enter)"
          >
            <CheckIcon className="h-3 w-3" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group rounded-md bg-white/80 shadow-sm dark:bg-gray-800/60">
      <div className="flex items-start">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-start gap-1.5 px-2 py-1.5 text-left text-[11px] leading-relaxed text-gray-700 hover:bg-white dark:text-gray-200 dark:hover:bg-gray-800"
        >
          <span className="mt-[1px] flex-shrink-0">{meta.emoji}</span>
          <span className="flex-1 break-words">{fact.content}</span>
          <span
            className={`flex-shrink-0 font-mono text-[10px] tabular-nums ${confColor}`}
            title="综合置信度"
          >
            {conf.toFixed(2)}
          </span>
        </button>
        {(onUpdate || onDelete) && (
          <div className="flex flex-shrink-0 items-start gap-0.5 pr-1 pt-1.5 opacity-0 transition-opacity group-hover:opacity-100">
            {onUpdate && (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setEditing(true); }}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-blue-500 dark:hover:bg-gray-700"
                title="编辑"
              >
                <PencilIcon className="h-3 w-3" />
              </button>
            )}
            {onDelete && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm("删除这条记忆？")) onDelete(fact.id);
                }}
                className="rounded p-1 text-gray-400 hover:bg-red-100 hover:text-red-500 dark:hover:bg-red-900/30"
                title="删除"
              >
                <Trash2Icon className="h-3 w-3" />
              </button>
            )}
          </div>
        )}
      </div>

      {open && (
        <div className="space-y-2 border-t border-gray-200/60 bg-gray-50/60 px-2.5 py-2 dark:border-gray-700 dark:bg-gray-900/40">
          {/* Overall confidence bar */}
          <div>
            <div className="mb-1 flex items-center justify-between text-[10px] font-semibold text-gray-500 dark:text-gray-400">
              <span>综合置信度</span>
              <span className={`font-mono tabular-nums ${confColor}`}>{conf.toFixed(3)}</span>
            </div>
            <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
              <div
                className={`absolute inset-y-0 left-0 ${confBar}`}
                style={{ width: `${Math.max(Math.min(conf * 100, 100), 2)}%` }}
              />
            </div>
          </div>

          {(E === 0 && R === 0 && C === 0) && (
            <div className="rounded bg-amber-50/70 px-2 py-1.5 text-[10px] leading-snug text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
              这条记忆是早期版本创建的，没有保留 breakdown。新提取的记忆会完整展示打分过程。
            </div>
          )}

          {/* Formula — only meaningful when breakdown was recorded */}
          {(E !== 0 || R !== 0 || C !== 0) && (
          <div className="rounded bg-white/70 px-2 py-1.5 font-mono text-[10px] leading-snug text-gray-600 dark:bg-gray-800/70 dark:text-gray-300">
            <div className="mb-0.5 text-gray-400 dark:text-gray-500">confidence =</div>
            <div>
              <span className="text-sky-600 dark:text-sky-400">0.3</span>
              <span className="text-gray-400"> · </span>
              <span className="text-sky-700 dark:text-sky-300">{E.toFixed(2)}</span>
              <span className="text-gray-400"> + </span>
              <span className="text-emerald-600 dark:text-emerald-400">0.4</span>
              <span className="text-gray-400"> · </span>
              <span className="text-emerald-700 dark:text-emerald-300">{R.toFixed(2)}</span>
              <span className="text-gray-400"> + </span>
              <span className="text-violet-600 dark:text-violet-400">0.3</span>
              <span className="text-gray-400"> · </span>
              <span className="text-violet-700 dark:text-violet-300">{C.toFixed(2)}</span>
            </div>
            <div className="mt-0.5 text-gray-500 dark:text-gray-400">
              = {contrib.explicitness.toFixed(2)} + {contrib.repetition.toFixed(2)} + {contrib.consistency.toFixed(2)}
              {" "}= <span className={`font-bold ${confColor}`}>{conf.toFixed(3)}</span>
            </div>
          </div>
          )}

          {/* Three component rows */}
          {(E !== 0 || R !== 0 || C !== 0) && (
          <div className="space-y-1.5">
            {(["explicitness", "repetition", "consistency"] as const).map((key) => {
              const cfg = COMPONENT_LABELS[key]!;
              const val = ({ explicitness: E, repetition: R, consistency: C })[key];
              return (
                <div key={key}>
                  <div className="mb-0.5 flex items-center justify-between text-[10px]">
                    <span className="font-medium text-gray-600 dark:text-gray-300">
                      {cfg.label}
                      <span className="ml-1 text-gray-400">
                        · 权重 {SCORE_WEIGHTS[key]}
                      </span>
                    </span>
                    <span className="font-mono tabular-nums text-gray-500 dark:text-gray-400">
                      {val.toFixed(2)}
                    </span>
                  </div>
                  <div className="h-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className={`h-full ${cfg.color}`}
                      style={{ width: `${Math.min(val * 100, 100)}%` }}
                    />
                  </div>
                  <div className="mt-0.5 text-[10px] leading-tight text-gray-500 dark:text-gray-400">
                    {cfg.hint}
                  </div>
                </div>
              );
            })}
          </div>
          )}

          {/* Metadata */}
          {(fact.access_count !== undefined || fact.source_thread || fact.created_at) && (
            <div className="flex flex-wrap gap-x-2 gap-y-0.5 pt-1 text-[10px] text-gray-400 dark:text-gray-500">
              {fact.access_count !== undefined && (
                <span title="此记忆被注入 prompt 的次数">↻ {fact.access_count} 次引用</span>
              )}
              {fact.source_thread && (
                <span title="该记忆最早在哪个 thread 里提取出来">
                  来源 {fact.source_thread.slice(0, 12)}
                </span>
              )}
              {fact.created_at && (
                <span>建于 {fact.created_at.slice(5, 16).replace("T", " ")}</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
