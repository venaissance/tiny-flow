"use client";

import { useCallback, useRef, useState } from "react";
import type { SSEEventType } from "@/lib/types";

type EventHandler = (data: unknown) => void;

export function useSSE() {
  const [isConnected, setIsConnected] = useState(false);
  const handlersRef = useRef<Map<SSEEventType, EventHandler>>(new Map());
  const abortRef = useRef<AbortController | null>(null);

  const on = useCallback((event: SSEEventType, handler: EventHandler) => {
    handlersRef.current.set(event, handler);
  }, []);

  const off = useCallback((event: SSEEventType) => {
    handlersRef.current.delete(event);
  }, []);

  const clearHandlers = useCallback(() => {
    handlersRef.current.clear();
  }, []);

  const connect = useCallback(
    async (url: string, body: Record<string, unknown>) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsConnected(true);
      let doneReceived = false;

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        // Persist currentEvent across chunks so split event:/data: lines work
        let currentEvent: SSEEventType = "content";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split("\n");
          buffer = parts.pop() || "";

          for (const line of parts) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith(":")) continue;

            if (trimmed.startsWith("event:")) {
              currentEvent = trimmed.slice(6).trim() as SSEEventType;
            } else if (trimmed.startsWith("data:")) {
              const dataStr = trimmed.slice(5).trim();
              try {
                const data = JSON.parse(dataStr);
                const handler = handlersRef.current.get(currentEvent);
                handler?.(data);
                if (currentEvent === "done") doneReceived = true;
              } catch {
                // ignore parse errors
              }
              currentEvent = "content"; // reset after processing
            } else if (trimmed.startsWith("id:")) {
              // SSE id field — skip
            }
          }
        }

        // Process remaining buffer
        if (buffer.trim()) {
          const lines = buffer.split("\n");
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith("event:")) {
              currentEvent = trimmed.slice(6).trim() as SSEEventType;
            } else if (trimmed.startsWith("data:")) {
              try {
                const data = JSON.parse(trimmed.slice(5).trim());
                handlersRef.current.get(currentEvent)?.(data);
                if (currentEvent === "done") doneReceived = true;
              } catch {
                // ignore
              }
              currentEvent = "content";
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          const errorHandler = handlersRef.current.get("error");
          errorHandler?.(err);
        }
      } finally {
        setIsConnected(false);
        // Only fire done if the SSE event wasn't already received
        if (!doneReceived) {
          handlersRef.current.get("done")?.({});
        }
      }
    },
    [],
  );

  const disconnect = useCallback(() => {
    abortRef.current?.abort();
    setIsConnected(false);
  }, []);

  return { connect, disconnect, on, off, clearHandlers, isConnected };
}
