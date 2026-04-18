"use client";

import { useMemo, useState } from "react";
import {
  PlusIcon,
  Trash2Icon,
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
    color: "bg-[var(--color-lapis)]",
  },
  repetition: {
    label: "重复度",
    hint: "多次提到相似信息 → 越可信（每次相似度>0.5 +0.3，上限1.0）",
    color: "bg-[var(--color-verdigris)]",
  },
  consistency: {
    label: "一致性",
    hint: "与已有同类记忆不冲突 → 越可信（无冲突=1.0，疑似冲突=0.5）",
    color: "bg-[var(--color-gilt)]",
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
          "group relative flex w-full cursor-pointer items-start gap-2.5 rounded-[4px] px-2.5 py-2 text-left transition-all duration-150 ease-in-out",
          isActive
            ? "bg-[var(--color-parchment)] text-[var(--color-ink)]"
            : "text-[var(--color-ink-soft)] hover:bg-[var(--color-parchment)]/60 hover:text-[var(--color-ink)]",
        ].join(" ")}
      >
        {/* Left accent rule — vermilion when active */}
        <div
          className={[
            "absolute inset-y-1.5 left-0 w-[2px] rounded-full transition-all",
            isActive
              ? "bg-[var(--color-vermilion)]"
              : "bg-transparent group-hover:bg-[var(--color-ink)]/20",
          ].join(" ")}
        />

        {/* Content */}
        <div className="ml-1 min-w-0 flex-1">
          <span className={[
            "block truncate text-[13px] leading-snug",
            isActive ? "font-display font-medium" : "font-display italic",
          ].join(" ")}>
            {thread.title || "新对话"}
          </span>
          {relativeTime && (
            <span className="mt-0.5 block font-mono text-[10px] leading-none tracking-wide text-[var(--color-ink-faint)]">
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
          className="mt-0.5 flex-shrink-0 rounded-sm p-1 text-[var(--color-ink-faint)] opacity-0 transition-all duration-150 hover:bg-[var(--color-vermilion-soft)] hover:text-[var(--color-vermilion-deep)] group-hover:opacity-100"
          title="删除"
        >
          <Trash2Icon className="h-3 w-3" strokeWidth={1.6} />
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
    <aside className="relative flex h-full w-full flex-col border-r border-[var(--color-rule)] bg-[var(--color-sidebar)]/85 backdrop-blur-[2px]">
      {/* Marginal rule — like a manuscript vertical guide */}
      <div className="pointer-events-none absolute right-[10px] top-10 bottom-10 w-px bg-gradient-to-b from-transparent via-[var(--color-rule)] to-transparent" />

      {/* Header */}
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-baseline gap-2">
          <span className="label-eyebrow text-[9px]">Codex</span>
          <div className="h-px flex-1 bg-[var(--color-rule)]" />
          <span className="font-mono text-[10px] tracking-wide text-[var(--color-ink-faint)]">
            v0.1
          </span>
        </div>
      </div>

      {/* New thread button — ink on paper */}
      <div className="px-4 pb-3">
        <button
          onClick={onNew}
          className="group relative flex w-full items-center justify-between gap-2 rounded-[5px] border border-[var(--color-ink)]/85 bg-[var(--color-ink)] px-3.5 py-2 text-[var(--color-paper)] transition-all duration-200 hover:border-[var(--color-vermilion)] hover:bg-[var(--color-vermilion)] active:scale-[0.99]"
        >
          <span className="flex items-center gap-2.5">
            <PlusIcon className="h-3.5 w-3.5" strokeWidth={1.8} />
            <span className="font-display text-[14px] italic leading-none">新的探究</span>
          </span>
          <span className="font-mono text-[10px] tracking-[0.15em] text-[var(--color-paper)]/60 group-hover:text-[var(--color-paper)]/80">
            N
          </span>
        </button>
      </div>

      {/* Thread list */}
      <div className="flex-1 overflow-y-auto px-3 pb-2">
        <div className="mb-2 px-2 pt-1">
          <span className="label-eyebrow text-[9px]">Folios · 对话</span>
        </div>
        {threads.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-3 py-10 text-center">
            <svg viewBox="0 0 48 48" className="mb-3 h-10 w-10 text-[var(--color-ink-faint)]" fill="none" stroke="currentColor" strokeWidth="1">
              <rect x="8" y="6" width="32" height="36" rx="2" />
              <path d="M14 14h20M14 20h20M14 26h14" opacity="0.5" />
            </svg>
            <p className="font-display text-[13px] italic text-[var(--color-ink-mute)]">一纸尚白</p>
            <p className="mt-1 text-[10px] tracking-wide text-[var(--color-ink-faint)]">
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

      {/* Memory panel */}
      {userMemory.length > 0 && (
        <div className="relative border-t border-[var(--color-rule)] bg-[var(--color-parchment)]/55 px-3 pt-3 pb-2.5 dark:bg-[var(--color-paper-deep)]/50">
          <div className="absolute -top-[9px] left-4 bg-[var(--color-sidebar)] px-1.5">
            <span className="label-eyebrow text-[9px] text-[var(--color-ink-mute)]">Memoria</span>
          </div>
          <div className="mb-2 flex items-center justify-between px-1">
            <div className="flex items-baseline gap-2">
              <span className="font-display text-[13px] italic text-[var(--color-ink)]">
                用户记忆
              </span>
              <span className="font-mono text-[10px] tracking-wide text-[var(--color-ink-faint)]">
                · {userMemory.length} 条
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
                className="rounded-sm px-1.5 py-0.5 text-[10px] tracking-wide text-[var(--color-ink-faint)] transition hover:bg-[var(--color-vermilion-soft)] hover:text-[var(--color-vermilion-deep)]"
                title="清空全部记忆"
              >
                清空
              </button>
            )}
          </div>
          <div className="max-h-64 space-y-1 overflow-y-auto pr-1">
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

      {/* Colophon */}
      <div className="border-t border-[var(--color-rule)] px-4 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ZapIcon className="h-2.5 w-2.5 text-[var(--color-vermilion)]" strokeWidth={2} />
            <span className="font-display text-[11px] italic leading-none text-[var(--color-ink-mute)]">
              TinyFlow
            </span>
          </div>
          <span className="font-mono text-[9px] tracking-[0.2em] text-[var(--color-ink-faint)]">
            MMXXVI
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
    conf >= 0.7 ? "text-[var(--color-verdigris-deep)] dark:text-[var(--color-verdigris)]" :
    conf >= 0.5 ? "text-[var(--color-lapis)] dark:text-[var(--color-lapis-soft)]" :
    conf >= 0.3 ? "text-[var(--color-gilt-deep)] dark:text-[var(--color-gilt)]" :
                  "text-[var(--color-ink-faint)]";
  const confBar =
    conf >= 0.7 ? "bg-[var(--color-verdigris)]" :
    conf >= 0.5 ? "bg-[var(--color-lapis)]" :
    conf >= 0.3 ? "bg-[var(--color-gilt)]" :
                  "bg-[var(--color-ink-faint)]";

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
      <div className="rounded-[4px] border border-[var(--color-vermilion)]/50 bg-[var(--color-paper)] p-2 shadow-[0_2px_6px_-2px_rgba(140,70,40,0.12)]">
        <div className="flex items-start gap-1.5">
          <select
            value={draftCat}
            onChange={(e) => setDraftCat(e.target.value)}
            className="flex-shrink-0 rounded-sm border border-[var(--color-rule)] bg-[var(--color-paper)] px-1 py-0.5 text-[10px] text-[var(--color-ink-soft)] focus:border-[var(--color-vermilion)]/40 focus:outline-none"
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
            className="flex-1 resize-none rounded-sm border border-[var(--color-rule)] bg-[var(--color-paper)] px-1.5 py-0.5 text-[11px] leading-relaxed text-[var(--color-ink)] focus:border-[var(--color-vermilion)]/40 focus:outline-none"
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
            className="rounded-sm px-1.5 py-0.5 text-[var(--color-ink-mute)] hover:bg-[var(--color-parchment)]"
            title="取消 (Esc)"
          >
            <XIcon className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={handleSaveEdit}
            className="rounded-sm bg-[var(--color-ink)] px-1.5 py-0.5 text-[var(--color-paper)] hover:bg-[var(--color-vermilion)]"
            title="保存 (⌘/Ctrl+Enter)"
          >
            <CheckIcon className="h-3 w-3" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group rounded-[4px] border border-[var(--color-rule-soft)] bg-[var(--color-paper)]/80 transition-colors hover:border-[var(--color-rule)] dark:bg-[var(--color-card)]/50">
      <div className="flex items-start">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-start gap-2 px-2 py-1.5 text-left text-[11.5px] leading-relaxed text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]"
        >
          <span className="mt-[1px] flex-shrink-0 opacity-75">{meta.emoji}</span>
          <span className="flex-1 break-words font-display">{fact.content}</span>
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
                className="rounded-sm p-1 text-[var(--color-ink-faint)] hover:bg-[var(--color-parchment)] hover:text-[var(--color-ink)]"
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
                className="rounded-sm p-1 text-[var(--color-ink-faint)] hover:bg-[var(--color-vermilion-soft)] hover:text-[var(--color-vermilion-deep)]"
                title="删除"
              >
                <Trash2Icon className="h-3 w-3" />
              </button>
            )}
          </div>
        )}
      </div>

      {open && (
        <div className="space-y-2 border-t border-[var(--color-rule-soft)] bg-[var(--color-parchment)]/40 px-2.5 py-2 dark:bg-[var(--color-paper-deep)]/40">
          {/* Overall confidence bar */}
          <div>
            <div className="mb-1 flex items-center justify-between text-[10px] text-[var(--color-ink-mute)]">
              <span className="label-eyebrow text-[9px]">综合置信度</span>
              <span className={`font-mono tabular-nums ${confColor}`}>{conf.toFixed(3)}</span>
            </div>
            <div className="relative h-1 w-full overflow-hidden rounded-full bg-[var(--color-rule-soft)]">
              <div
                className={`absolute inset-y-0 left-0 ${confBar}`}
                style={{ width: `${Math.max(Math.min(conf * 100, 100), 2)}%` }}
              />
            </div>
          </div>

          {(E === 0 && R === 0 && C === 0) && (
            <div className="rounded-sm border border-[var(--color-gilt)]/30 bg-[var(--color-gilt-soft)]/60 px-2 py-1.5 text-[10px] italic leading-snug text-[var(--color-gilt-deep)] dark:bg-[var(--color-parchment)]/40">
              这条记忆是早期版本创建的，没有保留 breakdown。新提取的记忆会完整展示打分过程。
            </div>
          )}

          {/* Formula */}
          {(E !== 0 || R !== 0 || C !== 0) && (
          <div className="rounded-sm border border-[var(--color-rule-soft)] bg-[var(--color-paper)]/80 px-2 py-1.5 font-mono text-[10px] leading-snug text-[var(--color-ink-soft)]">
            <div className="mb-0.5 text-[var(--color-ink-faint)]">confidence =</div>
            <div>
              <span className="text-[var(--color-lapis)]">0.3</span>
              <span className="text-[var(--color-ink-faint)]"> · </span>
              <span className="text-[var(--color-lapis)]">{E.toFixed(2)}</span>
              <span className="text-[var(--color-ink-faint)]"> + </span>
              <span className="text-[var(--color-verdigris-deep)]">0.4</span>
              <span className="text-[var(--color-ink-faint)]"> · </span>
              <span className="text-[var(--color-verdigris-deep)]">{R.toFixed(2)}</span>
              <span className="text-[var(--color-ink-faint)]"> + </span>
              <span className="text-[var(--color-gilt-deep)]">0.3</span>
              <span className="text-[var(--color-ink-faint)]"> · </span>
              <span className="text-[var(--color-gilt-deep)]">{C.toFixed(2)}</span>
            </div>
            <div className="mt-0.5 text-[var(--color-ink-mute)]">
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
                    <span className="text-[var(--color-ink-soft)]">
                      <span className="font-display italic">{cfg.label}</span>
                      <span className="ml-1 font-mono text-[9px] text-[var(--color-ink-faint)]">
                        · w {SCORE_WEIGHTS[key]}
                      </span>
                    </span>
                    <span className="font-mono tabular-nums text-[var(--color-ink-mute)]">
                      {val.toFixed(2)}
                    </span>
                  </div>
                  <div className="h-[3px] overflow-hidden rounded-full bg-[var(--color-rule-soft)]">
                    <div
                      className={`h-full ${cfg.color}`}
                      style={{ width: `${Math.min(val * 100, 100)}%` }}
                    />
                  </div>
                  <div className="mt-0.5 text-[10px] italic leading-tight text-[var(--color-ink-faint)]">
                    {cfg.hint}
                  </div>
                </div>
              );
            })}
          </div>
          )}

          {/* Metadata */}
          {(fact.access_count !== undefined || fact.source_thread || fact.created_at) && (
            <div className="flex flex-wrap gap-x-2.5 gap-y-0.5 border-t border-[var(--color-rule-soft)] pt-1.5 font-mono text-[10px] text-[var(--color-ink-faint)]">
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
