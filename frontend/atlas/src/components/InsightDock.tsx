import type { AtlasEvidenceSort, AtlasItem, AtlasRegion } from "../api/contracts";
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
  selectedSubregion: AtlasRegion | null;
  selectedItem: AtlasItem | null;
  regionRepresentatives: AtlasItem[];
  regionDetailLoaded: boolean;
  evidenceSections: EvidenceSections<AtlasItem> | null;
  evidenceSort: AtlasEvidenceSort;
  onEvidenceSortChange: (sort: AtlasEvidenceSort) => void;
  onSelectRegion: (regionKey: string) => void;
  onDrillRegion: () => void;
  onSelectSubregion: (subregionKey: string) => void;
  onDrillSubregion: () => void;
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
  selectedSubregion,
  selectedItem,
  regionRepresentatives,
  regionDetailLoaded,
  evidenceSections,
  evidenceSort,
  onEvidenceSortChange,
  onSelectRegion,
  onDrillRegion,
  onSelectSubregion,
  onDrillSubregion,
  onSelectItem,
  onPreviousEvidencePage,
  onNextEvidencePage,
  canPreviousEvidencePage,
  canNextEvidencePage,
}: InsightDockProps) {
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
              onClick={onDrillSubregion}
              disabled={selectedSubregion === null}
            >
              Open evidence
            </button>
          )}
        </header>

        {level === "overview" && regionDetailLoaded ? (
          visibleSubregions.length > 0 ? (
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
        ) : (
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
                <option value="semantic_summary_asc">Title / summary</option>
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
          <Facet label="Apps" values={activeFocusRegion?.top_apps ?? []} />
          <Facet label="Entities" values={activeFocusRegion?.top_entities ?? []} />
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
      <strong>{values.length > 0 ? values.slice(0, 3).join(" · ") : "None"}</strong>
    </div>
  );
}
