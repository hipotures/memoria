import { useEffect, useMemo, useState } from "react";

import type { AtlasEvidenceSort, AtlasFilters, AtlasItem, AtlasRegion } from "../api/contracts";
import {
  type AtlasRegionFocusScope,
  type AtlasOverviewScope,
  DEFAULT_ATLAS_REGION_LIST_SORT,
  type AtlasRegionListSort,
  formatAtlasDateRange,
  humanizeAtlasValue,
  isFocusWindowActive,
  resolveFocusPeople,
  sortAtlasRegions,
  titleCaseAtlasValue,
} from "../lib/atlasPresentation";
import type { EvidenceSections } from "../lib/evidenceSections";
import type { AtlasLevel } from "../state/atlasReducer";
import { EvidenceList } from "./EvidenceList";

type InsightDockProps = {
  level: AtlasLevel;
  loading: boolean;
  visibleRegions: AtlasRegion[];
  selectedRegion: AtlasRegion | null;
  activeFocusRegion: AtlasRegion | null;
  visibleSubregions: AtlasRegion[];
  hasGeneratedSubregions: boolean;
  selectedSubregion: AtlasRegion | null;
  selectedItem: AtlasItem | null;
  evidenceSections: EvidenceSections<AtlasItem> | null;
  evidenceSort: AtlasEvidenceSort;
  currentFilters: AtlasFilters;
  evidenceActionLabel: string;
  overviewScope: AtlasOverviewScope;
  regionFocusScope: AtlasRegionFocusScope;
  onEvidenceSortChange: (sort: AtlasEvidenceSort) => void;
  onOverviewScopeChange: (scope: AtlasOverviewScope) => void;
  onRegionFocusScopeChange: (scope: AtlasRegionFocusScope) => void;
  onSelectRegion: (regionKey: string) => void;
  onDrillRegion: () => void;
  onSelectSubregion: (subregionKey: string) => void;
  onOpenEvidence: () => void;
  canOpenEvidence: boolean;
  onApplyFocusApp: (appHint: string) => void;
  onApplyFocusWindow: () => void;
  onClearFocusFilters: () => void;
  onSelectItem: (sourceItemId: number) => void;
  onPreviousEvidencePage: () => void;
  onNextEvidencePage: () => void;
  canPreviousEvidencePage: boolean;
  canNextEvidencePage: boolean;
};

