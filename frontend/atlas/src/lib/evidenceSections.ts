type EvidenceIdentity = {
  source_item_id: number;
};

export type EvidenceSectionTotals = {
  representatives: number;
  bridges: number;
  long_tail: number;
};

export type EvidencePage<T extends EvidenceIdentity> = {
  items: T[];
  limit: number;
  offset: number;
  total: number;
};

export type EvidenceSectionsInput<T extends EvidenceIdentity> = {
  representatives: T[];
  bridges: T[];
  long_tail_page: EvidencePage<T>;
  section_totals: EvidenceSectionTotals;
};

export type EvidenceSections<T extends EvidenceIdentity> = {
  representatives: T[];
  bridges: T[];
  longTail: EvidencePage<T>;
  totals: {
    representatives: number;
    bridges: number;
    longTail: number;
  };
};

export function splitEvidenceSections<T extends EvidenceIdentity>(
  slice: EvidenceSectionsInput<T>,
): EvidenceSections<T> {
  const representatives = dedupeBySourceItemId(slice.representatives);
  const representativeIds = new Set(representatives.map((item) => item.source_item_id));

  const bridges = dedupeBySourceItemId(
    slice.bridges.filter((item) => !representativeIds.has(item.source_item_id)),
  );
  const protectedIds = new Set([
    ...representatives.map((item) => item.source_item_id),
    ...bridges.map((item) => item.source_item_id),
  ]);

  return {
    representatives,
    bridges,
    longTail: {
      ...slice.long_tail_page,
      items: dedupeBySourceItemId(
        slice.long_tail_page.items.filter((item) => !protectedIds.has(item.source_item_id)),
      ),
    },
    totals: {
      representatives: slice.section_totals.representatives,
      bridges: slice.section_totals.bridges,
      longTail: slice.section_totals.long_tail,
    },
  };
}

function dedupeBySourceItemId<T extends EvidenceIdentity>(items: T[]): T[] {
  const seen = new Set<number>();
  const unique: T[] = [];

  for (const item of items) {
    if (seen.has(item.source_item_id)) {
      continue;
    }

    seen.add(item.source_item_id);
    unique.push(item);
  }

  return unique;
}
