"use client";

import { useCallback, useState } from "react";
import { Streamdown } from "streamdown";
import { streamdownPlugins } from "@/core/streamdown";
import { Bot, Loader2, Copy, Check, FileCode2, ExternalLink } from "lucide-react";
import type { Message } from "@/lib/types";

/**
 * Detect if message content contains a full HTML document that would
 * pollute the parent page styles if rendered via Streamdown/rehype-raw.
 */
function containsHtmlDocument(content: string): boolean {
  return (
    content.includes("<!DOCTYPE") ||
    content.includes("<!doctype") ||
    /```html\s*\n[\s\S]*<style/i.test(content) ||
    (content.includes("<style") && content.includes("</style>"))
  );
}

function UserMessage({ message }: { message: Message }) {
  return (
    <div className="flex justify-end mb-4">
      <div className="max-w-[70%] rounded-2xl rounded-br-md bg-blue-500/90 px-4 py-2.5 text-white text-sm shadow-sm shadow-blue-500/20 backdrop-blur-sm">
        {message.content}
      </div>
    </div>
  );
}

function ProcessingMessage({ message }: { message: Message }) {
  return (
    <div className="mb-3 animate-step-in">
      {message.toolCalls?.map((tc, i) => (
        <div
          key={i}
          className="inline-flex items-center gap-2.5 rounded-xl border border-gray-200 bg-gray-50/80 px-4 py-2 text-xs text-gray-600 shadow-sm backdrop-blur-sm dark:border-gray-700/60 dark:bg-gray-800/50 dark:text-gray-300"
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
          <span className="text-gray-400 dark:text-gray-500">搜索</span>
          <span className="font-medium text-gray-700 dark:text-gray-200">{tc.query}</span>
        </div>
      ))}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Silently ignore if clipboard API unavailable
    }
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="rounded p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
      title="复制内容"
      aria-label="Copy message content"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-green-500" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

function HtmlArtifactCard({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  const titleMatch =
    content.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.trim() ||
    content.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)?.[1]?.replace(/<[^>]*>/g, "").trim();
  const title = isStreaming ? "正在生成网页..." : (titleMatch || "网页已生成");

  return (
    <div className="group mb-6 flex gap-3">
      <div className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-900/40">
        {isStreaming ? (
          <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
        ) : (
          <FileCode2 className="h-4 w-4 text-blue-600 dark:text-blue-400" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3 rounded-xl border border-blue-200/60 bg-gradient-to-r from-blue-50/80 to-indigo-50/50 px-4 py-3 shadow-sm dark:border-blue-800/40 dark:from-blue-950/30 dark:to-indigo-950/20">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-gray-800 dark:text-gray-200">{title}</p>
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {isStreaming ? "生成完成后可在右侧面板预览" : "HTML 页面已生成，请在右侧面板预览"}
            </p>
          </div>
          {!isStreaming && <ExternalLink className="h-4 w-4 flex-shrink-0 text-gray-400" />}
        </div>
      </div>
    </div>
  );
}

/**
 * Defense-in-depth: strip <style> and <script> tags from content before
 * passing to Streamdown, preventing CSS/JS injection into the host page.
 */
function sanitizeForStreamdown(content: string): string {
  return content
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "");
}

function AssistantMessage({
  message,
  isStreaming,
}: {
  message: Message;
  isStreaming: boolean;
}) {
  if (!message.content) return null;

  // ALWAYS intercept HTML documents — never pass to Streamdown
  // (regardless of streaming state, to prevent CSS/JS injection)
  if (containsHtmlDocument(message.content)) {
    return <HtmlArtifactCard content={message.content} isStreaming={isStreaming} />;
  }

  // Defense-in-depth: strip any stray <style>/<script> tags
  const safeContent = sanitizeForStreamdown(message.content);

  return (
    <div className="group mb-6 flex gap-3">
      <div className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100 dark:bg-gray-800">
        <Bot className="h-4 w-4 text-gray-500 dark:text-gray-400" />
      </div>
      <div className="relative min-w-0 flex-1 border-l-2 border-gray-200/60 pl-4 dark:border-gray-700/40">
        <div className="prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-headings:font-semibold">
          <Streamdown
            remarkPlugins={streamdownPlugins.remarkPlugins}
            rehypePlugins={streamdownPlugins.rehypePlugins}
            parseIncompleteMarkdown={isStreaming}
            isAnimating={isStreaming}
          >
            {safeContent}
          </Streamdown>
        </div>
        {!isStreaming && (
          <div className="absolute -top-1 right-0 opacity-0 transition-opacity group-hover:opacity-100">
            <CopyButton text={message.content} />
          </div>
        )}
      </div>
    </div>
  );
}

export function MessageItem({
  message,
  isStreaming = false,
}: {
  message: Message;
  isStreaming?: boolean;
}) {
  switch (message.role) {
    case "user":
      return <UserMessage message={message} />;
    case "processing":
      return <ProcessingMessage message={message} />;
    case "assistant":
      return <AssistantMessage message={message} isStreaming={isStreaming} />;
    default:
      return null;
  }
}
