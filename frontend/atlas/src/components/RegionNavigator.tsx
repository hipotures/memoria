import type { AtlasLevel } from "../state/atlasReducer";

type RegionNavigatorProps = {
  level: AtlasLevel;
  selectedRegionTitle: string | null;
  selectedSubregionTitle: string | null;
  selectedRegionCount: number | null;
  selectedSubregionCount: number | null;
  canDrillRegion: boolean;
  canOpenEvidence: boolean;
  evidenceActionLabel: string;
  onDrillRegion: () => void;
  onOpenEvidence: () => void;
  onReturnToRegion: () => void;
  onReset: () => void;
};

export function RegionNavigator({
  level,
  selectedRegionTitle,
  selectedSubregionTitle,
  selectedRegionCount,
  selectedSubregionCount,
  canDrillRegion,
  canOpenEvidence,
  evidenceActionLabel,
  onDrillRegion,
  onOpenEvidence,
  onReturnToRegion,
  onReset,
}: RegionNavigatorProps) {
  return (
    <header className="region-navigator">
      <div className="region-navigator__breadcrumbs" aria-label="Atlas breadcrumbs">
        <button type="button" className="atlas-crumb atlas-crumb--active" onClick={onReset}>
          Atlas overview
        </button>
        {selectedRegionTitle !== null ? <span className="atlas-crumb-separator">/</span> : null}
        {selectedRegionTitle !== null ? (
          <button
            type="button"
            className={`atlas-crumb ${level === "overview" ? "atlas-crumb--muted" : "atlas-crumb--active"}`}
            onClick={level === "overview" ? undefined : onReturnToRegion}
            disabled={level === "overview"}
          >
            {selectedRegionTitle}
          </button>
        ) : null}
        {level === "evidence" && selectedSubregionTitle !== null ? (
          <>
            <span className="atlas-crumb-separator">/</span>
            <span className="atlas-crumb atlas-crumb--current">{selectedSubregionTitle}</span>
          </>
        ) : null}
      </div>

      <div className="region-navigator__summary">
        <div>
          <p className="region-navigator__label">Current focus</p>
          <h2>
            {level === "overview"
              ? "Atlas overview"
              : level === "region"
                ? selectedRegionTitle ?? "Region focus"
                : selectedSubregionTitle ?? selectedRegionTitle ?? "Evidence focus"}
          </h2>
        </div>

        <div className="region-navigator__meta">
          {selectedRegionCount !== null ? <span>{selectedRegionCount} screenshots in region</span> : null}
          {selectedSubregionCount !== null ? (
            <span>{selectedSubregionCount} screenshots in selection</span>
          ) : null}
        </div>
      </div>

      <div className="region-navigator__actions">
        {level === "overview" ? (
          <button
            type="button"
            className="atlas-button"
            onClick={onDrillRegion}
            disabled={!canDrillRegion}
          >
            Enter region
          </button>
        ) : null}

        {level === "region" ? (
          <button
            type="button"
            className="atlas-button"
            onClick={onOpenEvidence}
            disabled={!canOpenEvidence}
          >
            {evidenceActionLabel}
          </button>
        ) : null}

        {level === "evidence" ? (
          <button type="button" className="atlas-button atlas-button--ghost" onClick={onReturnToRegion}>
            Return to region
          </button>
        ) : null}

        <button type="button" className="atlas-button atlas-button--ghost" onClick={onReset}>
          Reset atlas
        </button>
      </div>
    </header>
  );
}
