import type { NextConfig } from "next";
const config: NextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
    if (!/^https?:\/\/(127\.0\.0\.1|localhost):8000$/.test(backend)) throw new Error("Invalid private backend origin");
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
export default config;
