import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const atlasProxyTarget = env.VITE_ATLAS_API_ORIGIN || "http://127.0.0.1:8000";

  return {
    base: command === "build" ? "/atlas/" : undefined,
    plugins: [react()],
    server: {
      proxy: {
        "/atlas": {
          target: atlasProxyTarget,
          changeOrigin: true,
        },
        "/screenshots": {
          target: atlasProxyTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
    },
  };
});
