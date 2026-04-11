import { describe, expect, it, vi } from "vitest";

import { clearPixiContainer } from "./pixiCleanup";

describe("clearPixiContainer", () => {
  it("destroys detached stage children on redraw", () => {
    const firstChild = { destroy: vi.fn() };
    const secondChild = { destroy: vi.fn() };
    const container = {
      removeChildren: vi.fn(() => [firstChild, secondChild]),
    };

    clearPixiContainer(container);

    expect(container.removeChildren).toHaveBeenCalledTimes(1);
    expect(firstChild.destroy).toHaveBeenCalledWith({ children: true });
    expect(secondChild.destroy).toHaveBeenCalledWith({ children: true });
  });
});
