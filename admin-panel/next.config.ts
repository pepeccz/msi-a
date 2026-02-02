import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
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
};

export default nextConfig;
