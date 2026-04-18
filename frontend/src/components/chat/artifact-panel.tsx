"use client";

import { useCallback, useMemo, useState } from "react";
import { Streamdown } from "streamdown";
import { streamdownPlugins } from "@/core/streamdown";
import { CodeEditor } from "@/components/chat/code-editor";
import { cn } from "@/lib/utils";

interface ArtifactPanelProps {
  content: string;
  onClose: () => void;
  className?: string;
}

type ViewMode = "preview" | "html" | "css" | "js";

/**
 * Split a single HTML file into its constituent parts:
 * - HTML (with <style> and <script> blocks removed)
 * - CSS (all <style> contents joined)
 * - JS (all <script> contents joined)
 */
function splitHtmlParts(htmlSource: string): { html: string; css: string; js: string } {
  const cssBlocks: string[] = [];
  const htmlWithoutStyle = htmlSource.replace(
    /<style[^>]*>([\s\S]*?)<\/style>/gi,
    (_, content) => {
      cssBlocks.push(content.trim());
      return "";
    },
  );

  const jsBlocks: string[] = [];
  const htmlClean = htmlWithoutStyle.replace(
    /<script[^>]*>([\s\S]*?)<\/script>/gi,
    (_, content) => {
      jsBlocks.push(content.trim());
      return "";
    },
  );

  return {
    html: htmlClean.trim(),
    css: cssBlocks.join("\n\n"),
    js: jsBlocks.join("\n\n"),
  };
}

/**
 * Extract HTML from content — handles:
 * 1. Raw HTML (starts with <!DOCTYPE or <html)
 * 2. Markdown code block ```html ... ```
 * 3. Markdown with embedded HTML blocks
 */
function extractHtml(content: string): { html: string | null; isHtml: boolean } {
  const trimmed = content.trim();

  // Case 1: Raw HTML document
  if (
    trimmed.startsWith("<!DOCTYPE") ||
    trimmed.startsWith("<!doctype") ||
    trimmed.startsWith("<html") ||
    trimmed.startsWith("<HTML")
  ) {
    return { html: trimmed, isHtml: true };
  }

  // Case 2: Markdown code block containing HTML
  const htmlBlockMatch = trimmed.match(/```(?:html|HTML)\s*\n([\s\S]*?)```/);
  if (htmlBlockMatch && htmlBlockMatch[1]) {
    const extracted = htmlBlockMatch[1].trim();
    // Only treat as HTML if it looks like a full document or substantial HTML
    if (
      extracted.startsWith("<!DOCTYPE") ||
      extracted.startsWith("<!doctype") ||
      extracted.startsWith("<html") ||
      (extracted.includes("<head") && extracted.includes("<body"))
    ) {
      return { html: extracted, isHtml: true };
    }
  }

  return { html: null, isHtml: false };
}

