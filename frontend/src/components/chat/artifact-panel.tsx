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
    <div className={cn("flex h-full flex-col bg-white dark:bg-gray-950", className)}>
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {isHtml ? "网页预览" : "研究报告"}
        </span>

        <div className="flex items-center gap-1">
          {/* View mode toggle */}
          <div className="mr-2 flex rounded-md border text-xs dark:border-gray-700">
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
                  "px-2.5 py-1 transition-colors",
                  i === 0 && "rounded-l-md",
                  i === arr.length - 1 && "rounded-r-md",
                  viewMode === tab.key
                    ? "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100"
                    : "text-gray-500 hover:text-gray-700 dark:text-gray-400",
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
              className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
              title="新窗口打开"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
              </svg>
            </button>
          )}

          {/* Copy */}
          <button
            onClick={handleCopy}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
            title="复制"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
            </svg>
          </button>

          {/* Close */}
          <button
            onClick={onClose}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
            title="关闭"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {viewMode === "preview" ? (
          isHtml && html ? (
            <iframe
              className="h-full w-full border-0"
              title="HTML preview"
              sandbox="allow-scripts allow-forms allow-modals allow-popups allow-same-origin"
              srcDoc={html}
            />
          ) : (
            <div className="h-full overflow-y-auto p-6">
              <Streamdown
                className="prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-a:text-blue-600 prose-a:underline prose-a:underline-offset-2 prose-code:rounded prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-sm prose-code:dark:bg-gray-800 prose-pre:rounded-lg prose-pre:bg-gray-50 prose-pre:dark:bg-gray-900 prose-table:border-collapse prose-th:border prose-th:border-gray-200 prose-th:bg-gray-50 prose-th:px-3 prose-th:py-2 prose-th:dark:border-gray-700 prose-th:dark:bg-gray-800 prose-td:border prose-td:border-gray-200 prose-td:px-3 prose-td:py-2 prose-td:dark:border-gray-700"
                remarkPlugins={streamdownPlugins.remarkPlugins}
                rehypePlugins={streamdownPlugins.rehypePlugins}
              >
                {content}
              </Streamdown>
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
