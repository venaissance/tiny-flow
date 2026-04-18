import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function DELETE(
  _request: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  try {
    const response = await fetch(`${BACKEND_URL}/api/memory/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    if (!response.ok) return new Response("Backend error", { status: 502 });
    return Response.json(await response.json());
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }
}

export async function PATCH(
  request: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  try {
    const body = await request.json();
    const response = await fetch(`${BACKEND_URL}/api/memory/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) return new Response("Backend error", { status: 502 });
    return Response.json(await response.json());
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }
}
