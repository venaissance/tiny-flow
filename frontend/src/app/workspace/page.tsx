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
  Sparkles,
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
    <div className="mb-4 ml-10 space-y-0.5">
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        const isFailed = step.status === "failed";
        const isRunning = step.status === "running" && isLast;
        const Icon = stepIcon(step);

        return (
          <div
            key={step.id}
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-sm animate-step-in",
              isLast ? "opacity-100" : "opacity-50",
              isRunning && "bg-blue-50/60 dark:bg-blue-950/20",
            )}
          >
            <div className="flex-shrink-0">
              {isFailed ? (
                <XCircle className="h-3.5 w-3.5 text-red-400" />
              ) : isRunning ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
              ) : step.status === "completed" ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              ) : (
                <Icon className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
              )}
            </div>
            <span
              className={cn(
                "text-xs",
                isFailed
                  ? "text-red-600 dark:text-red-400"
                  : "text-gray-500 dark:text-gray-400",
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
  const { messages, isStreaming, steps, send, clearMessages, switchToThread, disconnect, todos, executionMode, memoryFacts } =
    useChat();
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
    <div className="flex h-screen">
      {/* ── Sidebar ── */}
      <div className={cn("flex-shrink-0 transition-all duration-200", sidebarOpen ? "w-64" : "w-0")}>
        {sidebarOpen && (
          <div className="flex h-full flex-col">
            <div className="flex-1 overflow-hidden">
              <ThreadSidebar
                threads={threads}
                activeThreadId={activeThreadId}
                onSelect={handleSwitchThread}
                onNew={handleNewThread}
                onDelete={deleteThread}
              />
            </div>
            {/* Memory Panel */}
            {memoryFacts.length > 0 && (
              <div className="border-t border-gray-200 bg-gradient-to-b from-blue-50/80 to-purple-50/60 p-3 dark:border-gray-700 dark:from-blue-950/30 dark:to-purple-950/20">
                <div className="mb-2 flex items-center gap-1.5">
                  <span className="text-sm">🧠</span>
                  <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">用户记忆</span>
                </div>
                <div className="space-y-1">
                  {memoryFacts.map((fact, i) => (
                    <div
                      key={i}
                      className="rounded-md bg-white/70 px-2 py-1 text-xs text-gray-700 shadow-sm dark:bg-gray-800/50 dark:text-gray-300"
                    >
                      {fact}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
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
            {/* Header */}
            <header className="relative z-10 flex items-center justify-between bg-white/80 px-4 py-2.5 shadow-[0_1px_3px_0_rgb(0_0_0/0.06),0_1px_2px_-1px_rgb(0_0_0/0.04)] backdrop-blur-sm dark:bg-gray-950/80">
              <div className="flex items-center gap-2.5">
                <button
                  onClick={() => setSidebarOpen((v) => !v)}
                  className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                  </svg>
                </button>
                <svg className="h-5 w-5 text-blue-600 dark:text-blue-400" viewBox="0 0 24 24" fill="none">
                  <circle cx="6" cy="12" r="2.5" fill="currentColor" opacity="0.85" />
                  <circle cx="18" cy="6" r="2.5" fill="currentColor" opacity="0.6" />
                  <circle cx="18" cy="18" r="2.5" fill="currentColor" opacity="0.6" />
                  <path d="M8.2 11.1L15.5 7.2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" opacity="0.5" />
                  <path d="M8.2 12.9L15.5 16.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" opacity="0.5" />
                </svg>
                <h1 className="text-sm font-semibold tracking-tight text-gray-800 dark:text-gray-200">
                  TinyFlow
                </h1>
              </div>
              <div className="flex items-center gap-3">
                {artifactContent && !showArtifact && (
                  <button
                    onClick={() => setShowArtifact(true)}
                    className="flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-600 shadow-sm transition-all hover:bg-blue-100 hover:shadow dark:bg-blue-950/60 dark:text-blue-400"
                  >
                    报告
                  </button>
                )}
              </div>
              {isStreaming && (
                <div className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden">
                  <div className="h-full w-full animate-[header-gradient_3s_ease_infinite] bg-gradient-to-r from-transparent via-blue-500 to-transparent bg-[length:200%_100%]" />
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
                  <div className="flex h-full items-center justify-center">
                    <div className="flex flex-col items-center gap-6 text-center">
                      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-blue-900/30 dark:to-indigo-900/20">
                        <Sparkles className="h-7 w-7 text-blue-500 dark:text-blue-400" />
                      </div>
                      <div>
                        <p className="text-base font-medium text-gray-700 dark:text-gray-200">有什么我可以帮你的?</p>
                        <p className="mt-1 text-sm text-gray-400">输入问题开始研究，或试试下面的例子</p>
                      </div>
                      <div className="flex flex-wrap justify-center gap-2">
                        {[
                          { label: "⚡ 什么是 ReAct Agent？", prompt: "什么是 ReAct Agent？" },
                          { label: "📋 搜索 Claude Code 更新", prompt: "帮我搜索一下 Claude Code 最新的更新内容" },
                          { label: "🚀 并行调研三个话题", prompt: "分别调研以下三个话题：1. Claude 4.5 最新能力 2. Cursor 和 Claude Code 的对比 3. 2026年 AI Coding 工具市场格局" },
                          { label: "📡 Pulse 科技日报", prompt: "帮我生成今日的 Pulse 科技日报" },
                          { label: "🎯 调研+制作 PPT", prompt: "先调研 AI Agent 2026 年最新趋势，然后用这些调研结果制作一个演示文稿" },
                        ].map(({ label, prompt }) => (
                          <button
                            key={label}
                            onClick={() => handleSend(prompt)}
                            className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm text-gray-600 shadow-sm transition-all hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                          >
                            {label}
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
                      <details className="mb-4 ml-10 rounded-lg border border-gray-200/60 dark:border-gray-700/40">
                        <summary className="cursor-pointer px-3 py-2 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300">
                          🔍 推理过程 ({steps.length} 步)
                        </summary>
                        <div className="border-t border-gray-100 dark:border-gray-800">
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
                  className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full border bg-white/90 px-3 py-1.5 text-xs text-gray-500 shadow-md backdrop-blur-sm hover:shadow-lg dark:border-gray-700 dark:bg-gray-800/90"
                >
                  <ArrowDown className="h-3.5 w-3.5" />
                  新内容
                </button>
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
