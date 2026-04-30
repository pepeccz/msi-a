import type { NextConfig } from "next";
import { buildSecurityHeaders } from "./src/app/next.config.headers";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["panel.autohomologacion.net"],
  async rewrites() {
    // En Docker, usa el nombre del servicio 'msia-api' para comunicación interna
    const apiUrl = process.env.INTERNAL_API_URL || "http://msia-api:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${apiUrl}/health`,
      },
      {
        source: "/images/:path*",
        destination: `${apiUrl}/images/:path*`,
      },
      {
        source: "/case-images/:path*",
        destination: `${apiUrl}/case-images/:path*`,
      },
      {
        source: "/llm-metrics/:path*",
        destination: `${apiUrl}/llm-metrics/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        // Apply security headers to all routes
        source: "/(.*)",
        headers: buildSecurityHeaders(),
      },
    ];
  },
};

export default nextConfig;
