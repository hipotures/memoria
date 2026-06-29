import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const similarityProxyTarget = env.VITE_SIMILARITY_API_ORIGIN || "http://127.0.0.1:8000";

  return {
    base: command === "build" ? "/similarity/" : undefined,
    plugins: [react()],
    server: {
      proxy: {
        "/similarity": {
          target: similarityProxyTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/setupTests.ts",
    },
  };
});
