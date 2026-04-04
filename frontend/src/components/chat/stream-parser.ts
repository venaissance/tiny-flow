// frontend/src/components/chat/stream-parser.ts
import type { SSEEventType } from "@/lib/types";

export interface ParsedSSELine {
  event: SSEEventType;
  data: unknown;
}

export function parseSSELine(line: string): ParsedSSELine | null {
  if (line.startsWith("data:")) {
    try {
      return { event: "content", data: JSON.parse(line.slice(5).trim()) };
    } catch {
      return null;
    }
  }
  return null;
}
