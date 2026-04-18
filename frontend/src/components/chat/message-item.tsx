"use client";

import { useCallback, useState } from "react";
import { Streamdown } from "streamdown";
import { streamdownPlugins } from "@/core/streamdown";
import { Bot, Loader2, Copy, Check, FileCode2, ExternalLink } from "lucide-react";
import { ThinkingBlock } from "@/components/chat/thinking-block";
import type { Message } from "@/lib/types";

/**
 * Extract <thinking>...</thinking> blocks from content.
 * Returns { thinking, answer } where answer is the content without thinking blocks.
 */
function extractThinking(content: string): { thinking: string | null; answer: string } {
  const match = content.match(/<thinking>([\s\S]*?)<\/thinking>/);
  if (!match) return { thinking: null, answer: content };
  const thinking = match[1]?.trim() || null;
  const answer = content.replace(/<thinking>[\s\S]*?<\/thinking>/, "").trim();
  return { thinking, answer };
}

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
    <div className="group mb-5 flex items-start justify-end gap-2">
      <div className="mt-2 opacity-0 transition-opacity group-hover:opacity-100">
        <CopyButton text={message.content} />
      </div>
      <div className="relative max-w-[72%] rounded-[6px] bg-[var(--color-ink)] px-4 py-2.5 text-[13.5px] leading-relaxed text-[var(--color-paper)] shadow-[0_1px_2px_rgba(0,0,0,0.08)]">
        <span className="pointer-events-none absolute -bottom-1 right-1 h-1.5 w-1.5 rounded-[1px] bg-[var(--color-vermilion)]" />
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
          className="inline-flex items-center gap-2.5 rounded-[5px] border border-[var(--color-rule)] bg-[var(--color-parchment)]/60 px-3.5 py-1.5 text-xs text-[var(--color-ink-soft)] shadow-[0_1px_2px_-1px_rgba(60,40,20,0.05)]"
        >
          <Loader2 className="h-3 w-3 animate-spin text-[var(--color-vermilion)]" />
          <span className="label-eyebrow text-[9px]">Query</span>
          <span className="font-display italic">{tc.query}</span>
        </div>
      ))}
    </div>
  );
}

function DurationLabel({ firstTokenMs, durationMs }: { firstTokenMs?: number; durationMs?: number }) {
  if (durationMs == null && firstTokenMs == null) return null;
  const fmt = (ms: number) =>
    ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10000 ? 0 : 1)}s` : `${Math.round(ms)}ms`;
  const title =
    firstTokenMs != null && durationMs != null
      ? `首字 ${fmt(firstTokenMs)} · 总耗时 ${fmt(durationMs)}`
      : undefined;
  return (
    <span
      title={title}
      className="font-mono text-[10px] tracking-wide text-[var(--color-ink-faint)]"
    >
      {durationMs != null ? fmt(durationMs) : firstTokenMs != null ? `${fmt(firstTokenMs)}…` : ""}
    </span>
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
      className="rounded-sm p-1 text-[var(--color-ink-faint)] transition-colors hover:bg-[var(--color-parchment)] hover:text-[var(--color-ink)]"
      title="复制内容"
      aria-label="Copy message content"
    >
      {copied ? (
        <Check className="h-3 w-3 text-[var(--color-verdigris-deep)]" />
      ) : (
        <Copy className="h-3 w-3" />
      )}
    </button>
  );
}

function HtmlArtifactCard({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  const titleMatch =
    content.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.trim() ||
    content.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)?.[1]?.replace(/<[^>]*>/g, "").trim();
  const title = isStreaming ? "正在生成网页..." : (titleMatch || "网页已生成");

  // Extract a readable preview: strip HTML tags, take last ~150 chars (most recent content)
  const preview = isStreaming
    ? content.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(-150)
    : null;

  return (
    <div className="group mb-6 flex gap-3">
      <div className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[4px] border border-[var(--color-vermilion)]/30 bg-[var(--color-vermilion-soft)]/60">
        {isStreaming ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--color-vermilion)]" />
        ) : (
          <FileCode2 className="h-3.5 w-3.5 text-[var(--color-vermilion-deep)]" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="rounded-[5px] border border-[var(--color-rule)] bg-[var(--color-paper)]/80 shadow-[0_1px_2px_-1px_rgba(60,40,20,0.05)]">
          <div className="flex items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <span className="label-eyebrow block text-[9px]">Folio · Artifact</span>
              <p className="mt-0.5 truncate font-display text-[15px] font-medium text-[var(--color-ink)]">{title}</p>
              <p className="mt-0.5 font-mono text-[10px] text-[var(--color-ink-faint)]">
                {isStreaming
                  ? `已生成 ${content.length} 字符...`
                  : "HTML 页面已生成，请在右侧面板预览"}
              </p>
            </div>
            {!isStreaming && <ExternalLink className="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-ink-mute)]" />}
          </div>
          {isStreaming && preview && (
            <div className="border-t border-[var(--color-rule-soft)] px-4 py-2">
              <p className="line-clamp-3 font-mono text-[10.5px] leading-relaxed text-[var(--color-ink-faint)]">
                {preview}
              </p>
            </div>
          )}
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

  // Extract <thinking> blocks and strip dangerous tags
  const { thinking, answer } = extractThinking(message.content);
  const safeContent = sanitizeForStreamdown(answer);

  return (
    <div className="group mb-6 flex gap-3">
      <div className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[4px] border border-[var(--color-rule)] bg-[var(--color-parchment)]/60">
        <Bot className="h-3.5 w-3.5 text-[var(--color-ink-soft)]" strokeWidth={1.5} />
      </div>
      <div className="relative min-w-0 flex-1 border-l border-[var(--color-rule-soft)] pl-4">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="label-eyebrow text-[9px]">Scholar</span>
          <div className="h-px flex-1 bg-[var(--color-rule-soft)]" />
        </div>
        {thinking && !isStreaming && <ThinkingBlock content={thinking} />}
        <div className="prose prose-sm max-w-none prose-p:leading-relaxed prose-p:text-[var(--color-ink)] prose-headings:font-display prose-headings:font-medium prose-headings:text-[var(--color-ink)] prose-strong:text-[var(--color-ink)] prose-code:text-[var(--color-vermilion-deep)] prose-a:text-[var(--color-vermilion-deep)] prose-a:decoration-[var(--color-vermilion)]/40 hover:prose-a:text-[var(--color-vermilion)] dark:prose-invert dark:prose-p:text-[var(--color-ink)] dark:prose-headings:text-[var(--color-ink)] dark:prose-code:text-[var(--color-vermilion-soft)] dark:prose-a:text-[var(--color-vermilion-soft)]">
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
          <div className="mt-2 flex items-center gap-2 border-t border-[var(--color-rule-soft)] pt-2">
            <CopyButton text={message.content} />
            <DurationLabel
              firstTokenMs={message.firstTokenMs}
              durationMs={message.durationMs}
            />
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
