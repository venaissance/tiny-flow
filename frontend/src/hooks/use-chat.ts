"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { nanoid } from "nanoid";
import type { Message, ToolCallInfo, AgentStep, TodoItem, ExecutionMode, SSEEventType } from "@/lib/types";

export type { AgentStep } from "@/lib/types";

/**
 * Per-thread streaming state — each thread has its own fetch/SSE connection,
 * buffer, and abort controller. Threads run independently in the background.
 */
interface ThreadStream {
  buffer: {
    messages: Message[];
    assistantCreated: boolean;
    todos: TodoItem[];
    steps: AgentStep[];
    mode: ExecutionMode | null;
  };
  abortController: AbortController;
  running: boolean;
}

/**
 * Parse SSE lines from a text chunk. Handles event:/data: pairs.
 */
export function parseSSELines(
  lines: string[],
  currentEvent: { value: SSEEventType },
  callback: (event: SSEEventType, data: unknown) => void,
) {
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith(":") || trimmed.startsWith("id:")) continue;
    if (trimmed.startsWith("event:")) {
      currentEvent.value = trimmed.slice(6).trim() as SSEEventType;
    } else if (trimmed.startsWith("data:")) {
      try {
        const data = JSON.parse(trimmed.slice(5).trim());
        callback(currentEvent.value, data);
      } catch { /* ignore */ }
      currentEvent.value = "content";
    }
  }
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [executionMode, setExecutionMode] = useState<ExecutionMode | null>(null);
  // Durable, cross-thread user memory facts (from MemoryEngine, persisted to disk).
  const [userMemory, setUserMemory] = useState<Array<{
    id: string;
    content: string;
    category: string;
    confidence: number;
    access_count?: number;
    score_breakdown?: { explicitness?: number; repetition?: number; consistency?: number };
    source_thread?: string;
    created_at?: string;
  }>>([]);
  // Per-thread rolling conversation summary (from AsyncCompactor).
  const [threadSummary, setThreadSummary] = useState<string>("");
  const activeThreadRef = useRef<string>("default");

  // Fetch durable user memory on mount so the sidebar shows facts even
  // before any stream fires an SSE event.
  const refetchMemory = useCallback(async () => {
    try {
      const r = await fetch("/api/memory");
      if (!r.ok) return;
      const data = await r.json();
      if (data?.facts) setUserMemory(data.facts);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    let cancelled = false;
    refetchMemory().then(() => { if (cancelled) return; });
    return () => { cancelled = true; };
  }, [refetchMemory]);

  const deleteMemoryFact = useCallback(async (id: string) => {
    setUserMemory((prev) => prev.filter((f) => f.id !== id));
    await fetch(`/api/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
    await refetchMemory();
  }, [refetchMemory]);

  const updateMemoryFact = useCallback(async (
    id: string,
    patch: { content?: string; category?: string; confidence?: number },
  ) => {
    setUserMemory((prev) =>
      prev.map((f) => (f.id === id ? { ...f, ...patch } : f)),
    );
    await fetch(`/api/memory/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    await refetchMemory();
  }, [refetchMemory]);

  const clearMemory = useCallback(async () => {
    setUserMemory([]);
    await fetch("/api/memory", { method: "DELETE" });
  }, []);

  // Per-thread streams: each thread can run independently
  const streamsRef = useRef<Map<string, ThreadStream>>(new Map());

  const isCurrent = useCallback((threadId: string) => {
    return activeThreadRef.current === threadId;
  }, []);

  // Sync a thread's buffer to UI state (only if it's the active thread)
  const syncToUI = useCallback((threadId: string, stream: ThreadStream) => {
    if (!isCurrent(threadId)) return;
    setMessages([...stream.buffer.messages]);
    setSteps([...stream.buffer.steps]);
    setTodos([...stream.buffer.todos]);
    setExecutionMode(stream.buffer.mode);
    setIsStreaming(stream.running);
  }, [isCurrent]);

  const send = useCallback(
    async (content: string, threadId: string = "default") => {
      // Per-thread lock: only block same thread, not other threads
      const existingStream = streamsRef.current.get(threadId);
      if (existingStream?.running) return;

      activeThreadRef.current = threadId;

      const userMsg: Message = {
        id: nanoid(), role: "user", content, timestamp: Date.now(),
      };

      const abortController = new AbortController();
      const startedAt = Date.now();
      const stream: ThreadStream = {
        buffer: {
          messages: [...messages, userMsg],
          assistantCreated: false,
          todos: [],
          steps: [],
          mode: null,
        },
        abortController,
        running: true,
      };
      streamsRef.current.set(threadId, stream);

      // Update UI immediately
      setMessages(stream.buffer.messages);
      setIsStreaming(true);
      setSteps([]);
      setTodos([]);
      setExecutionMode(null);

      const addStep = (step: AgentStep) => {
        stream.buffer.steps = [...stream.buffer.steps, step];
        if (isCurrent(threadId)) setSteps([...stream.buffer.steps]);
      };

      // SSE event handler
      const handleEvent = (event: SSEEventType, data: unknown) => {
        const buf = stream.buffer;
        const raw = data as Record<string, unknown>;

        switch (event) {
          case "thinking": {
            const text = (raw.content ?? "") as string;
            addStep({ id: nanoid(), type: "thinking", content: text, status: "running", timestamp: Date.now() });
            break;
          }
          case "tool_call": {
            const name = (raw.name ?? "") as string;
            const query = (raw.query ?? "") as string;
            const pm: Message = { id: nanoid(), role: "processing", content: "", toolCalls: [{ name, query }], timestamp: Date.now() };
            buf.messages = [...buf.messages, pm];
            addStep({ id: nanoid(), type: "tool_call", content: `🔍 ${name}: ${query}`, status: "running", timestamp: Date.now() });
            if (isCurrent(threadId)) setMessages([...buf.messages]);
            break;
          }
          case "tool_result": {
            buf.messages = buf.messages.filter((m) => m.role !== "processing");
            addStep({ id: nanoid(), type: "tool_result", content: `✅ ${(raw.name ?? "") as string} 返回结果`, status: "completed", timestamp: Date.now() });
            if (isCurrent(threadId)) setMessages([...buf.messages]);
            break;
          }
          case "subagent_status": {
            addStep({ id: nanoid(), type: "subagent_status", content: (raw.label ?? "任务执行中...") as string, status: "running", timestamp: Date.now() });
            break;
          }
          case "subagent_result": {
            addStep({ id: nanoid(), type: "subagent_done", content: (raw.label ?? "完成") as string, status: (raw.status as string) === "completed" ? "completed" : "failed", timestamp: Date.now() });
            break;
          }
          case "content": {
            const chunk = (raw.content ?? "") as string;
            buf.messages = buf.messages.filter((m) => m.role !== "processing");
            if (!buf.assistantCreated) {
              buf.assistantCreated = true;
              buf.messages = [
                ...buf.messages,
                {
                  id: nanoid(),
                  role: "assistant",
                  content: chunk,
                  timestamp: Date.now(),
                  firstTokenMs: Date.now() - startedAt,
                },
              ];
            } else {
              const msgs = [...buf.messages];
              for (let i = msgs.length - 1; i >= 0; i--) {
                if (msgs[i]?.role === "assistant") {
                  msgs[i] = { ...msgs[i]!, content: msgs[i]!.content + chunk };
                  break;
                }
              }
              buf.messages = msgs;
            }
            if (isCurrent(threadId)) setMessages([...buf.messages]);
            break;
          }
          case "todo_update": {
            buf.todos = (raw.todos ?? []) as TodoItem[];
            if (isCurrent(threadId)) setTodos([...buf.todos]);
            break;
          }
          case "mode_selected": {
            buf.mode = (raw.mode ?? null) as ExecutionMode | null;
            const reason = (raw.reason ?? "") as string;
            if (isCurrent(threadId)) setExecutionMode(buf.mode);
            const modeLabel = buf.mode === "flash" ? "⚡ 快速回答" : buf.mode === "thinking" ? "🧠 深度推理" : buf.mode === "pro" ? "📋 规划执行" : "🚀 并行研究";
            addStep({ id: nanoid(), type: "thinking", content: `策略: ${modeLabel} — ${reason}`, status: "completed", timestamp: Date.now() });
            break;
          }
          case "loop_warning": {
            addStep({ id: nanoid(), type: "thinking", content: `⚠️ ${(raw.message ?? "") as string}`, status: "failed", timestamp: Date.now() });
            break;
          }
          case "context_compacted": {
            const strategy = (raw.strategy ?? "truncate") as string;
            const strategyLabel = strategy === "smart" ? "🧠 智能压缩" : "✂️ 截断压缩";
            const preview = (raw.summary_preview ?? "") as string;
            const compactMsg = `${strategyLabel} · ${raw.original_messages} → ${raw.compacted_to} 条消息`;
            addStep({ id: nanoid(), type: "thinking", content: compactMsg, status: "completed", timestamp: Date.now() });
            if (preview) setThreadSummary(preview);
            break;
          }
          case "user_memory": {
            // Durable cross-thread user facts from MemoryEngine.
            const facts = (raw.facts ?? []) as Array<{
              id?: string;
              content: string;
              category?: string;
              confidence?: number;
              access_count?: number;
              score_breakdown?: { explicitness?: number; repetition?: number; consistency?: number };
              source_thread?: string;
              created_at?: string;
            }>;
            if (Array.isArray(facts)) {
              setUserMemory(
                facts.map((f) => ({
                  id: f.id ?? nanoid(),
                  content: f.content,
                  category: f.category ?? "context",
                  confidence: f.confidence ?? 0.5,
                  access_count: f.access_count,
                  score_breakdown: f.score_breakdown,
                  source_thread: f.source_thread,
                  created_at: f.created_at,
                })),
              );
            }
            break;
          }
          case "error": {
            const errMsg = (raw.error ?? "未知错误") as string;
            buf.messages = [...buf.messages, { id: nanoid(), role: "assistant", content: `❌ 错误: ${errMsg}`, timestamp: Date.now() }];
            if (isCurrent(threadId)) setMessages([...buf.messages]);
            break;
          }
          case "done": {
            buf.messages = buf.messages.filter((m) => m.role !== "processing");
            if (isCurrent(threadId)) setMessages([...buf.messages]);
            break;
          }
        }
      };

      // Independent fetch + SSE parsing (not shared useSSE)
      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: content, thread_id: threadId }),
          signal: abortController.signal,
        });

        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = "";
        const currentEvent = { value: "content" as SSEEventType };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          sseBuffer += decoder.decode(value, { stream: true });
          const parts = sseBuffer.split("\n");
          sseBuffer = parts.pop() || "";
          parseSSELines(parts, currentEvent, handleEvent);
        }
        if (sseBuffer.trim()) {
          parseSSELines(sseBuffer.split("\n"), currentEvent, handleEvent);
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          handleEvent("error", { error: (err as Error).message });
        }
      } finally {
        stream.running = false;
        // Finalize all "running" steps to "completed"
        stream.buffer.steps = stream.buffer.steps.map((s) =>
          s.status === "running" ? { ...s, status: "completed" as const } : s,
        );
        // Stamp total duration on last assistant message
        const totalMs = Date.now() - startedAt;
        const lastAssistantIdx = [...stream.buffer.messages]
          .map((m, i) => ({ m, i }))
          .reverse()
          .find(({ m }) => m.role === "assistant")?.i;
        if (lastAssistantIdx !== undefined) {
          const msgs = [...stream.buffer.messages];
          msgs[lastAssistantIdx] = { ...msgs[lastAssistantIdx]!, durationMs: totalMs };
          stream.buffer.messages = msgs;
        }
        if (isCurrent(threadId)) {
          setIsStreaming(false);
          setSteps([...stream.buffer.steps]);
          setMessages([...stream.buffer.messages]);
        }
        saveBufferToBackend(threadId, stream.buffer);
      }
    },
    [messages, isCurrent],
  );

  const saveBufferToBackend = useCallback(
    (threadId: string, buffer: ThreadStream["buffer"]) => {
      const serializable = buffer.messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content, timestamp: m.timestamp }));
      if (serializable.length === 0) return;
      fetch(`/api/threads?thread_id=${threadId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: serializable }),
      }).catch(() => {});
    },
    [],
  );

  const loadMessages = useCallback(async (threadId: string): Promise<Message[]> => {
    const stream = streamsRef.current.get(threadId);
    if (stream && stream.buffer.messages.length > 0) {
      return stream.buffer.messages;
    }
    try {
      const res = await fetch(`/api/threads?thread_id=${threadId}&messages=true`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.messages) && data.messages.length > 0) {
          return data.messages.map((m: { role: string; content: string; timestamp?: number }) => ({
            id: nanoid(), role: m.role as Message["role"], content: m.content, timestamp: m.timestamp || Date.now(),
          }));
        }
      }
    } catch { /* non-critical */ }
    return [];
  }, []);

  const switchToThread = useCallback(
    async (threadId: string) => {
      activeThreadRef.current = threadId;

      // Restore state from stream buffer if thread is running
      const stream = streamsRef.current.get(threadId);
      if (stream) {
        setMessages([...stream.buffer.messages]);
        setSteps([...stream.buffer.steps]);
        setTodos([...stream.buffer.todos]);
        setExecutionMode(stream.buffer.mode);
        setIsStreaming(stream.running);
      } else {
        // Load from backend
        const saved = await loadMessages(threadId);
        setMessages(saved);
        setSteps([]);
        setTodos([]);
        setExecutionMode(null);
        setIsStreaming(false);
      }
    },
    [loadMessages],
  );

  const disconnect = useCallback(() => {
    const threadId = activeThreadRef.current;
    const stream = streamsRef.current.get(threadId);
    if (stream) {
      stream.abortController.abort();
      stream.running = false;
    }
    setIsStreaming(false);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setSteps([]);
    setTodos([]);
    setExecutionMode(null);
    setIsStreaming(false);
  }, []);

  return {
    messages, isStreaming, steps, todos, executionMode,
    userMemory, threadSummary,
    send, disconnect, clearMessages, switchToThread, setMessages,
    deleteMemoryFact, updateMemoryFact, clearMemory,
  };
}