export function InsightDock({
  level,
  loading,
  visibleRegions,
  selectedRegion,
  activeFocusRegion,
  visibleSubregions,
  hasGeneratedSubregions,
  selectedSubregion,
  selectedItem,
  evidenceSections,
  evidenceSort,
  currentFilters,
  evidenceActionLabel,
  overviewScope,
  regionFocusScope,
  onEvidenceSortChange,
  onOverviewScopeChange,
  onRegionFocusScopeChange,
  onSelectRegion,
  onDrillRegion,
  onSelectSubregion,
  onOpenEvidence,
  canOpenEvidence,
  onApplyFocusApp,
  onApplyFocusWindow,
  onClearFocusFilters,
  onSelectItem,
  onPreviousEvidencePage,
  onNextEvidencePage,
  canPreviousEvidencePage,
  canNextEvidencePage,
}: InsightDockProps) {
  const [regionListSort, setRegionListSort] = useState<AtlasRegionListSort>(
    DEFAULT_ATLAS_REGION_LIST_SORT,
  );
  const [previewItem, setPreviewItem] = useState<AtlasItem | null>(null);
  const peopleValues = resolveFocusPeople(activeFocusRegion);
  const timeRange = formatAtlasDateRange(
    activeFocusRegion?.time_start,
    activeFocusRegion?.time_end,
  );
  const primaryFocusApp = activeFocusRegion?.top_apps[0] ?? null;
  const focusWindowActive = isFocusWindowActive(currentFilters, activeFocusRegion);
  const hasLocalFocusFilters =
    currentFilters.app_hint !== null ||
    currentFilters.observed_from !== null ||
    currentFilters.observed_to !== null;
  const dockTitle =
    selectedSubregion?.title ??
    selectedRegion?.title ??
    "Atlas overview";
  const selectedScreenshotUrl = selectedItem === null ? null : screenshotImageUrl(selectedItem);
  const previewScreenshotUrl = previewItem === null ? null : screenshotImageUrl(previewItem);
  const orderedVisibleRegions = useMemo(
    () => sortAtlasRegions(visibleRegions, regionListSort),
    [regionListSort, visibleRegions],
  );
  const orderedVisibleSubregions = useMemo(
    () => sortAtlasRegions(visibleSubregions, regionListSort),
    [regionListSort, visibleSubregions],
  );

  useEffect(() => {
    if (previewItem === null) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPreviewItem(null);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [previewItem]);

  const openScreenshotPreview = (item: AtlasItem) => {
    onSelectItem(item.source_item_id);
    setPreviewItem(item);
  };

  return (
    <>
      <aside className="insight-dock">
        <div className="insight-dock__hero">
          <p className="insight-dock__eyebrow">Workbench</p>
          <h2>{dockTitle}</h2>
          <p>
            {loading
              ? "Refreshing the active view."
              : "Selection details, representative evidence, and drill actions stay pinned here while the atlas remains visible."}
          </p>
        </div>

      <section className="dock-panel">
        <header className="dock-panel__header">
          <h3>Focus summary</h3>
        </header>
        {activeFocusRegion !== null ? (
          <div className="focus-summary">
            <strong>{activeFocusRegion.title}</strong>
            <span>{activeFocusRegion.overlay.match_count} matching screenshots</span>
            <span>{activeFocusRegion.item_count} screenshots in scope</span>
            <span>
              {activeFocusRegion.top_labels.slice(0, 2).join(" · ") || "No top labels yet"}
            </span>
            {peopleValues.length > 0 ? (
              <span>People / anchors: {peopleValues.slice(0, 2).join(" · ")}</span>
            ) : null}
            {timeRange !== null ? <span>{timeRange}</span> : null}
            {activeFocusRegion !== null ? (
              <div className="dock-focus-actions">
                {primaryFocusApp !== null ? (
                  <button
                    type="button"
                    className="atlas-button atlas-button--ghost dock-focus-actions__button"
                    onClick={() => onApplyFocusApp(primaryFocusApp)}
                    disabled={currentFilters.app_hint === primaryFocusApp}
                  >
                    Filter app: {titleCaseAtlasValue(primaryFocusApp)}
                  </button>
                ) : null}
                {timeRange !== null ? (
                  <button
                    type="button"
                    className="atlas-button atlas-button--ghost dock-focus-actions__button"
                    onClick={onApplyFocusWindow}
                    disabled={focusWindowActive}
                  >
                    Use focus window
                  </button>
                ) : null}
                {hasLocalFocusFilters ? (
                  <button
                    type="button"
                    className="atlas-button atlas-button--ghost dock-focus-actions__button"
                    onClick={onClearFocusFilters}
                  >
                    Clear focus filters
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="dock-empty">Select a region to open the atlas workbench.</p>
        )}
      </section>

      <section className="dock-panel">
        <header className="dock-panel__header">
          <div className="dock-panel__controls">
            <h3>
              {level === "overview" ? "Regions" : "Subregions"}
            </h3>
            {level === "overview" ? (
              <label className="dock-select-field">
                <span>Overview scope</span>
                <select
                  value={overviewScope}
                  onChange={(event) =>
                    onOverviewScopeChange(event.target.value as AtlasOverviewScope)
                  }
                >
                  <option value="condensed">Condensed</option>
                  <option value="all">All</option>
                </select>
              </label>
            ) : hasGeneratedSubregions ? (
              <label className="dock-select-field">
                <span>Region scope</span>
                <select
                  value={regionFocusScope}
                  onChange={(event) =>
                    onRegionFocusScopeChange(event.target.value as AtlasRegionFocusScope)
                  }
                >
                  <option value="featured">Featured</option>
                  <option value="all">All</option>
                </select>
              </label>
            ) : null}
            <label className="dock-select-field">
              <span>Region order</span>
              <select
                value={regionListSort}
                onChange={(event) => setRegionListSort(event.target.value as AtlasRegionListSort)}
              >
                <option value="match_count_desc">Most matching</option>
                <option value="item_count_desc">Largest scope</option>
                <option value="title_asc">Title A-Z</option>
                <option value="stable_order">Stable cluster order</option>
              </select>
            </label>
          </div>
          {level === "overview" ? (
            <button
              type="button"
              className="atlas-button atlas-button--ghost"
              onClick={onDrillRegion}
              disabled={selectedRegion === null}
            >
              Enter region
            </button>
          ) : level === "region" && !hasGeneratedSubregions ? (
            <button
              type="button"
              className="atlas-button atlas-button--ghost"
              onClick={onOpenEvidence}
              disabled={!canOpenEvidence}
            >
              {evidenceActionLabel}
            </button>
          ) : null}
        </header>

        {level === "overview" ? (
          <div className="dock-list-scroll">
            <ul className="dock-list">
              {orderedVisibleRegions.map((region) => (
                <li key={region.region_key} className="dock-list__row">
                  <button
                    type="button"
                    className={`dock-list__button ${
                      region.region_key === selectedRegion?.region_key ? "dock-list__button--selected" : ""
                    }`}
                    onClick={() => onSelectRegion(region.region_key)}
                  >
                    {region.title}
                  </button>
                  <span>{region.overlay.match_count} matching screenshots</span>
                </li>
              ))}
            </ul>
          </div>
        ) : !hasGeneratedSubregions ? (
          <p className="dock-empty">
            No generated lanes for this region yet. Use {evidenceActionLabel.toLowerCase()} to inspect the whole region.
          </p>
        ) : orderedVisibleSubregions.length > 0 ? (
          <div className="dock-list-scroll">
            <ul className="dock-list">
              {orderedVisibleSubregions.map((subregion) => (
                <li key={subregion.region_key} className="dock-list__row">
                  <button
                    type="button"
                    className={`dock-list__button ${
                      subregion.region_key === selectedSubregion?.region_key
                        ? "dock-list__button--selected"
                        : ""
                    }`}
                    onClick={() => onSelectSubregion(subregion.region_key)}
                  >
                    {subregion.title}
                  </button>
                  <span>{subregion.overlay.match_count} matching screenshots</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="dock-empty">No subregions match the current atlas request.</p>
        )}
      </section>

      {level === "evidence" && evidenceSections !== null ? (
        <section className="dock-panel dock-panel--evidence">
          <header className="dock-panel__header dock-panel__header--stacked">
            <div>
              <h3>Evidence stack</h3>
            </div>
            <label className="dock-sort">
              <span>Evidence order</span>
              <select
                value={evidenceSort}
                onChange={(event) =>
                onEvidenceSortChange(event.currentTarget.value as AtlasEvidenceSort)
                }
              >
                <option value="observed_at_desc">Newest first</option>
                <option value="observed_at_asc">Oldest first</option>
                <option value="app_hint_asc">App</option>
                <option value="semantic_summary_asc">Summary / topic-ish</option>
              </select>
            </label>
          </header>
          <EvidenceList
            sections={evidenceSections}
            selectedItemId={selectedItem?.source_item_id ?? null}
            onSelectItem={onSelectItem}
            onPreviousPage={onPreviousEvidencePage}
            onNextPage={onNextEvidencePage}
            canPreviousPage={canPreviousEvidencePage}
            canNextPage={canNextEvidencePage}
          />
        </section>
      ) : null}

      <section className="dock-panel">
        <header className="dock-panel__header">
          <h3>Facets</h3>
        </header>
        <div className="facet-grid">
          <Facet label="Labels" values={activeFocusRegion?.top_labels ?? []} />
          <Facet label="People / anchors" values={peopleValues} />
          <Facet label="Apps" values={activeFocusRegion?.top_apps ?? []} />
          <Facet label="Entities" values={activeFocusRegion?.top_entities ?? []} />
          <Facet label="Window" values={timeRange !== null ? [timeRange] : []} />
        </div>
      </section>

      {selectedItem !== null ? (
        <section className="dock-panel">
          <header className="dock-panel__header">
            <h3>Selected evidence</h3>
          </header>
          <div className="focus-summary">
            <strong>{selectedItem.semantic_summary ?? "Untitled evidence"}</strong>
            <span>{selectedItem.app_hint ?? "Unknown app"}</span>
            <span>{selectedItem.object_refs.slice(0, 3).join(" · ") || "No linked objects"}</span>
            {selectedScreenshotUrl !== null ? (
              <button
                type="button"
                className="focus-summary__image-button"
                onClick={() => openScreenshotPreview(selectedItem)}
              >
                Open screenshot preview
              </button>
            ) : null}
          </div>
        </section>
      ) : null}
    </aside>
    {previewItem !== null && previewScreenshotUrl !== null ? (
      <div
        className="screenshot-preview"
        role="dialog"
        aria-modal="true"
        aria-label={`Screenshot #${previewItem.source_item_id}`}
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            setPreviewItem(null);
          }
        }}
      >
        <div className="screenshot-preview__panel">
          <header className="screenshot-preview__header">
            <div>
              <span>Screenshot #{previewItem.source_item_id}</span>
              <strong>{previewItem.semantic_summary ?? "Screenshot preview"}</strong>
            </div>
            <button
              type="button"
              className="screenshot-preview__close"
              onClick={() => setPreviewItem(null)}
              aria-label="Close screenshot preview"
            >
              X
            </button>
          </header>
          <div className="screenshot-preview__body">
            <img
              src={previewScreenshotUrl}
              alt={previewItem.semantic_summary ?? `Screenshot #${previewItem.source_item_id}`}
            />
          </div>
          <div className="screenshot-preview__actions">
            <a href={previewScreenshotUrl} target="_blank" rel="noreferrer">
              Open raw image
            </a>
          </div>
        </div>
      </div>
    ) : null}
    </>
  );
}

function screenshotImageUrl(item: AtlasItem): string | null {
  if (item.screenshot_detail_url === null) {
    return null;
  }

  return `${item.screenshot_detail_url.replace(/\/$/, "")}/blob`;
}

function Facet({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="facet-panel">
      <span>{label}</span>
      <strong>
        {values.length > 0
          ? values.slice(0, 3).map(humanizeAtlasValue).join(" · ")
          : "None"}
      </strong>
    </div>
  );
}
