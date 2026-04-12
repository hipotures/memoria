import type { AtlasEvidenceSort, AtlasFilters, AtlasItem, AtlasRegion } from "../api/contracts";
import {
  formatAtlasDateRange,
  humanizeAtlasValue,
  isFocusWindowActive,
  resolveFocusPeople,
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
  regionRepresentatives: AtlasItem[];
  regionDetailLoaded: boolean;
  evidenceSections: EvidenceSections<AtlasItem> | null;
  evidenceSort: AtlasEvidenceSort;
  currentFilters: AtlasFilters;
  evidenceActionLabel: string;
  onEvidenceSortChange: (sort: AtlasEvidenceSort) => void;
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
  regionRepresentatives,
  regionDetailLoaded,
  evidenceSections,
  evidenceSort,
  currentFilters,
  evidenceActionLabel,
  onEvidenceSortChange,
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

  return (
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
          <h3>
            {level === "overview" && regionDetailLoaded ? "Region lanes" : level === "overview" ? "Regions" : "Subregions"}
          </h3>
          {level === "overview" ? (
            <button
              type="button"
              className="atlas-button atlas-button--ghost"
              onClick={onDrillRegion}
              disabled={selectedRegion === null}
            >
              Enter region
            </button>
          ) : (
            <button
              type="button"
              className="atlas-button atlas-button--ghost"
              onClick={onOpenEvidence}
              disabled={!canOpenEvidence}
            >
              {evidenceActionLabel}
            </button>
          )}
        </header>

        {level === "overview" && regionDetailLoaded ? (
          !hasGeneratedSubregions ? (
            <p className="dock-empty">
              No generated lanes for this region yet. Enter the region to inspect the whole evidence slice.
            </p>
          ) : visibleSubregions.length > 0 ? (
            <ul className="dock-list">
              {visibleSubregions.map((subregion) => (
                <li key={subregion.region_key} className="dock-list__row">
                  <strong className="dock-list__preview-title">{subregion.title}</strong>
                  <span>{subregion.overlay.match_count} matching screenshots</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dock-empty">No subregions match the current atlas request.</p>
          )
        ) : level === "overview" ? (
          <ul className="dock-list">
            {visibleRegions.map((region) => (
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
        ) : !hasGeneratedSubregions ? (
          <p className="dock-empty">
            No generated lanes for this region yet. Use {evidenceActionLabel.toLowerCase()} to inspect the whole region.
          </p>
        ) : visibleSubregions.length > 0 ? (
          <ul className="dock-list">
            {visibleSubregions.map((subregion) => (
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
        ) : (
          <p className="dock-empty">No subregions match the current atlas request.</p>
        )}
      </section>

      {selectedRegion !== null && regionDetailLoaded ? (
        <section className="dock-panel">
          <header className="dock-panel__header">
            <h3>
              {regionRepresentatives.length} representative screenshot
              {regionRepresentatives.length === 1 ? "" : "s"}
            </h3>
          </header>
          {regionRepresentatives.length > 0 ? (
            <ul className="dock-representatives">
              {regionRepresentatives.map((item) => (
                <li key={item.source_item_id}>
                  <button
                    type="button"
                    className={`dock-representatives__button ${
                      item.source_item_id === selectedItem?.source_item_id
                        ? "dock-representatives__button--selected"
                        : ""
                    }`}
                    onClick={() => onSelectItem(item.source_item_id)}
                  >
                    <span>#{item.source_item_id}</span>
                    <strong>{item.semantic_summary ?? "Untitled evidence"}</strong>
                    <span>{item.app_hint ?? "Unknown app"}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dock-empty">No representative evidence matches the current request.</p>
          )}
        </section>
      ) : null}

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
            {selectedItem.screenshot_detail_url !== null ? (
              <a href={selectedItem.screenshot_detail_url}>Open screenshot detail</a>
            ) : null}
          </div>
        </section>
      ) : null}
    </aside>
  );
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
