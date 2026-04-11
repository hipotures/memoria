import { useDeferredValue, useEffect, useMemo, useReducer, useState } from "react";

import type {
  AtlasEvidenceSliceResponse,
  AtlasFilters,
  AtlasItem,
  AtlasOverviewResponse,
  AtlasRegion,
  AtlasRegionDetailResponse,
} from "./api/contracts";
import {
  fetchAtlasEvidenceSlice,
  fetchAtlasOverview,
  fetchAtlasRegionDetail,
} from "./api/client";
import { AtlasCanvas } from "./canvas/AtlasCanvas";
import {
  AtlasToolbar,
  type AtlasToolbarDraft,
} from "./components/AtlasToolbar";
import { InsightDock } from "./components/InsightDock";
import { RegionNavigator } from "./components/RegionNavigator";
import { splitEvidenceSections } from "./lib/evidenceSections";
import { atlasReducer, initialAtlasState } from "./state/atlasReducer";

type LoadState = "idle" | "loading" | "ready" | "error";

const INITIAL_TOOLBAR_DRAFT: AtlasToolbarDraft = {
  searchText: "",
  appHint: "",
  observedFrom: "",
  observedTo: "",
  knowledge: "all",
};

export default function App() {
  const [atlasState, dispatch] = useReducer(atlasReducer, initialAtlasState);
  const [toolbarDraft, setToolbarDraft] = useState<AtlasToolbarDraft>(INITIAL_TOOLBAR_DRAFT);
  const [serverFilters, setServerFilters] = useState<AtlasFilters>(
    buildServerFilters(INITIAL_TOOLBAR_DRAFT),
  );
  const [longTailOffset, setLongTailOffset] = useState(0);

  const [overviewData, setOverviewData] = useState<AtlasOverviewResponse | null>(null);
  const [overviewState, setOverviewState] = useState<LoadState>("loading");
  const [overviewError, setOverviewError] = useState<string | null>(null);

  const [regionDetail, setRegionDetail] = useState<AtlasRegionDetailResponse | null>(null);
  const [regionState, setRegionState] = useState<LoadState>("idle");
  const [regionError, setRegionError] = useState<string | null>(null);

  const [evidenceData, setEvidenceData] = useState<AtlasEvidenceSliceResponse | null>(null);
  const [evidenceState, setEvidenceState] = useState<LoadState>("idle");
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  const deferredSearchText = useDeferredValue(toolbarDraft.searchText.trim());

  useEffect(() => {
    let cancelled = false;
    setOverviewState("loading");
    setOverviewError(null);

    void fetchAtlasOverview(serverFilters)
      .then((response) => {
        if (cancelled) {
          return;
        }
        setOverviewData(response);
        setOverviewState("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setOverviewState("error");
        setOverviewError(error instanceof Error ? error.message : "Could not load atlas overview.");
      });

    return () => {
      cancelled = true;
    };
  }, [serverFilters]);

  useEffect(() => {
    if (atlasState.level === "overview" || atlasState.selectedRegionKey === null) {
      return;
    }

    const filtersAlreadyApplied =
      regionDetail !== null &&
      regionDetail.region.region_key === atlasState.selectedRegionKey &&
      sameFilters(regionDetail.active_filters, serverFilters);

    if (filtersAlreadyApplied) {
      return;
    }

    let cancelled = false;
    setRegionState("loading");
    setRegionError(null);

    void fetchAtlasRegionDetail(atlasState.selectedRegionKey, serverFilters)
      .then((response) => {
        if (cancelled) {
          return;
        }
        setRegionDetail(response);
        setRegionState("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setRegionState("error");
        setRegionError(error instanceof Error ? error.message : "Could not load region detail.");
      });

    return () => {
      cancelled = true;
    };
  }, [atlasState.level, atlasState.selectedRegionKey, regionDetail, serverFilters]);

  useEffect(() => {
    if (
      atlasState.level !== "evidence" ||
      atlasState.selectedRegionKey === null ||
      atlasState.selectedSubregionKey === null
    ) {
      return;
    }

    let cancelled = false;
    setEvidenceState("loading");
    setEvidenceError(null);

    void fetchAtlasEvidenceSlice({
      regionKey: atlasState.selectedRegionKey,
      subregionKey: atlasState.selectedSubregionKey,
      limit: 25,
      offset: longTailOffset,
      sort: "observed_at_desc",
      ...serverFilters,
    })
      .then((response) => {
        if (cancelled) {
          return;
        }
        setEvidenceData(response);
        setEvidenceState("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setEvidenceState("error");
        setEvidenceError(error instanceof Error ? error.message : "Could not load evidence.");
      });

    return () => {
      cancelled = true;
    };
  }, [
    atlasState.level,
    atlasState.selectedRegionKey,
    atlasState.selectedSubregionKey,
    longTailOffset,
    serverFilters,
  ]);

  useEffect(() => {
    if (overviewData === null || atlasState.selectedRegionKey === null) {
      return;
    }

    const regionStillVisible = overviewData.regions.some(
      (region) => region.region_key === atlasState.selectedRegionKey,
    );
    if (!regionStillVisible) {
      dispatch({ type: "breadcrumbs.reset" });
      setRegionDetail(null);
      setEvidenceData(null);
    }
  }, [atlasState.selectedRegionKey, overviewData]);

  useEffect(() => {
    if (
      regionDetail === null ||
      atlasState.level !== "evidence" ||
      atlasState.selectedSubregionKey === null
    ) {
      return;
    }

    const subregionStillVisible = regionDetail.subregions.some(
      (subregion) => subregion.region_key === atlasState.selectedSubregionKey,
    );
    if (!subregionStillVisible) {
      dispatch({ type: "breadcrumbs.region" });
      setEvidenceData(null);
      setLongTailOffset(0);
    }
  }, [atlasState.level, atlasState.selectedSubregionKey, regionDetail]);

  const selectedRegion = useMemo(() => {
    if (atlasState.selectedRegionKey === null) {
      return null;
    }

    if (regionDetail?.region.region_key === atlasState.selectedRegionKey) {
      return regionDetail.region;
    }

    return (
      overviewData?.regions.find((region) => region.region_key === atlasState.selectedRegionKey) ?? null
    );
  }, [atlasState.selectedRegionKey, overviewData, regionDetail]);

  const selectedSubregion = useMemo(() => {
    if (atlasState.selectedSubregionKey === null) {
      return null;
    }

    return (
      regionDetail?.subregions.find(
        (subregion) => subregion.region_key === atlasState.selectedSubregionKey,
      ) ?? null
    );
  }, [atlasState.selectedSubregionKey, regionDetail]);

  const visibleRegions = useMemo(
    () =>
      filterRegions(
        overviewData?.regions ?? [],
        deferredSearchText,
        atlasState.selectedRegionKey,
      ),
    [atlasState.selectedRegionKey, deferredSearchText, overviewData],
  );

  const visibleOverviewEdges = useMemo(() => {
    const visibleKeys = new Set(visibleRegions.map((region) => region.region_key));
    return (overviewData?.edges ?? []).filter(
      (edge) =>
        visibleKeys.has(edge.source_region_key) && visibleKeys.has(edge.target_region_key),
    );
  }, [overviewData, visibleRegions]);

  const visibleSubregions = useMemo(
    () =>
      filterRegions(
        regionDetail?.subregions ?? [],
        deferredSearchText,
        atlasState.selectedSubregionKey,
      ),
    [atlasState.selectedSubregionKey, deferredSearchText, regionDetail],
  );

  const visibleRegionRepresentatives = useMemo(
    () =>
      filterItems(
        regionDetail?.representatives ?? [],
        deferredSearchText,
        atlasState.selectedItemId,
      ),
    [atlasState.selectedItemId, deferredSearchText, regionDetail],
  );

  const filteredEvidence = useMemo(() => {
    if (evidenceData === null) {
      return null;
    }

    const representatives = filterItems(
      evidenceData.representatives,
      deferredSearchText,
      atlasState.selectedItemId,
    );
    const bridges = filterItems(
      evidenceData.bridges,
      deferredSearchText,
      atlasState.selectedItemId,
    );
    const longTailItems = filterItems(
      evidenceData.long_tail_page.items,
      deferredSearchText,
      atlasState.selectedItemId,
    );

    const searchActive = deferredSearchText.length > 0;

    return splitEvidenceSections({
      representatives,
      bridges,
      long_tail_page: {
        ...evidenceData.long_tail_page,
        items: longTailItems,
        total: searchActive ? longTailItems.length : evidenceData.long_tail_page.total,
      },
      section_totals: searchActive
        ? {
            representatives: representatives.length,
            bridges: bridges.length,
            long_tail: longTailItems.length,
          }
        : evidenceData.section_totals,
    });
  }, [atlasState.selectedItemId, deferredSearchText, evidenceData]);

  const selectedItem = useMemo(() => {
    const targetId = atlasState.selectedItemId;
    if (targetId === null) {
      return null;
    }

    const candidates: AtlasItem[] = [];
    candidates.push(...(regionDetail?.representatives ?? []));
    candidates.push(...(evidenceData?.representatives ?? []));
    candidates.push(...(evidenceData?.bridges ?? []));
    candidates.push(...(evidenceData?.long_tail_page.items ?? []));

    return candidates.find((item) => item.source_item_id === targetId) ?? null;
  }, [atlasState.selectedItemId, evidenceData, regionDetail]);

  const visibleEvidenceItems = useMemo(() => {
    if (filteredEvidence === null) {
      return [];
    }

    return [
      ...filteredEvidence.representatives,
      ...filteredEvidence.bridges,
      ...filteredEvidence.longTail.items,
    ];
  }, [filteredEvidence]);

  const loading =
    overviewState === "loading" ||
    regionState === "loading" ||
    evidenceState === "loading";

  const currentError =
    atlasState.level === "evidence"
      ? evidenceError ?? regionError ?? overviewError
      : atlasState.level === "region"
        ? regionError ?? overviewError
        : overviewError;

  const appOptions = useMemo(() => {
    const values = new Set<string>();
    const pushRegionApps = (regions: AtlasRegion[]) => {
      regions.forEach((region) => region.top_apps.forEach((app) => values.add(app)));
    };

    pushRegionApps(overviewData?.regions ?? []);
    pushRegionApps(regionDetail?.subregions ?? []);
    selectedRegion?.top_apps.forEach((app) => values.add(app));
    visibleEvidenceItems.forEach((item) => {
      if (item.app_hint !== null) {
        values.add(item.app_hint);
      }
    });

    return Array.from(values).sort((left, right) => left.localeCompare(right));
  }, [overviewData, regionDetail, selectedRegion, visibleEvidenceItems]);

  const emptyFilteredState =
    overviewState === "ready" &&
    overviewData?.atlas_run !== null &&
    visibleRegions.length === 0 &&
    atlasState.level === "overview";

  const handleDraftChange = (patch: Partial<AtlasToolbarDraft>) => {
    setToolbarDraft((current) => ({ ...current, ...patch }));
  };

  const handleApplyFilters = () => {
    setLongTailOffset(0);
    setServerFilters(buildServerFilters(toolbarDraft));
  };

  const handleResetFilters = () => {
    setToolbarDraft(INITIAL_TOOLBAR_DRAFT);
    setLongTailOffset(0);
    setServerFilters(buildServerFilters(INITIAL_TOOLBAR_DRAFT));
  };

  const handleSelectRegion = (regionKey: string) => {
    dispatch({ type: "region.selected", regionKey });
    setEvidenceData(null);
    setLongTailOffset(0);
  };

  const handleDrillRegion = (regionKey?: string) => {
    const nextRegionKey = regionKey ?? atlasState.selectedRegionKey;
    if (nextRegionKey === null) {
      return;
    }
    dispatch({ type: "region.drilled", regionKey: nextRegionKey });
  };

  const handleSelectSubregion = (subregionKey: string) => {
    dispatch({ type: "subregion.selected", subregionKey });
    setLongTailOffset(0);
    setEvidenceData(null);
  };

  const handleDrillSubregion = (subregionKey?: string) => {
    const nextSubregionKey = subregionKey ?? atlasState.selectedSubregionKey;
    if (nextSubregionKey === null) {
      return;
    }
    setLongTailOffset(0);
    dispatch({ type: "subregion.drilled", subregionKey: nextSubregionKey });
  };

  const handleSelectItem = (sourceItemId: number) => {
    dispatch({ type: "item.selected", sourceItemId });
  };

  const handleReturnToRegion = () => {
    dispatch({ type: "breadcrumbs.region" });
  };

  const handleResetAtlas = () => {
    setLongTailOffset(0);
    setEvidenceData(null);
    dispatch({ type: "breadcrumbs.reset" });
  };

  const canPreviousEvidencePage =
    deferredSearchText.length === 0 &&
    evidenceData !== null &&
    evidenceData.long_tail_page.offset > 0;
  const canNextEvidencePage =
    deferredSearchText.length === 0 &&
    evidenceData !== null &&
    evidenceData.long_tail_page.offset + evidenceData.long_tail_page.limit <
      evidenceData.long_tail_page.total;

  return (
    <main className="atlas-app-shell">
      <AtlasToolbar
        draft={toolbarDraft}
        appOptions={appOptions}
        loading={loading}
        onDraftChange={handleDraftChange}
        onApply={handleApplyFilters}
        onReset={handleResetFilters}
      />

      <div className="atlas-layout">
        <section className="atlas-workbench">
          <RegionNavigator
            level={atlasState.level}
            selectedRegionTitle={selectedRegion?.title ?? null}
            selectedSubregionTitle={selectedSubregion?.title ?? null}
            selectedRegionCount={selectedRegion?.item_count ?? null}
            selectedSubregionCount={selectedSubregion?.item_count ?? null}
            canDrillRegion={selectedRegion !== null}
            canDrillSubregion={selectedSubregion !== null}
            onDrillRegion={() => handleDrillRegion()}
            onDrillSubregion={() => handleDrillSubregion()}
            onReturnToRegion={handleReturnToRegion}
            onReset={handleResetAtlas}
          />

          <section className="atlas-surface">
            <div className="atlas-surface__meta">
              <span>
                {overviewData?.atlas_run?.atlas_key ?? "No published atlas"} ·{" "}
                {overviewData?.atlas_run?.embedding_model ?? "awaiting data"}
              </span>
              <span>
                {selectedRegion !== null
                  ? selectedRegion.top_labels.slice(0, 2).join(" · ") || "No topical labels"
                  : "Select a region to inspect its contours"}
              </span>
            </div>

            {currentError !== null ? (
              <section className="atlas-empty-state atlas-empty-state--error">
                <h2>Atlas request failed</h2>
                <p>{currentError}</p>
              </section>
            ) : null}

            {overviewState === "ready" && overviewData?.atlas_run === null ? (
              <section className="atlas-empty-state">
                <h2>No published atlas run</h2>
                <p>The atlas shell is ready, but there is no published projection to render yet.</p>
              </section>
            ) : null}

            {emptyFilteredState ? (
              <section className="atlas-empty-state">
                <h2>No regions match the current filters</h2>
                <p>Broaden the time window or clear the server filters to restore the atlas field.</p>
              </section>
            ) : null}

            {currentError === null &&
            overviewData?.atlas_run !== null &&
            !(overviewState === "ready" && (overviewData?.regions.length ?? 0) === 0) &&
            !emptyFilteredState ? (
              <AtlasCanvas
                level={atlasState.level}
                overviewRegions={visibleRegions}
                overviewEdges={visibleOverviewEdges}
                focusRegion={selectedRegion}
                subregions={visibleSubregions}
                evidenceItems={visibleEvidenceItems}
                selectedRegionKey={atlasState.selectedRegionKey}
                selectedSubregionKey={atlasState.selectedSubregionKey}
                selectedItemId={atlasState.selectedItemId}
                onSelectRegion={handleSelectRegion}
                onDrillRegion={handleDrillRegion}
                onSelectSubregion={handleSelectSubregion}
                onDrillSubregion={handleDrillSubregion}
                onSelectItem={handleSelectItem}
              />
            ) : null}
          </section>
        </section>

        <InsightDock
          level={atlasState.level}
          loading={loading}
          visibleRegions={visibleRegions}
          selectedRegion={selectedRegion}
          visibleSubregions={visibleSubregions}
          selectedSubregion={selectedSubregion}
          selectedItem={selectedItem}
          regionRepresentatives={visibleRegionRepresentatives}
          evidenceSections={filteredEvidence}
          onSelectRegion={handleSelectRegion}
          onDrillRegion={() => handleDrillRegion()}
          onSelectSubregion={handleSelectSubregion}
          onDrillSubregion={() => handleDrillSubregion()}
          onSelectItem={handleSelectItem}
          onPreviousEvidencePage={() =>
            setLongTailOffset((current) => Math.max(current - 25, 0))
          }
          onNextEvidencePage={() => setLongTailOffset((current) => current + 25)}
          canPreviousEvidencePage={canPreviousEvidencePage}
          canNextEvidencePage={canNextEvidencePage}
        />
      </div>
    </main>
  );
}

function buildServerFilters(draft: AtlasToolbarDraft): AtlasFilters {
  return {
    app_hint: draft.appHint.trim() || null,
    has_knowledge: draft.knowledge === "with" ? true : null,
    observed_from: draft.observedFrom ? toStartOfDayIso(draft.observedFrom) : null,
    observed_to: draft.observedTo ? toEndOfDayIso(draft.observedTo) : null,
  };
}

function toStartOfDayIso(dateValue: string): string {
  const [year, month, day] = dateValue.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 0, 0, 0, 0)).toISOString();
}

function toEndOfDayIso(dateValue: string): string {
  const [year, month, day] = dateValue.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 23, 59, 59, 999)).toISOString();
}

