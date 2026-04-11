import { useReducer } from "react";

import { atlasReducer, initialAtlasState } from "./state/atlasReducer";

export default function App() {
  const [state, dispatch] = useReducer(atlasReducer, initialAtlasState);
  const hasRegionFocus = state.level === "region" && state.selectedRegionKey !== null;

  return (
    <main className="app-shell">
      <section className="card hero">
        <p className="eyebrow">Memoria / Semantic Atlas</p>
        <h1>Frontend workspace scaffold</h1>
        <p className="lede">
          Task 5 establishes the atlas package, state machine, evidence grouping helper, and
          API client contracts. Canvas rendering and dock UI remain reserved for Task 6.
        </p>
      </section>

      <section className="panel-grid">
        <article className="card">
          <header className="card-header">
            <h2>State machine</h2>
            <button
              type="button"
              className="ghost-button"
              onClick={() => dispatch({ type: "breadcrumbs.reset" })}
            >
              Reset
            </button>
          </header>
          <p className="muted">
            Selection is separate from drill-down. Only explicit drill actions change the atlas
            level.
          </p>
          <dl className="state-grid">
            <div>
              <dt>Level</dt>
              <dd>{state.level}</dd>
            </div>
            <div>
              <dt>Region</dt>
              <dd>{state.selectedRegionKey ?? "None"}</dd>
            </div>
            <div>
              <dt>Subregion</dt>
              <dd>{state.selectedSubregionKey ?? "None"}</dd>
            </div>
            <div>
              <dt>Item</dt>
              <dd>{state.selectedItemId ?? "None"}</dd>
            </div>
          </dl>
          <div className="button-row">
            <button
              type="button"
              onClick={() => dispatch({ type: "region.selected", regionKey: "region-a" })}
            >
              Select region
            </button>
            <button
              type="button"
              onClick={() => dispatch({ type: "region.drilled", regionKey: "region-a" })}
            >
              Drill region
            </button>
            <button
              type="button"
              disabled={!hasRegionFocus}
              onClick={() =>
                dispatch({ type: "subregion.selected", subregionKey: "region-a/subregion-1" })
              }
            >
              Select subregion
            </button>
            <button
              type="button"
              disabled={!hasRegionFocus}
              onClick={() =>
                dispatch({ type: "subregion.drilled", subregionKey: "region-a/subregion-1" })
              }
            >
              Drill evidence
            </button>
          </div>
        </article>

        <article className="card">
          <h2>Reserved for Task 6</h2>
          <ul className="placeholder-list">
            <li>Atlas canvas with stable region-first rendering</li>
            <li>Region navigator and evidence dock</li>
            <li>Evidence pagination controls and drill-down wiring</li>
            <li>Overview, region, and evidence data loading</li>
          </ul>
        </article>
      </section>
    </main>
  );
}
