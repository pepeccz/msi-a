import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * SSE Proxy Route for Docker container logs.
 *
 * Next.js rewrites buffer responses and don't support SSE streaming.
 * This API route properly proxies the SSE stream without buffering.
 *
 * Auth: reads the admin_token httpOnly cookie and forwards it as a
 * Bearer token to the backend. The token is never exposed in the URL.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ service: string }> }
) {
  const { service } = await params;
  const tail = request.nextUrl.searchParams.get("tail") || "100";

  // Read auth token from the httpOnly cookie — NOT from a query parameter
  const token = request.cookies.get("admin_token")?.value;

  if (!token) {
    return new Response("Unauthorized", { status: 401 });
  }

  // Validate service name
  const validServices = ["api", "agent", "postgres", "redis", "admin-panel"];
  if (!validServices.includes(service)) {
    return new Response(`Invalid service: ${service}`, { status: 400 });
  }

  // Build backend URL — token sent via Authorization header, NOT in URL
  const backendUrl = process.env.INTERNAL_API_URL || "http://api:8000";
  const url = `${backendUrl}/api/admin/system/${service}/logs?tail=${tail}`;

  try {
    // Fetch with streaming - don't await the body
    const response = await fetch(url, {
      headers: {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
        Authorization: `Bearer ${token}`,
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