function filterRegions(
  regions: AtlasRegion[],
  searchText: string,
  selectedKey: string | null,
): AtlasRegion[] {
  if (searchText.length === 0) {
    return regions;
  }

  const query = searchText.toLowerCase();
  return regions.filter((region) => {
    if (region.region_key === selectedKey) {
      return true;
    }

    return [
      region.title,
      ...region.top_labels,
      ...region.top_apps,
      ...region.top_entities,
    ]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function filterItems(items: AtlasItem[], searchText: string, selectedItemId: number | null): AtlasItem[] {
  if (searchText.length === 0) {
    return items;
  }

  const query = searchText.toLowerCase();
  return items.filter((item) => {
    if (item.source_item_id === selectedItemId) {
      return true;
    }

    return [
      item.semantic_summary ?? "",
      item.app_hint ?? "",
      ...item.object_refs,
      String(item.source_item_id),
    ]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function sameFilters(left: AtlasFilters, right: AtlasFilters): boolean {
  return (
    (left.app_hint ?? null) === (right.app_hint ?? null) &&
    (left.has_knowledge ?? null) === (right.has_knowledge ?? null) &&
    (left.observed_from ?? null) === (right.observed_from ?? null) &&
    (left.observed_to ?? null) === (right.observed_to ?? null) &&
    (left.connector_instance_id ?? null) === (right.connector_instance_id ?? null) &&
    (left.screen_category ?? null) === (right.screen_category ?? null)
  );
}
