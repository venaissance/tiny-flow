"use client";

import { useState } from "react";
import { Brain, ChevronRight, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface ThinkingBlockProps {
  content: string;
  defaultOpen?: boolean;
}

export function ThinkingBlock({ content, defaultOpen = false }: ThinkingBlockProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="my-2 rounded-lg border-l-2 border-blue-200 dark:border-blue-800">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-600 transition-colors hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200",
          open && "text-gray-800 dark:text-gray-200"
        )}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-4 w-4 flex-shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 flex-shrink-0" />
        )}
        <Brain className="h-4 w-4 flex-shrink-0 text-blue-500 dark:text-blue-400" />
        <span className="font-medium">思考过程</span>
        {!open && (
          <span className="text-xs text-gray-400 dark:text-gray-500">(点击展开)</span>
        )}
      </button>
      <div
        className={cn(
          "overflow-hidden transition-[max-height] duration-300 ease-in-out",
          open ? "max-h-[2000px]" : "max-h-0"
        )}
      >
        <pre className="whitespace-pre-wrap break-words rounded-b-lg bg-gray-50 px-4 py-3 text-sm leading-relaxed text-gray-700 dark:bg-gray-800/50 dark:text-gray-300">
          {content}
        </pre>
      </div>
    </div>
  );
}
