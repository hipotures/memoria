import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import type {
  AtlasEvidenceSliceResponse,
  AtlasEvidenceSort,
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
import {
  applyOverlayFilter,
  inputDateFromIso,
  isFocusWindowActive,
  regionSetHasMatches,
  titleCaseAtlasValue,
  toEndOfDayIso,
  toStartOfDayIso,
} from "./lib/atlasPresentation";
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

const DEFAULT_EVIDENCE_SORT: AtlasEvidenceSort = "observed_at_desc";

export default function App() {
  const [atlasState, dispatch] = useReducer(atlasReducer, initialAtlasState);
  const [toolbarDraft, setToolbarDraft] = useState<AtlasToolbarDraft>(INITIAL_TOOLBAR_DRAFT);
  const [serverFilters, setServerFilters] = useState<AtlasFilters>(
    buildServerFilters(INITIAL_TOOLBAR_DRAFT),
  );
  const [evidenceSort, setEvidenceSort] = useState<AtlasEvidenceSort>(DEFAULT_EVIDENCE_SORT);
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
  const toolbarDraftRef = useRef(toolbarDraft);

  useEffect(() => {
    toolbarDraftRef.current = toolbarDraft;
  }, [toolbarDraft]);

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

  const regionDetailMatchesSelection =
    atlasState.selectedRegionKey !== null &&
    regionDetail !== null &&
    regionDetail.region.region_key === atlasState.selectedRegionKey &&
    sameFilters(regionDetail.active_filters, serverFilters);

  useEffect(() => {
    if (atlasState.selectedRegionKey === null || regionDetailMatchesSelection) {
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
  }, [atlasState.selectedRegionKey, regionDetailMatchesSelection, serverFilters]);

  useEffect(() => {
    if (
      atlasState.level !== "evidence" ||
      atlasState.selectedRegionKey === null
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
      sort: evidenceSort,
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
    evidenceSort,
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
      setRegionDetail(null);
      setEvidenceData(null);
      setLongTailOffset(0);
      dispatch({ type: "breadcrumbs.reset" });
    }
  }, [atlasState.selectedRegionKey, overviewData]);

  useEffect(() => {
    if (
      regionDetail === null ||
      !regionDetailMatchesSelection ||
      atlasState.selectedSubregionKey === null
    ) {
      return;
    }

    const subregionStillVisible = regionDetail.subregions.some(
      (subregion) => subregion.region_key === atlasState.selectedSubregionKey,
    );
    if (!subregionStillVisible) {
      setEvidenceData(null);
      setLongTailOffset(0);
      dispatch({ type: "subregion.invalidated" });
    }
  }, [
    atlasState.selectedSubregionKey,
    regionDetail,
    regionDetailMatchesSelection,
  ]);

  const activeRegionDetail = regionDetailMatchesSelection ? regionDetail : null;

  const selectedRegion = useMemo(() => {
    if (atlasState.selectedRegionKey === null) {
      return null;
    }

    if (activeRegionDetail !== null) {
      return activeRegionDetail.region;
    }

    return (
      overviewData?.regions.find((region) => region.region_key === atlasState.selectedRegionKey) ?? null
    );
  }, [activeRegionDetail, atlasState.selectedRegionKey, overviewData]);

  const selectedSubregion = useMemo(() => {
    if (activeRegionDetail === null || atlasState.selectedSubregionKey === null) {
      return null;
    }

    return (
      activeRegionDetail.subregions.find(
        (subregion) => subregion.region_key === atlasState.selectedSubregionKey,
      ) ?? null
    );
  }, [activeRegionDetail, atlasState.selectedSubregionKey]);

  const activeFocusRegion = selectedSubregion ?? selectedRegion;
  const searchQuery = serverFilters.search_query?.trim() ?? "";
  const backendFilteringActive = hasBackendFilters(serverFilters);
  const structuralOverviewRegions = overviewData?.regions ?? [];
  const structuralOverviewEdges = overviewData?.edges ?? [];
  const structuralSubregions = activeRegionDetail?.subregions ?? [];
  const hasGeneratedSubregions = structuralSubregions.length > 0;

  const listedRegions = useMemo(
    () =>
      applyOverlayFilter(
        structuralOverviewRegions,
        backendFilteringActive,
        atlasState.selectedRegionKey,
      ),
    [atlasState.selectedRegionKey, backendFilteringActive, structuralOverviewRegions],
  );

  const listedSubregions = useMemo(
    () =>
      applyOverlayFilter(
        structuralSubregions,
        backendFilteringActive,
        atlasState.selectedSubregionKey,
      ),
    [atlasState.selectedSubregionKey, backendFilteringActive, structuralSubregions],
  );

  const regionRepresentatives = activeRegionDetail?.representatives ?? [];
  const evidenceSections = evidenceData === null ? null : splitEvidenceSections(evidenceData);

  const selectedItem = useMemo(() => {
    const targetId = atlasState.selectedItemId;
    if (targetId === null) {
      return null;
    }

    const candidates: AtlasItem[] = [
      ...regionRepresentatives,
      ...(evidenceData?.representatives ?? []),
      ...(evidenceData?.bridges ?? []),
      ...(evidenceData?.long_tail_page.items ?? []),
    ];

    return candidates.find((item) => item.source_item_id === targetId) ?? null;
  }, [atlasState.selectedItemId, evidenceData, regionRepresentatives]);

  const visibleEvidenceItems = useMemo(() => {
    if (evidenceSections === null) {
      return [];
    }

    return [
      ...evidenceSections.representatives,
      ...evidenceSections.bridges,
      ...evidenceSections.longTail.items,
    ];
  }, [evidenceSections]);

  const loading =
    overviewState === "loading" ||
    (atlasState.selectedRegionKey !== null && regionState === "loading") ||
    (atlasState.level === "evidence" && evidenceState === "loading");

  const currentError =
    atlasState.level === "evidence"
      ? evidenceError ?? regionError ?? overviewError
      : atlasState.selectedRegionKey !== null
        ? regionError ?? overviewError
        : overviewError;

  const appOptions = useMemo(() => {
    const values = new Set<string>();
    const pushRegionApps = (regions: AtlasRegion[]) => {
      regions.forEach((region) => region.top_apps.forEach((app) => values.add(app)));
    };

    pushRegionApps(overviewData?.regions ?? []);
    pushRegionApps(activeRegionDetail?.subregions ?? []);
    activeFocusRegion?.top_apps.forEach((app) => values.add(app));
    visibleEvidenceItems.forEach((item) => {
      if (item.app_hint !== null) {
        values.add(item.app_hint);
      }
    });

    return Array.from(values).sort((left, right) => left.localeCompare(right));
  }, [activeFocusRegion, activeRegionDetail, overviewData, visibleEvidenceItems]);

  const stageRegions =
    atlasState.level === "overview"
      ? structuralOverviewRegions
      : hasGeneratedSubregions
        ? structuralSubregions
        : selectedRegion !== null
          ? [selectedRegion]
          : [];
  const emptyFilteredState =
    backendFilteringActive &&
    overviewState === "ready" &&
    overviewData?.atlas_run !== null &&
    stageRegions.length > 0 &&
    !regionSetHasMatches(stageRegions);
  const canOpenRegionEvidence =
    atlasState.level === "region" &&
    activeRegionDetail !== null &&
    selectedRegion !== null &&
    !hasGeneratedSubregions;
  const canOpenEvidence = selectedSubregion !== null || canOpenRegionEvidence;
  const evidenceActionLabel = canOpenRegionEvidence ? "Open region evidence" : "Open evidence";
  const stageNotice =
    atlasState.level === "region" && activeRegionDetail !== null && !hasGeneratedSubregions
      ? {
          title: "No generated lanes for this region yet",
          detail: "Open region evidence to inspect the whole region without waiting for a lane breakdown.",
        }
      : emptyFilteredState
        ? {
            title:
              atlasState.level === "overview"
                ? "No regions match the current filters"
                : "No visible lanes match the current filters",
            detail:
              "The atlas field stays pinned so you can keep your bearings while broadening the request.",
          }
        : null;

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
    setLongTailOffset(0);
    setEvidenceData(null);
    dispatch({ type: "region.selected", regionKey });
  };

  const handleDrillRegion = (regionKey?: string) => {
    const nextRegionKey = regionKey ?? atlasState.selectedRegionKey;
    if (nextRegionKey === null) {
      return;
    }
    dispatch({ type: "region.drilled", regionKey: nextRegionKey });
  };

  const handleSelectSubregion = (subregionKey: string) => {
    setLongTailOffset(0);
    setEvidenceData(null);
    dispatch({ type: "subregion.selected", subregionKey });
  };

  const handleOpenEvidence = (subregionKey?: string) => {
    const nextSubregionKey = subregionKey ?? selectedSubregion?.region_key ?? null;
    setLongTailOffset(0);
    setEvidenceData(null);

    if (nextSubregionKey !== null) {
      dispatch({ type: "subregion.drilled", subregionKey: nextSubregionKey });
      return;
    }

    if (canOpenRegionEvidence) {
      dispatch({ type: "region.evidenceOpened" });
    }
  };

  const handleSelectItem = (sourceItemId: number) => {
    dispatch({ type: "item.selected", sourceItemId });
  };

  const handleReturnToRegion = () => {
    dispatch({ type: "breadcrumbs.region" });
  };

  const handleResetAtlas = () => {
    setLongTailOffset(0);
    setRegionDetail(null);
    setEvidenceData(null);
    dispatch({ type: "breadcrumbs.reset" });
  };

  const handleEvidenceSortChange = (sort: AtlasEvidenceSort) => {
    setLongTailOffset(0);
    setEvidenceSort(sort);
  };

  const handleCommitDraftPatch = (patch: Partial<AtlasToolbarDraft>) => {
    const nextDraft = { ...toolbarDraftRef.current, ...patch };
    toolbarDraftRef.current = nextDraft;
    setToolbarDraft(nextDraft);
    setLongTailOffset(0);
    setServerFilters(buildServerFilters(nextDraft));
  };

  const handleApplyFocusApp = (appHint: string) => {
    handleCommitDraftPatch({ appHint });
  };

  const handleApplyFocusWindow = () => {
    if (activeFocusRegion === null) {
      return;
    }

    handleCommitDraftPatch({
      observedFrom: inputDateFromIso(activeFocusRegion.time_start),
      observedTo: inputDateFromIso(activeFocusRegion.time_end),
    });
  };

  const handleClearFocusFilters = () => {
    handleCommitDraftPatch({
      appHint: "",
      observedFrom: "",
      observedTo: "",
    });
  };

  useEffect(() => {
    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key !== "Enter" || event.repeat || event.defaultPrevented) {
        return;
      }

      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable ||
          target.closest("input, select, textarea, button, a, [role='button']") !== null)
      ) {
        return;
      }

      if (atlasState.level === "overview" && atlasState.selectedRegionKey !== null) {
        event.preventDefault();
        handleDrillRegion();
        return;
      }

      if (atlasState.level === "region" && selectedSubregion !== null) {
        event.preventDefault();
        handleOpenEvidence();
        return;
      }

      if (atlasState.level === "region" && canOpenRegionEvidence) {
        event.preventDefault();
        handleOpenEvidence();
      }
    };

    window.addEventListener("keydown", handleKeydown);
    return () => {
      window.removeEventListener("keydown", handleKeydown);
    };
  }, [
    atlasState.level,
    canOpenRegionEvidence,
    atlasState.selectedRegionKey,
    selectedSubregion,
  ]);

  const canPreviousEvidencePage =
    evidenceData !== null && evidenceData.long_tail_page.offset > 0;
  const canNextEvidencePage =
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
            canOpenEvidence={canOpenEvidence}
            evidenceActionLabel={evidenceActionLabel}
            onDrillRegion={() => handleDrillRegion()}
            onOpenEvidence={() => handleOpenEvidence()}
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
                {searchQuery.length > 0
                  ? `Search: ${searchQuery}`
                  : selectedRegion !== null
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

            {currentError === null &&
            overviewData?.atlas_run !== null &&
            ((overviewData?.regions.length ?? 0) > 0 || selectedRegion !== null) ? (
              <AtlasCanvas
                level={atlasState.level}
                overviewRegions={structuralOverviewRegions}
                overviewEdges={structuralOverviewEdges}
                focusRegion={selectedRegion}
                subregions={structuralSubregions}
                evidenceItems={visibleEvidenceItems}
                filteringActive={backendFilteringActive}
                stageNotice={stageNotice}
                selectedRegionKey={atlasState.selectedRegionKey}
                selectedSubregionKey={atlasState.selectedSubregionKey}
                selectedItemId={atlasState.selectedItemId}
                onSelectRegion={handleSelectRegion}
                onDrillRegion={handleDrillRegion}
                onSelectSubregion={handleSelectSubregion}
                onDrillSubregion={handleOpenEvidence}
                onSelectItem={handleSelectItem}
              />
            ) : null}
          </section>
        </section>

        <InsightDock
          level={atlasState.level}
          loading={loading}
          visibleRegions={listedRegions}
          selectedRegion={selectedRegion}
          activeFocusRegion={activeFocusRegion}
          visibleSubregions={listedSubregions}
          hasGeneratedSubregions={hasGeneratedSubregions}
          selectedSubregion={selectedSubregion}
          selectedItem={selectedItem}
          regionRepresentatives={regionRepresentatives}
          regionDetailLoaded={activeRegionDetail !== null}
          evidenceSections={evidenceSections}
          evidenceSort={evidenceSort}
          currentFilters={serverFilters}
          evidenceActionLabel={evidenceActionLabel}
          onEvidenceSortChange={handleEvidenceSortChange}
          onSelectRegion={handleSelectRegion}
          onDrillRegion={() => handleDrillRegion()}
          onSelectSubregion={handleSelectSubregion}
          onOpenEvidence={() => handleOpenEvidence()}
          canOpenEvidence={canOpenEvidence}
          onApplyFocusApp={handleApplyFocusApp}
          onApplyFocusWindow={handleApplyFocusWindow}
          onClearFocusFilters={handleClearFocusFilters}
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
    search_query: draft.searchText.trim() || null,
  };
}

function sameFilters(left: AtlasFilters, right: AtlasFilters): boolean {
  return (
    (left.app_hint ?? null) === (right.app_hint ?? null) &&
    (left.has_knowledge ?? null) === (right.has_knowledge ?? null) &&
    (left.observed_from ?? null) === (right.observed_from ?? null) &&
    (left.observed_to ?? null) === (right.observed_to ?? null) &&
    (left.connector_instance_id ?? null) === (right.connector_instance_id ?? null) &&
    (left.screen_category ?? null) === (right.screen_category ?? null) &&
    (left.search_query ?? null) === (right.search_query ?? null)
  );
}

function hasBackendFilters(filters: AtlasFilters): boolean {
  return [
    filters.connector_instance_id,
    filters.app_hint,
    filters.screen_category,
    filters.observed_from,
    filters.observed_to,
    filters.search_query,
    filters.has_knowledge,
  ].some((value) => value !== null && value !== undefined && value !== "");
}