export function ArtifactPanel({ content, onClose, className }: ArtifactPanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("preview");
  const { html, isHtml } = useMemo(() => extractHtml(content), [content]);
  const parts = useMemo(() => (html ? splitHtmlParts(html) : null), [html]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(isHtml && html ? html : content);
    } catch {
      // fallback
    }
  }, [content, html, isHtml]);

  // Open in new tab for full-screen preview
  const handleOpenInTab = useCallback(() => {
    if (!html) return;
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }, [html]);

  return (
    <div className={cn("relative flex h-full flex-col border-l border-[var(--color-rule)] bg-[var(--color-paper)]/90 backdrop-blur-sm", className)}>
      {/* Header — masthead for the folio */}
      <div className="relative flex items-center justify-between border-b border-[var(--color-rule)] px-5 py-2.5">
        <div className="flex items-baseline gap-2.5">
          <span className="label-eyebrow text-[9px]">
            {isHtml ? "Folio · Artifact" : "Folio · Research"}
          </span>
          <span className="font-display text-[15px] italic leading-none text-[var(--color-ink)]">
            {isHtml ? "网页预览" : "研究报告"}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {/* View mode toggle — book-tab style */}
          <div className="mr-1 flex overflow-hidden rounded-[4px] border border-[var(--color-rule)] bg-[var(--color-parchment)]/40 text-[11px]">
            {(
              isHtml
                ? [
                    { key: "preview" as ViewMode, label: "预览" },
                    { key: "html" as ViewMode, label: "HTML" },
                    { key: "css" as ViewMode, label: "CSS" },
                    { key: "js" as ViewMode, label: "JS" },
                  ]
                : [
                    { key: "preview" as ViewMode, label: "预览" },
                    { key: "html" as ViewMode, label: "源码" },
                  ]
            ).map((tab, i, arr) => (
              <button
                key={tab.key}
                onClick={() => setViewMode(tab.key)}
                className={cn(
                  "px-3 py-1 font-display italic transition-colors",
                  i > 0 && "border-l border-[var(--color-rule)]",
                  viewMode === tab.key
                    ? "bg-[var(--color-paper)] text-[var(--color-vermilion-deep)]"
                    : "text-[var(--color-ink-mute)] hover:bg-[var(--color-paper)]/60 hover:text-[var(--color-ink)]",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Open in new tab (HTML only) */}
          {isHtml && (
            <button
              onClick={handleOpenInTab}
              className="rounded-sm p-1.5 text-[var(--color-ink-faint)] transition-colors hover:bg-[var(--color-parchment)] hover:text-[var(--color-vermilion)]"
              title="新窗口打开"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.4}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
              </svg>
            </button>
          )}

          {/* Copy */}
          <button
            onClick={handleCopy}
            className="rounded-sm p-1.5 text-[var(--color-ink-faint)] transition-colors hover:bg-[var(--color-parchment)] hover:text-[var(--color-ink)]"
            title="复制"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.4}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
            </svg>
          </button>

          {/* Close */}
          <button
            onClick={onClose}
            className="rounded-sm p-1.5 text-[var(--color-ink-faint)] transition-colors hover:bg-[var(--color-vermilion-soft)] hover:text-[var(--color-vermilion-deep)]"
            title="关闭"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="relative flex-1 overflow-hidden">
        {/* Marginal decorative rule on the left edge */}
        <div className="pointer-events-none absolute left-[28px] top-6 bottom-6 w-px bg-[var(--color-rule-soft)]" aria-hidden />

        {viewMode === "preview" ? (
          isHtml && html ? (
            <iframe
              className="h-full w-full border-0 bg-white"
              title="HTML preview"
              sandbox="allow-scripts allow-forms allow-modals allow-popups allow-same-origin"
              srcDoc={html}
            />
          ) : (
            <div className="relative h-full overflow-y-auto">
              <article className="mx-auto max-w-2xl px-10 py-8">
                <Streamdown
                  className={cn(
                    "prose prose-sm max-w-none",
                    // base
                    "prose-p:leading-[1.8] prose-p:text-[var(--color-ink)]",
                    // headings
                    "prose-headings:font-display prose-headings:font-medium prose-headings:tracking-tight prose-headings:text-[var(--color-ink)]",
                    "prose-h1:text-[28px] prose-h1:leading-[1.15] prose-h1:mb-4 prose-h1:mt-0 prose-h1:border-b prose-h1:border-[var(--color-rule)] prose-h1:pb-3",
                    "prose-h2:text-[22px] prose-h2:italic prose-h2:mt-10 prose-h2:mb-3 prose-h2:text-[var(--color-vermilion-deep)]",
                    "prose-h3:text-[17px] prose-h3:italic prose-h3:mt-6 prose-h3:mb-2",
                    // links
                    "prose-a:text-[var(--color-vermilion-deep)] prose-a:decoration-[var(--color-vermilion)]/40 prose-a:underline-offset-[3px] hover:prose-a:text-[var(--color-vermilion)]",
                    // inline code
                    "prose-code:rounded-sm prose-code:border prose-code:border-[var(--color-rule-soft)] prose-code:bg-[var(--color-parchment)]/50 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[12.5px] prose-code:font-medium prose-code:text-[var(--color-vermilion-deep)] prose-code:before:content-none prose-code:after:content-none",
                    // pre / code blocks
                    "prose-pre:rounded-[5px] prose-pre:border prose-pre:border-[var(--color-rule)] prose-pre:bg-[var(--color-parchment)]/60 prose-pre:p-4 prose-pre:text-[12px] prose-pre:leading-relaxed prose-pre:shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]",
                    // tables — hairline manuscript style
                    "prose-table:my-6 prose-table:border-collapse prose-table:text-[13px]",
                    "prose-th:border-b-2 prose-th:border-[var(--color-ink)] prose-th:bg-transparent prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:font-display prose-th:font-semibold prose-th:italic",
                    "prose-td:border-b prose-td:border-[var(--color-rule-soft)] prose-td:px-3 prose-td:py-2.5 prose-td:align-top",
                    // blockquote
                    "prose-blockquote:border-l-2 prose-blockquote:border-[var(--color-vermilion)]/60 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-[var(--color-ink-soft)]",
                    // ul / ol
                    "prose-li:marker:text-[var(--color-vermilion)]/60 prose-li:my-0.5",
                    // strong
                    "prose-strong:font-semibold prose-strong:text-[var(--color-ink)]",
                    // hr
                    "prose-hr:border-[var(--color-rule)] prose-hr:my-8",
                    "dark:prose-invert",
                  )}
                  remarkPlugins={streamdownPlugins.remarkPlugins}
                  rehypePlugins={streamdownPlugins.rehypePlugins}
                >
                  {content}
                </Streamdown>
              </article>
            </div>
          )
        ) : viewMode === "html" ? (
          <CodeEditor
            value={isHtml && parts ? parts.html : content}
            className="h-full"
          />
        ) : viewMode === "css" ? (
          <CodeEditor
            value={parts?.css ?? ""}
            className="h-full"
          />
        ) : (
          <CodeEditor
            value={parts?.js ?? ""}
            className="h-full"
          />
        )}
      </div>
    </div>
  );
}
