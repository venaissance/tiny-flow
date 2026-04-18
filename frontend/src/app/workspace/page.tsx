"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import type { GroupImperativeHandle } from "react-resizable-panels";

import { MessageItem } from "@/components/chat/message-item";
import { InputBox, type InputBoxHandle } from "@/components/chat/input-box";
import { ThreadSidebar } from "@/components/chat/thread-sidebar";
import { ArtifactPanel } from "@/components/chat/artifact-panel";
import { TodoCard } from "@/components/chat/todo-card";
import { ModeBadge } from "@/components/chat/mode-badge";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { useChat, type AgentStep } from "@/hooks/use-chat";
import { useThreads } from "@/hooks/use-threads";
import { cn } from "@/lib/utils";
import {
  Brain,
  Search,
  Zap,
  CheckCircle2,
  XCircle,
  Loader2,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Step Timeline
// ---------------------------------------------------------------------------

function stepIcon(step: AgentStep) {
  if (step.type === "thinking") return Brain;
  if (step.type === "tool_call" || step.type === "tool_result") return Search;
  return Zap;
}

function StepTimeline({ steps }: { steps: AgentStep[] }) {
  if (steps.length === 0) return null;

  return (
    <div className="mb-4 ml-10 space-y-0 border-l border-dashed border-[var(--color-rule)] pl-4">
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        const isFailed = step.status === "failed";
        const isRunning = step.status === "running" && isLast;
        const Icon = stepIcon(step);

        return (
          <div
            key={step.id}
            className={cn(
              "group relative -ml-6 flex items-center gap-3 rounded-sm py-1 pl-6 text-sm animate-step-in",
              isLast ? "opacity-100" : "opacity-55",
            )}
          >
            <div className={cn(
              "absolute left-[-7px] top-1/2 flex h-[13px] w-[13px] -translate-y-1/2 items-center justify-center rounded-full border bg-[var(--color-paper)] transition-colors",
              isFailed ? "border-[var(--color-vermilion-deep)]"
                : isRunning ? "border-[var(--color-vermilion)]"
                : step.status === "completed" ? "border-[var(--color-verdigris)]"
                : "border-[var(--color-ink-faint)]",
            )}>
              {isFailed ? (
                <XCircle className="h-2.5 w-2.5 text-[var(--color-vermilion-deep)]" />
              ) : isRunning ? (
                <Loader2 className="h-2.5 w-2.5 animate-spin text-[var(--color-vermilion)]" />
              ) : step.status === "completed" ? (
                <CheckCircle2 className="h-2.5 w-2.5 text-[var(--color-verdigris-deep)]" />
              ) : (
                <Icon className="h-2.5 w-2.5 text-[var(--color-ink-mute)]" />
              )}
            </div>
            <span
              className={cn(
                "font-display text-[12.5px] italic leading-tight",
                isFailed ? "text-[var(--color-vermilion-deep)]"
                  : isRunning ? "text-[var(--color-ink)]"
                  : "text-[var(--color-ink-mute)]",
              )}
            >
              {step.content}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel layout constants (DeerFlow pattern)
// ---------------------------------------------------------------------------
const LAYOUT_CHAT_ONLY = { chat: 100, artifact: 0 };
const LAYOUT_WITH_ARTIFACT = { chat: 58, artifact: 42 };

// ---------------------------------------------------------------------------
// Workspace Page
// ---------------------------------------------------------------------------

export default function WorkspacePage() {
  const {
    messages, isStreaming, steps, send, clearMessages, switchToThread, disconnect,
    todos, executionMode, userMemory, threadSummary,
    deleteMemoryFact, updateMemoryFact, clearMemory,
  } = useChat();
  const {
    threads,
    activeThreadId,
    createThread,
    switchThread,
    deleteThread,
    updateTitle,
  } = useThreads();

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<InputBoxHandle>(null);
  const layoutRef = useRef<GroupImperativeHandle>(null);
  const [artifactContent, setArtifactContent] = useState<string | null>(null);
  const [showArtifact, setShowArtifact] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const firstMessageSentRef = useRef(false);
  const initialLoadDone = useRef(false);

  // On mount: if URL hash has a threadId, load its messages
  useEffect(() => {
    if (initialLoadDone.current) return;
    if (activeThreadId && messages.length === 0) {
      initialLoadDone.current = true;
      switchToThread(activeThreadId);
    }
  }, [activeThreadId, messages.length, switchToThread]);

  // Scroll tracking
  const isNearBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handleScroll = () => {
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
      isNearBottomRef.current = dist <= 100;
      setShowScrollButton(dist > 100);
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (!isNearBottomRef.current) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, steps]);

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, []);

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key === "k") { e.preventDefault(); inputRef.current?.focus(); return; }
      if (mod && e.key === "\\") { e.preventDefault(); setSidebarOpen((v) => !v); return; }
      if (e.key === "Escape" && showArtifact) { e.preventDefault(); setShowArtifact(false); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [showArtifact]);

  // ── Artifact panel sync (DeerFlow pattern: always render, use setLayout) ──
  useEffect(() => {
    if (!layoutRef.current) return;
    if (showArtifact && artifactContent) {
      layoutRef.current.setLayout(LAYOUT_WITH_ARTIFACT);
    } else {
      layoutRef.current.setLayout(LAYOUT_CHAT_ONLY);
    }
  }, [showArtifact, artifactContent]);

  // Auto-detect artifacts
  useEffect(() => {
    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
    if (!lastAssistant || isStreaming) return;
    const text = lastAssistant.content;
    const hasHtml = text.includes("<!DOCTYPE") || text.includes("<!doctype") || /```html\s*\n/.test(text);
    if (hasHtml || text.length > 500) {
      setArtifactContent(text);
      setShowArtifact(true);
    }
  }, [messages, isStreaming]);

  // ── Thread management ──
  const handleSend = useCallback(
    async (content: string) => {
      let threadId = activeThreadId;
      if (!threadId) {
        threadId = await createThread();
      }
      if (!firstMessageSentRef.current) {
        firstMessageSentRef.current = true;
        updateTitle(threadId, content);
      }
      send(content, threadId);
    },
    [activeThreadId, createThread, send, updateTitle],
  );

  // Switch thread: abort stream + load saved messages
  const handleSwitchThread = useCallback(
    async (threadId: string) => {
      switchThread(threadId);
      setArtifactContent(null);
      setShowArtifact(false);
      firstMessageSentRef.current = true;
      await switchToThread(threadId);
    },
    [switchThread, switchToThread],
  );

  const handleNewThread = useCallback(async () => {
    await createThread();
    clearMessages();
    setArtifactContent(null);
    setShowArtifact(false);
    firstMessageSentRef.current = false;
  }, [createThread, clearMessages]);

  const handleCloseArtifact = useCallback(() => {
    setShowArtifact(false);
  }, []);

  const artifactOpen = showArtifact && !!artifactContent;

  return (
    <div className="relative z-10 flex h-screen">
      {/* ── Sidebar ── */}
      <div className={cn("flex-shrink-0 transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]", sidebarOpen ? "w-72" : "w-0")}>
        {sidebarOpen && (
          <ThreadSidebar
            threads={threads}
            activeThreadId={activeThreadId}
            onSelect={handleSwitchThread}
            onNew={handleNewThread}
            onDelete={deleteThread}
            userMemory={userMemory}
            onMemoryDelete={deleteMemoryFact}
            onMemoryUpdate={updateMemoryFact}
            onMemoryClear={clearMemory}
          />
        )}
      </div>

      {/* ── Chat + Artifact (DeerFlow: always render both, use setLayout) ── */}
      <ResizablePanelGroup
        orientation="horizontal"
        groupRef={layoutRef}
        defaultLayout={LAYOUT_CHAT_ONLY}
      >
        <ResizablePanel id="chat" defaultSize={100} minSize={40}>
          <div className="flex h-full flex-col">
            {/* Header — the masthead */}
            <header className="relative z-10 flex items-center justify-between border-b border-[var(--color-rule-soft)] bg-[var(--color-paper)]/70 px-6 py-3 backdrop-blur-[6px]">
              <div className="flex items-center gap-3.5">
                <button
                  onClick={() => setSidebarOpen((v) => !v)}
                  className="rounded p-1 text-[var(--color-ink-mute)] transition-colors hover:bg-[var(--color-parchment)] hover:text-[var(--color-ink)]"
                  aria-label="Toggle sidebar"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.4}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                  </svg>
                </button>
                <div className="h-4 w-px bg-[var(--color-rule)]" />
                {/* Brand: ornament + display serif wordmark */}
                <div className="flex items-baseline gap-2.5">
                  <svg
                    className="h-[18px] w-[18px] translate-y-[2px] text-[var(--color-vermilion)]"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.4"
                  >
                    <circle cx="12" cy="12" r="4" fill="currentColor" fillOpacity="0.18" />
                    <circle cx="12" cy="12" r="4" />
                    <circle cx="5" cy="6" r="1.4" fill="currentColor" />
                    <circle cx="19" cy="6" r="1.4" fill="currentColor" opacity="0.55" />
                    <circle cx="5" cy="18" r="1.4" fill="currentColor" opacity="0.55" />
                    <circle cx="19" cy="18" r="1.4" fill="currentColor" opacity="0.8" />
                    <path d="M6.2 6.8 L10 10.3 M17.8 6.8 L14 10.3 M6.2 17.2 L10 13.7 M17.8 17.2 L14 13.7" stroke="currentColor" strokeWidth="0.9" opacity="0.6" />
                  </svg>
                  <h1 className="font-display text-[19px] font-medium leading-none tracking-tight text-[var(--color-ink)]">
                    Tiny<span className="italic text-[var(--color-vermilion)]">Flow</span>
                  </h1>
                  <span className="label-eyebrow hidden translate-y-[-1px] sm:inline">
                    Venaissance Workbench
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {artifactContent && !showArtifact && (
                  <button
                    onClick={() => setShowArtifact(true)}
                    className="group inline-flex items-center gap-2 rounded-full border border-[var(--color-vermilion)]/30 bg-[var(--color-vermilion-soft)] px-3.5 py-1 text-[11px] font-medium tracking-wide text-[var(--color-vermilion-deep)] transition-all hover:border-[var(--color-vermilion)]/60 hover:shadow-sm dark:border-[var(--color-vermilion)]/40 dark:bg-[var(--color-vermilion)]/10 dark:text-[var(--color-vermilion-soft)]"
                  >
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-vermilion)]" />
                    <span className="small-caps text-[10px]">Folio</span>
                    <span className="font-display italic">报告</span>
                  </button>
                )}
              </div>
              {isStreaming && (
                <div className="absolute inset-x-0 bottom-[-1px] h-[1.5px] overflow-hidden">
                  <div className="h-full w-full animate-[header-gradient_3s_ease_infinite] bg-[length:200%_100%] bg-gradient-to-r from-transparent via-[var(--color-vermilion)] to-transparent" />
                </div>
              )}
            </header>

            {/* Messages */}
            <div className="relative flex-1">
              <div ref={scrollRef} className="absolute inset-0 overflow-y-auto px-6">
                {isStreaming && (
                  <div className="sticky top-0 z-10 h-0.5 w-full overflow-hidden">
                    <div className="h-full w-1/3 animate-[stream-bar_1.8s_ease-in-out_infinite] rounded-full bg-blue-500/70" />
                  </div>
                )}
                {messages.length === 0 ? (
                  <div className="flex h-full items-center justify-center px-6">
                    <div className="flex w-full max-w-2xl flex-col items-center gap-10 text-center">
                      {/* Illuminated initial — a Renaissance drop-cap */}
                      <div className="relative">
                        <div className="flex h-24 w-24 items-center justify-center">
                          <svg viewBox="0 0 96 96" className="absolute inset-0 h-full w-full text-[var(--color-vermilion)]/30">
                            <circle cx="48" cy="48" r="46" fill="none" stroke="currentColor" strokeWidth="0.75" strokeDasharray="1 3" />
                            <circle cx="48" cy="48" r="38" fill="none" stroke="currentColor" strokeWidth="0.5" />
                          </svg>
                          <span className="font-display text-[64px] font-light italic leading-none tracking-tight text-[var(--color-vermilion)]">T</span>
                        </div>
                      </div>

                      <div className="space-y-3">
                        <p className="label-eyebrow">Folio I · A New Inquiry</p>
                        <h2 className="font-display text-4xl font-light leading-[1.1] tracking-tight text-[var(--color-ink)]">
                          有什么值得<span className="italic text-[var(--color-vermilion)]">探究</span>的？
                        </h2>
                        <p className="mx-auto max-w-md font-serif text-[15px] italic leading-relaxed text-[var(--color-ink-mute)]" style={{ fontFamily: "var(--font-display)" }}>
                          Propose a question, and the agents shall begin their dialogue.
                        </p>
                      </div>

                      <div className="ornament-rule w-48" />

                      <div className="grid w-full grid-cols-1 gap-px overflow-hidden rounded-[6px] border border-[var(--color-rule)] bg-[var(--color-rule)] sm:grid-cols-2">
                        {[
                          { numeral: "I",   cap: "Definitions",     label: "什么是 ReAct Agent？", prompt: "什么是 ReAct Agent？" },
                          { numeral: "II",  cap: "Dispatches",      label: "搜索 Claude Code 更新", prompt: "帮我搜索一下 Claude Code 最新的更新内容" },
                          { numeral: "III", cap: "Parallel Studies", label: "并行调研三个话题", prompt: "分别调研以下三个话题：1. Claude 4.5 最新能力 2. Cursor 和 Claude Code 的对比 3. 2026年 AI Coding 工具市场格局" },
                          { numeral: "IV",  cap: "Daily Folio",     label: "Pulse 科技日报", prompt: "帮我生成今日的 Pulse 科技日报" },
                          { numeral: "V",   cap: "Codex Atelier",   label: "调研 + 制作 PPT", prompt: "先调研 AI Agent 2026 年最新趋势，然后用这些调研结果制作一个演示文稿" },
                        ].map(({ numeral, cap, label, prompt }) => (
                          <button
                            key={label}
                            onClick={() => handleSend(prompt)}
                            className="group relative flex items-start gap-3 bg-[var(--color-paper)] px-5 py-4 text-left transition-colors duration-200 hover:bg-[var(--color-parchment)] focus-visible:bg-[var(--color-parchment)]"
                          >
                            <span className="font-display mt-0.5 w-7 flex-shrink-0 text-right text-[13px] italic leading-none text-[var(--color-vermilion)]/70 group-hover:text-[var(--color-vermilion)]">
                              {numeral}.
                            </span>
                            <span className="flex-1">
                              <span className="label-eyebrow block text-[9px] text-[var(--color-ink-faint)] group-hover:text-[var(--color-ink-mute)]">
                                {cap}
                              </span>
                              <span className="mt-1 block font-display text-[15px] font-normal leading-snug text-[var(--color-ink)] group-hover:text-[var(--color-ink)]">
                                {label}
                              </span>
                            </span>
                            <svg className="mt-1 h-3.5 w-3.5 flex-shrink-0 text-[var(--color-ink-faint)] opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                              <path d="M5 12h14M13 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mx-auto max-w-3xl py-4">
                    {messages.map((msg, i) => (
                      <div key={msg.id} className="animate-[msg-in_0.3s_ease-out_forwards]">
                        <MessageItem
                          message={msg}
                          isStreaming={isStreaming && i === messages.length - 1 && msg.role === "assistant"}
                        />
                      </div>
                    ))}
                    {/* Mode badge + TODO card */}
                    {executionMode && <ModeBadge mode={executionMode} />}
                    {todos.length > 0 && <TodoCard todos={todos} />}

                    {/* Step timeline: live during streaming, collapsible after */}
                    {isStreaming && steps.length > 0 && <StepTimeline steps={steps} />}
                    {!isStreaming && steps.length > 0 && (
                      <details className="mb-4 ml-10 rounded-[4px] border border-[var(--color-rule)]/70 bg-[var(--color-paper-deep)]/40">
                        <summary className="flex cursor-pointer select-none items-center gap-2 px-3 py-2 text-[var(--color-ink-mute)] transition-colors hover:text-[var(--color-ink)]">
                          <span className="label-eyebrow text-[9px]">Apparatus</span>
                          <span className="font-display text-[12px] italic">推理过程</span>
                          <span className="font-mono text-[10px] tracking-wide text-[var(--color-ink-faint)]">
                            · {steps.length} 步
                          </span>
                        </summary>
                        <div className="border-t border-[var(--color-rule-soft)] pt-2">
                          <StepTimeline steps={steps} />
                        </div>
                      </details>
                    )}
                  </div>
                )}
              </div>

              {showScrollButton && messages.length > 0 && (
                <button
                  onClick={scrollToBottom}
                  className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-[var(--color-rule)] bg-[var(--color-paper)]/95 px-3.5 py-1 text-[11px] font-medium tracking-wide text-[var(--color-ink-soft)] shadow-[0_2px_10px_-2px_rgba(60,40,20,0.1)] backdrop-blur-sm transition-all hover:border-[var(--color-vermilion)]/40 hover:text-[var(--color-vermilion)]"
                >
                  <ArrowDown className="h-3 w-3" />
                  <span className="small-caps text-[9px]">Scroll</span>
                  <span className="font-display italic">新内容</span>
                </button>
              )}

              {/* Per-thread compaction summary — a marginalia note */}
              {threadSummary && (
                <div className="pointer-events-auto absolute bottom-3 left-3 z-10 max-w-xs">
                  <details className="group rounded-[4px] border border-[var(--color-gilt)]/35 bg-[var(--color-gilt-soft)]/90 px-3 py-2 text-xs shadow-[0_2px_12px_-3px_rgba(140,100,40,0.12)] backdrop-blur-sm dark:border-[var(--color-gilt)]/30 dark:bg-[var(--color-parchment)]/60">
                    <summary className="flex cursor-pointer select-none items-center gap-2 text-[var(--color-gilt-deep)] dark:text-[var(--color-gilt)]">
                      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M4 19h16M6 19V7l6-3 6 3v12" />
                        <path d="M9 12h6" opacity="0.5" />
                      </svg>
                      <span className="small-caps text-[9px]">Marginalia</span>
                      <span className="font-display italic">本会话记忆</span>
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap font-display text-[12px] italic leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-ink-soft)]">
                      {threadSummary}
                    </p>
                  </details>
                </div>
              )}
            </div>

            {/* Input */}
            <div className="mx-auto w-full max-w-3xl">
              <InputBox ref={inputRef} onSend={handleSend} onStop={disconnect} disabled={isStreaming} isStreaming={isStreaming} />
            </div>
          </div>
        </ResizablePanel>

        {/* Handle — visible only when artifact is open */}
        <ResizableHandle
          id="chat-artifact-sep"
          withHandle
          className={cn(
            "transition-opacity duration-200",
            artifactOpen ? "opacity-40 hover:opacity-100" : "pointer-events-none opacity-0",
          )}
        />

        {/* Artifact panel — always rendered, size controlled by setLayout */}
        <ResizablePanel
          id="artifact"
          defaultSize={0}
          className={cn(
            "transition-opacity duration-300",
            !artifactOpen && "opacity-0",
          )}
        >
          <div className={cn("h-full transition-transform duration-300", artifactOpen ? "translate-x-0" : "translate-x-full")}>
            {artifactContent && (
              <ArtifactPanel content={artifactContent} onClose={handleCloseArtifact} />
            )}
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
