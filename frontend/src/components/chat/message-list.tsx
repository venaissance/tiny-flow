"use client";

import { useEffect, useRef } from "react";
import type { Message } from "@/lib/types";
import { MessageItem } from "./message-item";

export function MessageList({
  messages,
  isStreaming = false,
}: {
  messages: Message[];
  isStreaming?: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4">
      {messages.map((msg, i) => (
        <MessageItem
          key={msg.id}
          message={msg}
          isStreaming={isStreaming && i === messages.length - 1}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
