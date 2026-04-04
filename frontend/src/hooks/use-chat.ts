"use client";

import { useCallback, useRef, useState } from "react";
import { nanoid } from "nanoid";
import type { Message, ToolCallInfo, AgentStep, TodoItem, ExecutionMode } from "@/lib/types";
import { useSSE } from "./use-sse";

export type { AgentStep } from "@/lib/types";

/**
 * Per-thread message buffer — accumulates messages during streaming
 * so background streams can save correctly even after thread switch.
 */
interface ThreadBuffer {
  messages: Message[];
  assistantCreated: boolean;
  todos: TodoItem[];
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [executionMode, setExecutionMode] = useState<ExecutionMode | null>(null);
  const { connect, disconnect, on, clearHandlers } = useSSE();
  const sendingRef = useRef(false);
  const activeThreadRef = useRef<string>("default");

  // Per-thread buffers: accumulate messages independently of React state
  const buffersRef = useRef<Map<string, ThreadBuffer>>(new Map());

  const send = useCallback(
    async (content: string, threadId: string = "default") => {
      if (sendingRef.current) return;
      sendingRef.current = true;
      activeThreadRef.current = threadId;

      const userMsg: Message = {
        id: nanoid(),
        role: "user",
        content,
        timestamp: Date.now(),
      };

      // Initialize buffer for this thread
      const buffer: ThreadBuffer = {
        messages: [...messages, userMsg],
        assistantCreated: false,
        todos: [],
      };
      buffersRef.current.set(threadId, buffer);

      setMessages(buffer.messages);
      setIsStreaming(true);
      setSteps([]);

      const expectedThread = threadId;
      const isCurrent = () => activeThreadRef.current === expectedThread;

      on("thinking", (data) => {
        if (!isCurrent()) return;
        const { content: text } = data as { node: string; content: string };
        setSteps((prev) => [
          ...prev,
          { id: nanoid(), type: "thinking", content: text, status: "running", timestamp: Date.now() },
        ]);
      });

      on("tool_call", (data) => {
        const { name, query } = data as ToolCallInfo;
        const processingMsg: Message = {
          id: nanoid(),
          role: "processing",
          content: "",
          toolCalls: [{ name, query }],
          timestamp: Date.now(),
        };
        // Always update buffer
        buffer.messages = [...buffer.messages, processingMsg];
        // Only update UI if current thread
        if (isCurrent()) {
          setMessages([...buffer.messages]);
          setSteps((prev) => [
            ...prev,
            { id: nanoid(), type: "tool_call", content: `🔍 ${name}: ${query}`, status: "running", timestamp: Date.now() },
          ]);
        }
      });

      on("tool_result", (data) => {
        const { name } = data as { name: string; preview: string };
        // Remove processing messages (search spinners) from buffer
        buffer.messages = buffer.messages.filter((m) => m.role !== "processing");
        if (isCurrent()) {
          setMessages([...buffer.messages]);
          setSteps((prev) => [
            ...prev,
            { id: nanoid(), type: "tool_result", content: `✅ ${name} 返回结果`, status: "completed", timestamp: Date.now() },
          ]);
        }
      });

      on("subagent_status", (data) => {
        if (!isCurrent()) return;
        const raw = data as Record<string, unknown>;
        setSteps((prev) => [
          ...prev,
          { id: nanoid(), type: "subagent_status", content: (raw.label ?? "任务执行中...") as string, status: "running", timestamp: Date.now() },
        ]);
      });

      on("subagent_result", (data) => {
        if (!isCurrent()) return;
        const raw = data as Record<string, unknown>;
        setSteps((prev) => [
          ...prev,
          { id: nanoid(), type: "subagent_done", content: (raw.label ?? "完成") as string, status: (raw.status as string) === "completed" ? "completed" : "failed", timestamp: Date.now() },
        ]);
      });

      on("content", (data) => {
        const { content: chunk } = data as { content: string };

        // Clear processing messages (search spinners) once content arrives
        const hadProcessing = buffer.messages.some((m) => m.role === "processing");
        if (hadProcessing) {
          buffer.messages = buffer.messages.filter((m) => m.role !== "processing");
        }

        if (!buffer.assistantCreated) {
          buffer.assistantCreated = true;
          const assistantMsg: Message = {
            id: nanoid(),
            role: "assistant",
            content: chunk,
            timestamp: Date.now(),
          };
          buffer.messages = [...buffer.messages, assistantMsg];
        } else {
          // Append to last assistant message in buffer
          const msgs = [...buffer.messages];
          for (let i = msgs.length - 1; i >= 0; i--) {
            const m = msgs[i];
            if (m && m.role === "assistant") {
              msgs[i] = { ...m, content: m.content + chunk };
              break;
            }
          }
          buffer.messages = msgs;
        }

        // Only update UI if this is the current thread
        if (isCurrent()) {
          setMessages([...buffer.messages]);
        }
      });

      on("todo_update", (data) => {
        const { todos: newTodos } = data as { todos: TodoItem[] };
        buffer.todos = newTodos;
        if (isCurrent()) setTodos(newTodos);
      });

      on("mode_selected", (data) => {
        const { mode, reason } = data as { mode: ExecutionMode; reason: string };
        if (isCurrent()) {
          setExecutionMode(mode);
          setSteps(prev => [...prev, {
            id: nanoid(), type: "thinking",
            content: `策略: ${mode === "flash" ? "⚡ 快速回答" : mode === "thinking" ? "🧠 深度推理" : mode === "pro" ? "📋 规划执行" : "🚀 并行研究"} — ${reason}`,
            status: "completed", timestamp: Date.now(),
          }]);
        }
      });

      on("loop_warning", (data) => {
        const { message } = data as { message: string };
        if (isCurrent()) {
          setSteps(prev => [...prev, {
            id: nanoid(), type: "thinking",
            content: `⚠️ ${message}`,
            status: "failed", timestamp: Date.now(),
          }]);
        }
      });

      on("context_compacted", (data) => {
        const { original_messages, compacted_to } = data as { original_messages: number; compacted_to: number };
        if (isCurrent()) {
          setSteps(prev => [...prev, {
            id: nanoid(), type: "thinking",
            content: `ℹ️ 对话较长，已压缩 ${original_messages} 条消息为 ${compacted_to} 条`,
            status: "completed", timestamp: Date.now(),
          }]);
        }
      });

      on("done", () => {
        // Clean up any remaining processing messages
        buffer.messages = buffer.messages.filter((m) => m.role !== "processing");
        if (isCurrent()) {
          setMessages([...buffer.messages]);
        }
        // Save buffer to backend
        saveBufferToBackend(expectedThread, buffer);
      });

      on("error", (data) => {
        const errMsg = (data as Record<string, unknown>)?.error ?? "未知错误";
        const errorMsg: Message = {
          id: nanoid(),
          role: "assistant",
          content: `❌ 错误: ${errMsg}`,
          timestamp: Date.now(),
        };
        buffer.messages = [...buffer.messages, errorMsg];
        if (isCurrent()) {
          setMessages([...buffer.messages]);
        }
      });

      try {
        await connect("/api/chat", { message: content, thread_id: threadId });
      } finally {
        // Only update streaming state if this is still the current thread
        if (isCurrent()) {
          setIsStreaming(false);
        }
        sendingRef.current = false;
        clearHandlers();
        // Final save
        saveBufferToBackend(expectedThread, buffer);
      }
    },
    [connect, on, clearHandlers, messages],
  );

