import { act } from "react";
import type { Root } from "react-dom/client";
import { createRoot } from "react-dom/client";

import App from "./App";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("App", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root.render(<App />);
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("keeps subregion controls disabled until region focus is entered", () => {
    const selectRegionButton = findButton("Select region", container);
    const drillRegionButton = findButton("Drill region", container);
    const selectSubregionButton = findButton("Select subregion", container);
    const drillEvidenceButton = findButton("Drill evidence", container);

    expect(selectSubregionButton.disabled).toBe(true);
    expect(drillEvidenceButton.disabled).toBe(true);

    act(() => {
      selectRegionButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(selectSubregionButton.disabled).toBe(true);
    expect(drillEvidenceButton.disabled).toBe(true);

    act(() => {
      drillRegionButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(selectSubregionButton.disabled).toBe(false);
    expect(drillEvidenceButton.disabled).toBe(false);
  });
});

function findButton(label: string, container: HTMLElement): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll("button")).find(
    (candidate) => candidate.textContent === label,
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Could not find button with label: ${label}`);
  }

  return button;
}
