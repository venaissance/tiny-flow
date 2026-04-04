"use client";

import type { MemoryFact } from "@/lib/types";

export function MemoryViewer({ facts }: { facts: MemoryFact[] }) {
  if (facts.length === 0) {
    return <div className="p-4 text-sm text-gray-500">No memory facts</div>;
  }

  return (
    <div className="space-y-3 p-4">
      <h3 className="text-sm font-semibold">
        Memory Facts ({facts.length})
      </h3>
      {facts.map((fact) => (
        <div key={fact.id} className="rounded border p-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs text-gray-500">{fact.category}</span>
            <div className="flex items-center gap-1">
              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-200">
                <div
                  className="h-full rounded-full bg-blue-500"
                  style={{ width: `${fact.confidence * 100}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">
                {Math.round(fact.confidence * 100)}%
              </span>
            </div>
          </div>
          <div className="text-sm">{fact.content}</div>
        </div>
      ))}
    </div>
  );
}
