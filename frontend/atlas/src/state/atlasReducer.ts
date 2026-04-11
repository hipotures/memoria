export type AtlasLevel = "overview" | "region" | "evidence";

export type AtlasState = {
  level: AtlasLevel;
  selectedRegionKey: string | null;
  selectedSubregionKey: string | null;
  selectedItemId: number | null;
};

export type AtlasAction =
  | { type: "region.selected"; regionKey: string }
  | { type: "region.drilled"; regionKey: string }
  | { type: "subregion.selected"; subregionKey: string }
  | { type: "subregion.drilled"; subregionKey: string }
  | { type: "subregion.invalidated" }
  | { type: "item.selected"; sourceItemId: number }
  | { type: "breadcrumbs.region" }
  | { type: "breadcrumbs.reset" };

export const initialAtlasState: AtlasState = {
  level: "overview",
  selectedRegionKey: null,
  selectedSubregionKey: null,
  selectedItemId: null,
};

export function atlasReducer(state: AtlasState, action: AtlasAction): AtlasState {
  switch (action.type) {
    case "region.selected":
      return {
        ...state,
        selectedRegionKey: action.regionKey,
        selectedSubregionKey: null,
        selectedItemId: null,
      };
    case "region.drilled":
      return {
        level: "region",
        selectedRegionKey: action.regionKey,
        selectedSubregionKey: null,
        selectedItemId: null,
      };
    case "subregion.selected":
      if (state.level !== "region" || state.selectedRegionKey === null) {
        return state;
      }

      return {
        ...state,
        selectedSubregionKey: action.subregionKey,
        selectedItemId: null,
      };
    case "subregion.drilled":
      if (state.level !== "region" || state.selectedRegionKey === null) {
        return state;
      }

      return {
        ...state,
        level: "evidence",
        selectedSubregionKey: action.subregionKey,
        selectedItemId: null,
      };
    case "subregion.invalidated":
      if (state.selectedRegionKey === null) {
        return initialAtlasState;
      }

      return {
        level: "region",
        selectedRegionKey: state.selectedRegionKey,
        selectedSubregionKey: null,
        selectedItemId: null,
      };
    case "item.selected":
      return {
        ...state,
        selectedItemId: action.sourceItemId,
      };
    case "breadcrumbs.region":
      if (state.selectedRegionKey === null) {
        return initialAtlasState;
      }

      return {
        level: "region",
        selectedRegionKey: state.selectedRegionKey,
        selectedSubregionKey: state.selectedSubregionKey,
        selectedItemId: null,
      };
    case "breadcrumbs.reset":
      return initialAtlasState;
  }
}
