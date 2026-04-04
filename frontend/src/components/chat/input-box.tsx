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
      <div className="px-4 pb-4 pt-2">
        <div
          className={cn(
            "relative rounded-2xl border bg-white shadow-sm transition-all duration-200 dark:bg-gray-900",
            focused
              ? "border-blue-300 shadow-[0_0_0_3px_rgba(59,130,246,0.08)] dark:border-blue-600/50 dark:shadow-[0_0_0_3px_rgba(59,130,246,0.12)]"
              : "border-gray-200 dark:border-gray-700/60",
            disabled && "opacity-60 cursor-not-allowed",
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="输入消息..."
            disabled={disabled}
            rows={1}
            className="block w-full resize-none bg-transparent px-4 py-3 pr-12 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none disabled:cursor-not-allowed dark:text-gray-100 dark:placeholder:text-gray-500"
          />
          {isStreaming ? (
            <button
              onClick={onStop}
              className="absolute bottom-2 right-2 flex h-8 w-8 items-center justify-center rounded-xl bg-red-500 text-white shadow-sm transition-all duration-200 hover:bg-red-600 active:scale-95"
              title="停止生成"
            >
              <Square className="h-3.5 w-3.5" fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!canSend}
              className={cn(
                "absolute bottom-2 right-2 flex h-8 w-8 items-center justify-center rounded-xl transition-all duration-200",
                canSend
                  ? "bg-blue-500 text-white shadow-sm hover:bg-blue-600 active:scale-95"
                  : "bg-gray-100 text-gray-300 dark:bg-gray-800 dark:text-gray-600",
              )}
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            </button>
          )}
        </div>
        {value.length >= CHAR_COUNT_THRESHOLD && (
          <div className="mt-1 text-right text-xs text-gray-400">
            {value.length} chars
          </div>
        )}
      </div>
    );
  },
);
