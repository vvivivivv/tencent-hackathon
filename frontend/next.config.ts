import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["pixi.js"],
  // Use webpack instead of turbopack (pixi.js v8 uses import.meta which turbopack has issues with)
  turbopack: undefined,
};

export default nextConfig;
