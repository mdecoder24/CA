import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // All pages are client-rendered against the local API, so instant-navigation
  // validation only produces noise. Validate only segments that opt in.
  experimental: {
    instantInsights: {
      validationLevel: "manual-warning",
    },
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
