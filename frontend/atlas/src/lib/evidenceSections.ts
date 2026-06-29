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
  return {
    representatives: slice.representatives,
    bridges: slice.bridges,
    longTail: slice.long_tail_page,
    totals: {
      representatives: slice.section_totals.representatives,
      bridges: slice.section_totals.bridges,
      longTail: slice.section_totals.long_tail,
    },
  };
}
