// @vitest-environment node

import { describe, expect, it } from "vitest";

import viteConfig from "../vite.config";

describe("vite atlas build config", () => {
  it("emits production assets under /atlas/", async () => {
    const resolved =
      typeof viteConfig === "function"
        ? await viteConfig({ command: "build", mode: "test" })
        : viteConfig;

    expect(resolved.base).toBe("/atlas/");
  });

  it("proxies screenshot image requests during development", async () => {
    const resolved =
      typeof viteConfig === "function"
        ? await viteConfig({ command: "serve", mode: "test" })
        : viteConfig;

    expect(resolved.server?.proxy).toHaveProperty("/screenshots");
  });
});
