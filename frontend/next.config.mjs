/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: process.env.BUILD_MOBILE === "true" ? "export" : "standalone",
  images: { unoptimized: true }, // Required for Capacitor mobile export
};

export default nextConfig;
