import { describe, expect, it } from "vitest";

import { presentRegionVisualTreatment } from "./regionVisualTreatment";

describe("presentRegionVisualTreatment", () => {
  it("renders unselected region-mode lanes as outline-first when another lane is active", () => {
    expect(
      presentRegionVisualTreatment({
        level: "region",
        isSelected: false,
        isDimmed: false,
        index: 3,
        hasActiveSelection: true,
      }),
    ).toMatchObject({
      fillAlpha: 0,
      showLabel: false,
      showCountLabel: false,
      showCentroid: true,
    });
  });

  it("keeps the selected lane emphasized in region mode", () => {
    expect(
      presentRegionVisualTreatment({
        level: "region",
        isSelected: true,
        isDimmed: false,
        index: 6,
        hasActiveSelection: true,
      }),
    ).toMatchObject({
      fillAlpha: 0.18,
      showLabel: true,
      showCountLabel: true,
      showCentroid: false,
    });
  });

  it("shows the featured lanes as visible filled regions before any lane is selected", () => {
    expect(
      presentRegionVisualTreatment({
        level: "region",
        isSelected: false,
        isDimmed: false,
        index: 1,
        hasActiveSelection: false,
      }),
    ).toMatchObject({
      fillAlpha: 0.1,
      strokeAlpha: 0.4,
      showLabel: true,
      showCountLabel: true,
      showCentroid: false,
    });

    expect(
      presentRegionVisualTreatment({
        level: "region",
        isSelected: false,
        isDimmed: false,
        index: 5,
        hasActiveSelection: false,
      }),
    ).toMatchObject({
      fillAlpha: 0.08,
      showLabel: true,
      showCountLabel: true,
    });
  });
});
