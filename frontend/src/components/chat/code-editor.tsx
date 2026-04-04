"use client";

import { useMemo } from "react";
import { css } from "@codemirror/lang-css";
import { html } from "@codemirror/lang-html";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { languages } from "@codemirror/language-data";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import { cn } from "@/lib/utils";

const darkTheme = monokaiInit({
  settings: {
    background: "transparent",
    gutterBackground: "transparent",
    gutterForeground: "#555",
    fontSize: "13px",
  },
});

const lightTheme = basicLightInit({
  settings: {
    background: "transparent",
    fontSize: "13px",
  },
});

export function CodeEditor({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  // Detect dark mode via media query
  const isDark = typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;

  const extensions = useMemo(() => [
    css(),
    html(),
    javascript({}),
    json(),
    markdown({ base: markdownLanguage, codeLanguages: languages }),
    python(),
  ], []);

  return (
    <CodeMirror
      readOnly
      value={value}
      theme={isDark ? darkTheme : lightTheme}
      extensions={extensions}
      className={cn(
        "h-full overflow-auto font-mono [&_.cm-editor]:h-full [&_.cm-focused]:outline-none!",
        className,
      )}
      basicSetup={{
        foldGutter: true,
        highlightActiveLine: false,
        highlightActiveLineGutter: false,
        lineNumbers: true,
      }}
    />
  );
}