  // Save a thread buffer to backend
  const saveBufferToBackend = useCallback(
    (threadId: string, buffer: ThreadBuffer) => {
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

  // Load messages for a thread from backend
  const loadMessages = useCallback(async (threadId: string): Promise<Message[]> => {
    // Check buffer first (may have in-progress stream data)
    const buf = buffersRef.current.get(threadId);
    if (buf && buf.messages.length > 0) {
      return buf.messages;
    }
    // Fetch from backend
    try {
      const res = await fetch(`/api/threads?thread_id=${threadId}&messages=true`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.messages) && data.messages.length > 0) {
          return data.messages.map((m: { role: string; content: string; timestamp?: number }) => ({
            id: nanoid(),
            role: m.role as Message["role"],
            content: m.content,
            timestamp: m.timestamp || Date.now(),
          }));
        }
      }
    } catch {
      // non-critical
    }
    return [];
  }, []);

  // Switch to a different thread (does NOT abort background streams)
  const switchToThread = useCallback(
    async (threadId: string) => {
      // DON'T disconnect — let background streams finish
      activeThreadRef.current = threadId;
      setSteps([]);
      setTodos([]);
      setExecutionMode(null);

      // If not currently streaming for this thread, clear streaming state
      if (!sendingRef.current || activeThreadRef.current !== threadId) {
        setIsStreaming(false);
      }

      // Load messages (from buffer or backend)
      const saved = await loadMessages(threadId);
      setMessages(saved);
    },
    [loadMessages],
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setSteps([]);
    setIsStreaming(false);
  }, []);

  return { messages, isStreaming, steps, todos, executionMode, send, disconnect, clearMessages, switchToThread, setMessages };
}
