export type SSEEventType =
  | "thinking"
  | "content"
  | "tool_call"
  | "tool_result"
  | "subagent_status"
  | "subagent_result"
  | "memory_update"
  | "done"
  | "error";

export interface AgentStep {
  id: string;
  type: "thinking" | "tool_call" | "tool_result" | "subagent_status" | "subagent_done";
  content: string;
  status?: "running" | "completed" | "failed";
  timestamp: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "processing";
  content: string;
  thinking?: string;
  toolCalls?: ToolCallInfo[];
  timestamp: number;
}

export interface ToolCallInfo {
  name: string;
  query: string;
  preview?: string;
}

export interface SubagentTask {
  taskId: string;
  status: "pending" | "running" | "completed" | "failed" | "timed_out";
  type: string;
  label?: string;
  output?: string;
}

export interface MemoryFact {
  id: string;
  content: string;
  category: string;
  confidence: number;
}

export interface Thread {
  thread_id: string;
  title?: string;
  updated_at?: string;
}
