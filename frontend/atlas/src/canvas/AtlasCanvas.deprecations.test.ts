// @vitest-environment node

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const source = readFileSync(fileURLToPath(new URL("./AtlasCanvas.tsx", import.meta.url)), "utf8");

describe("AtlasCanvas Pixi usage", () => {
  it("uses deck.gl instead of the previous Pixi renderer", () => {
    expect(source).toContain("@deck.gl/react");
    expect(source).toContain("@deck.gl/layers");
    expect(source).toContain("@deck.gl/extensions");
    expect(source).not.toContain("pixi.js");
  });

  it("enables label collision filtering for atlas text", () => {
    expect(source).toContain("CollisionFilterExtension");
    expect(source).toContain("collisionEnabled: true");
  });
});
