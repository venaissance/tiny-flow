import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const params = await context.params;
  const pathParts = params.path;
  // Expected format: [thread_id, ...artifact_path]
  if (pathParts.length < 2) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  const threadId = pathParts[0];
  const artifactPath = pathParts.slice(1).join("/");

  try {
    const response = await fetch(
      `${BACKEND_URL}/api/threads/${threadId}/artifacts/${artifactPath}`
    );

    if (!response.ok) {
      return NextResponse.json({ error: "Artifact not found" }, { status: 404 });
    }

    const contentType = response.headers.get("content-type") || "text/plain";
    const content = await response.text();

    return new Response(content, {
      headers: { "Content-Type": contentType },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Error" },
      { status: 500 }
    );
  }
}
