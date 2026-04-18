"use client";

import {
  useState,
  useCallback,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
  type KeyboardEvent,
  type ChangeEvent,
} from "react";
import { ArrowUp, Square } from "lucide-react";
import { cn } from "@/lib/utils";

const CHAR_COUNT_THRESHOLD = 200;
const MAX_ROWS = 6;
const LINE_HEIGHT = 24; // px — matches leading-6 / text-sm default

interface InputBoxProps {
  onSend: (message: string) => void;
  onStop?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
}

export interface InputBoxHandle {
  focus: () => void;
}

export const InputBox = forwardRef<InputBoxHandle, InputBoxProps>(
  function InputBox({ onSend, onStop, disabled, isStreaming }, ref) {
    const [value, setValue] = useState("");
    const [focused, setFocused] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(ref, () => ({
      focus() {
        textareaRef.current?.focus();
      },
    }));

    // Auto-resize textarea height based on content
    const autoResize = useCallback(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "auto";
      const maxHeight = LINE_HEIGHT * MAX_ROWS;
      el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    }, []);

    useEffect(() => {
      autoResize();
    }, [value, autoResize]);

    const handleSend = useCallback(() => {
      const trimmed = value.trim();
      if (!trimmed || disabled) return;
      onSend(trimmed);
      setValue("");
      // Reset height after clearing
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (el) el.style.height = "auto";
      });
    }, [value, disabled, onSend]);

    const handleKeyDown = (e: KeyboardEvent) => {
      // Enter (no modifier) or Cmd/Ctrl+Enter both send
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
        return;
      }
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        handleSend();
      }
    };

    const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
      setValue(e.target.value);
    };

    const canSend = value.trim().length > 0 && !disabled;

    return (
      <div className="px-5 pb-5 pt-2">
        <div className="mb-2 flex items-center justify-between px-1">
          <span className="label-eyebrow text-[9px]">Inscribe</span>
          <span className="font-mono text-[10px] tracking-wide text-[var(--color-ink-faint)]">
            ⏎ 发送 · ⇧⏎ 换行
          </span>
        </div>

        <div
          className={cn(
            "relative rounded-[6px] border bg-[var(--color-paper)]/95 backdrop-blur-sm transition-all duration-200",
            focused
              ? "border-[var(--color-vermilion)]/55 shadow-[0_0_0_3px_oklch(0.58_0.205_30/0.08),0_1px_0_0_oklch(0.92_0.015_78)_inset]"
              : "border-[var(--color-rule)] shadow-[0_1px_0_0_oklch(0.92_0.015_78)_inset,0_1px_2px_-1px_rgba(60,40,20,0.06)]",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          <div className="pointer-events-none absolute left-3.5 top-1/2 h-[55%] w-px -translate-y-1/2 bg-[var(--color-rule)]" />

          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="提出一个问题…"
            disabled={disabled}
            rows={1}
            className="block w-full resize-none bg-transparent px-7 py-3.5 pr-14 text-[14px] leading-relaxed text-[var(--color-ink)] placeholder:italic placeholder:text-[var(--color-ink-faint)] focus:outline-none disabled:cursor-not-allowed"
            style={{ fontFamily: "var(--font-sans)" }}
          />
          {isStreaming ? (
            <button
              onClick={onStop}
              className="absolute bottom-2.5 right-2.5 flex h-8 w-8 items-center justify-center rounded-[5px] bg-[var(--color-vermilion-deep)] text-[var(--color-paper)] shadow-[0_1px_2px_rgba(0,0,0,0.1)] transition-all duration-200 hover:bg-[var(--color-vermilion)] active:scale-95"
              title="停止生成"
            >
              <Square className="h-3 w-3" fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!canSend}
              className={cn(
                "absolute bottom-2.5 right-2.5 flex h-8 w-8 items-center justify-center rounded-[5px] transition-all duration-200",
                canSend
                  ? "bg-[var(--color-ink)] text-[var(--color-paper)] hover:bg-[var(--color-vermilion)] active:scale-95"
                  : "bg-[var(--color-parchment)] text-[var(--color-ink-faint)]",
              )}
            >
              <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.2} />
            </button>
          )}
        </div>
        {value.length >= CHAR_COUNT_THRESHOLD && (
          <div className="mt-1.5 pr-1 text-right font-mono text-[10px] tracking-wide text-[var(--color-ink-faint)]">
            {value.length} chars
          </div>
        )}
      </div>
    );
  },
);
