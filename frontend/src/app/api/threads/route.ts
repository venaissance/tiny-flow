import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const threadId = searchParams.get("thread_id");
  const wantMessages = searchParams.get("messages") === "true";

  try {
    if (threadId) {
      // Fetch single thread (optionally with messages)
      const url = `${BACKEND_URL}/api/threads/${threadId}${wantMessages ? "?messages=true" : ""}`;
      const response = await fetch(url);
      if (!response.ok) return new Response("Backend error", { status: 502 });
      const data = await response.json();
      return Response.json(data);
    }
    // List all threads
    const response = await fetch(`${BACKEND_URL}/api/threads`);
    if (!response.ok) return new Response("Backend error", { status: 502 });
    const data = await response.json();
    return Response.json(data);
  } catch {
    return Response.json(threadId ? { messages: [] } : []);
  }
}

export async function POST() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) return new Response("Backend error", { status: 502 });
    const data = await response.json();
    return Response.json(data);
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }
}

export async function DELETE(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const threadId = searchParams.get("thread_id");
  if (!threadId) {
    return Response.json({ error: "thread_id required" }, { status: 400 });
  }
  try {
    const response = await fetch(`${BACKEND_URL}/api/threads/${threadId}`, {
      method: "DELETE",
    });
    if (!response.ok) return new Response("Backend error", { status: 502 });
    const data = await response.json();
    return Response.json(data);
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }
}

export async function PATCH(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const threadId = searchParams.get("thread_id");
  if (!threadId) {
    return Response.json({ error: "thread_id required" }, { status: 400 });
  }
  try {
    const body = await request.json();
    const response = await fetch(`${BACKEND_URL}/api/threads/${threadId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) return new Response("Backend error", { status: 502 });
    const data = await response.json();
    return Response.json(data);
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }
}
