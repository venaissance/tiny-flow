"use client";

import { cn } from "@/lib/utils";

export function Terminal({ className, children }: React.ComponentProps<"div"> & { children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "border-border bg-background/25 z-0 h-full max-h-[400px] w-full max-w-lg rounded-xl border",
        className,
      )}
    >
      <div className="border-border flex flex-col gap-y-2 border-b p-4">
        <div className="flex flex-row gap-x-2">
          <div className="h-2 w-2 rounded-full bg-red-500"></div>
          <div className="h-2 w-2 rounded-full bg-yellow-500"></div>
          <div className="h-2 w-2 rounded-full bg-green-500"></div>
        </div>
      </div>
      <pre className="p-4">
        <code className="grid gap-y-1 overflow-auto text-sm">{children}</code>
      </pre>
    </div>
  );
}
