import { describe, expect, it } from "vitest";

import { presentRegionCanvasTitle } from "./labelPresentation";

describe("presentRegionCanvasTitle", () => {
  it("keeps short human labels readable", () => {
    expect(presentRegionCanvasTitle("software updates")).toBe("software updates");
  });

  it("compacts technical file-like labels before wrapping", () => {
    const rendered = presentRegionCanvasTitle(
      "python3 scripts/pipeline/benchmark_semantic_announcement_models.py",
    );

    expect(rendered).toContain("\n");
    expect(rendered).toContain("benchmark");
    expect(rendered).not.toContain(".py");
    expect(rendered).not.toContain("python3");
    expect(rendered.split("\n")).toHaveLength(2);
  });

  it("clamps very long labels to two lines with ellipsis", () => {
    const rendered = presentRegionCanvasTitle(
      "customer support reimbursement follow up and ticket routing",
    );

    expect(rendered.split("\n")).toHaveLength(2);
    expect(rendered.endsWith("…")).toBe(true);
  });
});
