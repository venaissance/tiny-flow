import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export async function POST() {
  // Create new thread
  const threadId = `thread_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  return NextResponse.json({ thread_id: threadId });
}

export async function DELETE(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const threadId = searchParams.get("thread_id");

  if (!threadId) {
    return NextResponse.json({ error: "thread_id required" }, { status: 400 });
  }

  try {
    const response = await fetch(`${BACKEND_URL}/api/threads/${threadId}`, {
      method: "DELETE",
    });
    return NextResponse.json(await response.json());
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Internal error" },
      { status: 500 }
    );
  }
}
