export type AtlasToolbarDraft = {
  searchText: string;
  appHint: string;
  observedFrom: string;
  observedTo: string;
  knowledge: "all" | "with";
};

type AtlasToolbarProps = {
  draft: AtlasToolbarDraft;
  appOptions: string[];
  loading: boolean;
  onDraftChange: (patch: Partial<AtlasToolbarDraft>) => void;
  onApply: () => void;
  onReset: () => void;
};

export function AtlasToolbar({
  draft,
  appOptions,
  loading,
  onDraftChange,
  onApply,
  onReset,
}: AtlasToolbarProps) {
  const activeSearchCount = draft.searchText.trim().length > 0 ? 1 : 0;
  const activeFilterCount = [
    draft.appHint.trim().length > 0,
    draft.observedFrom.length > 0,
    draft.observedTo.length > 0,
    draft.knowledge !== "all",
  ].filter(Boolean).length;

  return (
    <section className="atlas-toolbar" aria-label="Atlas filters">
      <div className="atlas-toolbar__title">
        <p className="atlas-toolbar__eyebrow">Memoria / Semantic Atlas</p>
        <h1>Semantic atlas workbench</h1>
        <p className="atlas-toolbar__lede">
          Start at the regional field, then move into subregions and screenshot evidence without
          losing orientation.
        </p>
      </div>

      <div className="atlas-toolbar__controls">
        <label className="atlas-field atlas-field--search">
          <span>Search atlas</span>
          <input
            type="search"
            placeholder="Filter visible labels, regions, and evidence"
            value={draft.searchText}
            onChange={(event) => onDraftChange({ searchText: event.currentTarget.value })}
          />
        </label>

        <label className="atlas-field">
          <span>App</span>
          <input
            type="text"
            list="atlas-app-options"
            placeholder="Telegram, Gmail, Slack..."
            value={draft.appHint}
            onChange={(event) => onDraftChange({ appHint: event.currentTarget.value })}
          />
        </label>

        <label className="atlas-field">
          <span>Observed from</span>
          <input
            type="date"
            value={draft.observedFrom}
            onChange={(event) => onDraftChange({ observedFrom: event.currentTarget.value })}
          />
        </label>

        <label className="atlas-field">
          <span>Observed to</span>
          <input
            type="date"
            value={draft.observedTo}
            onChange={(event) => onDraftChange({ observedTo: event.currentTarget.value })}
          />
        </label>

        <label className="atlas-field atlas-field--compact">
          <span>Knowledge</span>
          <select
            value={draft.knowledge}
            onChange={(event) =>
              onDraftChange({ knowledge: event.currentTarget.value as AtlasToolbarDraft["knowledge"] })
            }
          >
            <option value="all">All</option>
            <option value="with">With knowledge</option>
          </select>
        </label>

        <div className="atlas-toolbar__actions">
          <button type="button" className="atlas-button" onClick={onApply} disabled={loading}>
            {loading ? "Refreshing…" : "Apply filters"}
          </button>
          <button type="button" className="atlas-button atlas-button--ghost" onClick={onReset}>
            Reset filters
          </button>
        </div>

        <div className="atlas-toolbar__status" aria-live="polite">
          <span>{activeSearchCount} active search term{activeSearchCount === 1 ? "" : "s"}</span>
          <span>{activeFilterCount} server filter{activeFilterCount === 1 ? "" : "s"}</span>
          <span>{loading ? "Refreshing atlas…" : "Projection stable"}</span>
        </div>
      </div>

      <datalist id="atlas-app-options">
        {appOptions.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
    </section>
  );
}
