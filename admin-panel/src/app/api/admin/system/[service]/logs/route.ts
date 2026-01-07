import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * SSE Proxy Route for Docker container logs.
 *
 * Next.js rewrites buffer responses and don't support SSE streaming.
 * This API route properly proxies the SSE stream without buffering.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ service: string }> }
) {
  const { service } = await params;
  const token = request.nextUrl.searchParams.get("token");
  const tail = request.nextUrl.searchParams.get("tail") || "100";

  if (!token) {
    return new Response("Token required", { status: 401 });
  }

  // Validate service name
  const validServices = ["api", "agent", "postgres", "redis", "admin-panel"];
  if (!validServices.includes(service)) {
    return new Response(`Invalid service: ${service}`, { status: 400 });
  }

  // Build backend URL
  const backendUrl = process.env.INTERNAL_API_URL || "http://api:8000";
  const url = `${backendUrl}/api/admin/system/${service}/logs?tail=${tail}&token=${encodeURIComponent(token)}`;

  try {
    // Fetch with streaming - don't await the body
    const response = await fetch(url, {
      headers: {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Backend error for ${service} logs:`, response.status, errorText);
      return new Response(`Backend error: ${response.status}`, {
        status: response.status,
      });
    }

    // Return the stream directly without buffering
    // response.body is a ReadableStream that we pass through
    return new Response(response.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no", // Disable nginx buffering
      },
    });
  } catch (error) {
    console.error("SSE proxy error:", error);
    return new Response(
      `Proxy error: ${error instanceof Error ? error.message : String(error)}`,
      { status: 502 }
    );
  }
}
