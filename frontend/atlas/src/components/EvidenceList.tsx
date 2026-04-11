import { useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

import type { AtlasItem } from "../api/contracts";
import type { EvidenceSections } from "../lib/evidenceSections";

type EvidenceListProps = {
  sections: EvidenceSections<AtlasItem>;
  selectedItemId: number | null;
  onSelectItem: (sourceItemId: number) => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
  canPreviousPage: boolean;
  canNextPage: boolean;
};

type EvidenceRow =
  | { kind: "section"; id: string; title: string; count: number }
  | { kind: "item"; id: string; item: AtlasItem }
  | {
      kind: "pager";
      id: string;
      offset: number;
      limit: number;
      total: number;
    };

export function EvidenceList({
  sections,
  selectedItemId,
  onSelectItem,
  onPreviousPage,
  onNextPage,
  canPreviousPage,
  canNextPage,
}: EvidenceListProps) {
  const rows = useMemo<EvidenceRow[]>(
    () => [
      {
        kind: "section",
        id: "representatives-header",
        title: "Representatives",
        count: sections.totals.representatives,
      },
      ...sections.representatives.map((item) => ({
        kind: "item" as const,
        id: `representative-${item.source_item_id}`,
        item,
      })),
      {
        kind: "section",
        id: "bridges-header",
        title: "Bridges",
        count: sections.totals.bridges,
      },
      ...sections.bridges.map((item) => ({
        kind: "item" as const,
        id: `bridge-${item.source_item_id}`,
        item,
      })),
      {
        kind: "section",
        id: "long-tail-header",
        title: "Long tail",
        count: sections.totals.longTail,
      },
      ...sections.longTail.items.map((item) => ({
        kind: "item" as const,
        id: `long-tail-${item.source_item_id}`,
        item,
      })),
      {
        kind: "pager",
        id: "long-tail-pager",
        offset: sections.longTail.offset,
        limit: sections.longTail.limit,
        total: sections.longTail.total,
      },
    ],
    [sections],
  );

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    initialRect: {
      width: 0,
      height: 360,
    },
    estimateSize: (index) => {
      const row = rows[index];
      if (row?.kind === "section") {
        return 48;
      }
      if (row?.kind === "pager") {
        return 80;
      }
      return 92;
    },
    overscan: 6,
  });
  const useTestRender = import.meta.env.MODE === "test";

  return (
    <div className="evidence-list">
      {useTestRender ? (
        <div className="evidence-list__plain">
          {rows.map((row) => (
            <EvidenceRowView
              key={row.id}
              row={row}
              selectedItemId={selectedItemId}
              onSelectItem={onSelectItem}
              onPreviousPage={onPreviousPage}
              onNextPage={onNextPage}
              canPreviousPage={canPreviousPage}
              canNextPage={canNextPage}
            />
          ))}
        </div>
      ) : (
        <div ref={scrollRef} className="evidence-list__viewport">
          <div
            className="evidence-list__rail"
            style={{ height: `${virtualizer.getTotalSize()}px` }}
          >
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const row = rows[virtualRow.index];
              if (row === undefined) {
                return null;
              }

              return (
                <div
                  key={row.id}
                  className="evidence-list__row"
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                >
                  <EvidenceRowView
                    row={row}
                    selectedItemId={selectedItemId}
                    onSelectItem={onSelectItem}
                    onPreviousPage={onPreviousPage}
                    onNextPage={onNextPage}
                    canPreviousPage={canPreviousPage}
                    canNextPage={canNextPage}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function EvidenceRowView({
  row,
  selectedItemId,
  onSelectItem,
  onPreviousPage,
  onNextPage,
  canPreviousPage,
  canNextPage,
}: {
  row: EvidenceRow;
  selectedItemId: number | null;
  onSelectItem: (sourceItemId: number) => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
  canPreviousPage: boolean;
  canNextPage: boolean;
}) {
  if (row.kind === "section") {
    return (
      <div className="evidence-list__section">
        <h3>{row.title}</h3>
        <span>{row.count}</span>
      </div>
    );
  }

  if (row.kind === "item") {
    return (
      <button
        type="button"
        className={`evidence-card ${
          selectedItemId === row.item.source_item_id ? "evidence-card--selected" : ""
        }`}
        onClick={() => onSelectItem(row.item.source_item_id)}
      >
        <span className="evidence-card__eyebrow">
          {itemKind(row.item)} · #{row.item.source_item_id}
        </span>
        <strong>{row.item.semantic_summary ?? "Untitled evidence"}</strong>
        <span className="evidence-card__meta">
          <span>{row.item.app_hint ?? "Unknown app"}</span>
          <span>{formatObservedAt(row.item.observed_at)}</span>
        </span>
        <span className="evidence-card__objects">
          {row.item.object_refs.length > 0
            ? row.item.object_refs.slice(0, 3).join(" · ")
            : "No linked objects"}
        </span>
      </button>
    );
  }

  return (
    <div className="evidence-list__pager">
      <span>
        Showing {row.total === 0 ? 0 : row.offset + 1}-{Math.min(row.offset + row.limit, row.total)} of{" "}
        {row.total}
      </span>
      <div className="evidence-list__pager-actions">
        <button
          type="button"
          className="atlas-button atlas-button--ghost"
          onClick={onPreviousPage}
          disabled={!canPreviousPage}
        >
          Previous page
        </button>
        <button
          type="button"
          className="atlas-button atlas-button--ghost"
          onClick={onNextPage}
          disabled={!canNextPage}
        >
          Next page
        </button>
      </div>
    </div>
  );
}

function itemKind(item: AtlasItem): string {
  if (item.is_representative) {
    return `Representative ${item.representative_rank ?? ""}`.trim();
  }
  if (item.is_bridge) {
    return item.bridge_type ? `Bridge · ${item.bridge_type}` : "Bridge";
  }
  return "Evidence";
}

function formatObservedAt(observedAt: string | null): string {
  if (observedAt === null) {
    return "Unknown time";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(observedAt));
}
