import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(_request: NextRequest) {
  try {
    const response = await fetch(`${BACKEND_URL}/api/memory`, { cache: "no-store" });
    if (!response.ok) return new Response("Backend error", { status: 502 });
    return Response.json(await response.json());
  } catch {
    return Response.json({ facts: [], stats: { total: 0 } });
  }
}

export async function DELETE(_request: NextRequest) {
  try {
    const response = await fetch(`${BACKEND_URL}/api/memory`, {
      method: "DELETE",
    });
    if (!response.ok) return new Response("Backend error", { status: 502 });
    return Response.json(await response.json());
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }
}
