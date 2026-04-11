import { atlasReducer, initialAtlasState } from "./atlasReducer";

describe("atlasReducer", () => {
  it("selects on single click and drills down only on explicit action", () => {
    const selected = atlasReducer(initialAtlasState, {
      type: "region.selected",
      regionKey: "region-a",
    });

    expect(selected.level).toBe("overview");
    expect(selected.selectedRegionKey).toBe("region-a");
    expect(selected.selectedSubregionKey).toBeNull();
    expect(selected.selectedItemId).toBeNull();

    const drilled = atlasReducer(selected, {
      type: "region.drilled",
      regionKey: "region-a",
    });

    expect(drilled.level).toBe("region");
    expect(drilled.selectedRegionKey).toBe("region-a");
    expect(drilled.selectedSubregionKey).toBeNull();
    expect(drilled.selectedItemId).toBeNull();
  });

  it("keeps subregion selection separate from evidence drill-down", () => {
    const regionState = atlasReducer(initialAtlasState, {
      type: "region.drilled",
      regionKey: "region-a",
    });
    const subregionSelected = atlasReducer(regionState, {
      type: "subregion.selected",
      subregionKey: "region-a/subregion-1",
    });

    expect(subregionSelected.level).toBe("region");
    expect(subregionSelected.selectedSubregionKey).toBe("region-a/subregion-1");
    expect(subregionSelected.selectedItemId).toBeNull();

    const evidenceState = atlasReducer(subregionSelected, {
      type: "subregion.drilled",
      subregionKey: "region-a/subregion-1",
    });

    expect(evidenceState.level).toBe("evidence");
    expect(evidenceState.selectedSubregionKey).toBe("region-a/subregion-1");
    expect(evidenceState.selectedItemId).toBeNull();
  });
});
