import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: process.env.BUILD_MOBILE === "true" ? "export" : "standalone",
  images: { unoptimized: true }, // Required for Capacitor mobile export and static hosting
  poweredByHeader: false,
  turbopack: {
    resolveAlias: {
      "@/components": path.join(__dirname, "components"),
      "@/lib": path.join(__dirname, "lib"),
    },
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
