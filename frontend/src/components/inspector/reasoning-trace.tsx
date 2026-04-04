"use client";

import type { Message } from "@/lib/types";

export function ReasoningTrace({ messages }: { messages: Message[] }) {
  const thinkingMessages = messages.filter((m) => m.thinking);

  if (thinkingMessages.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-500">No reasoning trace yet</div>
    );
  }

  return (
    <div className="space-y-3 p-4">
      <h3 className="text-sm font-semibold">Reasoning Trace</h3>
      {thinkingMessages.map((msg, i) => (
        <div key={msg.id} className="rounded border p-3 text-xs">
          <div className="mb-1 text-gray-500">Step {i + 1}</div>
          <div className="whitespace-pre-wrap text-gray-700 dark:text-gray-300">
            {msg.thinking}
          </div>
        </div>
      ))}
    </div>
  );
}
